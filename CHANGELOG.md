# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- Reconcile catalog checklists with the published v1.0.0 evidence, distinguishing completed validation from unresolved admission review.
- Make release creation safe to rerun, with exact remote tag verification and explicit failures for authentication, network and target mismatches. Document the tag-triggered workflow as the sole release creator.

### Unchanged
- Plugin runtime, existing v1.0.0 tag and installed v0.1.1 remain unchanged. These maintenance changes are not a new release or a new catalog pin.

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

[1.0.0]: https://github.com/thebergerking91/hermes-approval-tldr/compare/v0.1.1...v1.0.0
[0.1.1]: https://github.com/thebergerking91/hermes-approval-tldr/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/thebergerking91/hermes-approval-tldr/releases/tag/v0.1.0
