"""Catalog entry: the in-repo template must describe the same release as plugin.yaml.

Why it exists: the catalog bump is part of every release. If the entry names another version,
other Hermes requirement or other hooks than the manifest, a release would ship with a stale
listing, so fail here (and in the Release workflow) instead.
"""

from __future__ import annotations

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
    """A commit cannot contain its own SHA: the template stays a placeholder, the release asset holds the pin."""
    entry = _load(CATALOG)
    assert entry["sha"] == "<FINAL_COMMIT_SHA>"
    for url in [entry["image"], *entry["screenshots"]]:
        assert "/<FINAL_COMMIT_SHA>/" in url


def _catalog_pin():
    import importlib.util
    spec = importlib.util.spec_from_file_location("catalog_pin", PLUGIN_ROOT / "scripts" / "catalog_pin.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_pinned_entry_is_generated_from_the_tree():
    """What the Release workflow attaches: every placeholder pinned, version taken from plugin.yaml."""
    import hermes_yaml as yaml
    sha = "a" * 40
    text = _catalog_pin().pin(PLUGIN_ROOT, sha)
    assert "FINAL_COMMIT_SHA" not in text and not text.startswith("#")
    pinned, manifest = yaml.safe_load(text), _load(PLUGIN_ROOT / "plugin.yaml")
    assert pinned["sha"] == sha
    assert str(pinned["version"]) == str(manifest["version"])
    assert pinned["requires_hermes"] == manifest["requires_hermes"]
    for url in [pinned["image"], *pinned["screenshots"]]:
        assert f"/{sha}/" in url


def test_pin_takes_version_from_manifest_and_rejects_bad_input(tmp_path):
    import pytest
    pin = _catalog_pin().pin
    (tmp_path / "docs" / "catalog").mkdir(parents=True)
    (tmp_path / "plugin.yaml").write_text('name: x\nversion: 9.8.7\nrequires_hermes: ">=1.2.3"\n', encoding="utf-8")
    template = tmp_path / "docs" / "catalog" / "approval-tldr.yaml"
    template.write_text('# draft\nsha: <FINAL_COMMIT_SHA>\nversion: "1.0.0"\nrequires_hermes: ">=0.1.0"\n', encoding="utf-8")
    assert pin(tmp_path, "b" * 40) == f'sha: {"b" * 40}\nversion: "9.8.7"\nrequires_hermes: ">=1.2.3"\n'
    with pytest.raises(ValueError, match="40 lowercase hex"):
        pin(tmp_path, "v1.0.0")
    template.write_text(template.read_text(encoding="utf-8")
                        + "image: https://raw.githubusercontent.com/thebergerking91/hermes-approval-tldr/"
                          "<FINAL_COMMIT_SHA>/docs/missing.png\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing from the tree"):
        pin(tmp_path, "b" * 40)
