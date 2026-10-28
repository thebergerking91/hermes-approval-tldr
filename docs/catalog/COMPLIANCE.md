# Catalog compliance checklist

Each Hermes plugin-catalog admission requirement, mapped to the file or setting that satisfies it.
Rules: `plugin-catalog/README.md` in NousResearch/hermes-agent (mirrored at
<https://hermes-agent.nousresearch.com/docs/developer-guide/plugins/catalog-submission>).
Re-check this table before every SHA-bump PR.

## Pre-submission requirements

| Requirement | Satisfied by | Status |
|---|---|---|
| Public `https://` repository | <https://github.com/thebergerking91/hermes-approval-tldr> | ✓ |
| Loadable plugin at the pinned commit: `plugin.yaml` + an entrypoint | `plugin.yaml` (manifest v2) + `__init__.py` `register(ctx)` | ✓ |
| Public surfaces only, no runtime patching | `__init__.py` uses `ctx.register_hook`, `ctx.register_approval_transport`, `ctx.register_auxiliary_task`, `ctx.llm`; internals are *called* only, in `tldr/redispatch.py` | ✓ (⚠ warning, see rule 9) |
| `hermes plugins validate <dir> --install-deps` passes | Run locally at the pin; output "Validation passed" | ✓ |

## Admission rules

| # | Rule | Satisfied by | Status |
|---|---|---|---|
| 1 | Human-merged gate | Process: one PR adding `plugin-catalog/approval-tldr.yaml` (`docs/catalog/approval-tldr.yaml` is the draft) | ✓ |
| 2 | Exact 40-char SHA pin | Tag `vX.Y.Z` on `main`; `release.yml` prints the pin on the Release's first line | pending tag |
| 3 | No self-updating code | No fetch/replace code anywhere in `__init__.py` / `tldr/`; updates only via SHA-bump PR (`CONTRIBUTING.md` → Releasing) | ✓ |
| 4 | SHA bumps are new PRs | Process; `CONTRIBUTING.md` → Releasing | ✓ |
| 5 | Owner submits | Repo owner = `maintainer: thebergerking91` = `plugin.yaml` `author` | ✓ |
| 6 | Declared capabilities match reality | `plugin.yaml` `provides_hooks: [pre_approval_request, post_approval_response]`; no tools/middleware/env; validate: "declared hooks — matches registrations" | ✓ |
| 7 | Install scanner | validate: "security scan — safe" | ✓ |
| 8 | Desktop plugins inside SDK | N/A — no `desktop/plugin.js` | n/a |
| 9 | No runtime overrides of core | validate: "no core override — no runtime rebinds". Warning on private imports in `tldr/redispatch.py` (8 seams, call-only, documented in `docs/ARCHITECTURE.md`; dev-only `scripts/seam_check.py` adds 3). Public-seam issue drafted in `SUBMISSION.md` | ✓ with disclosed ⚠ |
| 10 | Dependency policy | stdlib only; validate: "python dependencies — none declared" | ✓ |
| 11 | Credentials via Hermes only | LLM via `ctx.llm` (`__init__.py`, `tldr/summarize.py`); no `.env`/`auth.json`/keychain reads; only env read is non-secret `HERMES_SESSION_*` fallback (`tldr/redispatch.py`) | ✓ |
| 12 | Approvals and unattended runs respected | Deny on any non-answer (`map_gateway_decision`, `map_cli_choice`), `clamp()` to offered choices, `/stop` propagation, deadline −5 s withdraw (`tldr/redispatch.py`, `__init__.py`); unattended runs never reach transports | ✓ |
| 13 | Risky behaviour disclosed | `README.md` → Disclosure; `SECURITY.md`; catalog `description` disclosure clause; PR text in `SUBMISSION.md` | ✓ |
| 14 | Compatibility metadata truthful | `plugin.yaml` `requires_hermes: ">=0.22.2"` (SemVer, ≤ current v0.22.5; all seams verified present at v0.22.2); `version: 0.1.0` = `CHANGELOG.md` `[0.1.0] - 2026-10-27`; `release.yml` refuses a tag that disagrees | ✓ |
| 15 | No skins/forks of bundled plugins | Original; core declined the feature (#6959) | ✓ |
| 16 | One listing per lineage | No overlapping entry (`approval-ledger` observes, `ntfy-approval` routes) | ✓ |
| 17 | No unscannable payloads | `git ls-files` is text only; `.gitignore` excludes bytecode; `ci.yml` fails on tracked binaries | ✓ |
| 18 | Password managers from vendor | N/A — no `register_login_backend` | n/a |

## Repository hygiene (not rules, but reviewers look)

| Item | Where |
|---|---|
| License | `LICENSE` (MIT), `plugin.yaml` `license: MIT` |
| Changelog | `CHANGELOG.md` (Keep a Changelog, SemVer) |
| Tests + CI | `tests/` (160), `.github/workflows/ci.yml` (PR gate), `upstream-canary.yml` (daily drift check) |
| Release process | `.github/workflows/release.yml`, `CONTRIBUTING.md` → Releasing |
| Security policy | `SECURITY.md`, private vulnerability reporting enabled |
| Supply chain | All actions SHA-pinned; `.github/dependabot.yml`; `sha_pinning_required` repo setting |
| Branch protection | Ruleset `protect-main` (PR + `test` check, squash only, no force-push); ruleset `protect-release-tags` (`v*` immutable) |
| Fork PRs | Workflow runs require maintainer approval for all external contributors |
| Attribution | GitHub handle only (`AGENTS.md`, `CONTRIBUTING.md`) |
