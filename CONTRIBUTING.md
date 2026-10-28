# Contributing

Thanks for looking. This is a small, security-sensitive plugin, so the bar for changes is
deliberately high and the process is deliberately boring.

## Before you open a PR

- Read `AGENTS.md` (layout, conventions, pitfalls) and `DESIGN.md` §4.6–4.7 (the binding
  contract: Hermes keeps all authority; the plugin only changes displayed strings and relays a
  human's choice, clamped to what Hermes offered). A PR that moves authority into the plugin, adds
  any auto-approve path, or patches Hermes code at runtime will be declined, however clean.
- Open an issue first for anything beyond a bug fix or a docs touch, so the design is agreed
  before the code exists.
- Run the gates locally (see `AGENTS.md` → *Test, validate, check*): the test suite, the seam
  check, `hermes plugins validate .` and `hermes plugins doctor . --ci` must all pass.

## Pull requests

- Branch from `main`; one topic per PR; squash merge only.
- `main` is protected by a ruleset: no direct pushes, the `test` CI job must pass, review
  threads must be resolved. Fork PRs do not run CI until the maintainer approves the run — this
  is intentional, please don't ask for it to be relaxed.
- Commit messages: `type: subject` (`feat:`, `fix:`, `docs:`, `ci:`, `test:`), body explains
  *why*.
- Behaviour change → entry in `CHANGELOG.md` under *Unreleased*; user-visible → `README.md`
  (written for non-programmers, short sentences).
- New dependency on a Hermes-internal function → adapter in `tldr/redispatch.py` **and** a row in
  `scripts/seam_check.py` **and** the seam list in `docs/ARCHITECTURE.md`. The plugin is
  stdlib-only; do not add Python packages.
- Never commit binaries, bytecode, or anything a reviewer cannot read as source (the Hermes
  plugin catalog refuses them, and CI checks).
- Every action in `.github/workflows` is pinned to a full commit SHA. Do not use
  `pull_request_target`, and never interpolate `${{ github.event.* }}` into a `run:` line.

## Attribution

Public attribution in this repository is the GitHub handle `thebergerking91` only. Do not add a
personal name or e-mail anywhere (files, commit trailers, release notes).

## Security issues

Not in the issue tracker — see `SECURITY.md`.

## Releasing (maintainer)

1. In one PR: bump `version:` in `plugin.yaml`, move the *Unreleased* notes in `CHANGELOG.md`
   under `## [X.Y.Z] - YYYY-MM-DD`, and merge.
2. Tag the merge commit: `git tag -a vX.Y.Z <sha> -m "vX.Y.Z" && git push origin vX.Y.Z`. The
   `Release` workflow verifies the tag matches `plugin.yaml` and the CHANGELOG, then publishes a
   GitHub Release whose first line is the **catalog pin** (the full 40-character SHA).
3. Let the tag-triggered workflow be the **only release creator**. Do not run `gh release create`
   alongside it. Wait for the Release job to succeed, verify the published tag resolves to the
   intended commit, then upload any validation logs or pinned catalog YAML with `gh release upload`.
   Reruns verify an existing stable release and leave its notes/assets unchanged. Auth/network
   errors and mismatched targets are failures, not reasons to create or overwrite a release.
   Verify test CI, canary and Release independently; a published release alone does not prove
   all three jobs succeeded. Never move an existing release tag to fix an automation failure.
4. After explicit submission approval, open a catalog PR (or SHA-bump PR for an existing listing)
   on `NousResearch/hermes-agent` editing
   `plugin-catalog/approval-tldr.yaml` (`sha:` and `version:`), linking the release.
   Users receive the update through `hermes plugins update approval-tldr` once that PR merges.
   The tag is for people; the SHA is what installs.
5. Revalidate the exact proposed SHA and update every SHA-pinned image URL when selecting a new
   candidate. Evidence for an older release is historical, not validation of the new tree.
