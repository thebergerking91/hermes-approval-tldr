"""Stash: TTL expiry, size bound, eviction, hook-driven population."""

from __future__ import annotations

import threading


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _entry(stash_mod, key="s1"):
    return stash_mod.StashEntry(session_key=key, surface="transport:tldr", platform="telegram", source="",
                                agent_tid=1, cli_callback=None)


def test_put_and_pop_roundtrip(stash_mod):
    st = stash_mod.Stash()
    st.put("r1", _entry(stash_mod), ttl_seconds=10)
    assert "r1" in st
    assert st.pop("r1").session_key == "s1"
    assert st.pop("r1") is None  # popped means gone


def test_ttl_expiry(stash_mod):
    clock = Clock()
    st = stash_mod.Stash(clock=clock)
    st.put("r1", _entry(stash_mod), ttl_seconds=360)
    clock.now += 359
    assert "r1" in st
    clock.now += 2
    assert st.pop("r1") is None
    assert len(st) == 0


def test_bound_drops_oldest(stash_mod):
    st = stash_mod.Stash(max_entries=64)
    for i in range(70):
        st.put(f"r{i}", _entry(stash_mod), ttl_seconds=100)
    assert len(st) == 64
    assert st.pop("r0") is None and st.pop("r5") is None
    assert st.pop("r6") is not None and st.pop("r69") is not None


def test_evict_and_clear(stash_mod):
    st = stash_mod.Stash()
    st.put("a", _entry(stash_mod), 10)
    st.put("b", _entry(stash_mod), 10)
    st.evict("a")
    st.evict("missing")  # no error
    assert "a" not in st and "b" in st
    st.clear()
    assert len(st) == 0


def test_thread_safety_smoke(stash_mod):
    st = stash_mod.Stash(max_entries=32)

    def worker(n):
        for i in range(200):
            rid = f"{n}-{i}"
            st.put(rid, _entry(stash_mod), 10)
            st.pop(rid)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len(st) <= 32


def test_on_pre_stashes_only_our_transport(registered, monkeypatch):
    monkeypatch.setenv("HERMES_SESSION_PLATFORM", "telegram")
    monkeypatch.setenv("HERMES_SESSION_SOURCE", "")
    cb = lambda *a, **k: "once"  # noqa: E731
    monkeypatch.setattr(registered._redispatch, "hermes_cli_callback", lambda: cb)

    registered.on_pre(command="x", description="d", pattern_key="p", pattern_keys=["p"], session_key="sess",
                      surface="gateway", request_id="skip-me", request_digest="d", turn_id="t")
    registered.on_pre(command="x", description="d", pattern_key="p", pattern_keys=["p"], session_key="sess",
                      surface="transport:other", request_id="skip-2", request_digest="d")
    assert len(registered._STASH) == 0

    registered.on_pre(command="x", description="d", pattern_key="p", pattern_keys=["p"], session_key="sess",
                      surface="transport:tldr", request_id="rid-1", request_digest="d",
                      turn_id="t", tool_call_id="c", session_id="sid")
    entry = registered._STASH.pop("rid-1")
    assert entry.session_key == "sess"
    assert entry.platform == "telegram" and entry.source == ""
    assert entry.agent_tid == threading.get_ident()
    assert entry.cli_callback is cb


def test_on_post_evicts_and_hooks_never_raise(registered, monkeypatch):
    registered.on_pre(session_key="s", surface="transport:tldr", request_id="rid-2")
    assert "rid-2" in registered._STASH
    registered.on_post(request_id="rid-2", choice="once")
    assert "rid-2" not in registered._STASH

    def boom(*a, **k):
        raise ValueError("nope")

    monkeypatch.setattr(registered._redispatch, "hermes_session_env", boom)
    registered.on_pre(session_key="s", surface="transport:tldr", request_id="rid-3")  # must not raise
    registered.on_post(request_id=None)
    registered.on_post()
    assert "rid-3" not in registered._STASH


def test_ttl_uses_approval_timeout_plus_grace(registered, monkeypatch):
    seen = {}
    real_put = registered._STASH.put
    monkeypatch.setattr(registered._STASH, "put", lambda rid, e, ttl: (seen.update(ttl=ttl), real_put(rid, e, ttl)))
    monkeypatch.setattr(registered._redispatch, "hermes_approval_timeout_s", lambda: 120.0)
    registered.on_pre(session_key="s", surface="transport:tldr", request_id="rid-4")
    assert seen["ttl"] == 180.0


def test_finished_set_is_bounded_ttl_and_cleared(stash_mod):
    clock = Clock()
    st = stash_mod.Stash(clock=clock, max_finished=3)
    for i in range(5):
        st.mark_finished(f"f{i}", 100)
    assert not st.is_finished("f0") and not st.is_finished("f1")
    assert st.is_finished("f2") and st.is_finished("f4")
    clock.now += 101
    assert not st.is_finished("f4")  # TTL
    st.mark_finished("x", 100)
    st.clear()
    assert not st.is_finished("x")


def test_on_post_marks_finished_and_withdraws(registered, monkeypatch):
    calls = []
    monkeypatch.setattr(registered._redispatch, "_hermes_withdraw", lambda sk, rid, cause="": calls.append((sk, rid)))
    registered.on_pre(session_key="s", surface="transport:tldr", request_id="rid-9")
    registered.on_post(request_id="rid-9", session_key="s", choice="timeout")
    assert "rid-9" not in registered._STASH and registered._STASH.is_finished("rid-9")
    assert calls == [("s", "rid-9")]
    # withdraw failures are swallowed
    monkeypatch.setattr(registered._redispatch, "_hermes_withdraw", lambda *a, **k: 1 / 0)
    registered.on_post(request_id="rid-10", session_key="s")
    assert registered._STASH.is_finished("rid-10")


def test_on_pre_prefers_acting_for_tid(registered):
    from tools import interrupt
    token = interrupt.acting_for_tid.set(424242)
    try:
        registered.on_pre(session_key="s", surface="transport:tldr", request_id="rid-a")
    finally:
        interrupt.acting_for_tid.reset(token)
    assert registered._STASH.pop("rid-a").agent_tid == 424242
    registered.on_pre(session_key="s", surface="transport:tldr", request_id="rid-b")
    assert registered._STASH.pop("rid-b").agent_tid == threading.get_ident()
