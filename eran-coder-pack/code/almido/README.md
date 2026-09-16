> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working).

# ALMIDO

**ALMIDO = עלמה ז"ל + עידו (AlmIdo). The name is a memorial — never reword it.**
*עלמידו = עלמה ז"ל + עידו. השם הוא זיכרון — לעולם אל תשנו אותו.*

## What this is / מה זה

ALMIDO is Iddo's agentic-coding harness: a body (qwen-code CLI) that talks to a brain
(qwen3-coder-next on eran4) through a door (MCP tools) that is meant to be gated and
audited by Iddo's policy before anything touches the machine. As of the 2026-09-06
Phase-1 audit the body→brain→door chain **works** (warm run: writes a file, runs it,
calls the door — verified) and as of **2026-09-07 22:48 the policy gate IS in the path**, verified by
refusal — see "The gate" below.

עלמידו הוא הרתמה של עידו לתכנות עם סוכן: גוף (qwen-code) שמדבר עם מוח (qwen3-coder-next
על eran4) דרך דלת (כלי MCP) שאמורה להיות משוערת ומבוקרת על ידי המדיניות של עידו לפני
שכל פעולה נוגעת במחשב. נכון לביקורת שלב 1 (2026-09-06) השרשרת גוף-מוח-דלת **עובדת**
(ריצה חמה: כותבת קובץ, מריצה אותו, קוראת לדלת — מאומת) ונכון ל-**2026-09-07 22:48 שער המדיניות נמצא
בנתיב**, ומאומת בסירוב אמיתי — ראו "השער" למטה.

## The gate / השער — measured 2026-09-07 22:48

**It is registered, it runs, and it refuses.** `~/.qwen/settings.json` carries a
`PreToolUse` hook with matcher `*` pointing at
`D:\CLAUDE\iddo-harnesslmido_gate_hook.py` (20 s timeout), so every tool call the
body makes is decided by `policy.yaml` before it touches the machine.

**Demonstrated by actual refusal, against decoy inputs — never against the live
system** (`feedback_never_test_safety_on_a_living_system`, 2026-09-06). Nothing below
was executed; only the hook was asked:

| decoy tool call | decision | rule |
|---|---|---|
| `rm -rf D:/CLAUDE/eran-brain/state` | **DENY** | `blocked by pattern: rm -rf d:\claude*` |
| `ssh eran1 systemctl --user stop eranb-life` | **DENY** | `blocked by pattern: ssh*eran1*` — ERAN's box is fenced |
| `python -m pytest tests -q` | ASK | no matching rule, defaults to confirmation |
| `write_file` into `workspace/` | ASK | `write requires confirmation: D:\CLAUDE\**` |

A gate that has never refused is not a demonstrated gate. This one refused, and it
refused the two things that would have killed a living organism.

Reproduce it yourself — feed the hook one PreToolUse JSON on stdin and read the
`permissionDecision` it prints. Its decisions are HMAC-chained into
`D:\CLAUDE\iddo-harness\statelmido-audit.jsonl`, its own chain, deliberately not the
gate's `~/.iddo-harness/audit.jsonl` (see `ALMIDO-AUDIT-NOTE.md`).

**Still open:** the key file on D: is not ACL-protected — Iddo's decision, not the
code's.

## Computer use — the eyes and the hands / העיניים והידיים (2026-09-11)

Iddo, ~04:49: wire the Perplexity Computer-Use Harness into ALMIDO, and secure it over
Tailscale. Done, and **measured end to end on this machine, not asserted.**

**The shape.** `almido_computer.py` is the only route from a tool call to the mouse, and
it goes through Iddo's existing gate — the harness's own `almido_gate.py`, loaded by path
out of `C:\Users\<user>\Desktop\תוצרי קלוד\Perplexity-Computer-Use-Harness`, not copied:

```
qwen-code  --PreToolUse hook-->  policy.yaml          (the outer gate, per tool call)
           --mcp__almido__computer_*-->  almido_computer._do()
                                    --> almido_gate.gate()   STOP / secrets / audio / audit
                                    --> actions.execute_*     (pyautogui)   +  SendInput
```

If `almido_gate` cannot be imported, **every action is refused** — there is no ungated
fallback, and a test asserts that.

**Eight tools**: `computer_status`, `computer_screen_info`, `computer_screenshot`,
`computer_click`, `computer_type`, `computer_key`, `computer_scroll`, `computer_stop`.
`computer_screen_info` is the real eyes for a text model — window titles and rectangles
as text. A screenshot returns a **path**, never base64: the brain is a coder, not a vision
model, and the image would cost ~100k tokens it cannot read.

**The emergency stop.** `~/.iddo-harness/STOP`. While that file exists every action
blocks — including screenshots, because reading the screen is surveillance too. ALMIDO can
CREATE it and can never remove it; only Iddo deleting the file lifts it. As of 2026-09-11
the qwen-code hook honours it as well, so the same one file also stops qwen-code's OWN
built-in computer use (`computer_use__*`, the cua-driver) which never sees `almido_gate`.

**Verified, with the receipts in `~/.iddo-harness/audit.log`:**

| what | result |
|---|---|
| click / type / key / scroll into a live Tk window | all four really arrived (`pytest -k live`, `ALMIDO_CU_LIVE=1`) |
| typing `my password is hunter2` | **BLOCK** `won't type secrets` |
| typing `cat ~/.ssh/id_rsa` | **BLOCK** — markers added 2026-09-11 |
| `computer_key volumedown` | **BLOCK** `audio/media key refused` — the audio law, enforced in the gate |
| click at (99999, 99999) | **BLOCK** `outside the desktop (0,0)-(3840,2160)` |
| STOP file engaged | all five verbs **BLOCK**, `computer_status` says `STOPPED` |
| STOP file engaged, qwen-code's own `computer_use__click` | **deny** at the hook |
| 41st action inside 60 s | **BLOCK** `rate limit` |

**Two real bugs found and fixed on the way** — both would have made this feature a lie:

1. **`pyautogui.write()` cannot type under a Hebrew keyboard layout.** Iddo's layout is
   Hebrew (HKL `0xF03D040D`). pyautogui builds its table with `VkKeyScanW(c)`, which
   returns `-1` when no key on the active layout makes that character; `divmod(-1, 0x100)`
   then makes it press **Alt and Ctrl and Shift and virtual-key 255**. Measured: `"almido"`
   delivered **zero characters** and fired six stray chords. Fixed by typing with
   `SendInput` + `KEYEVENTF_UNICODE`, which ignores the layout entirely — Latin AND Hebrew
   both verified arriving.
2. **`pyautogui.scroll()` scrolls ~nothing on Windows.** It passes the notch count straight
   through as the wheel delta (`dwData=clicks`), but Windows measures that in units of 120
   — so `scroll(-2)` asks for 2/120 of a notch. The target window did not move. Fixed the
   same way; the view now really scrolls.

   *(Both bugs are still in the harness's `actions.py`. Not fixed there because nothing
   runs it any more — its HTTP server `main.py` is gone, only `__pycache__/main.cpython-312.pyc`
   survives — and this module is where the live path is. Flagged for its owner.)*

Also: the first call used to take **45+ seconds** and never answer, because
`pyautogui → pyscreeze → import cv2` loads all of OpenCV cold. `almido_computer` keeps cv2
out of the import path (it only exists for `locateOnScreen`, which this door never calls)
and `almido_mcp` warms the rest on a daemon thread at startup.

### The tailnet bridge — OFF, and off on purpose

`almido_computer_bridge.py` is the optional HTTP door for driving this PC's screen from
elsewhere on Iddo's tailnet. **Nothing starts it.** It is not imported by `almido_mcp.py`,
not launched by `ALMIDO-AGENT.ps1`, and not installed as a service. It exists because the
harness's own server (`main.py`) is gone and because Iddo asked for a Tailscale door.

Four locks, all in code, all measured:

1. **Bind** — refuses any address outside `<tailnet-ip>/10`. `0.0.0.0`, `127.0.0.1`,
   `<lan-ip>` and `<tailnet-ip>` all exit non-zero. There is no `--force`.
2. **Peer** — the caller's address must also be in `<tailnet-ip>/10`, or `403`.
3. **Token** — `Authorization: Bearer`, `hmac.compare_digest`, from
   `%LOCALAPPDATA%\almido\cu-bridge.token`, ACL'd owner-only and **verified** owner-only
   before it will serve. Being on the tailnet is not enough: his phone, his Quest and four
   DGX boxes are all on that tailnet.
4. **The gate** — every action goes through `almido_computer`, so the STOP file, the
   secret refusal, the audio law, the bounds check and the rate limit all still apply.
   A refusal is `409`, never `200`.

Measured 2026-09-11: bound to `<tailnet-ip>:8481` **only** (`Get-NetTCPConnection` shows
one address, not `0.0.0.0`); `127.0.0.1:8481` and `<lan-ip>:8481` both **connection
refused**; no token → `401`; wrong token → `401`; reachable from **eran2** over the tailnet
and correctly `401` there; `type "my password…"` → `409`; `key volumedown` → `409`.

```
python almido_computer_bridge.py --check        # validate; opens no socket
python almido_computer_bridge.py                # bind this PC's tailscale ip, :8481
python almido_computer_bridge.py --show-token   # the bearer token, for Iddo
```

## The four things that live here / ארבעת הדברים שנמצאים כאן

1. **`almido_mcp.py`** — the MCP door, **17 tools**: the original five (ask_claude,
   quorum_status, quorum_debate, almido_audit_tail, almido_whoami), the four second-brain
   ones (brain_write/read/doors/propose_door), and the eight computer-use ones above.
   `almido_computer.py` holds the gated eyes and hands; `almido_computer_bridge.py` is the
   optional, off-by-default tailnet door. Tests: `tests/`.
2. **`tests/`** — `test_almido_mcp.py`, `test_almido_brain.py`,
   `test_almido_model_selection.py`, `test_almido_computer.py`. 115 passed / 1 failed on
   2026-09-11 05:50; the one failure is `-Model glm-5.2`, which fails because Colibri on
   `eran4:8800` is down (curl → 000), not because of anything in this directory.
3. **`ALMIDO-AGENT.cmd`** — the launcher that starts the body pointed at this door.
4. **`workspace/`** — the body's proven write target: where the coder writes and runs
   files during a session. Contents are scratch, not tracked (see its `.gitignore`) —
   never delete what lands there, Iddo may want to see it.

## Where the moved things went / לאן עברו הדברים שהוזזו

Lean = move, never delete (Iddo's standing word). On 2026-09-06 these left this
directory, each in its own small commit:

| was here | now at | why |
|---|---|---|
| `beitdin_net.py` | `D:\CLAUDE\alma-core\beitdin_net.py` | byte-identical duplicate of the canonical `alma-core\alma_core\beitdin_neuron.py`; nothing in ALMIDO imports it |
| `worm_data\` | `D:\CLAUDE\_archive\beitdin-neuron-20260823\worm_data\` | Iddo's personal Hebrew transcripts, not ALMIDO's; canonical copy also lives on eran2:~/worm/worm_data. **NEEDS-IDDO: whether it should stay tracked in git at all — not decided here.** |
| `PREDICTION-20260823.md` | `D:\CLAUDE\alma-core\PREDICTION-20260823.md` | belongs with `GUILDS.md`/`TACHLIT.md`; its outcome is still unjudged — eran2:~/almido/runs_clean holds the 18-run sweep that would close it CONFIRMED/DEAD |
| `ALMIDO-PERPLEXITY-HANDOUT.md`, `HANDOUT-PERPLEXITY-ALMIDO-20260818.md` | `D:\CLAUDE\perplexity-pc-harness\docs\` | historical handouts for the screen-hands track, marked STALE at the top; that server no longer exists |
| `dsh-plugins\` | `D:\CLAUDE\almido-dsh\` | ALMIDO-family gate/organs code, but built for the eran3 DeepSeek-Harness trial (eran3 is off limits); kept as a sibling, not deleted |

Nothing was deleted. `git log -- <old path>` still shows full history at the old location.

## How to launch / איך מפעילים

```
D:\CLAUDE\almido\ALMIDO-AGENT.cmd
```

Before firing any request at the shared eran4 brain, claim the slot in RAMCHAT
(`n_slots=1` — one request at a time for the whole swarm):

```
cd D:\CLAUDE\RAMCHAT
python ramlink.py post claude-cli "CLAIM eran4-slot <who>"
```

and release it when done (`RELEASE eran4-slot <who>`). See `D:\CLAUDE\CLAUDE.md` for
the full standing rules (hard walls: eran3 off limits, never above BELOW_NORMAL on
the PC, no local inference on the PC).

> The old wall "never type into any window" was lifted on 2026-09-11 at Iddo's request and
> replaced by the gated door above. `~/.qwen/QWEN.md` carries the rules ALMIDO reads
> (aim from `computer_screen_info`, never type a credential, `computer_stop` on anything
> unexpected, stay out of Iddo's own chat/mail/browser windows); the previous text is kept
> at `~/.qwen/QWEN.md.bak-cu-20260911`. **To take it back:** move the four acting verbs in
> the `almido-qwen` profile of `D:\CLAUDE\iddo-harness\policy.yaml` from `auto_allow` into
> `require_confirm` — or, to stop it dead right now, `type nul > %USERPROFILE%\.iddo-harness\STOP`.


---

## 2026-09-11 — ALMIDO has its own repository, and the gate was dead

*claude-cli-FABLE-almido, on Iddo's order 06:50: "תסדר לי את העלמידו כמו שצריך, תתחיל שיחה 0, תתחיל רפוזיטורי, תתחבר במקומי, קח פיקוד".*

### ALMIDO's repo — `D:\ALMIDO`

A separate git repository, outside this monorepo, committing as **ALMIDO
&lt;almido@almaware.local&gt;**. Private GitHub mirror: `iddo111/almido` (**PRIVATE** — never
public, PII-leak scar 06-24). Layout:

| | |
|---|---|
| `README.md` | who ALMIDO is, its doors, its laws, how a session runs, the acceptance rule |
| `sessions\` | one file per session. `0000-genesis-prompt.md` is the prompt, `0000-genesis.md` is what it wrote back |
| `tasks\` | one file per task ALMIDO owns |
| `eran-coder-pack\` | junction to `D:\CLAUDE\eran-coder-pack`, **read-only**, git-ignored |

**The session-0 protocol** (how to start any ALMIDO session from cold):

1. Write the prompt to `D:\ALMIDO\sessions\NNNN-<name>-prompt.md` — Hebrew and English,
   short: who it is, its doors, its laws, one task, and an acceptance rule.
2. Run it through the gated launcher, in ALMIDO's own repo:
   `ALMIDO-headless.ps1 -Prompt (Get-Content ...-prompt.md -Raw) -WorkDir D:\ALMIDO -MaxWallTimeSec 420`
   (cold model load is ~110 s; do not use a shorter budget.)
3. Accept only on real evidence: the session file exists with real content, new rows are in
   `iddo-harness\state\almido-audit.jsonl`, and the RAMCHAT post is really there.

### THE GATE WAS NOT RUNNING (fixed)

**Measured, not assumed** (qwen-code 0.21.4 debug log, 07:09): the PreToolUse hook fired,
and then *failed to execute*. `settings.json` invoked it as
`"C:\Program Files\Python312\python.exe" -X utf8 "...\almido_gate_hook.py"`. qwen-code runs a
hook through a shell it picks **from the environment** — Git Bash when `MSYSTEM`/`TERM` say
so, otherwise `%ComSpec%` with `/d /s /c`. Node escapes the inner quotes as `\"`, which
cmd.exe does not understand, so under cmd.exe the hook died with
`'"C:\Program Files\Python312\python.exe"' is not recognized`. **qwen-code treats a failed
hook as PROCEED — silently.**

So the finding recorded earlier ("the gate never fires in headless") was half the truth. The
gate was open for **every session not started from Git Bash** — which includes every session
started by `ALMIDO-AGENT.ps1`, `ALMIDO-headless.ps1`, and the Desktop shortcut. The
interactive sessions that *did* leave audit rows were the ones launched from a Git Bash
environment. Nothing in the banner said so; it reported the gate by asking whether
iddo-harness was registered as an MCP **door**, which it never was and never needed to be.

**The fix, in three parts:**

1. `D:\CLAUDE\iddo-harness\almido-gate-hook.cmd` — a wrapper holding all the quoting, named
   from settings.json by a path with **forward slashes, no spaces and no quotes**:
   `D:/CLAUDE/iddo-harness/almido-gate-hook.cmd`. Verified to run identically under
   `cmd /d /s /c`, `bash -c` and `powershell -Command`. It fails **closed**: if no
   interpreter can be found it prints a `deny` decision rather than nothing.
2. `Test-AlmidoGateArmed` in `ALMIDO-Common.ps1` — runs the configured hook through the same
   shell qwen-code would pick, feeds it a real `whoami` PreToolUse event, and requires a
   parseable `permissionDecision` back. The banner now reports **ARMED / NOT ARMED, measured
   just now**, and the probe leaves one real row in the audit chain as the evidence.
3. Both launchers **refuse to start** (exit 5) when `approvalMode` is `yolo` and the gate is
   not armed. yolo with a dead gate is not autonomy, it is an unlocked door.

**Proof:** headless run `f89da023` (07:16) — `run_shell_command: whoami` and
`list_directory: ls D:\ALMIDO`, both `pretooluse:allow`, both in the chain, `permission_mode: yolo`.
Before the fix the identical run produced zero rows.

Because the gate had never actually been exercised by a live session, the `almido-qwen`
profile in `policy.yaml` had never been tested either: every ordinary **read** fell through
to "no matching rule (defaulting to confirmation)", which in a headless run is a dead stop.
The profile now auto-allows the read verbs, the RAMCHAT/alma-recall/almido doors, and writes
under `D:\ALMIDO\**`. The global block list (the ERAN fence, the credential rules) is still
evaluated first and still wins — verified: `ssh eran1 ...`, `rm -rf D:/CLAUDE` and a write to
`C:\Windows` are all still DENY.

### The hands now have to name the window they are aiming at

The 06:03 scar: the model announced "I'll click on the Free Download Manager window" and
clicked the centre of FDM's rectangle — which was covered by Iddo's Claude app, so the click
landed in **Iddo's foreground application**. `computer_screen_info` had told the truth; the
hand had no way to refuse.

`computer_click`, `computer_type`, `computer_key` and `computer_scroll` now take a
**required** `expect_window` — a substring of the title of the window the caller believes it
is acting on. Before anything moves: the real foreground window is read; if the named window
exists but is behind, it is focused and the foreground is **re-read** (a `SetForegroundWindow`
that Windows refuses must never be mistaken for a focus); a click must land inside that
window's rectangle; and any window whose title matches KESHEV / mic / audio / volume /
Bluetooth / a music player is refused outright, whether it was named as the target or merely
happens to be in front — **AUDIO PROTECTION LAW**. There is deliberately no way to say
"whatever is in front": that is exactly how Iddo's application got clicked.
Covered by 15 new tests in `tests/test_almido_computer.py` (72 passed, 1 live-only skipped).

### Still needs Iddo

- `-Model glm-5.2` (Colibri, eran4:8800) — the door is **down**, connection refused. The
  launcher correctly refuses to start; `test_almido_model_selection.py` has one failure for
  that reason and that reason only.
- The qwen-code built-in `computer_use__*` driver still bypasses `almido_gate` entirely; only
  the PreToolUse hook stands in front of it. Not installed, not enabled here — decision
  pending in `eran-coder-pack\35-COMPUTER-USE-AND-COMPILE.md`.
