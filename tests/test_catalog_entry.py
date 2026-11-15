"""Catalog entry: the in-repo template must describe the same release as plugin.yaml.

Why it exists: the catalog bump is part of every release. If the entry names another version,
other Hermes requirement or other hooks than the manifest, a release would ship with a stale
listing, so fail here (and in the Release workflow) instead.
"""

from __future__ import annotations

import re
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
CATALOG = PLUGIN_ROOT / "docs" / "catalog" / "approval-tldr.yaml"


def _load(path: Path) -> dict:
    import hermes_yaml as yaml
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_catalog_entry_matches_manifest():
    manifest, entry = _load(PLUGIN_ROOT / "plugin.yaml"), _load(CATALOG)
    assert str(entry["version"]) == str(manifest["version"])
    assert entry["requires_hermes"] == manifest["requires_hermes"]
    assert entry["name"] == manifest["name"]
    assert entry["maintainer"] == manifest["author"]
    assert entry["capabilities"]["provides_hooks"] == manifest["provides_hooks"]


def test_catalog_template_keeps_sha_placeholders():
    """A commit cannot contain its own SHA: the template stays a placeholder, receipts hold the pin."""
    entry = _load(CATALOG)
    assert entry["sha"] == "<FINAL_COMMIT_SHA>"
    for url in [entry["image"], *entry["screenshots"]]:
        assert "/<FINAL_COMMIT_SHA>/" in url


def test_current_release_receipts_pin_one_full_sha():
    version = str(_load(PLUGIN_ROOT / "plugin.yaml")["version"])
    pinned_path = CATALOG.parent / "receipts" / f"v{version}" / "approval-tldr.pinned.yaml"
    if not pinned_path.exists():  # added after the tag exists; the release PR itself cannot have it
        import pytest
        pytest.skip(f"no receipts for v{version} yet")
    pinned = _load(pinned_path)
    assert re.fullmatch(r"[0-9a-f]{40}", pinned["sha"])
    assert str(pinned["version"]) == version
    for url in [pinned["image"], *pinned["screenshots"]]:
        assert f"/{pinned['sha']}/" in url
    assert "FINAL_COMMIT_SHA" not in pinned_path.read_text(encoding="utf-8")
