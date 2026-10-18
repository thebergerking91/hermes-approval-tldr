#!/usr/bin/env python3
"""Upstream canary: verify every internal Hermes seam approval-tldr relies on still exists unchanged.

Why it exists: the plugin re-dispatches approval prompts through a handful of underscore-prefixed
Hermes functions (see docs/ARCHITECTURE.md). Upstream may rename or re-shape them in any release.
This script imports each one against a given hermes-agent checkout and compares its call signature
with the one the plugin was written against. It prints a human-readable report and exits non-zero
on any drift, so CI can open an issue BEFORE the user runs `hermes update`.

Usage:  PYTHONPATH=/path/to/hermes-agent python scripts/seam_check.py [--json out.json]
"""

from __future__ import annotations

import argparse
import importlib
import inspect
import json
import sys
from typing import Any

# (module, attribute, expected signature or None for non-callables, kind)
# Signatures are inspect.signature() strings taken from Hermes v0.22.2 (2026.9.24).
SEAMS: list[tuple[str, str, str | None]] = [
    ("tools.approval", "_gateway_notify_cb", "(session_key: str)"),
    ("tools.approval", "withdraw_gateway_approval", "(session_key: str, request_id: str, cause: str) -> bool"),
    ("tools.approval", "resolve_gateway_approval", None),  # used only by tests; presence check
    ("tools.approval_gateway_wait", "_await_gateway_decision",
     "(session_key: str, notify_cb, approval_data: dict, *, surface: str = 'gateway') -> dict"),
    ("tools.approval_prompt", "prompt_dangerous_approval",
     "(command: str, description: str, timeout_seconds: int | None = None, allow_permanent: bool = True, "
     "approval_callback=None, *, allow_session: bool = True, smart_denied: bool = False, "
     "title: str | None = None) -> str"),
    ("tools.terminal_tool", "_get_approval_callback", "()"),
    ("tools.interrupt", "is_interrupted", "() -> bool"),
    ("tools.interrupt", "acting_for_tid", None),  # contextvars.ContextVar
    ("gateway.session_context", "get_session_env", None),  # (name, default=...) — checked loosely below
    ("tools.approval_context", "_get_approval_timeout", None),
    ("agent.plugin_llm", "PluginLlmTrustError", None),
    ("hermes_cli.approval_transport", "ApprovalRequest", None),
    ("hermes_cli.approval_transport", "invoke_approval_transport", None),
]

# Dataclass fields the plugin reads off ApprovalRequest.
REQUEST_FIELDS = {"request_id", "digest", "command", "description", "pattern_key", "pattern_keys",
                  "surface", "timeout_seconds", "allowed_choices"}
# Hook kwargs the plugin reads in pre_approval_request (grep'd from tools/approval_prompt.py).
HOOK_KWARGS = {"command", "description", "pattern_key", "pattern_keys", "session_key", "surface",
               "request_id", "request_digest"}


def _sig(obj: Any) -> str | None:
    try:
        return str(inspect.signature(obj))
    except (TypeError, ValueError):
        return None


def check() -> dict:
    results: list[dict] = []
    ok = True
    for module, attr, expected in SEAMS:
        row: dict[str, Any] = {"seam": f"{module}.{attr}", "status": "ok"}
        try:
            mod = importlib.import_module(module)
        except Exception as exc:  # noqa: BLE001
            row.update(status="MISSING_MODULE", detail=f"{type(exc).__name__}: {exc}")
            ok = False
            results.append(row)
            continue
        obj = getattr(mod, attr, None)
        if obj is None:
            row.update(status="MISSING_ATTR")
            ok = False
            results.append(row)
            continue
        actual = _sig(obj)
        row["signature"] = actual
        if expected is not None and actual != expected:
            row.update(status="SIGNATURE_CHANGED", expected=expected)
            ok = False
        results.append(row)

    # Structural checks that a bare signature compare cannot express.
    try:
        from hermes_cli.approval_transport import ApprovalRequest
        import dataclasses
        fields = {f.name for f in dataclasses.fields(ApprovalRequest)}
        missing = REQUEST_FIELDS - fields
        results.append({"seam": "ApprovalRequest fields", "status": "ok" if not missing else "FIELDS_MISSING",
                        "detail": sorted(missing) or sorted(fields)})
        ok = ok and not missing
    except Exception as exc:  # noqa: BLE001
        results.append({"seam": "ApprovalRequest fields", "status": "ERROR", "detail": str(exc)})
        ok = False

    try:
        import tools.approval_prompt as ap
        src = inspect.getsource(ap._present_with_selected_transport)
        missing = sorted(k for k in HOOK_KWARGS if k not in src)
        results.append({"seam": "pre_approval_request hook kwargs (transport path)",
                        "status": "ok" if not missing else "HOOK_KWARGS_MISSING", "detail": missing})
        ok = ok and not missing
    except Exception as exc:  # noqa: BLE001
        results.append({"seam": "pre_approval_request hook kwargs", "status": "ERROR", "detail": str(exc)})
        ok = False

    try:
        from gateway.session_context import get_session_env
        params = list(inspect.signature(get_session_env).parameters)
        good = len(params) >= 2
        results.append({"seam": "gateway.session_context.get_session_env arity",
                        "status": "ok" if good else "SIGNATURE_CHANGED", "detail": params})
        ok = ok and good
    except Exception as exc:  # noqa: BLE001
        results.append({"seam": "get_session_env arity", "status": "ERROR", "detail": str(exc)})
        ok = False

    return {"ok": ok, "results": results}


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--json", help="also write the report as JSON to this path")
    args = parser.parse_args()
    report = check()
    for row in report["results"]:
        mark = "✓" if row["status"] == "ok" else "✗"
        line = f"{mark} {row['seam']} — {row['status']}"
        if row["status"] != "ok":
            if "expected" in row:
                line += f"\n    expected {row['expected']}\n    actual   {row.get('signature')}"
            elif row.get("detail"):
                line += f"\n    {row['detail']}"
        print(line)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2)
    print("\nSEAM CHECK:", "OK" if report["ok"] else "DRIFT DETECTED")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
