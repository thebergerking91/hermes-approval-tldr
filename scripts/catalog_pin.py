#!/usr/bin/env python3
"""Print the catalog entry for one exact commit: the in-repo template with every placeholder pinned.

Why it exists: a commit cannot contain its own SHA, so docs/catalog/approval-tldr.yaml carries
`<FINAL_COMMIT_SHA>` placeholders. The Release workflow runs this against the tagged tree and
attaches the result to the GitHub release, so no hand-edited copy is ever needed. `version` and
`requires_hermes` are taken from that tree's plugin.yaml, which is what the commit really ships.

Dev/CI only: nothing in the plugin imports this file. Stdlib only.

Usage:  python scripts/catalog_pin.py /path/to/plugin/checkout <40-char-commit-sha> > approval-tldr.yaml
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

PLACEHOLDER = "<FINAL_COMMIT_SHA>"
RAW_PREFIX = "https://raw.githubusercontent.com/thebergerking91/hermes-approval-tldr/"


def _manifest_value(manifest: str, key: str) -> str:
    match = re.search(rf'^{key}:[ \t]*"?([^"\n]+?)"?[ \t]*$', manifest, flags=re.MULTILINE)
    if not match:
        raise ValueError(f"plugin.yaml has no top-level {key!r}")
    return match.group(1)


def pin(root: Path, sha: str) -> str:
    """Return the pinned entry text, or raise ValueError when the tree cannot back it."""
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("commit SHA must be 40 lowercase hex characters")
    template = (root / "docs" / "catalog" / "approval-tldr.yaml").read_text(encoding="utf-8")
    manifest = (root / "plugin.yaml").read_text(encoding="utf-8")
    if PLACEHOLDER not in template:
        raise ValueError("catalog template has no placeholder to pin")

    lines = [line for line in template.splitlines() if not line.startswith("#")]
    text = "\n".join(lines).strip("\n").replace(PLACEHOLDER, sha) + "\n"
    for key in ("version", "requires_hermes"):
        value = _manifest_value(manifest, key)
        text, count = re.subn(rf'^{key}:.*$', f'{key}: "{value}"', text, flags=re.MULTILINE)
        if count != 1:
            raise ValueError(f"catalog template must have exactly one top-level {key!r}")

    # Every pinned raw URL must point at a file that exists in this very tree.
    for path in re.findall(re.escape(RAW_PREFIX + sha) + r"/(\S+)", text):
        if not (root / path).is_file():
            raise ValueError(f"pinned URL points at a file missing from the tree: {path}")
    return text


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print((__doc__ or "").strip().splitlines()[-1], file=sys.stderr)
        return 2
    try:
        sys.stdout.write(pin(Path(argv[1]), argv[2]))
    except (OSError, ValueError) as exc:
        print(f"::error::catalog_pin: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
