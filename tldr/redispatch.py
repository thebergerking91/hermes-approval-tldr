"""Re-entry into Hermes' own prompt surfaces, plus every private Hermes seam the plugin touches.

Why it exists: the plugin never decides anything — after composing the friendlier text it hands the
question back to the same gateway queue (Telegram/Desktop) or CLI panel Hermes would have used and
relays the human's answer. All the Hermes internals this needs are reached through the tiny
``_hermes_*`` adapters below, so an upstream rename breaks in exactly one place with one clear log
line (and the host then falls back to its built-in prompt) instead of failing obscurely elsewhere.
"""

from __future__ import annotations

import contextvars
import logging
import os
import threading
from typing import Any, Callable, Optional

from .stash import StashEntry

logger = logging.getLogger("plugins.approval-tldr")

DEFAULT_APPROVAL_TIMEOUT_S = 300


# ── Adapters: the ONLY place that imports Hermes internals ────────────────────────────────────────

def _upstream_broken(what: str, exc: BaseException) -> RuntimeError:
    logger.error("approval-tldr: Hermes internal API changed or missing (%s): %s — "
                 "the plugin cannot re-dispatch; Hermes will use its built-in prompt", what, exc)
    return RuntimeError(f"approval-tldr: upstream API unavailable: {what}")


def _hermes_notify_cb(session_key: str) -> Optional[Callable[[dict], None]]:
    """tools.approval._gateway_notify_cb(session_key): the gateway's card-sender, or None."""
    try:
        from tools import approval
        return approval._gateway_notify_cb(session_key)
    except (ImportError, AttributeError, TypeError) as exc:
        raise _upstream_broken("tools.approval._gateway_notify_cb", exc) from exc


def _hermes_await_gateway_decision(session_key: str, notify_cb: Callable[[dict], None],
                                   data: dict) -> dict:
    """tools.approval_gateway_wait._await_gateway_decision(...): queue + notify + block."""
    try:
        from tools.approval_gateway_wait import _await_gateway_decision
    except (ImportError, AttributeError) as exc:
        raise _upstream_broken("tools.approval_gateway_wait._await_gateway_decision", exc) from exc
    return _await_gateway_decision(session_key, notify_cb, data, surface="gateway")


def _hermes_cli_prompt(command: str, description: str, *, allow_permanent: bool, allow_session: bool,
                       smart_denied: bool, approval_callback: Optional[Callable[..., Any]],
                       timeout_seconds: Optional[int] = None) -> str:
    """tools.approval_prompt.prompt_dangerous_approval(...): the CLI panel / input() prompt."""
    try:
        from tools.approval_prompt import prompt_dangerous_approval
    except (ImportError, AttributeError) as exc:
        raise _upstream_broken("tools.approval_prompt.prompt_dangerous_approval", exc) from exc
    return prompt_dangerous_approval(
        command, description, timeout_seconds=timeout_seconds, allow_permanent=allow_permanent,
        allow_session=allow_session, smart_denied=smart_denied, approval_callback=approval_callback)


def _hermes_withdraw(session_key: str, request_id: str, cause: str = "approval-tldr: host deadline") -> bool:
    """tools.approval.withdraw_gateway_approval(session_key, request_id, cause): drop one pending card.

    Idempotent: False when the request is no longer pending. The waiter wakes with ``cancelled``.
    """
    try:
        from tools.approval import withdraw_gateway_approval
    except (ImportError, AttributeError) as exc:
        raise _upstream_broken("tools.approval.withdraw_gateway_approval", exc) from exc
    return bool(withdraw_gateway_approval(session_key, request_id, cause))


def hermes_is_interrupted() -> bool:
    """tools.interrupt.is_interrupted(): True once /stop reached this (bound) worker's agent thread."""
    try:
        from tools.interrupt import is_interrupted
        return bool(is_interrupted())
    except Exception as exc:
        logger.debug("approval-tldr: interrupt state unreadable (%s)", exc)
        return False


def hermes_acting_for_tid() -> Optional[int]:
    """tools.interrupt.acting_for_tid: the tool-thread this context acts for, if any."""
    try:
        from tools.interrupt import acting_for_tid
        value = acting_for_tid.get()
        return int(value) if value is not None else None
    except Exception:
        return None


def hermes_is_llm_trust_error(exc: BaseException) -> bool:
    """True for agent.plugin_llm.PluginLlmTrustError (task not allowed for this plugin)."""
    try:
        from agent.plugin_llm import PluginLlmTrustError
        if isinstance(exc, PluginLlmTrustError):
            return True
    except Exception:
        pass
    return any(cls.__name__ == "PluginLlmTrustError" for cls in type(exc).__mro__)


def hermes_cli_callback() -> Optional[Callable[..., Any]]:
    """tools.terminal_tool._get_approval_callback(): the CURRENT thread's CLI panel callback."""
    try:
        from tools.terminal_tool import _get_approval_callback
        return _get_approval_callback()
    except (ImportError, AttributeError) as exc:
        logger.warning("approval-tldr: cannot read the CLI approval callback (%s)", exc)
        return None


def hermes_bind_interrupt_target(agent_tid: int) -> Optional[contextvars.Token]:
    """Point tools.interrupt.acting_for_tid at the agent thread so /stop reaches this worker."""
    try:
        from tools.interrupt import acting_for_tid
        return acting_for_tid.set(agent_tid)
    except (ImportError, AttributeError) as exc:
        logger.warning("approval-tldr: /stop propagation unavailable (%s)", exc)
        return None


def hermes_release_interrupt_target(token: Optional[contextvars.Token]) -> None:
    if token is None:
        return
    try:
        from tools.interrupt import acting_for_tid
        acting_for_tid.reset(token)
    except Exception:  # worker thread is ending anyway
        pass


def hermes_session_env(name: str) -> str:
    """gateway.session_context.get_session_env(name): contextvar first, then os.environ."""
    try:
        from gateway.session_context import get_session_env
        return str(get_session_env(name, "") or "").strip().lower()
    except Exception:
        return str(os.getenv(name, "") or "").strip().lower()


def hermes_approval_timeout_s() -> float:
    """tools.approval_context._get_approval_timeout(): approvals.timeout in seconds."""
    try:
        from tools.approval_context import _get_approval_timeout
        return float(_get_approval_timeout())
    except Exception as exc:
        logger.debug("approval-tldr: approvals.timeout unreadable (%s); assuming %ss",
                     exc, DEFAULT_APPROVAL_TIMEOUT_S)
        return float(DEFAULT_APPROVAL_TIMEOUT_S)


# ── Choice normalisation ──────────────────────────────────────────────────────────────────────────

def map_gateway_decision(decision: dict) -> str:
    """Gateway result -> choice. Non-answers are a definite ``deny``; ``notify_failed`` raises."""
    if not isinstance(decision, dict):
        return "deny"
    if decision.get("notify_failed"):
        # The card was never shown, so nobody could answer: that is a failure of this transport,
        # not a user denial. Raise so the host falls back to its built-in prompt.
        raise RuntimeError("approval-tldr: the approval card could not be delivered (notify failed)")
    if decision.get("cancelled") or not decision.get("resolved"):
        return "deny"
    choice = decision.get("choice")
    if choice in (None, "deny"):
        return "deny"
    return str(choice)


def map_cli_choice(choice: Any) -> str:
    """CLI result -> choice. ``timeout`` / ``cancelled`` (Unanswered) / unknown -> ``deny``."""
    text = str(choice) if choice is not None else ""
    if text in ("once", "session", "always"):
        return text
    return "deny"


def clamp(choice: str, allowed: tuple[str, ...] | list[str]) -> str:
    """Never widen scope: anything the host did not offer becomes ``deny``."""
    return choice if choice in allowed else "deny"


# ── The re-dispatch itself ────────────────────────────────────────────────────────────────────────

def build_gateway_data(request: Any, display_command: str, display_description: str) -> dict:
    allowed = tuple(request.allowed_choices)
    data: dict[str, Any] = {
        "request_id": request.request_id,  # lets the host's Desktop path and our withdraw target this card
        "command": display_command,
        "description": display_description,
        "pattern_key": request.pattern_key,
        "pattern_keys": list(request.pattern_keys),
        "allow_permanent": "always" in allowed,
        "allow_session": "session" in allowed,
    }
    if "session" not in allowed:
        data["smart_denied"] = True
    return data


def _withdraw_quietly(session_key: str, request_id: str) -> None:
    try:
        withdrawn = _hermes_withdraw(session_key, request_id)
        if withdrawn:
            logger.info("approval-tldr: withdrew card %s before the host deadline", request_id[:8])
    except Exception as exc:
        logger.debug("approval-tldr: deadline withdraw failed (%s)", exc)


def redispatch(request: Any, entry: StashEntry, display_command: str, display_description: str,
               remaining_s: Optional[float] = None) -> str:
    """Show the composed text on the surface the request came from; return a clamped choice.

    ``remaining_s`` bounds the inner wait so it ends before the host's own deadline (gateway: a
    daemon timer withdraws the card; CLI: passed as the prompt timeout).
    Raises RuntimeError when no surface can answer (host then uses its built-in prompt).
    """
    allowed = tuple(request.allowed_choices)
    surface = request.surface

    if surface == "gateway":
        notify_cb = _hermes_notify_cb(entry.session_key)
        if notify_cb is not None:
            data = build_gateway_data(request, display_command, display_description)
            timer: Optional[threading.Timer] = None
            if remaining_s is not None:
                timer = threading.Timer(max(float(remaining_s), 0.0), _withdraw_quietly,
                                        args=(entry.session_key, request.request_id))
                timer.daemon = True
                timer.start()
            try:
                decision = _hermes_await_gateway_decision(entry.session_key, notify_cb, data)
            finally:
                if timer is not None:
                    timer.cancel()
            return clamp(map_gateway_decision(decision), allowed)
        if entry.cli_callback is None:
            raise RuntimeError("approval-tldr: no gateway notifier and no CLI callback for this session")
        # No gateway notifier but an interactive CLI panel exists: mirror the host's own fall-through.
        surface = "cli"

    if surface == "cli":
        kwargs: dict[str, Any] = dict(
            allow_permanent="always" in allowed, allow_session="session" in allowed,
            smart_denied="session" not in allowed, approval_callback=entry.cli_callback)
        if remaining_s is not None:
            kwargs["timeout_seconds"] = max(int(remaining_s), 1)
        raw = _hermes_cli_prompt(display_command, display_description, **kwargs)
        return clamp(map_cli_choice(raw), allowed)

    raise RuntimeError(f"approval-tldr: unsupported approval surface {surface!r}")
