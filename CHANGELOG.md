# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- Newer Hermes (main after v0.23.1, upstream commit `b73018f424`) added an optional `identity` keyword to the internal wait function the plugin re-dispatches through. The plugin already worked there, but the seam check and one pinned-signature test flagged the new shape (#18). Both now accept the old and the new signature.

### Changed
- On Hermes versions that have the new keyword, the plugin tells the host which command a card is about. Identical commands raised at the same time now share one card, even on Desktop where each card carries its own AI summary. Different commands still get separate cards. Older Hermes is unchanged.

## [1.0.2] - 2026-11-14

### Changed
- Newer Hermes (main after v0.23.2-rc.7, upstream commit `18a2118b4f`) only lets a plugin task follow a built-in auxiliary slot's model when the operator grants `plugins.entries.approval-tldr.llm.allow_task_override`. Without that grant, summaries no longer follow `auxiliary.approval`: they run on your main model (still at low reasoning effort, still with the approval slot's timeout). The plugin code is unchanged and works either way; README explains the grant and the alternative of pinning `auxiliary.approval_summary.*`.

### Tests
- Route tests now set the grant when they check inheritance, and cover the ungranted path (skipped on Hermes versions without the gate). Fixes the `main` upstream-canary break (#15).

### Unchanged
- Plugin runtime is identical to v1.0.1; no internal Hermes seam moved, so `requires_hermes` stays `>=0.22.2`.
- `docs/catalog/approval-tldr.yaml` still pins v1.0.0; a catalog SHA bump is a separate, explicitly approved step.

## [1.0.1] - 2026-11-06

### Fixed
- Summaries no longer time out because they inherit high reasoning effort from the smart-approval model. The `approval_summary` task still follows `auxiliary.approval`, but registers `reasoning_effort: low` as its default; a user's own `auxiliary.approval_summary` settings still win.
- Default `llm_timeout_s` raised from 10 to 20 seconds, and the summary now gets at most half the time left before the host's approval deadline, so a slow model cannot eat the time to answer.
- Logs now record how long each summary took (`answered in`, `failed after`), and the timeout warning names the two settings that fix it. README documents choosing the summary model and that the CLI's "not a recognized config key" warning for `auxiliary.approval_summary` is harmless.
- Reconcile catalog checklists with the published v1.0.0 evidence, distinguishing completed validation from unresolved admission review.
- Make release creation safe to rerun, with exact remote tag verification and explicit failures for authentication, network and target mismatches. Document the tag-triggered workflow as the sole release creator.

### Unchanged
- Approval binding, allowed-choice enforcement, deadlines, replay protection, redispatch and the placeholder path. No new settings.
- `docs/catalog/approval-tldr.yaml` still pins v1.0.0; a catalog SHA bump is a separate, explicitly approved step.

## [1.0.0] - 2026-10-27

### Added
- Catalog submission documentation, explicit internal-API disclosures and a 1200×600 Baoyu-generated banner with production records.

### Unchanged
- Python runtime is identical to v0.1.1: native cross-surface approval prompts, summary-first Desktop layout, and the thread-context repair. No separate approval pane or rerouting.
- Catalog admission remains subject to maintainer review; publication is not submission or endorsement.

## [0.1.1] - 2026-10-27

### Fixed
- Preserve profile and credential context across the host transport worker and the summary worker, fixing `UnscopedSecretError` and unavailable AI summaries on current Hermes.
- Keep the existing native approval surfaces and summary-first Desktop layout unchanged. No separate Desktop pane or approval UI is introduced.

### Tests
- Release verification recorded 162 tests passing, including context propagation and concurrent-request isolation. A human-confirmed live Desktop native approval test showed the AI summary above the command and denial prevented execution; this is not a claim of live verification on every surface. The v1 packaging adds a real cropped native Desktop screenshot; the displayed command lies below its visible scroll boundary.

## [0.1.0] - 2026-10-27

### Added
- Repository hardening for catalog submission: SHA-pinned actions, a pull-request CI gate, a tag-triggered release workflow, Dependabot, CODEOWNERS, SECURITY.md and CONTRIBUTING.md.
- Opt-in approval transport `tldr` for Hermes Agent (requires Hermes >= 0.22.2, `plugins.isolation: in_process`).
- Plain-English summary paragraph (what it does, what it touches, reversibility, `Risk: LOW|MEDIUM|HIGH`) on shell-command and `execute_code` approval prompts.
- Per-surface display: Telegram/Discord/other gateway (summary in the description), Desktop (risk line, then the explanation, then the real command last, all inside the command box; workaround for upstream #133398), CLI (summary in the panel header).
- Auxiliary task `approval_summary` so the summary model can be chosen with `auxiliary.approval_summary.provider` / `.model`.
- Settings: `label`, `max_words`, `desktop_max_words`, `llm_timeout_s`, `desktop_inline`, `language`.
- Fallbacks: "AI summary unavailable" placeholder when the model fails or times out; Hermes' built-in prompt when the plugin fails (`transport_fallback: builtin`).
- Safety: prompt-injection-hardened summarizer, output sanitizing, choice clamped to the choices Hermes offered, definite deny on any non-answer, `/stop` propagation.
- Documentation: README, `docs/ARCHITECTURE.md`, MIT license.
- Upstream canary: `scripts/seam_check.py` plus a daily GitHub Actions workflow that tests the plugin against hermes-agent `main` and the newest release tag and opens/closes an `upstream-canary` issue when an internal seam drifts.

### Security
Fixes from the security review, all before the first release:
- Comment stripper word-boundary rule: a `#` starts a comment only at word start and never when escaped, so `a#b`, `$#` and `\#` are not mistaken for comments; the model is told comments were removed.
- Random fence tag: the command is wrapped in a randomly named tag, so a hostile command cannot close the wrapper and inject instructions.
- Slash-command neutralisation: `/approve`, `/deny`, `/yolo` and similar are defused anywhere in the summary, not only on their own line.
- Desktop command-first layout (setting `desktop_max_words`, default 60): originally risk line, exact command, then explanation, so the command was never pushed out of view of the ~7-line box. Amended: the layout is now verdict → explanation → command (summary-first, user's choice). A long explanation can push the command below the fold; `desktop_max_words` keeps it short.
- Deadline discipline: `present()` checks `/stop` and the host's finished-set after the LLM call and does not dispatch if the host already decided; the inner wait is withdrawn 5 s before the host deadline; the plugin's own card is withdrawn as soon as Hermes has a decision.
- Escaped-length Telegram budget: the 480-character limit is measured after HTML escaping, so the real message cannot exceed Telegram's cap.
- Documentation corrected to the real Telegram card order (summary inside "Why it was flagged") and to state the fallback caveats honestly (second prompt after a timeout, "denied" reported on no answer, oldest-first answering on Telegram).
- Divider defusing: runs of box-drawing/dash characters in the model's text are collapsed so the summary cannot impersonate the `── command ──` line above the real command on Desktop.

[1.0.2]: https://github.com/thebergerking91/hermes-approval-tldr/compare/v1.0.1...v1.0.2
[1.0.1]: https://github.com/thebergerking91/hermes-approval-tldr/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/thebergerking91/hermes-approval-tldr/compare/v0.1.1...v1.0.0
[0.1.1]: https://github.com/thebergerking91/hermes-approval-tldr/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/thebergerking91/hermes-approval-tldr/releases/tag/v0.1.0
