"""Per-surface display strings and length budgets.

Why it exists: each surface the user answers approvals on renders different fields. The Desktop card
only draws the command box (it hides the description), Telegram/Discord cap the reason line, and
the CLI panel shows the description as its header. This module decides where the AI paragraph
goes for each of them while keeping the real command and the detector's label visible. Only the
strings shown to the human change — never the command that executes.
"""

from __future__ import annotations

import html
import re

DESKTOP_SOURCES = ("desktop", "tui")
COMMAND_DIVIDER = "── command ──"
SUMMARY_DIVIDER = "── what it does ──"
DEFAULT_DESKTOP_MAX_WORDS = 60
MAX_RISK_REASON_CHARS = 90
FLAGGED_SEP = " · Flagged as: "
ELLIPSIS = "…"

# Max length of the whole description line (label + summary + "Flagged as: ..."), measured AFTER
# html.escape(quote=True): the hosts cap the reason at N *escaped* chars (Telegram 500, Discord 300,
# gateway/platforms/base.py _ea_fit), and ' / " / & / < / > expand to 4-6 chars each.
CAP_TELEGRAM = 480  # Telegram reason budget is 500 escaped chars
CAP_DISCORD = 280   # Discord field limit is ~300
CAP_OTHER = 480
MAX_FLAGGED_CHARS = 120  # keep the detector label from eating the whole budget

_RISK_TAIL = re.compile(r"\s*(Risk:.*)$", re.DOTALL)
_RISK_WORD = re.compile(r"\bRisk:", re.IGNORECASE)
_RISK_PARSE = re.compile(
    r"\bRisk:\s*(?P<level>[A-Za-z]+)?[\s.]*(?:[—–-]+\s*)?(?P<reason>.*)$", re.IGNORECASE | re.DOTALL)
_RISK_LEVELS = ("LOW", "MEDIUM", "HIGH", "UNKNOWN")


def _elen(text: str) -> int:
    """Length as the host's platform sees it: after HTML escaping (quotes included)."""
    return len(html.escape(text, quote=True))


def _truncate(text: str, limit: int) -> str:
    """Cut at a word boundary where possible; the result (with …) is at most ``limit`` chars."""
    if limit <= 0:
        return ""
    if len(text) <= limit:
        return text
    if limit == 1:
        return ELLIPSIS
    cut = text[: limit - 1]
    space = cut.rfind(" ")
    if space >= (limit - 1) // 2:
        cut = cut[:space]
    return cut.rstrip(" ,;:-—") + ELLIPSIS


def _truncate_escaped(text: str, limit: int) -> str:
    """Like ``_truncate`` but ``limit`` is in html-escaped chars."""
    if _elen(text) <= limit:
        return text
    raw = min(len(text), limit)
    while raw > 0:
        cut = _truncate(text, raw)
        if _elen(cut) <= limit:
            return cut
        raw -= 1
    return ""


def fit_summary_escaped(summary: str, budget: int) -> str:
    """``fit_summary`` where ``budget`` counts html-escaped chars (keeps the Risk verdict)."""
    raw = max(budget, 1)
    fitted = fit_summary(summary, raw)
    while _elen(fitted) > budget and raw > 1:
        raw -= 1
        fitted = fit_summary(summary, raw)
    return fitted if _elen(fitted) <= budget else _truncate_escaped(fitted, budget)


def fit_summary(summary: str, budget: int) -> str:
    """Shrink ``summary`` to ``budget`` chars, sacrificing the body before the ``Risk:`` verdict."""
    if len(summary) <= budget:
        return summary
    match = _RISK_TAIL.search(summary)
    if not match:
        return _truncate(summary, budget)
    tail, body = match.group(1), summary[: match.start()]
    tail = _truncate(tail, max(budget // 2, 1))
    body_budget = budget - len(tail) - 1
    if body_budget < 8:
        return _truncate(tail, budget)
    return f"{_truncate(body, body_budget)} {tail}"


def description_cap(platform: str) -> int | None:
    """Character budget of the description line for a gateway platform (None = unlimited)."""
    if platform == "telegram":
        return CAP_TELEGRAM
    if platform == "discord":
        return CAP_DISCORD
    return CAP_OTHER


def _description_line(label: str, summary: str, description: str, cap: int | None) -> str:
    prefix = f"{label}: " if label else ""
    flagged = _truncate(description.strip(), MAX_FLAGGED_CHARS) if description else ""
    suffix = f"{FLAGGED_SEP}{flagged}" if flagged else ""
    if cap is None:
        return f"{prefix}{summary}{suffix}"
    budget = cap - _elen(prefix) - _elen(suffix)
    if budget < 40:  # label/description unreasonably long: still guarantee room for the summary
        budget = max(cap - _elen(prefix) - 20, 20)
        suffix = _truncate_escaped(suffix, max(cap - _elen(prefix) - budget, 0))
    line = f"{prefix}{fit_summary_escaped(summary, budget)}{suffix}"
    return line if _elen(line) <= cap else _truncate_escaped(line, cap)


def split_risk(summary: str) -> tuple[str, str, str]:
    """Split a summary into ``(body, LEVEL, reason)`` using its trailing ``Risk: …`` sentence.

    LEVEL is LOW|MEDIUM|HIGH or UNKNOWN (no/unparseable Risk tail); reason is cut to ~90 chars.
    """
    text = (summary or "").strip()
    starts = [m.start() for m in _RISK_WORD.finditer(text)]
    if not starts:
        return text, "UNKNOWN", ""
    # Take the LAST "Risk:" in the text (the verdict closes the paragraph).
    match = _RISK_PARSE.match(text, starts[-1])
    if match is None:  # pragma: no cover - _RISK_PARSE always matches at a "Risk:" start
        return text, "UNKNOWN", ""
    body = text[: match.start()].rstrip()
    level = (match.group("level") or "").upper()
    reason = (match.group("reason") or "").strip()
    if level not in _RISK_LEVELS:
        reason = f"{match.group('level') or ''} {reason}".strip()
        level = "UNKNOWN"
    reason = _truncate(reason.strip(" .,;:—–-"), MAX_RISK_REASON_CHARS)
    return body, level, reason


def _cap_words(text: str, limit: int) -> str:
    words = text.split()
    if len(words) <= limit:
        return text
    kept = words[: max(limit, 1)]
    kept[-1] = kept[-1].rstrip(".,;:—-") + ELLIPSIS
    return " ".join(kept)


def _inline_command(label: str, summary: str, command: str,
                    max_words: int = DEFAULT_DESKTOP_MAX_WORDS) -> str:
    """Desktop command box. The card's <pre> is ~7 lines tall and scrolls. Order (summary-first):
    one-line verdict on line 1, then the (word-capped) explanation, then the REAL command last.
    A very long explanation can push the command below the fold; ``max_words`` keeps it short."""
    body, level, reason = split_risk(summary)
    if not label:  # placeholder case ("AI summary unavailable…"): that sentence is the headline
        head = _truncate(" ".join(summary.split()), 120)
        return f"{head}\n{COMMAND_DIVIDER}\n{command}"
    head = f"{label} — Risk: {level}" + (f" — {reason}" if reason else "")
    body = _cap_words(body, max_words)
    out = head
    if body:
        out += f"\n{SUMMARY_DIVIDER}\n{body}"
    return f"{out}\n{COMMAND_DIVIDER}\n{command}"


def compose(surface: str, platform: str, source: str, label: str, summary: str, command: str,
            description: str, desktop_inline: bool,
            desktop_max_words: int = DEFAULT_DESKTOP_MAX_WORDS) -> tuple[str, str]:
    """Return ``(display_command, display_description)`` for this surface.

    * Desktop / TUI (``source`` in desktop|tui): verdict line, then the explanation, then the
      real command (last), all inside the command box.
    * Telegram / Discord / other gateway platform: summary goes into the description, capped.
    * CLI: same as Telegram without a cap.
    * Gateway with neither platform nor source (unknown): summary in BOTH places.
    """
    platform = (platform or "").strip().lower()
    source = (source or "").strip().lower()

    if source in DESKTOP_SOURCES:
        if desktop_inline:
            return _inline_command(label, summary, command, desktop_max_words), description
        return command, _description_line(label, summary, description, CAP_OTHER)

    if surface == "cli":
        return command, _description_line(label, summary, description, None)

    if surface == "gateway" and not platform and not source:
        line = _description_line(label, summary, description, CAP_OTHER)
        if desktop_inline:
            return _inline_command(label, summary, command, desktop_max_words), line
        return command, line

    return command, _description_line(label, summary, description, description_cap(platform))
