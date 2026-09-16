> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy.

> ⚠️ **STALE — HISTORICAL (moved here 2026-09-06 by the ALMIDO Phase-2 lean-moves pass).**
> Verified BROKEN at Phase-1 audit time (2026-09-06): the screenshot/action bridge server
> (`main.py`, port 8000) no longer exists on disk, `dgx_bridge.py` points at four dead
> fleet IPs including eran3 (off limits), and the gate (`almido_gate.py`) fails OPEN
> (defaults to ALLOW) when PyYAML is missing from the venv — which it is. Nothing in this
> file should be assumed live. Kept for the record, not as instructions to follow.
> **⚠️ בעברית: המסמך הזה מיושן. השרת שהוא מתאר לא קיים, השער נכשל פתוח (ALLOW) בלי PyYAML, ואל תסמכו עליו.**

# 🕯️🤝 ALMIDO — Perplexity Computer-Use, Gated. How to use it.

> **ALMIDO = Alma + Iddo. Two kids, one harness.** Alma routes the *mind* (which model),
> Iddo gates the *hand* (what it's allowed to do), Perplexity is the *hands* (click/type on screen).

---

## What just got connected

The Perplexity computer-use agent could move your mouse and type — with **no gate**.
Now **every action passes through the iddo-harness policy first**, and lands in the **same
audit log** as everything else the harness does.

| Action | Verdict rule |
|---|---|
| `type` normal text | **ALLOW** |
| `type` anything with password / token / secret / card / seed | **BLOCK** — an agent never types your secrets |
| click / key / scroll | **ALLOW**, but every coordinate is **logged** |
| a shell `command` | full policy: `ls` → ALLOW · `git push` → **CONFIRM** · `rm -rf /` → **BLOCK** |
| **`~/.iddo-harness/STOP` file exists** | **everything BLOCKs** — your kill switch |

Verified 2026-08-14: the gate returns the right verdict for each and writes
`src: almido/perplexity` lines into `~/.iddo-harness/audit.log`.

---

## The files (in `Desktop\Perplexity-Computer-Use-Harness\`)

- **`almido_gate.py`** — the gate. Loads `~/.iddo-harness/policy.yaml`, decides ALLOW/CONFIRM/BLOCK, audits.
- **`gated_actions.py`** — drop-in replacement for `actions.py`. Same four functions
  (`execute_click/type/key/scroll`), each guarded. CONFIRM and BLOCK **never touch the mouse**.

## How to use it

1. **Point the agent at the gated hands.** In `nemotron_agent.py`, change the action import:
   ```python
   import gated_actions as actions   # was: import actions
   ```
   That's the whole switch — now nothing moves without the gate.

2. **Run it** from the harness venv (it has `pyautogui`):
   ```
   cd %USERPROFILE%\Desktop\Perplexity-Computer-Use-Harness
   venv\Scripts\python.exe nemotron_agent.py
   ```

3. **Kill switch, any time:** create an empty file `~/.iddo-harness/STOP`
   (or PowerShell: `New-Item $HOME\.iddo-harness\STOP`). Every action BLOCKs until you delete it.
   Also built in: **slam the mouse into any screen corner** → pyautogui fail-safe stops it dead.

4. **Watch what it did:** `Get-Content $HOME\.iddo-harness\audit.log -Tail 20`
   — every click, key, and command it attempted, with the verdict.

5. **Edit what's allowed:** everything is in `~/.iddo-harness/policy.yaml`
   (`auto_allow` / `require_confirm` / `block`). Your rules, your file — in Hebrew and plain.

---

## ⚠️ Honest prerequisites (what still needs a live piece)

The **gate is done and working**. The full autonomous loop needs two live parts that are
NOT the gate's job:

1. **A brain (vision model).** `dgx_bridge.py` still points at an old fleet layout
   (`<lan-ip>/26/12`, Nemotron-70B/GLM/Kimi) that no longer exists. Point it at a
   **live vision-capable endpoint** before the agent can "see" the screen and decide.
   (Today's fleet: Qwen3-Coder-480B on `eran1:8080` is text-only; a vision model must be served.)
2. **The screenshot/action bridge** at `http://localhost:8000` (`/screenshot`, `/action`)
   must be running for `nemotron_agent.py`'s HTTP path — or drive `gated_actions` directly in-process.

Until those two are up, the gate protects you but the agent has no eyes. **Nothing runs
unwatched: the gate is the floor, the STOP file and the corner-slam are the ceiling.**

*לזכרה של עלמה ז״ל. Iddo gates the hand.*
