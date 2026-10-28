"""Scope handoff regressions; sentinel only, no credential/provider access."""
import contextvars
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

from hermes_cli.approval_transport import invoke_approval_transport
from test_plugin_e2e import make_request, fire_pre

SUMMARY = "Lists files. Risk: LOW — read only."


def test_summary_thread_preserves_context_and_isolates_mutations(summarize_mod):
    scope = contextvars.ContextVar[object]("sentinel_scope", default=None)
    marker = object()
    seen = []

    class ScopedLlm:
        def complete(self, **kwargs):
            seen.append((scope.get(), threading.get_ident()))
            if scope.get() is not marker:
                raise RuntimeError("missing sentinel scope")
            scope.set(object())
            return SimpleNamespace(text=SUMMARY)

    def getter():
        assert scope.get() is marker
        return ScopedLlm()

    token = scope.set(marker)
    try:
        assert summarize_mod.summarize(getter, "ls", "listing", timeout_s=1) == SUMMARY
        assert seen[0][0] is marker
        assert seen[0][1] != threading.get_ident()
        assert scope.get() is marker
    finally:
        scope.reset(token)


def test_hook_transport_and_summary_preserve_distinct_request_contexts(registered, monkeypatch):
    scope = contextvars.ContextVar[object]("request_scope_sentinel", default=None)
    expected = {}
    seen = []
    shown = []

    class ScopedLlm:
        def complete(self, **kwargs):
            marker = scope.get()
            seen.append(marker)
            if marker not in expected.values():
                raise RuntimeError("missing request scope sentinel")
            return SimpleNamespace(text=SUMMARY)

    monkeypatch.setattr(registered, "_get_llm", lambda: ScopedLlm())

    def redispatch(request, entry, command, description, **kwargs):
        assert scope.get() is expected[request.request_id]
        shown.append(command + description)
        return "once"  # a fake human decision, not a provider call

    monkeypatch.setattr(registered._redispatch, "redispatch", redispatch)
    requests = [make_request(session_key="sentinel-a"), make_request(session_key="sentinel-b")]
    for request in requests:
        marker = object()
        expected[request.request_id] = marker
        token = scope.set(marker)
        try:
            fire_pre(registered, request)
        finally:
            scope.reset(token)
    assert scope.get() is None
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(invoke_approval_transport, registered.present, request,
                               timeout_seconds=3) for request in requests]
        results = [future.result(timeout=5) for future in futures]
    assert [(result.choice, result.failure) for result in results] == [("once", None)] * 2
    assert len(seen) == 2 and set(seen) == set(expected.values())
    assert len(shown) == 2 and all(SUMMARY in text for text in shown)
    assert scope.get() is None
    assert len(registered._STASH) == 0
