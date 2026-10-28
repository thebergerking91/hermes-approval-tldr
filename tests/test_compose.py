"""Composer: where the summary goes per surface, and the length budgets."""

from __future__ import annotations

import pytest

LABEL = "AI summary (may be wrong — read the command)"
SUMMARY = "Deletes Python cache files under this folder. They rebuild by themselves. Risk: LOW — harmless."
CMD = 'find . -name "*.pyc" -delete'
DESC = "recursive delete"


def run(compose_mod, surface="gateway", platform="", source="", label=LABEL, summary=SUMMARY,
        command=CMD, description=DESC, inline=True, desktop_max_words=60):
    return compose_mod.compose(surface, platform, source, label, summary, command, description, inline,
                               desktop_max_words)


@pytest.mark.parametrize("source", ["desktop", "tui"])
def test_desktop_inlines_summary_in_command(compose_mod, source):
    cmd, desc = run(compose_mod, platform="", source=source)
    body = "Deletes Python cache files under this folder. They rebuild by themselves."
    assert cmd == (f"{LABEL} — Risk: LOW — harmless\n── what it does ──\n{body}\n"
                   f"── command ──\n{CMD}")
    lines = cmd.split("\n")
    assert lines[0].startswith(f"{LABEL} — Risk: LOW")  # verdict is line 1
    assert cmd.index(body) < cmd.index(CMD)  # summary body comes before the command
    assert lines[-1] == CMD  # the real command is last
    assert desc == DESC


def test_desktop_inline_disabled_uses_description(compose_mod):
    cmd, desc = run(compose_mod, source="desktop", inline=False)
    assert cmd == CMD
    assert SUMMARY in desc and "Flagged as: recursive delete" in desc


def test_telegram_description_only_and_capped(compose_mod):
    cmd, desc = run(compose_mod, platform="telegram")
    assert cmd == CMD
    assert desc == f"{LABEL}: {SUMMARY} · Flagged as: {DESC}"
    long_summary = ("word " * 300) + "Risk: HIGH — long."
    _, desc = run(compose_mod, platform="telegram", summary=long_summary)
    assert len(desc) <= 480
    assert desc.endswith("Flagged as: recursive delete")
    assert "Risk: HIGH — long." in desc and "…" in desc


def test_discord_budget_is_shorter(compose_mod):
    long_summary = ("word " * 300) + "Risk: MEDIUM — hmm."
    _, desc = run(compose_mod, platform="discord", summary=long_summary)
    assert len(desc) <= 280
    assert "Flagged as: recursive delete" in desc and "Risk: MEDIUM" in desc


def test_other_gateway_platform_480(compose_mod):
    long_summary = ("word " * 300) + "Risk: LOW — ok."
    cmd, desc = run(compose_mod, platform="slack", summary=long_summary)
    assert cmd == CMD and len(desc) <= 480


def test_cli_has_no_cap_and_command_unchanged(compose_mod):
    long_summary = ("word " * 300) + "Risk: LOW — ok."
    cmd, desc = run(compose_mod, surface="cli", platform="", source="", summary=long_summary)
    assert cmd == CMD
    assert desc == f"{LABEL}: {long_summary} · Flagged as: {DESC}"
    assert len(desc) > 480


def test_unknown_gateway_puts_summary_in_both(compose_mod):
    cmd, desc = run(compose_mod, surface="gateway", platform="", source="")
    assert cmd.startswith(f"{LABEL} — Risk: LOW — harmless\n── what it does ──\n")
    assert cmd.endswith(f"── command ──\n{CMD}")
    assert SUMMARY in desc and "Flagged as" in desc


def test_huge_flagged_label_cannot_evict_summary(compose_mod):
    _, desc = run(compose_mod, platform="discord", description="x" * 5000)
    assert len(desc) <= 280
    assert "Risk: LOW" in desc


def test_empty_description_omits_flagged(compose_mod):
    _, desc = run(compose_mod, platform="telegram", description="")
    assert "Flagged as" not in desc


def test_empty_label_for_placeholder(compose_mod):
    cmd, desc = run(compose_mod, platform="telegram", label="", summary="AI summary unavailable — read the command carefully.")
    assert desc.startswith("AI summary unavailable")
    cmd, _ = run(compose_mod, source="desktop", label="", summary="AI summary unavailable — read the command carefully.")
    assert cmd.startswith("AI summary unavailable")
    assert cmd.split("\n")[1:3] == ["── command ──", CMD]


def test_real_command_is_never_altered_outside_desktop_box(compose_mod):
    for kw in (dict(platform="telegram"), dict(platform="discord"), dict(surface="cli")):
        cmd, _ = run(compose_mod, **kw)
        assert cmd == CMD
    cmd, _ = run(compose_mod, source="desktop")
    assert cmd.split("\n")[-1] == CMD and CMD in cmd


# ── Desktop layout (B3: summary first) ──
def test_desktop_command_is_last_even_with_long_summary(compose_mod):
    long_summary = ("word " * 200) + "Risk: HIGH — " + ("because " * 50)
    cmd, _ = run(compose_mod, source="desktop", summary=long_summary)
    lines = cmd.split("\n")
    assert lines[0].startswith(f"{LABEL} — Risk: HIGH — because")
    assert lines[1] == "── what it does ──"
    body = lines[2]
    assert lines[3:] == ["── command ──", CMD]
    assert len(body.split()) <= 60 and body.endswith("…")
    assert "Risk:" not in body
    assert len(lines[0]) < len(LABEL) + 40 + 90  # the reason is short


def test_desktop_max_words_is_configurable(compose_mod):
    summary = " ".join(f"w{i}" for i in range(100)) + ". Risk: LOW — fine."
    cmd, _ = compose_mod.compose("gateway", "", "tui", LABEL, summary, CMD, DESC, True, 25)
    assert len(cmd.split("\n")[2].split()) <= 25


def test_desktop_without_risk_tail_is_unknown(compose_mod):
    cmd, _ = compose_mod.compose("gateway", "", "desktop", LABEL, "Does something odd.", CMD, DESC, True)
    assert cmd.split("\n")[0] == f"{LABEL} — Risk: UNKNOWN"
    assert cmd.split("\n")[1:3] == ["── what it does ──", "Does something odd."]


def test_split_risk(compose_mod):
    split = compose_mod.split_risk
    assert split("Deletes things. Risk: HIGH — permanent loss.") == ("Deletes things.", "HIGH", "permanent loss")
    assert split("Lists files. Risk: low - read only") == ("Lists files.", "LOW", "read only")
    assert split("Does it. Risk: UNKNOWN.") == ("Does it.", "UNKNOWN", "")
    assert split("No verdict here.") == ("No verdict here.", "UNKNOWN", "")
    assert split("") == ("", "UNKNOWN", "")
    body, level, reason = split("A. Risk: MEDIUM — " + "x " * 100)
    assert (body, level) == ("A.", "MEDIUM") and 0 < len(reason) <= 90 and reason.endswith("…")
    # unparseable level word -> UNKNOWN, text kept as the reason; the LAST Risk: wins
    assert split("Risk: low for most. Risk: Severe damage")[1:] == ("UNKNOWN", "Severe damage")


# ── Escaped budgets (S2) ──
@pytest.mark.parametrize("platform,cap", [("telegram", 480), ("discord", 280), ("slack", 480)])
def test_budget_is_measured_after_html_escape(compose_mod, platform, cap):
    import html
    nasty = "It's the user's \"home\" folder & <stuff>; don't panic. " * 20 + "Risk: HIGH — it's gone."
    _, desc = run(compose_mod, platform=platform, summary=nasty, description="it's \"recursive\" delete")
    assert len(html.escape(desc, quote=True)) <= cap
    assert " · Flagged as: " in desc and desc.endswith('recursive" delete')
    assert "Risk: HIGH" in desc


def test_all_apostrophe_flagged_label_still_fits(compose_mod):
    import html
    _, desc = run(compose_mod, platform="telegram", description="'" * 500, summary="'" * 900 + " Risk: LOW — ok.")
    assert len(html.escape(desc, quote=True)) <= 480
