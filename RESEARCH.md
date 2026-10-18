# Research — Hermes approval prompts, plugin seams, prior art

Date: 2026-10-18. Hermes Agent v0.22.2 (2026.9.24), git install at `~/.hermes/hermes-agent`.
All file:line cites are against that checkout.

## 1. What an approval prompt is, today

- A shell command (`terminal`) or `execute_code` script matches a danger pattern
  (`tools/approval_detection.py`). The match yields a **static label** — e.g.
  `script execution via -e/-c flag`, `recursive delete` — stored in `description`.
  No LLM text is involved. (`tools/approval.py:1128-1171`, `:1174-1247`)
- In `approvals.mode: smart` an auxiliary LLM returns one word
  (APPROVE / DENY / ESCALATE) and **no rationale** (`tools/approval_smart.py:17-32`,
  `:123-140`). APPROVE skips the human entirely; DENY/ESCALATE shows the prompt.
- The human sees only `command` + `description`:
  - **CLI** panel: both, description capped ~10 wrapped rows (`hermes_cli/cli_tui_mixin.py:188-268`).
  - **Ink TUI**: both (`ui-tui/src/components/prompts.tsx:111-131`).
  - **Telegram**: fenced command, then `Why it was flagged: {description}` capped at 500 chars,
    buttons Allow Once / Session / Always / Deny (`plugins/platforms/telegram/adapter.py:4212-4241`).
  - **Discord**: same, description capped at 300 chars (`plugins/platforms/discord/adapter.py:5739`).
  - **Desktop app**: **command only**. `description` is rendered solely inside the
    "Always allow" confirm dialog (`apps/desktop/src/components/assistant-ui/tool/approval.tsx:285-295`,
    `:395`). This is upstream bug #133398 (P2, open).
- Payload to Desktop/TUI: `{command, description, allow_permanent, allow_session, smart_denied}`
  (`tools/approval.py:833-843`); contract allows extra keys (`tui_gateway/contracts/server_requests.py:169-183`)
  but the Desktop handler reads only the known ones
  (`apps/desktop/src/app/session/hooks/use-message-stream/gateway-event/server-requests.ts:381-404`).

## 2. Plugin seams available to an out-of-tree plugin

| Seam | What it gives | Limits |
|---|---|---|
| `ctx.register_approval_transport(name, present_fn)` (`hermes_cli/plugins.py:430`) | Replaces the human prompt for shell + execute_code gates when `security.approval.transport: <name>` is set. Receives frozen `ApprovalRequest` (`hermes_cli/approval_transport.py:40-53`): `command`, `description` (both force-redacted), `pattern_key(s)`, `surface` (`cli`/`gateway`), `timeout_seconds`, `allowed_choices`. Must return `request.respond(choice)`. | No `session_key` field. Runs on a daemon worker thread (`approval_transport.py:124-128`). Any exception/timeout = deny unless `security.approval.transport_fallback: builtin`. Only `_COMMAND_GATE` and `_EXECUTE_CODE_GATE` have `transport=True` (`tools/approval.py:689-722`); plugin-rule escalations, protected-file writes, memory saves, MCP consent do **not** reach a transport (#133946, #120859). Requires `plugins.isolation: in_process` (`plugin_isolation.py:41`). |
| `pre_approval_request` / `post_approval_response` hooks | Observer. For the transport path the pre-hook fires **on the agent thread, before** the transport, with `session_key`, `request_id`, `request_digest`, `surface="transport:<name>"` (`tools/approval_prompt.py:237-241`). | Returns ignored; cannot mutate the prompt. |
| `ctx.llm.complete(...)` (`agent/plugin_llm.py:446-496`) | Sync/async bounded LLM call. Default model = user's active main model; `task=<key>` uses `auxiliary.<key>` only for a task the plugin registered (`ctx.register_auxiliary_task`, `plugins.py:853`). | `provider=`/`model=` overrides need `plugins.entries.<id>.llm.allow_*_override`. Works under host isolation. |
| `pre_tool_call` hook | Can `block`, `approve` (escalate to human), or `modify` args. | Cannot reach the prompt's own fields. `approve` escalations bypass transports (#133946). |
| Desktop `desktop/plugin.js` | Panes, palette, composer slots, `host.request(rpc)`, `host.onEvent` (notifications only). | **Cannot** see or decorate the approval card: server requests do not flow to plugins; DOM access to `data-slot` is rejected by validate (`hermes_cli/plugin_validate_desktop.py:36-43`). |

### Re-entering the built-in surfaces from inside a transport (the trick we rely on)

- **Gateway (Telegram) and Desktop (tui_gateway)** both register a notify callback per session:
  Telegram → `run_turn_runner._approval_notify_sync` (`gateway/run_turn_runner.py:1455-1550`, registered `:1694`);
  Desktop → `_emit_approval_request` (`tui_gateway/server.py:818`, registered `:1055`).
  Both are reached through `tools.approval._gateway_notify_cb(session_key)` (`tools/approval.py:539-541`) and
  driven by `tools.approval_gateway_wait._await_gateway_decision(session_key, notify_cb, approval_data, surface="gateway")`
  (`tools/approval_gateway_wait.py:133`), which returns `{resolved, choice, reason, cancelled?, notify_failed?}`.
  Desktop sessions set `HERMES_GATEWAY_SESSION=1` so they take the **gateway** branch and the transport sees `surface="gateway"`
  (`tui_gateway/server.py:1391`; `tools/approval.py:815`).
- **CLI**: `tools.approval_prompt.prompt_dangerous_approval(command, description, allow_permanent=, allow_session=, approval_callback=)`
  (`tools/approval_prompt.py:20`) is importable and sits *below* the transport branch (no recursion). The prompt_toolkit callback
  is **thread-local** (`tools/terminal_tool.py:86`), so it must be captured on the agent thread (in `pre_approval_request`) and
  passed explicitly.
- Both are underscore/internal APIs. Breakage risk on upstream updates is real; the plugin must fail soft to `builtin` fallback.

## 3. Prior art on GitHub (NousResearch/hermes-agent) — searched 2026-10-18

Nothing merged; nothing in the plugin catalog does this.

| # | Title | State | Notes |
|---|---|---|---|
| [6959](https://github.com/NousResearch/hermes-agent/issues/6959) | Dangerous-command approvals should explain likely action and concrete risk in plain language | **Closed 2026-07-13 by maintainer** | Rationale: a second LLM call adds latency and "authoritative-sounding misexplanations" at the security boundary. This is the upstream position — makes an opt-in plugin the right vehicle. |
| [34625](https://github.com/NousResearch/hermes-agent/issues/34625) | Add plain-English semantic reasons to permission prompts | Open P3 | User tried skills/preferences; agent regressed 6× in 2 days. Same pain as this project. |
| [45290](https://github.com/NousResearch/hermes-agent/issues/45290) | Humanize dangerous command approval prompts via structured LLM explanation | Open P3 | Proposes purpose/scope/consequence/reversibility/risk fields; `approvals.show_humanized_explanation`. |
| [86084](https://github.com/NousResearch/hermes-agent/issues/86084) | Auxiliary-model summary and security review for execution approvals | Open P3 | Closest to our design: aux-model summary labeled AI-generated, shown next to unmodified command, secrets redacted, failure falls back. |
| [27604](https://github.com/NousResearch/hermes-agent/issues/27604) | Approval prompts should include the agent's contextual rationale (like Codex) | Open P3 | Agent-intent variant. PR #45700 open. |
| [113330](https://github.com/NousResearch/hermes-agent/issues/113330) | Approval cards show the matched pattern, not the agent's intent | Open P3 | Confirms observer hooks cannot add text to a card. |
| [123590](https://github.com/NousResearch/hermes-agent/issues/123590) | Explain the command inside the approval dialog | Open P3 (desktop) | Suggests deterministic parser alternative. |
| [133398](https://github.com/NousResearch/hermes-agent/issues/133398) | Desktop approval card still hides the flag reason for ordinary commands | Open **P2 bug** | Why the Desktop needs the command-box workaround. Fix PR #114339 open, unreviewed. |
| [135802](https://github.com/NousResearch/hermes-agent/issues/135802) | Smart approvals: infra failures indistinguishable from ESCALATE | Open P2 | Context: smart mode's guardian can silently fail → prompt storm. |

PRs attempting it (all **open, none merged**): #94853 / #75795 (model-supplied purpose/effect/risk fields on `terminal`),
#86096 (aux-model advisory in `tools/approval.py`), #135099 (guardian gives one-sentence reason, Desktop renders it),
#33945 / #46682 / #51397 / #34629 (deterministic plain-language expansions), #37652 (risk category banner), #45700 (agent rationale).

Catalog plugins touching approvals: `ntfy-approval` (phone push transport — proof the transport seam works in the wild),
`approval-ledger` (observer stats), `jev-approvals` (alternate guardian model). None summarize.

## 4. Testing facts

- Transport test pattern: `ApprovalRequest.create(...)` + `invoke_approval_transport(present, request, timeout_seconds=1)`
  (`tests/hermes_cli/test_approval_transport.py:31-109`). Scratch-home plugin load: `:443-510`.
- Fake aux LLM: patch `agent.auxiliary_client.call_llm` at source (`tests/tools/test_smart_approval_injection.py:84-102`).
- `hermes plugins validate <dir>` requires `name`, `version`, `description`; hooks registered must be declared in
  `provides_hooks` or validate fails (`hermes_cli/plugin_validate.py:416-433`). `register_approval_transport` is not checked by validate.
- Run one file: `scripts/run_tests.sh tests/.../test_x.py -q`.
