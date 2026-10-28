# Catalog submission kit

Everything needed to list approval-tldr in the Hermes plugin catalog
(`NousResearch/hermes-agent/plugin-catalog/`). Rules:
<https://hermes-agent.nousresearch.com/docs/developer-guide/plugins/catalog-submission>.

## Checklist (in order)

1. **Release is tagged.** `v0.1.0` exists, the Release workflow published it, and the release
   notes' first line shows the catalog pin SHA. The SHA must be on `main`.
2. **Validate at that commit.** From a clean checkout of the pinned SHA:
   `hermes plugins validate /path/to/checkout --install-deps` → "Validation passed". The one ⚠
   (private core imports) is expected; see the PR text below.
3. **Open the seam issue first** (text in *Issue: public seam* below) on
   <https://github.com/NousResearch/hermes-agent/issues/new>. Note its number.
4. **Fork `NousResearch/hermes-agent`**, branch `catalog/approval-tldr`, add exactly one file
   `plugin-catalog/approval-tldr.yaml` (copy `approval-tldr.yaml` from this folder, fill `sha:`).
5. **Open the PR** with the description below (fill `<sha>` and `#<issue>`), attach the validate
   log and Desktop + Telegram screenshots. Wait for the "Plugin Catalog CI" job to go green.
6. Answer review. Rule 9 questions are the likely ones; the talking points are below.

Later updates: bump `plugin.yaml` version + CHANGELOG, tag, then a SHA-bump PR editing `sha:` and
`version:` in the same catalog file (see CONTRIBUTING.md → Releasing).

## PR title

`plugin-catalog: add approval-tldr (community, tools) @ <sha> — v0.1.0`

## PR description

**What it does.** Hermes asks non-programmers "Approve?" over a raw shell command. approval-tldr
is an opt-in approval transport. Once selected with `security.approval.transport: tldr`, it adds a
short plain-English paragraph to every dangerous-command and `execute_code` prompt: what the
command does, what it touches, whether it can be undone, and a `Risk: LOW|MEDIUM|HIGH` verdict.
The text is labelled "AI summary (may be wrong — read the command)". The real command and the
buttons are unchanged. Surfaces: gateway (Telegram/Discord — text goes in "Why it was flagged"),
Desktop (inside the command box; workaround for #133398), CLI (panel header). Related: #86084,
#45290. Core declined this feature in #6959, which is why it is an opt-in plugin.

**Hermes surfaces used.**
- Public: `ctx.register_approval_transport("tldr", present)`;
  `ctx.register_hook("pre_approval_request" | "post_approval_response")`;
  `ctx.llm.complete(task="approval_summary")`;
  `ctx.register_auxiliary_task("approval_summary", inherit_from="approval")`; `ctx.get_config`;
  `request.respond(choice)`; `agent.plugin_llm.PluginLlmTrustError`.
- Internal — **called, never patched** (`no core override` ✓; the private-imports ⚠ from
  validate lists them):
  `tools.approval._gateway_notify_cb`, `tools.approval_gateway_wait._await_gateway_decision`,
  `tools.approval.withdraw_gateway_approval`, `tools.approval_prompt.prompt_dangerous_approval`,
  `tools.terminal_tool._get_approval_callback`, `tools.interrupt.acting_for_tid` /
  `is_interrupted` (set and reset by token on the transport worker so `/stop` reaches it),
  `gateway.session_context.get_session_env`, `tools.approval_context._get_approval_timeout`.
  All live in one adapter file (`tldr/redispatch.py`); every failure raises so the host falls
  back to its own prompt; signatures are pinned by tests and `scripts/seam_check.py` (dev-only —
  it accounts for 3 of the 14 warning sites) and a daily CI canary runs them against `main` and
  the newest tag. Why they are needed: the public transport contract is "deliver to *your* UI";
  there is no public way to re-show Hermes' *own* card with amended text. Seam request:
  #<issue>. We will switch to the public seam the release it lands and delete the private path
  in a SHA-bump PR.

**Disclosures (rule 13).**
- Network: the command text and flag reason (Hermes-redacted, best-effort) go to the user's
  configured LLM provider through `ctx.llm`, which may be a third party. No other network.
- No credential reads (no env secrets, `.env` or `auth.json`), no file writes, no processes, no
  background services beyond Hermes' own transport worker and one bounded summary thread.
- Approval safety: never approves on its own. Timeout, `/stop`, withdrawn card or no answer all
  become deny. Choices are clamped to what the host offered. Inner wait ends 5 s before the host
  deadline. Cron and other unattended runs never reach the transport.
- The documented install steps set `security.approval.transport_fallback: builtin` (host-wide):
  a plugin failure shows the stock prompt, and after a timeout the user may be asked twice.
- Fragility: depends on the internal functions above.
- The AI text can be wrong and a hostile command could try to steer it (mitigations: random
  fence tag, comment stripping, slash-command and divider defusing). On Desktop the real command
  can sit below the fold of the ~7-line box (`desktop_max_words`, default 60).

**Validation:** `hermes plugins validate --install-deps` → "Validation passed" (log attached).
Screenshots: Desktop and Telegram attached. Maintainer: @thebergerking91 (repo owner).

## Rule 9 talking points (if asked)

1. The ⚠ is expected; each import is listed with its reason in `docs/ARCHITECTURE.md`.
2. Zero rebinds, no `setattr`, no `sys.modules`, no writes into core tables. The only core state
   touched goes through core's own APIs: `ContextVar.set()`/`reset(token)` on the worker's own
   context, and queue insert/remove via `_await_gateway_decision` / `withdraw_gateway_approval`.
3. The gap is real: the public transport API cannot reuse the host card. Issue #<issue> asks
   for the seam; we'd rather use it than keep the private path.
4. Offer: hold the listing until the seam lands if maintainers prefer.

## Issue: public seam

**Title:** Approval transports: public way to present the built-in prompt with amended display
text

**Problem.** `ctx.register_approval_transport` lets a plugin own *where* an approval is shown. A
plugin that only wants to change *what text* the human sees on the host's own surface
(explanation, translation, accessibility rewrite) has no public path. Today it must re-enter
`tools.approval._gateway_notify_cb`, `tools.approval_gateway_wait._await_gateway_decision`,
`tools.approval.withdraw_gateway_approval`, `tools.approval_prompt.prompt_dangerous_approval` and
`tools.terminal_tool._get_approval_callback`, propagate `/stop` by setting
`tools.interrupt.acting_for_tid` (the transport worker is not the agent thread), and read
`tools.approval_context._get_approval_timeout`. Concrete consumer: approval-tldr (catalog PR
#<pr>). `hermes plugins validate` passes with no rebinds but warns on these 8 internal imports.

**Proposal (any one would do):**
1. `request.present_builtin(description=None, command_display=None, timeout_s=None) -> choice`:
   shows the host's normal prompt on the request's own surface with amended display strings (the
   executed command unchanged), honours `/stop` and the host deadline, returns a clamped choice
   for `request.respond()`.
2. A transform hook `transform_approval_display(command, description, surface, ...) ->
   {description?, command_prefix?}` run before the built-in prompt; no transport needed.
3. Minimum: public `request.is_cancelled()` / `request.deadline`, plus `request.platform` /
   `request.source`, so plugins need not read session env on the agent thread.

**Safety.** Hermes keeps detection, hardline blocks, scopes, persistence and the final decision;
only display strings change. Plugins stop drifting into private queue internals and two plugins
can no longer collide on the queue.
