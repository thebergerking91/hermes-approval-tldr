# Catalog admission checklist — v1.0.0 draft

Source for **every numbered rule**: [canonical admission policy, rules 1–18](https://github.com/NousResearch/hermes-agent/blob/main/plugin-catalog/README.md#admission-policy); [submission guide](https://hermes-agent.nousresearch.com/docs/developer-guide/plugins/catalog-submission). Local links cite this native v0.1.1 tree. Source assessments are not acceptance or final-pin validation.

| Rule | Evidence and actual status |
|---|---|
| 1 Human merge | **Pending:** owner-submitted one-file PR, CI and maintainer review/merge; [submission](SUBMISSION.md). |
| 2 Full SHA | **Pending:** fill the 40-hex SHA of the final public packaging commit **after that commit**, then verify pinned tree and image. A tag alone is not a pin. |
| 3 No self-update | **Source assessment:** [entrypoint](../../__init__.py), [runtime](../../tldr/) have no self-updater; final-pin scan pending. |
| 4 SHA updates | **Process pending:** future updates need separately reviewed SHA-bump PRs. |
| 5 Owner submission | **Pending:** owner [@thebergerking91](https://github.com/thebergerking91) submits. |
| 6 Capabilities | **Source assessment:** [manifest](../../plugin.yaml) and [entrypoint](../../__init__.py) register two approval hooks; [draft](approval-tldr.yaml) mirrors them. Validate final pin. |
| 7 Install scanner | **Pending:** final-pin `hermes plugins validate ... --install-deps`; inspect caution warnings and resolve failures. |
| 8 Desktop SDK | **Not applicable to renderer plugin:** no `desktop/plugin.js`; native host card used. [Architecture](../ARCHITECTURE.md). |
| 9 No core override; public surfaces | **Maintainer decision required:** release research reported zero override findings and private-import warnings (11 runtime and 3 seam-check sites), not a final-pin validator run. Public-only policy wording is real; internal calls and state effects need review. [Architecture](../ARCHITECTURE.md#internal-hermes-seams), [review](SUBMISSION.md#rule-9-review). Warnings are not automatic rejection or acceptance. |
| 10 Dependencies | **Source assessment:** [manifest](../../plugin.yaml) declares no Python dependencies; verify final-pin resolution. |
| 11 Credentials | **Source assessment:** native runtime uses `ctx.llm`, no direct credential-store reads; session markers are non-secret. Host/provider access is separate. [Disclosure](../../README.md#disclosure), [adapter](../../tldr/redispatch.py). Review pending. |
| 12 Approvals | **Source assessment:** offered choices clamped, no answer denies, delivery failure raises for configured fallback; [adapter](../../tldr/redispatch.py), [tests](../../tests/). No claim of all consent gates or live surfaces. Review pending. |
| 13 Risk disclosure | **Drafted, review pending:** [README](../../README.md#disclosure), [submission](SUBMISSION.md#draft-pr-description). |
| 14 Metadata | **Source assessment, final pin pending:** [manifest](../../plugin.yaml) and [draft](approval-tldr.yaml) both say 1.0.0 and `>=0.22.2`; validate compatibility. |
| 15 Bundled-plugin forks/skins | **Source assessment:** separate approval transport, not a bundled-plugin skin; reviewer decides. [README](../../README.md). |
| 16 One listing per lineage | **Review pending:** original project is not represented as a fork; verify lineage and listings. [Repository](https://github.com/thebergerking91/hermes-approval-tldr). |
| 17 Scannable payloads | **Final-pin scan pending:** verify the committed tree and scanner result, not just extensions. [Policy](https://github.com/NousResearch/hermes-agent/blob/main/plugin-catalog/README.md#admission-policy). |
| 18 Password managers | **Not applicable:** no login backend registration in [entrypoint](../../__init__.py). |

Release evidence in [CHANGELOG](../../CHANGELOG.md): 162 tests and a human-confirmed live Desktop approval; this packaging round has not rerun that evidence or captured screenshots. It does not establish live testing of every surface. Final-pin validation, artwork, screenshots, public commit and maintainer review remain open.
