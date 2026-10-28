#!/usr/bin/env python3
"""Create a stable release, or safely accept an already existing one."""
import json
import os
import re
import subprocess
import sys


def run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, text=True, capture_output=True, check=False)


def api(repo: str, endpoint: str) -> subprocess.CompletedProcess[str]:
    return run(["gh", "api", "--method", "GET", f"repos/{repo}/{endpoint}"])


def fail(message: str) -> int:
    print(f"::error::{message}", file=sys.stderr)
    return 1


def publish(repo: str, tag: str, github_sha: str, notes: str) -> int:
    if not re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", tag):
        return fail("Invalid stable release tag")
    if not re.fullmatch(r"[0-9a-fA-F]{40}", github_sha):
        return fail("Invalid GITHUB_SHA")
    resolved = run(["git", "rev-parse", "--verify", f"{github_sha}^{{commit}}"])
    if resolved.returncode:
        return fail(f"Cannot resolve event commit: {resolved.stderr.strip()}")
    expected = resolved.stdout.strip()
    if not re.fullmatch(r"[0-9a-f]{40}", expected):
        return fail("Invalid resolved event commit")

    # GitHub's ref API returns the tag object for annotated tags, not its commit.
    response = api(repo, f"git/ref/tags/{tag}")
    if response.returncode:
        return fail(f"Cannot read remote tag: {response.stderr.strip()}")
    try:
        obj = json.loads(response.stdout)["object"]
        for _ in range(16):
            kind, sha = obj["type"], obj["sha"]
            if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha):
                return fail("Invalid remote tag object SHA")
            if kind == "commit":
                break
            if kind != "tag":
                return fail("Remote tag does not resolve to a commit")
            response = api(repo, f"git/tags/{sha}")
            if response.returncode:
                return fail(f"Cannot peel remote tag: {response.stderr.strip()}")
            obj = json.loads(response.stdout)["object"]
        else:
            return fail("Remote tag nesting exceeds limit")
    except (ValueError, KeyError, TypeError):
        return fail("Invalid remote tag API response")
    if sha != expected:
        return fail(f"Remote tag resolves to {sha}, not event commit {expected}")

    response = api(repo, f"releases/tags/{tag}")
    if response.returncode:
        # gh reports API failures as 'gh: ... (HTTP NNN)'. Never treat other
        # failures (including auth, rate limits, or network errors) as absence.
        if not re.search(r"\(HTTP 404\)\s*$", response.stderr):
            return fail(f"Cannot look up release: {response.stderr.strip()}")
        created = run(["gh", "release", "create", tag, "--repo", repo,
                       "--title", f"approval-tldr {tag}", "--notes-file", notes,
                       "--verify-tag"])
        if created.returncode:
            return fail(f"Release creation failed: {created.stderr.strip()}")
        print(created.stdout.strip())
        response = api(repo, f"releases/tags/{tag}")
        if response.returncode:
            return fail(f"Cannot verify created release: {response.stderr.strip()}")
    try:
        existing = json.loads(response.stdout)
        if (existing["tag_name"] != tag or existing["draft"] is not False
                or existing["prerelease"] is not False):
            return fail("Existing release tag or stable publication state does not match")
    except (ValueError, KeyError, TypeError):
        return fail("Invalid release API response")
    print(f"Existing stable release {tag} matches the remote event commit; leaving it unchanged.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(publish(os.environ["GITHUB_REPOSITORY"], os.environ["TAG"],
                         os.environ["GITHUB_SHA"], os.path.join(os.environ["RUNNER_TEMP"], "release.md")))
    except (KeyError, OSError) as exc:
        sys.exit(fail(f"Release helper failed: {exc}"))
