# Security policy

## What this plugin can and cannot do

approval-tldr is an *approval transport* for Hermes Agent. It changes the text a person sees on a
dangerous-command approval prompt and relays that person's answer back to Hermes, clamped to the
choices Hermes offered. It cannot approve anything on its own: Hermes keeps the hardline blocks,
deny rules, request binding and final authorization. Any non-answer (timeout, error, `/stop`) is
reported to Hermes as **deny**. See `DESIGN.md` §4.6–4.7 for the binding contract and `README.md`
→ *Disclosure* for exactly what leaves your machine (the redacted command text, sent to the AI
provider you already configured in Hermes; nothing else).

## Supported versions

Only the newest tagged release (`vX.Y.Z`) and the commit pinned in the Hermes plugin catalog
receive fixes. Older tags are not patched; update instead.

## Reporting a vulnerability

Please **do not open a public issue** for anything that could let a command run without a real
approval, leak the command text somewhere other than the configured AI provider, or forge the
prompt a person sees (for example, text from the AI summary that imitates Hermes' own UI).

Use GitHub's private channel instead: **Security tab → Report a vulnerability** on
<https://github.com/thebergerking91/hermes-approval-tldr/security/advisories/new>.

Include the Hermes version (`hermes --version`), the plugin version (`plugin.yaml`), which surface
you were on (CLI, Desktop, Telegram or another gateway platform), and a reproduction. You will get
an acknowledgement within 7 days. Fixes ship as a new tag plus a SHA-bump PR to the Hermes plugin
catalog; the advisory is published once the catalog pin has moved.

## Scope notes

- The AI summary is advisory. A wrong or misleading summary is a quality bug, not a security
  vulnerability, *unless* the summary can impersonate Hermes' own prompt elements or hide the
  real command. Those are in scope.
- Problems in Hermes Agent itself belong to
  <https://github.com/NousResearch/hermes-agent/security>.
