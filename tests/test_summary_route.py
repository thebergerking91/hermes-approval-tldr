"""How fast the summary is asked to be: the route Hermes resolves for it, and its time budget.

The route tests use Hermes' real auxiliary-task registry entry builder and read-time resolver against
a scratch config.yaml, so they prove what Hermes would actually send, not what the plugin passes.
"""

from __future__ import annotations

import logging
import time

import pytest

from support import FakeLlm

APPROVAL_SLOT = {"provider": "openai-codex", "model": "slow-reasoner", "timeout": 30,
                 "reasoning_effort": "high"}


def _resolved_summary_route(plugin, ctx, monkeypatch, home, user_summary_block=None):
    import hermes_yaml as yaml
    from hermes_cli import plugins as hermes_plugins
    from hermes_cli.plugins_aux_tasks import build_auxiliary_task_entry
    from agent.auxiliary_task_config import _get_auxiliary_task_config

    aux = {"approval": dict(APPROVAL_SLOT)}
    if user_summary_block is not None:
        aux["approval_summary"] = user_summary_block
    (home / "config.yaml").write_text(yaml.safe_dump({"auxiliary": aux}), encoding="utf-8")

    plugin.register(ctx)
    (key, kwargs), = ctx.aux_tasks
    kwargs.setdefault("defaults", None)  # Hermes' own default when a plugin passes none
    entry = build_auxiliary_task_entry("approval-tldr", "approval-tldr", key, registered={}, **kwargs)
    monkeypatch.setattr(hermes_plugins, "get_plugin_auxiliary_tasks", lambda: [entry])
    return _get_auxiliary_task_config(key)


def test_summary_inherits_approval_model_but_not_its_high_reasoning(plugin, ctx, monkeypatch,
                                                                    _scratch_hermes_home):
    route = _resolved_summary_route(plugin, ctx, monkeypatch, _scratch_hermes_home)
    assert route["provider"] == "openai-codex" and route["model"] == "slow-reasoner"
    assert route["reasoning_effort"] == "low"


def test_user_pinned_summary_route_still_wins(plugin, ctx, monkeypatch, _scratch_hermes_home):
    route = _resolved_summary_route(
        plugin, ctx, monkeypatch, _scratch_hermes_home,
        {"provider": "anthropic", "model": "small-fast", "reasoning_effort": "medium"})
    assert (route["provider"], route["model"], route["reasoning_effort"]) == (
        "anthropic", "small-fast", "medium")


def test_user_effort_override_without_pinning_a_model(plugin, ctx, monkeypatch, _scratch_hermes_home):
    route = _resolved_summary_route(plugin, ctx, monkeypatch, _scratch_hermes_home,
                                    {"reasoning_effort": "high"})
    assert route["model"] == "slow-reasoner" and route["reasoning_effort"] == "high"


# ── Time budget ──
def test_default_timeout_is_twenty_seconds(registered):
    assert registered._settings()["llm_timeout_s"] == 20.0


@pytest.mark.parametrize("configured, remaining, expected", [
    (20, 295.0, 20.0),   # normal approvals.timeout: the setting applies
    (20, 25.0, 12.5),    # short host deadline: at most half of what is left
    (20, 0.5, 1.0),      # never below the 1 s floor
])
def test_summary_budget(registered, configured, remaining, expected):
    assert registered._summary_budget(configured, remaining) == pytest.approx(expected)


def test_summary_logs_how_long_the_model_took(summarize_mod, caplog):
    with caplog.at_level(logging.INFO, logger="plugins.approval-tldr"):
        text = summarize_mod.summarize(lambda: FakeLlm(), "ls", "listing", timeout_s=5)
    assert text != summarize_mod.PLACEHOLDER
    assert "summary model answered in" in caplog.text


def test_failed_summary_logs_elapsed_time(summarize_mod, caplog):
    class Boom:
        def complete(self, **kwargs):
            time.sleep(0.05)
            raise RuntimeError("provider down")

    with caplog.at_level(logging.WARNING, logger="plugins.approval-tldr"):
        assert summarize_mod.summarize(lambda: Boom(), "ls", "x", timeout_s=5) == summarize_mod.PLACEHOLDER
    assert "summary failed after" in caplog.text and "provider down" in caplog.text
