"""approval-tldr: a plain-English paragraph on every dangerous-command approval prompt.

Why it exists: Hermes shows non-programmers a raw shell command and asks "Approve?". This plugin
registers an opt-in approval transport (``security.approval.transport: tldr``) that asks the LLM
what the command does and how risky it is, then re-presents the host's own prompt with that
paragraph added. Hermes keeps all authority (detection, scopes, persistence, timeout); this
plugin only changes displayed text and relays the human's answer, clamped to the offered choices.
Any plugin failure makes the host fall back to the stock prompt rather than a silent deny.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Any, Optional

if not __package__:
    # Imported bare (e.g. pytest collecting this directory as a package, which has no parent
    # package): behave as a package so the relative imports below resolve. Hermes' own loader
    # always sets __package__, so this branch is inert in production.
    __package__ = __name__
    __path__ = [str(Path(__file__).resolve().parent)]

from .tldr import compose as _compose
from .tldr import redispatch as _redispatch
from .tldr import summarize as _summarize
from .tldr.stash import Stash, StashEntry, TTL_GRACE_SECONDS

logger = logging.getLogger("plugins.approval-tldr")

TRANSPORT_NAME = "tldr"
HOOK_SURFACE = f"transport:{TRANSPORT_NAME}"
AUX_TASK = "approval_summary"

DEFAULT_LABEL = "AI summary (may be wrong — read the command)"
DEFAULT_MAX_WORDS = 90
DEFAULT_LLM_TIMEOUT_S = 10.0
DEFAULT_DESKTOP_MAX_WORDS = 60
MIN_INNER_WAIT_S = 1.0  # below this much time left before the host deadline, don't show a card
DEADLINE_MARGIN_S = 5.0  # finish the inner wait this long before the host's own deadline

_CTX: Any = None  # PluginContext; kept so ctx.llm is resolved lazily at request time
_STASH = Stash()


# ── Config ────────────────────────────────────────────────────────────────────────────────────────

def _cfg(key: str, default: Any) -> Any:
    try:
        value = _CTX.get_config(key, default) if _CTX is not None else default
    except Exception as exc:
        logger.debug("approval-tldr: config read %s failed (%s)", key, exc)
        return default
    return default if value is None else value


def _cfg_bool(key: str, default: bool) -> bool:
    value = _cfg(key, default)
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


def _cfg_number(key: str, default: float, low: float, high: float) -> float:
    try:
        return min(max(float(_cfg(key, default)), low), high)
    except (TypeError, ValueError):
        return default


def _settings() -> dict:
    label = _cfg("label", DEFAULT_LABEL)
    # The AI disclosure must never disappear: a blank label falls back to the default.
    label = label.strip() if isinstance(label, str) else ""
    return {
        "label": label or DEFAULT_LABEL,
        "max_words": int(_cfg_number("max_words", DEFAULT_MAX_WORDS, 20, 300)),
        "desktop_max_words": int(_cfg_number("desktop_max_words", DEFAULT_DESKTOP_MAX_WORDS, 20, 200)),
        "llm_timeout_s": _cfg_number("llm_timeout_s", DEFAULT_LLM_TIMEOUT_S, 1, 60),
        "desktop_inline": _cfg_bool("desktop_inline", True),
        "language": str(_cfg("language", "en")),
    }


def _get_llm() -> Any:
    if _CTX is None:
        raise RuntimeError("approval-tldr is not registered")
    return _CTX.llm


# ── Hooks (agent thread) ──────────────────────────────────────────────────────────────────────────

def on_pre(**kwargs: Any) -> None:
    """Capture what the worker thread cannot see. Fires on the agent thread; never raises."""
    try:
        if kwargs.get("surface") != HOOK_SURFACE:
            return
        request_id = kwargs.get("request_id")
        if not request_id:
            return
        entry = StashEntry(
            session_key=str(kwargs.get("session_key") or ""),
            surface=str(kwargs.get("surface")),
            platform=_redispatch.hermes_session_env("HERMES_SESSION_PLATFORM"),
            source=_redispatch.hermes_session_env("HERMES_SESSION_SOURCE"),
            agent_tid=_redispatch.hermes_acting_for_tid() or threading.get_ident(),
            cli_callback=_redispatch.hermes_cli_callback(),
            captured_at=time.time(),
        )
        _STASH.put(str(request_id), entry, _redispatch.hermes_approval_timeout_s() + TTL_GRACE_SECONDS)
    except Exception as exc:
        logger.warning("approval-tldr: pre_approval_request hook failed (%s: %s)", type(exc).__name__, exc)


def on_post(**kwargs: Any) -> None:
    """The host has its answer: forget the request, remember it is finished, clear any card of ours.

    Never raises. ``finished`` stops a slow ``present()`` from posting a card after the host already
    timed out or was /stop'ed; the withdraw (idempotent) removes a card that is already up.
    """
    try:
        request_id = kwargs.get("request_id")
        if not request_id:
            return
        request_id = str(request_id)
        _STASH.evict(request_id)
        _STASH.mark_finished(request_id, _redispatch.hermes_approval_timeout_s() + TTL_GRACE_SECONDS)
        session_key = kwargs.get("session_key")
        if session_key:
            try:
                _redispatch._hermes_withdraw(str(session_key), request_id, "approval-tldr: host decided")
            except Exception as exc:
                logger.debug("approval-tldr: withdraw on post hook failed (%s)", exc)
    except Exception as exc:
        logger.debug("approval-tldr: post_approval_response hook failed (%s)", exc)


# ── Transport (host-managed daemon worker thread) ─────────────────────────────────────────────────

def _inner_deadline_remaining(entry: StashEntry, request: Any) -> float:
    """Seconds left for our own prompt, ending before the host's deadline (scaled margin for tiny timeouts)."""
    timeout = float(request.timeout_seconds)
    margin = min(DEADLINE_MARGIN_S, 0.25 * max(timeout, 0.0))
    return entry.captured_at + timeout - margin - time.time()


def present(request: Any) -> Any:
    """Summarize, compose, re-dispatch, and return the human's (clamped) decision."""
    entry: Optional[StashEntry] = _STASH.pop(request.request_id)
    if entry is None:
        if _STASH.is_finished(request.request_id):
            logger.info("approval-tldr: host already decided %s; not showing a card", request.request_id[:8])
            return request.respond("deny")
        raise RuntimeError("approval-tldr: no stashed context for this request "
                           "(pre_approval_request hook did not fire); host will use its built-in prompt")
    token = _redispatch.hermes_bind_interrupt_target(entry.agent_tid)
    try:
        cfg = _settings()
        summary = _summarize.summarize(
            _get_llm, request.command, request.description, max_words=cfg["max_words"],
            timeout_s=cfg["llm_timeout_s"], language=cfg["language"])
        # The summary can take seconds: the host may have timed out, or the user hit /stop, meanwhile.
        # A card posted now would be an orphan (Telegram resolves FIFO per session, so it would swallow
        # the NEXT approval tap) and would keep the agent waiting.
        if _redispatch.hermes_is_interrupted() or _STASH.is_finished(request.request_id):
            logger.info("approval-tldr: request %s was stopped or decided during the summary; "
                        "not showing a card", request.request_id[:8])
            return request.respond("deny")
        remaining = _inner_deadline_remaining(entry, request)
        if remaining <= MIN_INNER_WAIT_S:
            logger.info("approval-tldr: only %.1fs left before the host deadline for %s; not showing a card",
                        remaining, request.request_id[:8])
            return request.respond("deny")
        label = "" if summary == _summarize.PLACEHOLDER else cfg["label"]
        display_command, display_description = _compose.compose(
            request.surface, entry.platform, entry.source, label, summary, request.command,
            request.description, cfg["desktop_inline"], cfg["desktop_max_words"])
        choice = _redispatch.redispatch(request, entry, display_command, display_description,
                                        remaining_s=remaining)
    finally:
        _redispatch.hermes_release_interrupt_target(token)
    return request.respond(choice)


# ── Registration ──────────────────────────────────────────────────────────────────────────────────

def register(ctx: Any) -> None:
    global _CTX
    _CTX = ctx
    ctx.register_hook("pre_approval_request", on_pre)
    ctx.register_hook("post_approval_response", on_post)
    ctx.register_approval_transport(TRANSPORT_NAME, present)
    try:
        ctx.register_auxiliary_task(
            AUX_TASK, display_name="Approval summary (approval-tldr)",
            description="Writes the plain-English summary shown on approval prompts. "
                        "Pin a small, cheap model here via auxiliary.approval_summary.model.",
            inherit_from="approval")
    except Exception as exc:  # older Hermes or name clash: summaries just use the default model
        logger.warning("approval-tldr: auxiliary task registration unavailable (%s); "
                       "using the default model", exc)
