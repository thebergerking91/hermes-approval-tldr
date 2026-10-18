"""Re-dispatch: gateway/CLI choice mapping, clamping to allowed choices, upstream-drift errors."""

from __future__ import annotations

import pytest

from hermes_cli.approval_transport import ApprovalRequest


def make_request(surface="gateway", allow_session=True, allow_permanent=True):
    return ApprovalRequest.create(
        command="rm -rf /tmp/x", description="recursive delete", pattern_key="rm_recursive",
        pattern_keys=("rm_recursive", "other"), session_key="sess-1", surface=surface,
        allow_session=allow_session, allow_permanent=allow_permanent, timeout_seconds=5)


def make_entry(stash_mod, cli_callback=None):
    return stash_mod.StashEntry(session_key="sess-1", surface="transport:tldr", platform="telegram",
                                source="", agent_tid=1, cli_callback=cli_callback)


GATEWAY_CASES = [
    ({"resolved": True, "choice": "once"}, "once"),
    ({"resolved": True, "choice": "session"}, "session"),
    ({"resolved": True, "choice": "always"}, "always"),
    ({"resolved": True, "choice": "deny"}, "deny"),
    ({"resolved": True, "choice": None}, "deny"),
    ({"resolved": True, "choice": "once", "cancelled": "interrupted"}, "deny"),
    ({"resolved": False, "choice": "once"}, "deny"),
    ({"resolved": False, "choice": None}, "deny"),
    ({}, "deny"),
]


@pytest.mark.parametrize("decision,expected", GATEWAY_CASES)
def test_gateway_mapping(redispatch_mod, stash_mod, monkeypatch, decision, expected):
    monkeypatch.setattr(redispatch_mod, "_hermes_notify_cb", lambda sk: (lambda data: None))
    monkeypatch.setattr(redispatch_mod, "_hermes_await_gateway_decision", lambda sk, cb, data: decision)
    assert redispatch_mod.redispatch(make_request(), make_entry(stash_mod), "cmd", "desc") == expected


@pytest.mark.parametrize("decision", [{"resolved": False, "choice": None, "notify_failed": True},
                                      {"notify_failed": True, "resolved": True, "choice": "once"}])
def test_gateway_notify_failed_raises_for_builtin_fallback(redispatch_mod, stash_mod, monkeypatch, decision):
    """The card never reached anyone: that is a transport failure, not a user denial."""
    monkeypatch.setattr(redispatch_mod, "_hermes_notify_cb", lambda sk: (lambda data: None))
    monkeypatch.setattr(redispatch_mod, "_hermes_await_gateway_decision", lambda sk, cb, data: decision)
    with pytest.raises(RuntimeError, match="could not be delivered"):
        redispatch_mod.redispatch(make_request(), make_entry(stash_mod), "cmd", "desc")


def test_gateway_clamps_to_allowed_choices(redispatch_mod, stash_mod, monkeypatch):
    request = make_request(allow_session=False, allow_permanent=False)
    assert request.allowed_choices == ("once", "deny")
    monkeypatch.setattr(redispatch_mod, "_hermes_notify_cb", lambda sk: (lambda data: None))
    for sneaky in ("always", "session", "root", "ONCE"):
        monkeypatch.setattr(redispatch_mod, "_hermes_await_gateway_decision",
                            lambda sk, cb, data, c=sneaky: {"resolved": True, "choice": c})
        assert redispatch_mod.redispatch(request, make_entry(stash_mod), "c", "d") == "deny"
    monkeypatch.setattr(redispatch_mod, "_hermes_await_gateway_decision",
                        lambda sk, cb, data: {"resolved": True, "choice": "once"})
    assert redispatch_mod.redispatch(request, make_entry(stash_mod), "c", "d") == "once"


def test_gateway_data_shape(redispatch_mod, stash_mod, monkeypatch):
    seen = {}
    monkeypatch.setattr(redispatch_mod, "_hermes_notify_cb", lambda sk: seen.setdefault("sk", sk) and (lambda d: None))
    monkeypatch.setattr(redispatch_mod, "_hermes_await_gateway_decision",
                        lambda sk, cb, data: (seen.update(data=data, awaited=sk), {"resolved": True, "choice": "once"})[1])
    request = make_request()
    request_id = request.request_id
    redispatch_mod.redispatch(request, make_entry(stash_mod), "DISPLAY CMD", "DISPLAY DESC")
    assert seen["sk"] == seen["awaited"] == "sess-1"
    assert seen["data"] == {"request_id": request_id, "command": "DISPLAY CMD", "description": "DISPLAY DESC",
                            "pattern_key": "rm_recursive", "pattern_keys": ["rm_recursive", "other"],
                            "allow_permanent": True, "allow_session": True}

    request = make_request(allow_session=False, allow_permanent=False)
    redispatch_mod.redispatch(request, make_entry(stash_mod), "c", "d")
    assert seen["data"]["allow_permanent"] is False and seen["data"]["allow_session"] is False
    assert seen["data"]["smart_denied"] is True


def test_gateway_without_notifier_or_cli_raises(redispatch_mod, stash_mod, monkeypatch):
    monkeypatch.setattr(redispatch_mod, "_hermes_notify_cb", lambda sk: None)
    with pytest.raises(RuntimeError):
        redispatch_mod.redispatch(make_request(), make_entry(stash_mod), "c", "d")


def test_gateway_without_notifier_falls_through_to_cli_callback(redispatch_mod, stash_mod, monkeypatch):
    cb = lambda *a, **k: "once"  # noqa: E731
    seen = {}
    monkeypatch.setattr(redispatch_mod, "_hermes_notify_cb", lambda sk: None)
    monkeypatch.setattr(redispatch_mod, "_hermes_cli_prompt",
                        lambda c, d, **kw: (seen.update(kw=kw), "once")[1])
    assert redispatch_mod.redispatch(make_request(), make_entry(stash_mod, cb), "c", "d") == "once"
    assert seen["kw"]["approval_callback"] is cb


CLI_CASES = [("once", "once"), ("session", "session"), ("always", "always"), ("deny", "deny"),
             ("timeout", "deny"), ("cancelled", "deny"), ("", "deny"), (None, "deny"), ("garbage", "deny")]


@pytest.mark.parametrize("raw,expected", CLI_CASES)
def test_cli_mapping(redispatch_mod, stash_mod, monkeypatch, raw, expected):
    monkeypatch.setattr(redispatch_mod, "_hermes_cli_prompt", lambda c, d, **kw: raw)
    assert redispatch_mod.redispatch(make_request("cli"), make_entry(stash_mod), "c", "d") == expected


def test_cli_passes_scopes_and_clamps(redispatch_mod, stash_mod, monkeypatch):
    seen = {}
    cb = lambda *a, **k: None  # noqa: E731
    monkeypatch.setattr(redispatch_mod, "_hermes_cli_prompt", lambda c, d, **kw: (seen.update(args=(c, d), kw=kw), "always")[1])
    request = make_request("cli", allow_session=False, allow_permanent=False)
    assert redispatch_mod.redispatch(request, make_entry(stash_mod, cb), "SHOWN", "WHY") == "deny"  # clamped
    assert seen["args"] == ("SHOWN", "WHY")
    assert seen["kw"] == {"allow_permanent": False, "allow_session": False, "smart_denied": True,
                          "approval_callback": cb}


def test_unknown_surface_raises(redispatch_mod, stash_mod):
    with pytest.raises(RuntimeError):
        redispatch_mod.redispatch(make_request("telepathy"), make_entry(stash_mod), "c", "d")


def test_upstream_rename_gives_clear_error(redispatch_mod, monkeypatch, caplog):
    from tools import approval
    monkeypatch.delattr(approval, "_gateway_notify_cb")
    with caplog.at_level("ERROR", logger="plugins.approval-tldr"):
        with pytest.raises(RuntimeError, match="upstream API unavailable"):
            redispatch_mod._hermes_notify_cb("s")
    assert "_gateway_notify_cb" in caplog.text


def test_pinned_upstream_signatures():
    """If Hermes renames/reshapes these, fail here (and fall back at runtime) instead of obscurely."""
    import inspect
    from tools import approval, approval_context, approval_gateway_wait, approval_prompt, interrupt, terminal_tool

    assert list(inspect.signature(approval._gateway_notify_cb).parameters) == ["session_key"]
    assert list(inspect.signature(approval_gateway_wait._await_gateway_decision).parameters) == [
        "session_key", "notify_cb", "approval_data", "surface"]
    params = inspect.signature(approval_prompt.prompt_dangerous_approval).parameters
    for name in ("allow_permanent", "allow_session", "smart_denied", "approval_callback"):
        assert name in params
    assert callable(terminal_tool._get_approval_callback)
    assert callable(approval_context._get_approval_timeout)
    assert hasattr(interrupt, "acting_for_tid")
    assert list(inspect.signature(approval.resolve_gateway_approval).parameters)[:2] == ["session_key", "choice"]
    assert list(inspect.signature(approval.withdraw_gateway_approval).parameters) == [
        "session_key", "request_id", "cause"]
    assert "timeout_seconds" in params
    assert callable(interrupt.is_interrupted)


# ── S1 adapters / deadline bounding ──
def test_gateway_inner_wait_is_withdrawn_at_deadline(redispatch_mod, stash_mod, monkeypatch):
    import time
    seen = {}
    monkeypatch.setattr(redispatch_mod, "_hermes_notify_cb", lambda sk: (lambda data: None))
    monkeypatch.setattr(redispatch_mod, "_hermes_withdraw",
                        lambda sk, rid, cause="x": seen.update(w=(sk, rid)) or True)

    def slow_wait(sk, cb, data):
        time.sleep(0.5)
        return {"resolved": True, "choice": "once"}

    monkeypatch.setattr(redispatch_mod, "_hermes_await_gateway_decision", slow_wait)
    request = make_request()
    assert redispatch_mod.redispatch(request, make_entry(stash_mod), "c", "d", remaining_s=0.1) == "once"
    assert seen["w"] == ("sess-1", request.request_id)


def test_gateway_deadline_timer_cancelled_when_wait_returns(redispatch_mod, stash_mod, monkeypatch):
    import time
    seen = []
    monkeypatch.setattr(redispatch_mod, "_hermes_notify_cb", lambda sk: (lambda data: None))
    monkeypatch.setattr(redispatch_mod, "_hermes_withdraw", lambda *a, **k: seen.append(a) or True)
    monkeypatch.setattr(redispatch_mod, "_hermes_await_gateway_decision",
                        lambda sk, cb, data: {"resolved": True, "choice": "deny"})
    redispatch_mod.redispatch(make_request(), make_entry(stash_mod), "c", "d", remaining_s=0.2)
    time.sleep(0.4)
    assert seen == []


def test_cli_prompt_gets_bounded_timeout(redispatch_mod, stash_mod, monkeypatch):
    seen = {}
    monkeypatch.setattr(redispatch_mod, "_hermes_cli_prompt", lambda c, d, **kw: (seen.update(kw=kw), "once")[1])
    redispatch_mod.redispatch(make_request("cli"), make_entry(stash_mod), "c", "d", remaining_s=42.9)
    assert seen["kw"]["timeout_seconds"] == 42
    redispatch_mod.redispatch(make_request("cli"), make_entry(stash_mod), "c", "d")
    assert "timeout_seconds" not in seen["kw"]


def test_withdraw_adapter_calls_upstream_with_cause(redispatch_mod, monkeypatch):
    from tools import approval
    calls = []
    monkeypatch.setattr(approval, "withdraw_gateway_approval", lambda sk, rid, cause: calls.append((sk, rid, cause)) or True)
    assert redispatch_mod._hermes_withdraw("s", "r") is True
    assert calls == [("s", "r", "approval-tldr: host deadline")]


def test_withdraw_adapter_upstream_rename_is_clear(redispatch_mod, monkeypatch):
    from tools import approval
    monkeypatch.delattr(approval, "withdraw_gateway_approval")
    with pytest.raises(RuntimeError, match="upstream API unavailable"):
        redispatch_mod._hermes_withdraw("s", "r")


def test_is_interrupted_adapter_follows_acting_for_tid(redispatch_mod):
    import threading
    from tools import interrupt
    assert redispatch_mod.hermes_is_interrupted() is False
    other = 987654321
    token = redispatch_mod.hermes_bind_interrupt_target(other)
    try:
        interrupt.set_interrupt(True, other)
        assert redispatch_mod.hermes_is_interrupted() is True
        assert redispatch_mod.hermes_acting_for_tid() == other
    finally:
        interrupt.set_interrupt(False, other)
        redispatch_mod.hermes_release_interrupt_target(token)
    assert redispatch_mod.hermes_is_interrupted() is False
    assert redispatch_mod.hermes_acting_for_tid() is None


def test_trust_error_detection(redispatch_mod):
    class PluginLlmTrustError(PermissionError):
        pass

    assert redispatch_mod.hermes_is_llm_trust_error(PluginLlmTrustError("x"))
    assert not redispatch_mod.hermes_is_llm_trust_error(PermissionError("x"))
    assert not redispatch_mod.hermes_is_llm_trust_error(TimeoutError("x"))
    from agent.plugin_llm import PluginLlmTrustError as Real
    assert redispatch_mod.hermes_is_llm_trust_error(Real("nope"))
