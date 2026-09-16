# 🪟 BROKEN WINDOWS LAW — חוק החלונות השבורים
> if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

# CANONICAL — this is the one iddo-harness / זה העותק הקנוני

**English.** `D:\CLAUDE\iddo-harness` is the canonical home of the Iddo Harness
policy gate from 2026-09-06. It is a `git clone` of branch `feat/v3.1-transports`
(commit `009fc13`) out of `C:\Users\<user>\.iddo-harness\src`, plus the three
uncommitted working-tree changes that were actually running in the v3.1 worktree
(`agent/reporter.py` chunk reporting, `agent/perplexity_cli.py`, the `claude*`
auto-allow line in `policy.yaml`). The `origin` remote was **removed on purpose**:
nothing here is ever pushed.

**עברית.** מ-2026-09-06 זה הבית הקנוני של שער המדיניות. שאר העותקים נשארים על
הדיסק בדיוק כפי שהם — לא נמחק כלום — אבל הם היסטוריה, לא מקור.

## The four copies, and what each one is now

| path | what it is | status |
|---|---|---|
| `D:\CLAUDE\iddo-harness` | **CANONICAL** — the code and policy ALMIDO's gate uses | live source of truth |
| `C:\Users\<user>\.codex\worktrees\iddo-harness-v3.1-transports` | the worktree this was cloned from | **untouched**, kept as-is |
| `C:\Users\<user>\.codex\worktrees\iddo-harness-pr4` | the branch the pip-installed `iddo-harness` CLI imports | **untouched**, history |
| `C:\Users\<user>\.iddo-harness\src` | v1, the Scheduled Task's target (task `IddoHarness` is Disabled) | **untouched**, history |

`C:\Users\<user>\.iddo-harness\` (the *state* dir: `policy.yaml`, `audit.jsonl`,
`audit.key`, `ws-token`, `pending\`) is **security-critical and NOT changed by
this repo**. Switching it over to this policy is staged, not executed — see
`APPLY-GATE.cmd` and `GATE-DIFF.md`.

## What is different here from the worktree it came from

1. **The ws bearer token is gone from `config.yaml`.** It used to be pinned in
   plaintext and baked into `D:\CLAUDE\harness-web\index.html`. The value has
   been **rotated**; the new one lives in `state\ws-token` with an ACL that
   grants `IDDO1\iddo1` only, and `config.yaml` points at it with `ws.token_path`.
   No secret exists anywhere in this repo, and `state\` is git-ignored.
2. **`ws.enabled` and `mcp.enabled` are back to `false`.** The bridge has not run
   since 2026-08-25; a repo whose default opens a remote command channel is a
   broken window. Turn either on deliberately.
3. **`policy.yaml` carries the ERAN fence** as real `block` rules (see below).
4. **`agent/policy.py` path/command matching is fixed** — see `GATE-DIFF.md` §3.

## Test suite

`1132 passed, 14 skipped` at BELOW_NORMAL with an isolated `HOME`, 2026-09-06
(301.94 s). Phase 1 measured `1129 passed` **plus 3 failures** on the same 1132
tests; the three that failed were the `config.yaml` assertions, and they pass now
that the token is out of the file.

Re-run it the same way — never against the live `HOME`:

```powershell
$iso = "$env:TEMP\harness-home"; mkdir $iso -Force | Out-Null
$env:HOME=$iso; $env:USERPROFILE=$iso
cd D:\CLAUDE\iddo-harness; python -m pytest -q
```
