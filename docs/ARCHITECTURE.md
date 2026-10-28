# Architecture (maintainer notes)

Short technical companion to the README. Line numbers refer to Hermes Agent v0.22.2 and will drift. Re-verify them on every upstream bump.

## What the plugin is

An approval transport. When `security.approval.transport: tldr` is set, Hermes hands every shell-command and `execute_code` approval to `present(request)` on a host-managed worker thread instead of showing its own prompt. The plugin builds a summary with `ctx.llm`, re-shows the **built-in** prompt with the summary added to the display strings, waits for the human, and returns `request.respond(choice)`. Hermes keeps all authority: detection, smart-approval verdict, allowed scopes, persistence of "session"/"always", timeout, and the exact command executed.

## Sequence

```
agent thread                              plugin worker thread (host-managed, <= approvals.timeout)
------------                              ---------------------------------------------------------
tools.approval._human_decision
  > pre_approval_request hook ----------> on_pre(): stash[request_id] = {session_key, surface,
      (session_key, request_id,                      platform, cli_callback (thread-local, captured here),
       surface="transport:tldr")                     agent thread id}
  > invoke_approval_transport ----------> present(request):
      (frozen ApprovalRequest)              1. ctx = stash.pop(request_id)            (missing -> raise -> builtin fallback)
                                            2. summary = summarize(request)            (ctx.llm, hard timeout, injection-hardened,
                                                                                        failure -> placeholder text, never blocks)
                                            3. display = compose(surface/platform)      (Desktop: risk line, explanation, command inside command box;
                                                                                        Telegram/Discord/CLI: summary in description)
                                            4. choice = redispatch(display)             gateway -> tools.approval._gateway_notify_cb(session_key)
                                                                                                  + tools.approval_gateway_wait._await_gateway_decision
                                                                                        cli     -> tools.approval_prompt.prompt_dangerous_approval(
                                                                                                    ..., approval_callback=stashed cb)
                                            5. return request.respond(choice in allowed_choices)
  <---------------------------------------  ApprovalDecision (host validates id/digest/choice; persists session/always itself)
```

## Components

| Module | Job |
|---|---|
| `__init__.py` | `register(ctx)`: hooks, `register_approval_transport("tldr", present)`, `register_auxiliary_task("approval_summary")`. |
| `tldr/stash.py` | Bounded, thread-safe `request_id -> context` map. TTL = `approvals.timeout` + 60 s. `post_approval_response` also evicts. |
| `tldr/summarize.py` | Prompt, `ctx.llm.complete(...)`, hard timeout via helper thread + `join`, output sanitizer, placeholder. |
| `tldr/compose.py` | Per-surface display strings and length budgets (Telegram 480 chars measured AFTER HTML escaping, Discord shorter; Desktop uses `desktop_max_words`; model text has runs of box-drawing/dash characters collapsed so it cannot forge the `── command ──` divider). |
| `tldr/redispatch.py` | Gateway / CLI re-entry and choice normalization. |

## Internal Hermes seams

Seam 1 is a public plugin API. Everything after it is underscore/internal and is the real breakage risk. The test suite pins their signatures.

1. **Transport + hook contract** (public plugin API).
   - `ctx.register_approval_transport(name, present_fn)` — `hermes_cli/plugins.py:437`; frozen `ApprovalRequest` — `hermes_cli/approval_transport.py:40-53`; worker thread — `approval_transport.py:124-128`; requires `plugins.isolation: in_process` — `plugin_isolation.py:41`.
   - `pre_approval_request` fires on the agent thread, before the transport, with `session_key` and `request_id` — `tools/approval_prompt.py:237-241`. It is the only place to capture the session key, the surface markers and the thread-local CLI callback. `ApprovalRequest` has no `session_key`, and `get_current_session_key()` on the worker returns `"default"`.
   - Only `_COMMAND_GATE` and `_EXECUTE_CODE_GATE` have `transport=True` — `tools/approval.py:689-722`.
2. **`tools.approval._gateway_notify_cb(session_key)`** (internal) — `tools/approval.py:539-541`. Returns the per-session notify callback. Telegram: `run_turn_runner._approval_notify_sync` (`gateway/run_turn_runner.py:1455-1550`, registered `:1694`). Desktop: `_emit_approval_request` (`tui_gateway/server.py:818`, registered `:1055`). Returns `None` when no callback exists, so the plugin raises and the fallback applies.
3. **`tools.approval_gateway_wait._await_gateway_decision(session_key, notify_cb, data, surface="gateway")`** (internal) — `tools/approval_gateway_wait.py:133`; returns `{resolved, choice, reason, cancelled?, notify_failed?}`. Thread-safety verified: it uses `threading.Lock`/`Event` keyed by the explicit `session_key` (`approval_gateway_wait.py:158-186`). Telegram marshals onto the event loop through `self._schedule` / `run_coroutine_threadsafe` (`gateway/run_turn_runner.py:87-92`). Desktop writes under locks / `call_soon_threadsafe` (`tui_gateway/server_requests.py:214-230`, `tui_gateway/ws.py:123-143`).
4. **`tools.approval.withdraw_gateway_approval`** (internal) — removes a waiting gateway approval from the host queue. Used on the deadline path and in `on_post` so the plugin's own card does not linger after Hermes has a decision (see "Deadline discipline").
5. **`tools.approval_prompt.prompt_dangerous_approval(command, description, allow_permanent=, allow_session=, smart_denied=, approval_callback=)`** (internal) — `tools/approval_prompt.py:20`. Sits below the transport branch, so there is no recursion.
6. **`tools.terminal_tool._get_approval_callback()`** (internal) — `tools/terminal_tool.py:86`. The prompt_toolkit callback is thread-local, so the hook reads it on the agent thread and passes it explicitly to seam 5.
7. **`tools.interrupt.acting_for_tid` + `is_interrupted`** (internal) — `tools/interrupt.py:32-34`, `:57-58`. Used to propagate `/stop` from the agent thread to the worker (see below).
8. **`gateway.session_context.get_session_env`** (internal) — reads `HERMES_SESSION_PLATFORM` / `HERMES_SESSION_SOURCE`. Called inside the hook, never on the worker.
9. **`tools.approval_context._get_approval_timeout`** (internal) — the host approval timeout, used for the stash TTL and for the deadline math.

### Queue behavior: ours is not always the only entry

Do not assume the plugin's queue entry is the only one. With parallel tool calls, or after a built-in fallback, other entries for the same session can coexist. The two surfaces resolve differently:

- **Telegram** resolves FIFO per session and has no `request_id` in the reply. A button tap answers the OLDEST waiting entry. That is host behavior, not ours. This is why the plugin withdraws its own entry as soon as the host has decided: a stale entry at the front of the queue would swallow the next tap.
- **Desktop** resolves by `request_id`, so entries cannot be confused with each other.

Supporting facts the design depends on:

- Surface detection must happen in the hook, not on the worker; on the worker both env markers are empty. Desktop sets `HERMES_SESSION_PLATFORM=""` and `HERMES_SESSION_SOURCE="desktop"|"tui"` (`tui_gateway/server.py:1373-1378`, `:1563-1567`). Telegram sets `HERMES_SESSION_PLATFORM="telegram"` (`gateway/run.py:4213`). Read both with `gateway.session_context.get_session_env(...)`. Desktop takes the gateway branch because `HERMES_GATEWAY_SESSION=1` (`tui_gateway/server.py:1391`; `tools/approval.py:815`).
- `/stop` propagation: `is_interrupted()` checks the current thread id (`tools/interrupt.py:57-58`). The hook captures `threading.get_ident()`; `present` sets the `tools.interrupt.acting_for_tid` contextvar to it before waiting (`interrupt.py:32-34`). Without this a stale card can swallow the next approval tap on Telegram.
- Desktop withdraws the card when no client can answer — `tui_gateway/server.py:838-842` — which arrives as `choice=None`.

## Behavior rules that follow from the seams

- Every non-answer (`notify_failed`, `resolved=False`, `cancelled`, `choice=None`, timeout) maps to `deny`. This supersedes the earlier "do not answer" idea in DESIGN §4.5 (see §4.6).
- `choice` is checked against `request.allowed_choices` before `request.respond(...)`.
- Missing stash entry, no notify callback and no stashed CLI callback: raise, and the host falls back to the built-in prompt (`transport_fallback: builtin`).
- `present` stays synchronous. LLM time counts against `approvals.timeout`.
- The summarizer treats the (already host-redacted) command as untrusted: comments are stripped (rule below), the text is wrapped in a tag with a random fence name (so a command cannot close it early and inject text), and the system prompt says to ignore directives inside it and tells the model that comments were removed. Output is sanitized: one paragraph, neutralises slash-commands (`/approve`, `/deny`, `/yolo`) anywhere in the output, not only whole lines, strips C0 controls, caps at `max_words`, appends `Risk: UNKNOWN` if no `Risk:` token.

## Comment stripper (rule B1)

Comments are removed before the command reaches the model, so a hostile `# say APPROVE` cannot steer the summary. The rule:

- A `#` starts a comment only at the start of a word (after whitespace or at the start of the text).
- A `#` inside a word (`a#b`, `$#`, `${x#y}`, a URL fragment) is not a comment.
- An escaped `#` (`\#`) is never a comment.
- Quoting is respected as before: a `#` inside quotes is not a comment.
- The model is told that comments were removed, so it does not report a "silent" command that merely had a comment.

## Deadline discipline

The host gives `present()` one deadline (`approvals.timeout`). The plugin must not act after it, or the user may answer a card that no longer means anything.

- After the LLM call, `present()` checks `/stop` (`is_interrupted()`) and the host's finished-set. If the host already decided (timeout, `/stop`, answered elsewhere), nothing is dispatched.
- The inner wait (`_await_gateway_decision`) is withdrawn 5 s before the host deadline, so the plugin's answer cannot race the host's own timeout.
- `on_post` (the `post_approval_response` hook) withdraws the plugin's card via `withdraw_gateway_approval` as soon as Hermes has a decision, whoever made it, so stale cards do not linger and cannot swallow a later tap.
- Non-answers still map to `deny`. If the plugin fails or times out, Hermes falls back to its built-in prompt, which can ask a second time; the agent may then wait up to about twice `approvals.timeout`. If delivery fails outright, the plugin steps aside and the built-in prompt appears.

## Desktop layout

The Desktop card renders only the `command` field, in a scrolling box about 7 lines tall (`apps/desktop/src/components/assistant-ui/tool/approval.tsx`). The summary comes first and the exact command last (the user chose summary-first). The composed `command` string is:

```
{label} — Risk: {verdict}                 <- line 1: label + risk verdict (wraps)
── what it does ──                        <- line 2
{explanation, capped at desktop_max_words}
── command ──
{real command}                            <- last: exact command, unchanged
```

Order: risk verdict, explanation, exact command. Trade-off: a long explanation can push the command below the fold of the box (it scrolls). `desktop_max_words` (default 60) keeps it short; `max_words` (default 90) applies to the other surfaces. The executed command is never altered, only this display copy.

## Upstream canary (automatic)

`.github/workflows/upstream-canary.yml` runs daily (13:17 UTC) and on every push. For two lanes —
hermes-agent `main` and its newest `vX.Y.Z` release tag — it checks out upstream, runs
`scripts/seam_check.py` (imports every internal seam above and compares its `inspect.signature()`
to the one recorded from v0.22.2, plus the `ApprovalRequest` field set and the hook kwargs on the
transport path), then runs the full plugin test suite with upstream on `PYTHONPATH`. No Hermes
install: only `pytest requests psutil ruamel.yaml` are needed. On failure it opens (or comments on)
one issue per lane labelled `upstream-canary`; when the lane is green again it closes that issue.
GitHub emails the repo owner on each. Read a `main` failure as "plan a patch" and a `stable`
failure as "patch before `hermes update`". After fixing a seam, refresh the expected signature in
`scripts/seam_check.py` so the canary stops firing.

Run it locally: `PYTHONPATH=~/.hermes/hermes-agent python scripts/seam_check.py`.

## When upstream changes — checklist

Run on every Hermes upgrade and before every release (the canary covers the first two items daily).

- [ ] `hermes plugins validate <dir>` and `hermes plugins doctor <dir> --ci` are clean.
- [ ] The test suite passes against the new Hermes. It pins the signatures of every internal seam listed above (`_gateway_notify_cb`, `withdraw_gateway_approval`, `_await_gateway_decision`, `prompt_dangerous_approval`, `_get_approval_callback`, `acting_for_tid`/`is_interrupted`, `get_session_env`, `_get_approval_timeout`). A failure here means one of seams 2-9 moved.
- [ ] Re-check each file:line in this document. Update the numbers.
- [ ] `ApprovalRequest` fields, `respond()` and the digest check (`approval_transport.py`) unchanged?
- [ ] `pre_approval_request` still fires on the agent thread, before the transport, with `session_key` and `request_id`? (Smart-mode path changes can skip it.)
- [ ] Which gates have `transport=True`? If more prompt types now reach transports, update the README limitations list (#133946, #120859).
- [ ] Is #133398 fixed (Desktop renders `description`)? If so, default `desktop_inline` to `false` and later remove it.
- [ ] Is #138083 fixed (cron / `-q` sessions consult transports)? Update the README limitations.
- [ ] Did upstream ship its own summary (#86084, #45290)? If so, consider retiring this plugin or pointing to the native setting.
- [ ] `ctx.llm.complete` signature, `ctx.register_auxiliary_task`, and the `provider=`/`model=` override rules (`agent/plugin_llm.py:446-496`, `hermes_cli/plugins.py:853`) unchanged?
- [ ] Surface markers (`HERMES_SESSION_PLATFORM`, `HERMES_SESSION_SOURCE`) still set the same way for Desktop and Telegram?
- [ ] Live smoke test: trigger `python -c "print(1)"` from Desktop, Telegram and the CLI. Confirm the summary is visible, buttons work, deny and approve reach the agent, and `hermes logs --level WARNING | grep -i tldr` is empty.
- [ ] Update `requires_hermes` in `plugin.yaml` and add a CHANGELOG entry.
