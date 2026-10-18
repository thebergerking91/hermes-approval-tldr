"""Bounded, thread-safe request_id -> context map.

Why it exists: the host's ``ApprovalRequest`` carries no session key and the CLI approval
callback lives in thread-local storage, but the transport runs on a different (worker) thread
than the agent. The ``pre_approval_request`` hook fires on the agent thread right before the
transport, so it is the only place to capture those values. Entries expire (approval timeout +
60 s) and the map is size-capped, so a crashed or abandoned request can never leak memory.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

DEFAULT_MAX_ENTRIES = 64
DEFAULT_MAX_FINISHED = 256
TTL_GRACE_SECONDS = 60.0


@dataclass(frozen=True)
class StashEntry:
    """Everything the worker thread cannot see for itself, captured on the agent thread."""

    session_key: str
    surface: str  # hook surface, e.g. "transport:tldr"
    platform: str  # HERMES_SESSION_PLATFORM ("telegram", ... or "" on Desktop/TUI/CLI)
    source: str  # HERMES_SESSION_SOURCE ("desktop", "tui", ... )
    agent_tid: int  # agent thread ident, so /stop can be propagated to the worker
    cli_callback: Optional[Callable[..., Any]]  # thread-local CLI panel callback, may be None
    captured_at: float = field(default_factory=time.time)


class Stash:
    """Insertion-ordered store with TTL and a hard size cap (oldest entry dropped first)."""

    def __init__(self, max_entries: int = DEFAULT_MAX_ENTRIES,
                 clock: Callable[[], float] = time.monotonic,
                 max_finished: int = DEFAULT_MAX_FINISHED) -> None:
        self._max = max(1, int(max_entries))
        self._max_finished = max(1, int(max_finished))
        self._clock = clock
        self._lock = threading.Lock()
        self._items: "OrderedDict[str, tuple[float, StashEntry]]" = OrderedDict()
        # request_ids the host has already decided (post_approval_response): bounded, TTL'd.
        self._finished: "OrderedDict[str, float]" = OrderedDict()

    def put(self, request_id: str, entry: StashEntry, ttl_seconds: float) -> None:
        now = self._clock()
        with self._lock:
            self._purge_locked(now)
            self._items.pop(request_id, None)
            self._items[request_id] = (now + max(float(ttl_seconds), 0.0), entry)
            while len(self._items) > self._max:
                self._items.popitem(last=False)

    def pop(self, request_id: str) -> Optional[StashEntry]:
        """Remove and return the entry, or None when missing or expired."""
        now = self._clock()
        with self._lock:
            self._purge_locked(now)
            item = self._items.pop(request_id, None)
        return item[1] if item else None

    def evict(self, request_id: str) -> None:
        with self._lock:
            self._items.pop(request_id, None)

    def mark_finished(self, request_id: str, ttl_seconds: float) -> None:
        """Remember that the host already decided ``request_id`` (so we must not show a card for it)."""
        now = self._clock()
        with self._lock:
            self._purge_locked(now)
            self._finished.pop(request_id, None)
            self._finished[request_id] = now + max(float(ttl_seconds), 0.0)
            while len(self._finished) > self._max_finished:
                self._finished.popitem(last=False)

    def is_finished(self, request_id: str) -> bool:
        with self._lock:
            self._purge_locked(self._clock())
            return request_id in self._finished

    def clear(self) -> None:
        with self._lock:
            self._items.clear()
            self._finished.clear()

    def __len__(self) -> int:
        with self._lock:
            self._purge_locked(self._clock())
            return len(self._items)

    def __contains__(self, request_id: object) -> bool:
        with self._lock:
            self._purge_locked(self._clock())
            return request_id in self._items

    def _purge_locked(self, now: float) -> None:
        expired = [rid for rid, (deadline, _) in self._items.items() if deadline <= now]
        for rid in expired:
            del self._items[rid]
        gone = [rid for rid, deadline in self._finished.items() if deadline <= now]
        for rid in gone:
            del self._finished[rid]
