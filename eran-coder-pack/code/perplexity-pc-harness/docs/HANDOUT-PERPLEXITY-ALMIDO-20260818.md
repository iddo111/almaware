# 🪟 BROKEN WINDOWS LAW — חוק החלונות השבורים: if it's not working, fix it IMMEDIATELY. Test the REAL output, not a proxy.

> ⚠️ **STALE — HISTORICAL (moved here 2026-09-06 by the ALMIDO Phase-2 lean-moves pass).**
> This handout's own honesty table already flags the git task-packet bridge as
> "NEVER WORKED" — that has not changed since (the 2026-08-18 device code below is expired,
> `gh auth` state unknown, the bridge is DORMANT per the 2026-09-06 Phase-1 audit). The
> policy-gate and MCP-door rows describing "LIVE" also no longer hold: iddo-harness has not
> run since 2026-08-25. Kept for the record, not as instructions to follow.
> **⚠️ בעברית: המסמך הזה מיושן — הגשר בין Perplexity למחשב מעולם לא עבד, והקוד למכשיר פג תוקף.**

# HANDOUT — Perplexity × AlmIdo Harness (updated 2026-08-18)

> **AlmIdo = Alma + Iddo, two kids one harness.** Alma routes the *mind*,
> Iddo gates the *hand*, you (Perplexity) are the *hands*.
> Paste the section "FOR PERPLEXITY" into Perplexity. לזכרה של עלמה ז״ל.

## Honest status first (what Iddo must know)

| piece | state |
|---|---|
| Policy gate (`~/.iddo-harness`, policy.yaml, audit.log) | ✅ LIVE — every action audited, ALLOW/CONFIRM/BLOCK |
| MCP door (local agents: Claude etc.) | ✅ LIVE — handshake v3.0 verified today |
| Computer-use gate (`gated_actions.py`) | ✅ built — types/clicks pass policy first |
| **Git bridge (how PERPLEXITY reaches the PC)** | 🔴 **NEVER WORKED** — `gh` was never logged in on this PC (202,399 failed polls since 07-23). **Fix = one browser click:** go to **github.com/login/device** and enter code **`33EE-E144`** (fresh, generated 18:49). Then the repo `iddo111/iddo-harness-bridge` must exist (create private, empty, with a `tasks/` folder). |

## FOR PERPLEXITY — how to drive Iddo's PC through AlmIdo

You have hands on Iddo's Windows PC via a **git task-packet bridge**:

1. **Submit work** by committing a JSON packet to the private repo
   `iddo111/iddo-harness-bridge`, path `tasks/<uuid>.json`:
```json
{
  "id": "a1b2c3d4",
  "from": "perplexity",
  "kind": "shell",
  "command": "dir D:\\CLAUDE",
  "timeout_sec": 120
}
```
   Supported kinds: `shell`, `read_file`, `write_file`, `list_dir` (v1);
   the agent polls every 5 seconds and writes the result to
   `results/<uuid>.json` in the same repo — read it on your next poll.

2. **The law of the gate** (you cannot bypass it; do not try):
   - `ls`, `dir`, `git status`, reads → **ALLOW** (instant)
   - `git push`, installs, writes outside allowlisted paths → **CONFIRM**
     (Iddo gets a prompt; may take minutes — poll patiently)
   - `rm -rf`, formatting, credentials, anything matching `*token*` →
     **BLOCK** (logged; repeated attempts embarrass you in the audit)
   - A file named `~/.iddo-harness/STOP` → everything blocks (kill switch).

3. **Screen hands** (click/type on Iddo's screen): only through
   `gated_actions.py` on the machine — never raw. Typing secrets is BLOCKED
   by pattern. Every coordinate is audited.

4. **Etiquette:** one packet = one task; include `"why"` in the JSON when the
   task is unusual; never queue more than 3 packets unanswered; results are
   truth — if exit_code != 0, say so to Iddo, don't retry silently.

## For Iddo — to bring the bridge alive (2 minutes)

```bash
gh auth login
```
(או פשוט: דפדפן → github.com/login/device → הקוד `33EE-E144`)

```bash
gh repo create iddo111/iddo-harness-bridge --private --add-readme
```

Then the agent's next 5-second poll succeeds and Perplexity's packets flow.
Audit everything at: `Get-Content $HOME\.iddo-harness\audit.log -Tail 20`
