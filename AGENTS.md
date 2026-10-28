# approval-tldr — agent instructions

Out-of-tree Hermes Agent plugin; this folder is the plugin root (install by copying or symlinking it to `$HERMES_HOME/plugins/approval-tldr`). It registers an approval **transport** named `tldr` that adds an LLM-written plain-English "what it does / risk" paragraph to dangerous-command and `execute_code` approval prompts, then re-dispatches the prompt to the user's existing Telegram card / Desktop card / CLI panel. Hermes keeps all authority: the plugin only changes *displayed* strings and relays the human's choice, clamped to what the host offered. Design and evidence: `DESIGN.md` (§4.6–4.7 are the binding contract), `RESEARCH.md`, `docs/ARCHITECTURE.md`.

## Layout

- `plugin.yaml` — manifest v2; `provides_hooks` must list every hook `register()` registers or `hermes plugins validate` fails. Settings live under `config_schema`; read them via `ctx.get_config`.
- `__init__.py` — `register(ctx)`, hooks `on_pre`/`on_post` (agent thread), transport `present()` (host worker thread). Has an inert `__package__` shim so pytest can import it bare.
- `tldr/stash.py` — request_id → captured context (session_key, surface, platform, source, agent tid, CLI callback). TTL-bounded.
- `tldr/summarize.py` — prompt, LLM call with hard timeout, input/output hardening.
- `tldr/compose.py` — per-surface display strings and length budgets.
- `tldr/redispatch.py` — **the only file allowed to import Hermes internals**, each wrapped in a `_hermes_*` adapter.
- `scripts/seam_check.py` — pins the signature of every internal seam; run by CI.
- `tests/` — pytest; `tests/support.py` has `FakeCtx`, `FakeLlm`, `load_plugin()` (loads the plugin the way Hermes does).

## Dev environment

Stdlib-only Python 3.11+. A hermes-agent source checkout (>= 0.22.2, the version the seams were pinned against) is a read-only dependency: put it on `PYTHONPATH`, never edit it. Runtime extras the import graph needs: `pip install pytest requests psutil ruamel.yaml`.

## Test, validate, check

```bash
export HERMES_SRC=/path/to/hermes-agent              # git checkout of NousResearch/hermes-agent
PYTHONPATH=$HERMES_SRC python -m pytest tests -q      # 148 tests, ~10 s
hermes plugins validate .                             # must print "Validation passed"; one ⚠ about private core imports is expected
hermes plugins doctor . --ci                          # must report 2 hooks, OK
PYTHONPATH=$HERMES_SRC python scripts/seam_check.py   # exit 0 = seams unchanged
```

`pytest.ini` sets `--import-mode=importlib`; `tests/conftest.py` sandboxes `HERMES_HOME` to a tmp dir (autouse) — no test may touch a real Hermes home.

CI: `.github/workflows/upstream-canary.yml` runs the seam check + suite against hermes-agent `main` and the newest `vX.Y.Z` tag daily and on push; red opens an `upstream-canary` issue. After fixing a seam, update the expected signature string in `scripts/seam_check.py`.

## Conventions (observed)

- Every module opens with a one-paragraph "Why it exists" docstring; type hints throughout; logger name `plugins.approval-tldr`.
- Hooks never raise. `present()` raises `RuntimeError` only when the host should fall back to its built-in prompt (missing stash, no surface, upstream API gone); every other non-answer returns `request.respond("deny")`. Return choices pass through `clamp(choice, request.allowed_choices)`.
- New Hermes-internal dependency → new adapter in `tldr/redispatch.py` **and** a new row in `scripts/seam_check.py` `SEAMS` **and** the seam list in `docs/ARCHITECTURE.md`.
- Behavior change → `CHANGELOG.md` (Keep a Changelog) and, if user-visible, `README.md` (written for non-programmers; short sentences).
- Commits: `type: subject` (`feat:`, `fix:`, `docs(design):`, `ci:`); body explains why.
- Public attribution is the GitHub handle `thebergerking91` only — in files (`author:`, LICENSE, README credit), commit author/committer, and history. No personal name anywhere; the history was already rewritten once to enforce this. Commit with `-c user.name=thebergerking91 -c user.email=thebergerking91@users.noreply.github.com` if the global identity differs.

## Pitfalls

- `request.surface` is `"gateway"` for **both** Desktop and Telegram; the stash's `source` (`desktop|tui`) / `platform` (`telegram`) tells them apart. Both are empty on the worker thread — capture them in `on_pre` only.
- `get_current_session_key()` on the worker returns `"default"`; use the stashed `session_key`.
- The Desktop card renders only the `command` field in a ~7-line scrolling box (upstream #133398): order is verdict (line 1) → explanation → real command last (summary-first, B3); keep the explanation word-capped so the command is not pushed far below the fold.
- Telegram's 500-char reason cap is measured **after** `html.escape`; compose budgets must be too.
- Bash `#` is a comment only at word start — do not "simplify" `strip_shell_comments` back to any-`#`.
- A literal root-wipe command spelled out in any tracked `.md` trips validate's security scan.
- Enabling the plugin hot-loads hooks, but a transport registers only at process start: a stock card after enable means the gateway / Desktop backend has not been restarted yet. Restarting those is the operator's call.
- Revert live behavior instantly with `hermes config set security.approval.transport builtin`.
