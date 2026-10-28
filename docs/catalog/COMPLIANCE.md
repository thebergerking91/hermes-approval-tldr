# Catalog admission checklist — v1.0.0 evidence

Source for **every numbered rule**: [canonical admission policy, rules 1–18](https://github.com/NousResearch/hermes-agent/blob/main/plugin-catalog/README.md#admission-policy); [submission guide](https://hermes-agent.nousresearch.com/docs/developer-guide/plugins/catalog-submission). Evidence below is specifically for published v1.0.0 at `657a3b1c8eb62f8b0e518468a4a9818c2a0065bf`, whose runtime matches v0.1.1. Later documentation/automation changes do not inherit this exact-pin validation. Source assessments and passing checks are not maintainer acceptance.

Published receipts: [validator](https://github.com/thebergerking91/hermes-approval-tldr/releases/download/v1.0.0/v1.0.0-validation.txt), [doctor](https://github.com/thebergerking91/hermes-approval-tldr/releases/download/v1.0.0/v1.0.0-doctor.txt), [162 tests](https://github.com/thebergerking91/hermes-approval-tldr/releases/download/v1.0.0/v1.0.0-tests.txt), and [fully pinned entry](https://github.com/thebergerking91/hermes-approval-tldr/releases/download/v1.0.0/approval-tldr.yaml). The repository YAML remains an explicitly labeled template.

| Rule | Evidence and actual status |
|---|---|
| 1 Human merge | **Pending:** owner-submitted one-file PR, CI and maintainer review/merge; [submission](SUBMISSION.md). |
| 2 Full SHA | **Verified for v1.0.0:** release entry pins the full SHA above; code, banner and screenshot URLs were read back. Any replacement candidate requires a new pin and verification. |
| 3 No self-update | **Source assessment and scan passed at v1.0.0:** [entrypoint](../../__init__.py), [runtime](../../tldr/) have no self-updater. |
| 4 SHA updates | **Process pending:** future updates need separately reviewed SHA-bump PRs. |
| 5 Owner submission | **Pending:** owner [@thebergerking91](https://github.com/thebergerking91) submits. |
| 6 Capabilities | **Validated at v1.0.0:** manifest and registrations match; doctor reported two hooks and zero tools. |
| 7 Install scanner | **Passed at v1.0.0:** exact-pin `hermes plugins validate . --install-deps`; security scan safe. Private-import warnings remain disclosed, not waived. |
| 8 Desktop SDK | **Not applicable to renderer plugin:** no `desktop/plugin.js`; native host card used. [Architecture](../ARCHITECTURE.md). |
| 9 No core override; public surfaces | **Maintainer decision required:** exact-pin validation found zero overrides and private-import warnings (11 runtime and 3 seam-check sites). Public-only policy wording is real; internal calls and state effects need review. [Architecture](../ARCHITECTURE.md#internal-hermes-seams), [review](SUBMISSION.md#rule-9-review). Warnings are not automatic rejection or acceptance. |
| 10 Dependencies | **Validated at v1.0.0:** manifest declares no Python dependencies; full `--install-deps` validation passed. |
| 11 Credentials | **Source assessment:** native runtime uses `ctx.llm`, no direct credential-store reads; session markers are non-secret. Host/provider access is separate. [Disclosure](../../README.md#disclosure), [adapter](../../tldr/redispatch.py). Review pending. |
| 12 Approvals | **Source assessment:** offered choices clamped, no answer denies, delivery failure raises for configured fallback; [adapter](../../tldr/redispatch.py), [tests](../../tests/). No claim of all consent gates or live surfaces. Review pending. |
| 13 Risk disclosure | **Drafted, review pending:** [README](../../README.md#disclosure), [submission](SUBMISSION.md#draft-pr-description). |
| 14 Metadata | **Validated at v1.0.0:** manifest and published entry agree on 1.0.0 and `>=0.22.2`; CI and stable/main canary passed. |
| 15 Bundled-plugin forks/skins | **Source assessment:** separate approval transport, not a bundled-plugin skin; reviewer decides. [README](../../README.md). |
| 16 One listing per lineage | **Review pending:** original project is not represented as a fork; verify lineage and listings. [Repository](https://github.com/thebergerking91/hermes-approval-tldr). |
| 17 Scannable payloads | **Scan passed at v1.0.0:** official install scanner reported safe. [Policy](https://github.com/NousResearch/hermes-agent/blob/main/plugin-catalog/README.md#admission-policy). |
| 18 Password managers | **Not applicable:** no login backend registration in [entrypoint](../../__init__.py). |

The v1.0.0 packaging round reran 162 tests and exact-pin validation and published the 1200×600 banner and real Desktop screenshot. The screenshot shows the summary and controls, not the command below the scroll boundary; it does not prove live testing of every surface. CI and upstream canary passed. Separately, [release automation failed](https://github.com/thebergerking91/hermes-approval-tldr/actions/runs/40642523003) because manual publication had already created the release. The release exists; this failure is not a missing release or a successful automation run. Do not rewrite its tag to conceal it.

Still open: catalog PR creation (the attempted creation was refused), upstream catalog CI and maintainer review, especially rule 9. Revalidate any subsequently selected candidate; these receipts certify only the SHA above.
