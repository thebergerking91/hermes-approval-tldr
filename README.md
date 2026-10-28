# approval-tldr

Plain-English summaries on Hermes Agent approval prompts. A plugin for [Hermes Agent](https://github.com/NousResearch/hermes-agent) by Nous Research.

Repository: https://github.com/thebergerking91/hermes-approval-tldr

## What this does

When Hermes wants to run something risky, it stops and asks "Approve this?" It shows you the raw shell command or Python script. If you are not a programmer, you cannot tell a harmless cleanup from a command that destroys your work. So you end up approving everything, or denying everything.

This plugin adds a short paragraph to every approval prompt. It says what the command will do, what it touches, whether you can undo it, and a risk level (LOW, MEDIUM or HIGH). The paragraph is written by an AI model, so it is labeled as such and it can be wrong. The real command stays on screen next to it (on Desktop the box shows the risk line first, then the explanation, then the exact command at the bottom). The plugin never approves or denies anything for you.

**Before** (Telegram):

````
⚠️ Command Approval Required

```find . -name "*.pyc" -delete```

Why it was flagged: recursive delete

Reply within 5 minutes.
[✅ Allow Once] [✅ Session] [✅ Always] [❌ Deny]
````

**After** (Telegram, buttons unchanged). Our summary goes into the "Why it was flagged" line. The command above it is untouched:

````
⚠️ Command Approval Required

```find . -name "*.pyc" -delete```

Why it was flagged: AI summary (may be wrong — read the command): This deletes every Python cache file (*.pyc) under the current project folder. It does not touch your source code; the caches rebuild automatically the next time Python runs. Risk: LOW — only regenerable cache files. · Flagged as: recursive delete

Reply within 5 minutes.
[✅ Allow Once] [✅ Session] [✅ Always] [❌ Deny]
````

**After** (Desktop app). The Desktop card only draws the command box, and that box shows about 7 lines and then scrolls. So the summary goes inside that box, above the command:

```
┌ Command ──────────────────────────────────────────────────────┐
│ AI summary (may be wrong — read the command) — Risk: LOW — only  │
│ regenerable cache files                                         │
│ ── what it does ──                                              │
│ This deletes every Python cache file (*.pyc) under the current  │
│ project folder. It does not touch your source code; the caches  │
│ rebuild automatically the next time Python runs.                │
│ ── command ──                                                   │
│ find . -name "*.pyc" -delete                                    │
│                                    [Reject] [Always ▾] [Run]    │
└──────────────────────────────────────────────────────────────────┘
```

Reading order on Desktop: the risk verdict first, then the explanation, then the exact command. The box shows about 7 lines and scrolls. With the default settings the explanation is up to 60 words, so the exact command usually sits below what you see. Scroll down to it before you approve. The plugin also flattens any fake divider lines in the AI's text, so the AI cannot make its own words look like the "command" line. To keep the command in view, lower `desktop_max_words` in Settings.

In the terminal (CLI), the summary is the header line of the approval panel. The command sits beneath it. The same keys (o / s / a / d) work as before.

If the summary cannot be made in time, the prompt still appears. It says `AI summary unavailable — read the command carefully.` where the summary would be. If the plugin itself breaks and you set `transport_fallback: builtin` (install step 3), Hermes shows its normal, old-style prompt instead. Without that setting, Hermes' default is to treat a transport failure as a denial.

## Why a plugin and not core

Hermes' maintainers looked at this idea and said no for the core product. Issue [#6959](https://github.com/NousResearch/hermes-agent/issues/6959) ("explain the likely action and risk in plain language") was closed in July 2026. The reasoning: a second AI call adds delay, and a wrong explanation at a security checkpoint can sound more trustworthy than it deserves.

Other people still want it. These requests are open:

- [#86084](https://github.com/NousResearch/hermes-agent/issues/86084) — AI summary and security review for execution approvals
- [#45290](https://github.com/NousResearch/hermes-agent/issues/45290) — humanize dangerous-command prompts with an AI explanation
- [#133398](https://github.com/NousResearch/hermes-agent/issues/133398) — the Desktop card hides the "why it was flagged" text (this is why the Desktop summary sits inside the command box)

A plugin lets you opt in, and keeps the trade-off (extra delay, possible wrong summary) your own choice. Hermes keeps all authority over what runs.

## Install

You need Hermes Agent 0.22.2 or newer.

**From the Hermes plugin catalog** (once listed): `hermes plugins install approval-tldr`, then continue at step 3. The catalog installs the exact commit a Hermes maintainer reviewed.

**By hand:**

1. Put this folder at `$HERMES_HOME/plugins/approval-tldr`. `$HERMES_HOME` is normally `~/.hermes`. Either copy the folder or link it:

   ```
   ln -s /path/to/hermes-approval-tldr "$HERMES_HOME/plugins/approval-tldr"
   ```

   (Or copy: `cp -R /path/to/hermes-approval-tldr "$HERMES_HOME/plugins/approval-tldr"`.)

2. Turn the plugin on:

   ```
   hermes plugins enable approval-tldr
   ```

3. Tell Hermes to use it for approval prompts, and to fall back to the normal prompt if the plugin fails:

   ```
   hermes config set security.approval.transport tldr
   hermes config set security.approval.transport_fallback builtin
   ```

4. Restart anything that is already running. A running gateway (Telegram) or Desktop backend loaded its plugins at start-up. It will not see the new plugin until you restart it. The plugin cannot do this for you.

Two notes:

- `plugins.isolation` must be `in_process`. That is the default. Check with `hermes config get plugins.isolation` if you ever changed it. Hermes refuses approval plugins under `host` isolation.
- Always change settings with `hermes config set`. Do not edit `config.yaml` by hand.

Command details are in the Hermes docs: [approval transports](https://hermes-agent.nousresearch.com/docs/user-guide/features/plugins#approval-transports) and [managing plugins](https://hermes-agent.nousresearch.com/docs/user-guide/features/plugins#managing-plugins).

## Choosing the model for summaries

The summary comes from an AI model. You can pick a small, cheap, fast one. Summaries are short.

```
hermes config set auxiliary.approval_summary.provider <provider>
hermes config set auxiliary.approval_summary.model <model-name>
```

Replace `<provider>` and `<model-name>` with values you already use elsewhere in Hermes.

If you set nothing, the plugin uses the same model setup as Hermes' "smart approvals" feature (the `approval` auxiliary task). If that does not resolve to a working model, it uses your main model.

A faster model means a shorter wait before each prompt.

## Settings

All settings are optional. Change one like this:

```
hermes config set plugins.entries.approval-tldr.settings.<key> <value>
```

| Key | Type | Default | What it does |
|---|---|---|---|
| `label` | text | `AI summary (may be wrong — read the command)` | The warning text shown before the summary. |
| `max_words` | whole number | `90` | Longest the summary may be (Telegram, Discord and the terminal). |
| `desktop_max_words` | whole number | `60` | Longest the explanation may be in the Desktop box. Shorter than `max_words` because the box is small and scrolls. |
| `llm_timeout_s` | number | `10` | Seconds to wait for the AI before showing the prompt without a summary. |
| `desktop_inline` | true/false | `true` | On Desktop, put the summary inside the command box (risk line, then the explanation, then the command). Turn off once Hermes itself shows the description (#133398 fixed). |
| `language` | text | `en` | Language of the summary. |

Examples:

```
hermes config set plugins.entries.approval-tldr.settings.max_words 60
hermes config set plugins.entries.approval-tldr.settings.desktop_max_words 40
hermes config set plugins.entries.approval-tldr.settings.llm_timeout_s 5
hermes config set plugins.entries.approval-tldr.settings.language de
hermes config set plugins.entries.approval-tldr.settings.desktop_inline false
```

Restart the gateway or Desktop backend after changing settings.

## What it can NEVER do

- It cannot run, approve, or deny anything by itself. It only passes along the button or key you press.
- It cannot give you more power than Hermes offered. If Hermes did not offer "Always" for a command, the plugin cannot make that choice happen.
- It never changes the command that actually runs. Only the text shown to you changes.
- It never hides that the summary is AI-written. Every prompt labels it, and the real command and the "why it was flagged" reason are shown. On Desktop the exact command is at the bottom of the box, under the explanation. Scroll down to it before you approve.
- If the AI call fails or is slow, you get a prompt that says the summary is unavailable. You never get a missing prompt or an automatic answer.
- If the plugin breaks, you get Hermes' normal prompt (because of `transport_fallback builtin`). You never get a silent denial.

Honest caveats to that last promise:

- **Fallback can mean a second question.** If the plugin fails, times out, or you send `/stop`, Hermes falls back to its normal prompt. So after a timeout you may be asked a second time. In that case the agent can wait up to about twice the approval timeout in total.
- **No answer is reported as "denied".** When nobody answers (timeout, the card is withdrawn, or `/stop`), the plugin tells Hermes "denied". The agent is therefore told that you denied it, even though you did not click anything.
- **If the prompt could not be shown at all** (delivery failure, for example Telegram could not send the message), the plugin steps aside and Hermes shows its own prompt.
- **Telegram answers the oldest waiting approval.** When you tap a button, Telegram applies it to the OLDEST approval that is still waiting. That is how Hermes itself works, not something this plugin adds. If several approvals are pending at once, answer them in order. The plugin withdraws its own card as soon as Hermes has a decision, so stale cards do not linger.

## Limitations

- **Only shell commands and Python scripts (`execute_code`) are covered.** Other prompts keep the stock look: saving a memory, writing to protected files, MCP consent, and approvals triggered by other plugins' rules. Hermes does not route those through approval plugins yet (upstream #133946, #120859).
- **Smart approvals mode.** If `approvals.mode` is `smart`, Hermes' own checker sometimes approves a command without asking you. No prompt appears then, so no summary either. You see the summary only when Hermes does ask you.
- **A small delay.** Each prompt waits for the AI call first. The aim is about 3 seconds. It is capped at `llm_timeout_s`. That time counts against Hermes' overall approval timeout, which is long enough that the 10-second default does not matter.
- **It relies on Hermes internals.** The plugin calls a handful of internal Hermes functions (listed in docs/ARCHITECTURE.md) to show the prompt and wait for your answer. A Hermes update can rename them. If that happens you get the stock prompt again, not a crash. A daily GitHub Actions check ("upstream canary") tests this plugin against the latest Hermes code and release and opens an issue in this repo when something it relies on moves, so you hear about it before you update. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
- **The Desktop workaround is a workaround.** The summary goes in the command box because the Desktop card hides the description (#133398). The box shows about 7 lines and scrolls, which is why the explanation is kept short: a long one can push the command below the fold.
- **Unattended runs are unchanged.** Scheduled (cron) jobs, quiet `-q` runs and similar sessions never ask a human through approval plugins (upstream #138083).
- **No answer means "deny".** If nobody can answer a prompt (timeout, the card is withdrawn, or you send `/stop`), the plugin reports a denial to Hermes, so the agent is told you denied it. That is the safe direction.
- **Fallback can ask twice.** If the plugin fails, times out, or you send `/stop`, Hermes falls back to its normal prompt. After a timeout you may be asked a second time, and the agent can wait up to about twice the approval timeout.
- **Prompt could not be shown.** If delivery fails, the plugin steps aside and Hermes shows its own prompt.
- **Several approvals at once (Telegram).** A button tap answers the OLDEST waiting approval, as in plain Hermes. Answer pending approvals in order. The plugin withdraws its own card as soon as Hermes has a decision.
- **Summaries can be wrong.** Always read the command. For anything you do not understand, deny and ask.

## Disclosure

What a careful person would want to know before installing:

- **AI provider egress.** For every approval prompt it handles, the plugin sends the command text and Hermes' "why it was flagged" reason to your configured AI provider, through Hermes' own plugin LLM API (`ctx.llm`). That provider may be a third-party service. Hermes redacts secrets from approval text first, but redaction is best-effort and not identical on every surface. The provider is your main model, or the one you pin with `auxiliary.approval_summary.*` (the plugin registers that auxiliary task).
- **No other network, files or processes.** The plugin makes no other network requests, reads no credentials or files outside Hermes, writes no files (only Hermes' normal log), and starts no processes. The prompt card itself is delivered by Hermes' existing gateway (Telegram, Discord, Desktop) or CLI panel.
- **Uses Hermes internals.** To show the prompt on Hermes' own card and wait for your answer, the plugin calls eight internal (underscore or undocumented) Hermes functions, listed in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). It calls them and never replaces or patches them. A Hermes update can break them; you then get Hermes' stock prompt (with `transport_fallback: builtin`) or a denial (Hermes' default).
- **Never decides for you.** Anything except an explicit answer you gave (timeout, `/stop`, withdrawn card, delivery error) is reported to Hermes as "deny". Any choice Hermes did not offer becomes "deny".
- **One host setting changed by the install steps.** Step 3 sets `security.approval.transport_fallback: builtin`. That applies to all approval transports, not only this one. With it, a plugin failure shows Hermes' normal prompt, and after a timeout you may be asked a second time (the agent can wait up to about twice `approvals.timeout`).
- **Prompt injection.** The model is told to treat the command as untrusted data and to ignore any instructions written inside it. This reduces, but cannot remove, the chance that a hostile command steers its own summary. The real command is always shown. Read it.

## Troubleshooting

**The summary says "AI summary unavailable."**
The AI call timed out or failed. Check that your summary model works (`auxiliary.approval_summary.*`, or your main model). Try a faster model, or raise `llm_timeout_s`.

**The prompt looks like the old one, with no summary.**
Either the transport is not selected, or the plugin failed and Hermes fell back. Check, in order:

1. `hermes plugins list` shows `approval-tldr` as enabled.
2. `hermes config get security.approval.transport` prints `tldr`.
3. You restarted the gateway or Desktop backend after installing.
4. Look for warnings: `hermes logs --level WARNING | grep -i tldr`
5. Is it a prompt type from the Limitations list? Those never show a summary.

**On Desktop the summary is inside the command box, not above it.**
That is on purpose. The Desktop card does not display the description text (upstream #133398). The risk line comes first, then the explanation, then the command. Set `desktop_inline` to `false` once that bug is fixed.

**Prompts take a few seconds longer than before.**
That is the AI call. Use a faster model or lower `llm_timeout_s`.

## Uninstall

```
hermes config set security.approval.transport builtin
hermes plugins disable approval-tldr
```

Then restart your gateway or Desktop backend. You can delete `$HERMES_HOME/plugins/approval-tldr` afterwards. If `builtin` is not accepted on your version, run `hermes config get security.approval` to see the allowed values, or check the [Hermes docs](https://hermes-agent.nousresearch.com/docs/user-guide/features/plugins#approval-transports).

## Credits and license

MIT License. See [LICENSE](LICENSE).

Copyright (c) 2026 [thebergerking91](https://github.com/thebergerking91). Built with Hermes Agent by [Nous Research](https://github.com/NousResearch/hermes-agent).

Technical notes for maintainers: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Version history: [CHANGELOG.md](CHANGELOG.md).
