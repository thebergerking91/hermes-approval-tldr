"""Test support: plugin loader (same mechanics as Hermes' PluginManager) and fakes."""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import types
from dataclasses import dataclass, field
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
_HERMES_FALLBACK = Path.home() / ".hermes" / "hermes-agent"

# Sandbox before anything imports Hermes modules (some read HERMES_HOME at import time).
_BOOT_HOME = tempfile.mkdtemp(prefix="approval-tldr-boot-")
os.environ["HERMES_HOME"] = _BOOT_HOME
for _name in ("HERMES_SESSION_PLATFORM", "HERMES_SESSION_SOURCE", "HERMES_SESSION_KEY"):
    os.environ.pop(_name, None)
try:
    import tools  # noqa: F401
except ImportError:  # PYTHONPATH not set: fall back to the standard checkout location
    if _HERMES_FALLBACK.is_dir():
        sys.path.insert(0, str(_HERMES_FALLBACK))


def load_plugin(name: str = "hermes_plugins.approval_tldr_under_test") -> types.ModuleType:
    """Import the plugin root exactly like PluginManager._load_directory_module does."""
    ns = "hermes_plugins"
    if ns not in sys.modules:
        pkg = types.ModuleType(ns)
        pkg.__path__ = []  # type: ignore[attr-defined]
        pkg.__package__ = ns
        sys.modules[ns] = pkg
    for key in [k for k in sys.modules if k == name or k.startswith(name + ".")]:
        del sys.modules[key]
    init_file = PLUGIN_ROOT / "__init__.py"
    spec = importlib.util.spec_from_file_location(
        name, init_file, submodule_search_locations=[str(PLUGIN_ROOT)])
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    module.__package__ = name
    module.__path__ = [str(PLUGIN_ROOT)]  # type: ignore[attr-defined]
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@dataclass
class FakeLlmResult:
    text: str


class FakeLlm:
    """Stand-in for ctx.llm. ``behavior`` may be a str, an Exception, or a callable(**kw)."""

    def __init__(self, behavior="This lists files. Risk: LOW — read only.") -> None:
        self.behavior = behavior
        self.calls: list[dict] = []

    def complete(self, **kwargs):
        self.calls.append(kwargs)
        behavior = self.behavior
        if callable(behavior):
            behavior = behavior(**kwargs)
        if isinstance(behavior, BaseException):
            raise behavior
        return FakeLlmResult(text=behavior)


@dataclass
class FakeCtx:
    llm: FakeLlm = field(default_factory=FakeLlm)
    config: dict = field(default_factory=dict)
    hooks: list = field(default_factory=list)
    transports: dict = field(default_factory=dict)
    aux_tasks: list = field(default_factory=list)
    aux_error: Exception | None = None

    def get_config(self, key, default=None):
        return self.config.get(key, default)

    def register_hook(self, name, cb):
        self.hooks.append((name, cb))

    def register_approval_transport(self, name, fn):
        self.transports[name] = fn

    def register_auxiliary_task(self, key, **kwargs):
        if self.aux_error:
            raise self.aux_error
        self.aux_tasks.append((key, kwargs))


