# ALMIDO-AUDIT-NOTE — where ALMIDO's audit rows go, and the chain it broke

> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY —
> don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working).

**2026-09-06 · Phase 2, defect #4 · claude-cli-ALMIDO2-DOOR**

## בעברית — בקצרה

עלמידו כתב שורות ביקורת **בפורמט משלו** לתוך הקובץ החתום של השער
(`~/.iddo-harness/audit.jsonl`). זה **שבר את שרשרת ה-HMAC בשורה 33** ב-2026-09-03.
מהיום עלמידו כותב לשרשרת **משלו** ב-`D:\CLAUDE\iddo-harness\state\almido-audit.jsonl`,
דרך הקוד של השער עצמו (`agent/audit.py`), והשרשרת מאומתת. **הקטע השבור בקובץ החי לא
תוקן ולא נמחק — הוא היסטוריה.** נשאר פתוח: קובץ המפתח על כונן D אינו מוגן ב-ACL
(ראו "What is still open" למטה) — זו החלטה של עידו / בעל השער.

## What was wrong (measured, not assumed)

`almido_mcp.audit()` appended a row of its **own** schema —
`{ts, who, door, tool, args_sha, ok, note}`, local `+03:00` — to
`~/.iddo-harness/audit.jsonl`. That file is the harness's **HMAC-chained** security audit:
every line carries `hmac(N) = HMAC-SHA256(key, hmac(N-1) || canonical_json(record))`, so a
line that is not part of the chain breaks every verification from that point on.

Measured on this machine (read-only, the real key read in-process and never printed):

| fact | value |
|---|---|
| rows in `~/.iddo-harness/audit.jsonl` | **60** |
| harness-schema (chained) rows | **32** — lines 1–32, chain **intact** |
| ALMIDO rows | **28** — lines **33–60** |
| first ALMIDO row | `2026-09-03T23:05:49+03:00` — **the break point** |
| last ALMIDO row | `2026-09-06T16:55:28+03:00` — the last one ever written there |
| what they are | 18 × `session_start`, 10 × real tool calls |

The docstring claim that this was *"the same audit the AlmIdo policy harness reads"* was
false twice over: the gate's `policy.yaml:121` points it at `audit.log` (89.5 MB of
`Bridge sync failed` lines), and the gate has not run since 2026-08-25.

## What changed

* ALMIDO writes to **`D:\CLAUDE\iddo-harness\state\almido-audit.jsonl`** — its own chain,
  its own key (`almido-audit.key`), never the gate's file.
* Rows go through the **harness's own** `AuditLog.record()` (`agent/audit.py` in the
  canonical repo `D:\CLAUDE\iddo-harness`), so they are HMAC-chained in the harness's exact
  format: `{ts, actor, action, resource, outcome, meta, prev, hmac}`.
  `action = "tool:<name>"`, `resource = <sha256 of the arguments>[:12]`, `outcome = ok|error`,
  and a failure now carries **its reason** in `meta.note` (it used to carry `""`).
* `agent/audit.py` and `agent/file_security.py` are loaded **by path**, not by
  `import agent.audit`: three copies of the harness exist here and the pip-installed one
  (`Documents\Codex\...\PR-4`) wins on `sys.path` with different function names. Loading by
  path means the code that runs is the code in the repo we chose. (Phase-1 defect #10 — the
  real fix is the gate owner's.)
* Even if `ALMIDO_AUDIT` is pointed at the live chain, `_audit_target()` refuses and writes
  next to it instead. If the harness code is unreachable, rows go to a **separate**
  `*-unsigned.jsonl` — an unsigned row in a chained file is the bug this note exists about.

## The broken segment is HISTORY. Do not repair it.

Lines 33–60 of `~/.iddo-harness/audit.jsonl` stay exactly as they are. They record real
events; rewriting them to make `verify_chain` pass would be forging the audit to make the
audit look good. `iddo-harness audit verify` will keep reporting the break at line 33 —
**that report is correct**, and this file is the explanation of it. Iddo's call, whenever he
wants it: rotate that file so a fresh chain starts, keeping the old one (gzipped) as history.
Never delete it.

## Verified 2026-09-06

Two rows written by **live qwen-code sessions**, not by a test:

```
2026-09-06T14:08:14Z  tool:session_start  ok     posted as almido-qwen (501 messages, source=disk, ram=ok)
2026-09-06T14:13:56Z  tool:session_start  error  ramlink did not answer in 30 s
```

`verify_chain` → **True**. The second row is the point: the old code hard-coded `ok=True` for
`session_start` even when the council post threw (there is a row from 09-05 16:47:20 that says
`ok: true` over a `PermissionError` traceback). It now records what actually happened.

## What is still open — NEEDS IDDO / the gate owner

1. **The key file on `D:` is not ACL-restricted.** `almido_mcp` calls the harness's own
   `file_security.restrict_private_file()`, which works on `C:\Users\...` (proved in
   `tests/test_almido_mcp.py::test_the_hmac_key_is_really_ACLd_to_this_user`) but fails on
   `D:\CLAUDE\iddo-harness\state\almido-audit.key` with
   `PermissionError: ... SetAccessControl ... Attempted to perform an unauthorized operation`.
   The file is currently `Authenticated Users : Modify` — anyone who can write the key can
   forge the chain. The failure is **reported, not swallowed**: `almido_whoami` shows it as
   `audit.key_restricted`. The fix belongs in `agent/file_security.py` (its script sets the
   owner and the DACL in one `SetAccessControl`, which needs a privilege this process does not
   hold) — that module is the gate owner's, and it is security-critical.
2. **Merging into `~/.iddo-harness`** — whether ALMIDO's chain should eventually live beside
   the gate's is Iddo's decision, per the Phase-2 contract. Until he says so, they are two
   files with two keys.
