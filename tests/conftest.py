"""Shared fixtures: scratch HERMES_HOME and the plugin loaded the way Hermes loads it.

These are out-of-tree tests, so Hermes' own conftest does not sandbox HERMES_HOME for us; the
autouse fixture below does, and nothing here may ever write to the real ~/.hermes.
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import support  # noqa: E402  (sandboxes HERMES_HOME at import, before any Hermes module loads)
from support import FakeCtx, FakeLlm, load_plugin  # noqa: E402,F401


@pytest.fixture(autouse=True)
def _scratch_hermes_home(tmp_path, monkeypatch):
    home = tmp_path / "hermes_home"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    for name in ("HERMES_SESSION_PLATFORM", "HERMES_SESSION_SOURCE", "HERMES_SESSION_KEY"):
        monkeypatch.delenv(name, raising=False)
    yield home
    assert Path(os.environ["HERMES_HOME"]) == home


@pytest.fixture
def plugin():
    return load_plugin()


@pytest.fixture
def ctx():
    return FakeCtx()


@pytest.fixture
def registered(plugin, ctx):
    """The plugin module after register(fake_ctx) — same import path Hermes uses."""
    plugin.register(ctx)
    plugin._STASH.clear()
    return plugin


def _sub(plugin, name: str):
    return importlib.import_module(f"{plugin.__name__}.tldr.{name}")


@pytest.fixture
def stash_mod(plugin):
    return _sub(plugin, "stash")


@pytest.fixture
def summarize_mod(plugin):
    return _sub(plugin, "summarize")


@pytest.fixture
def compose_mod(plugin):
    return _sub(plugin, "compose")


@pytest.fixture
def redispatch_mod(plugin):
    return _sub(plugin, "redispatch")
