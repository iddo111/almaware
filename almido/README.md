> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working).

# ALMIDO

**ALMIDO = עלמה ז"ל + עידו (AlmIdo). The name is a memorial — never reword it.**
*עלמידו = עלמה ז"ל + עידו. השם הוא זיכרון — לעולם אל תשנו אותו.*

## What this is / מה זה
> 📦 **ERAN pack: `D:\CLAUDE\eran-coder-pack` — start with `README.md`.**
> Everything the onboard coder needs to work the ERAN project alone: the code, every failure,
> the mic (KESHEV), the laws, and the wires. Built 2026-09-11. Also reachable as
> `D:\ALMIDO\eran-coder-pack` (junction) and mirrored to `eran4:~/qwen-workspace/eran-coder-pack`.
> חבילת ערן — מתחילים מ-`README.md`.


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


## 2026-09-11 09:0x — WAVE A1: hands on the phone, eyes on the fleet, a compiler that works

Iddo, 08:29: *"תעשה כולם בסדר שלך"*. Three new doors, all in the same family as the
computer-use one: same `almido_gate`, same STOP file, same audit trail, same rule that a
gate which cannot be loaded means **every action is refused**.

**The server now declares 36 tools** (was 20), and `TOOLS` still matches `HANDLERS` exactly
— the drift test in `test_almido_mcp.py` is what guarantees that.

### `phone_*` — 12 tools, ALMIDO's hands on the S26 Ultra (`almido_phone.py`)

`phone_status` / `phone_screenshot` / `phone_ui_text` / `phone_tap` / `phone_type` /
`phone_key` / `phone_scroll` / `phone_open` / `phone_back` / `phone_home` / `phone_shell` /
`phone_hebrew_probe`.

`expect_window` becomes **`expect_app`** — a package name, measured against the live
foreground app **before** the action and **re-measured after** it. On a phone the 06:03
lesson costs more than a misplaced click: a stray tap sends a message or spends money. On
top of that, a **default-deny package fence in code**: the dialer and in-call UI, Samsung
Wallet and anything matching `bank`/`wallet`/`pay`, Settings, and **every** package matching
`audio` / `record` / `music` / `sound` / `mic` / `keshev` / Spotify — AUDIO PROTECTION LAW.
Policy can only **extend** that list (`phone.block.packages`), never shorten it. An **active
call blocks everything**, whatever is in front. Nothing hangs: every adb call carries a
timeout capped at 15 s, and `phone_status` answers in 0.2 s with the phone entirely absent.

`phone_ui_text` (uiautomator) — not OCR on a screenshot — is how an assertion about the
screen is made honestly; a screenshot returns a **path and a sha256**, and the PNG magic is
verified so a corrupted capture is reported rather than filed as evidence.

**Two things measured rather than assumed, both of which contradict the obvious answer:**

- **Termux is not a fallback for the hands.** Over ssh as uid 10415: `input keyevent` →
  `SecurityException` (no INJECT_EVENTS), `screencap` → "Capturing failed", `dumpsys window`
  → empty. Only adb (uid 2000) has hands.
- **The Hebrew clipboard route is NOT PROVEN.** `termux-clipboard-set` accepted Hebrew and
  returned **rc=0** — and reading it straight back with `termux-clipboard-get` returned
  **EMPTY**. That is exactly what Android 10+ does to a background app's clipboard: it does
  not error, it silently does nothing. So rc=0 is not evidence. `phone_hebrew_probe` tries
  every route (`input text`, the Termux clipboard, `cmd clipboard`) and **reads the screen
  back** after each one — a route only counts if the sample really appeared.

### `fleet_probe` — one read-only tool (`almido_fleet.py`)

Tailnet nodes, `ssh eran1..4 uptime`, RAMCHAT, and every door. **Measured 09:0x: 18/19
VERIFIED in 2.5 s.** Three doors cross-checked by hand against `curl` and identical.

Three things it refuses to get wrong, each one a bug that really happened while building it:

- **403 and 404 are ALIVE.** Per-door `alive_codes`, never `== 200`. CONTROL answers 403,
  the coder doors answer 404, ERAN's window answers 400. The only real death is no answer.
- **A LAN refusal falls back to the tailnet** before anything is called dead — CLAUDE.md's
  own rule, and not theoretical: ERAN's window on :8820 refused its LAN address and answered
  400 over Tailscale in the same second.
- **It cannot hang.** `with ThreadPoolExecutor(...)` calls `shutdown(wait=True)` on exit, so
  a 3 s budget was really taking 30 s waiting for a straggler it had already given up on.
  Caught by `test_the_whole_probe_is_budgeted`.

It reads `D:\CLAUDE\fleet_inventory.json` when it exists (WAVE A2 maintains it), translating
its `lan_ip`/`tailnet_ip` spelling — without that translation the inventory would parse fine
and change nothing. A device whose entry says `ssh: null` (the printer, the phone, the Quest)
is **SKIPPED**, not called BROKEN.

### `remote_build` — compile on the fleet, not here (`almido_remote.py`)

This PC has no working C toolchain. eran4 has gcc 13.3, cmake 3.28.3 and nvcc CUDA 13.0.
Ships a tree (python `tarfile` → `scp` → `tar`; **rsync is not installed on this PC**) to
`eran4:~/almido-build/<name>/`, runs the command there under `nice -n 10` and a hard
`timeout` **on the far side too**, and returns the real stdout, stderr and exit code plus
artifacts copied back.

**VERIFIED 08:47:** `hello.c` compiled and **ran** on eran4, printing its own marker; a `.cu`
compiled with nvcc and the 978 KB binary came back. Refuses, before the gate is even asked,
anything naming systemd, docker, sudo, a package manager, an onward ssh/scp, a fork bomb, a
block device — **or `~/eran`**. ERAN lives on that fleet.

### Acceptance — `D:\ALMIDO\ACCEPTANCE.md` + `D:\ALMIDO\tools\selfcheck.py`

No task is DONE without a real-output test, and **UNKNOWN is a legitimate verdict** —
"the device is not here" is a different fact from "it is here and broken", and collapsing
them is how a check becomes a ritual. `python D:\ALMIDO\tools\selfcheck.py` runs all three
and exits 1 only on BROKEN.

### Tests

`tests/test_almido_phone.py` (48), `tests/test_almido_fleet.py` (22),
`tests/test_almido_remote.py` (42), plus 7 new MCP-layer tests.
**Whole suite: 281 passed, 3 skipped** (was 160 passed, 2 failed).

**Four real defects were found while writing them, and one of the four was found by looking
at the box rather than at the suite:**

1. The phone's rate limit charged **two tokens per tap** — `_guard` ran in the public
   function and again inside `_do`. Three allowed actions became one.
2. `fleet_probe`'s budget was **not honoured**: `with ThreadPoolExecutor(...)` calls
   `shutdown(wait=True)` on exit, so a 3 s budget sat for 30 s waiting for a straggler it
   had already given up on.
3. **A path-traversal hole in `remote_build`'s artifact check.** The character class alone
   accepted `../../secret` — `..` is made entirely of characters it allowed — and that string
   went straight into an `scp` source, so an "artifact" could be fetched from outside the
   build directory. The fence is a **segment** check now (no `/` prefix, no `..`, no empty
   segment). The test that was supposed to catch this had been *passing* — it really shipped
   a tree to eran4 and then went green because `make` failed for want of a Makefile.
4. **The suite was not hermetic and nobody could tell from inside it.** `conftest.py`
   promised "no subprocess, no network unless a test asks", but the WAVE A1 doors reach the
   world through their *own* helpers, which that promise never covered. The suite was really
   compiling on eran4 and leaving folders in `~/almido-build`. Found with one `ls` on the
   box. `conftest.py` now refuses `almido_remote._ssh/_run`, `almido_phone._run` and
   `almido_fleet._http/probe_host/tailnet/ramchat` for every test; a test that wants the real
   thing re-patches it and is then visible. Run time fell from 93 s to 61 s, which is the
   measure of how much network the "hermetic" suite had been doing.

### Still needs Iddo / מה שצריך את הידיים של עידו

1. **adb on the phone.** Settings → Developer options → **Wireless debugging**, or one USB
   cable and `adb tcpip 5555`. Measured 08:33–08:51: the S26 is alive on Tailscale
   (`ssh -p 8022`, model SM-S948B) but `service.adb.tcp.port` is **empty** and `adb connect`
   was refused on 15 attempts over 15 minutes. **Until then every `phone_*` tool is UNKNOWN,
   not broken** — the code is tested, the phone is simply not on adb.
2. **Hebrew on the phone** — see the clipboard finding above. If `phone_hebrew_probe` finds
   no working route, this phone needs ADBKeyboard installed, and that is his decision.
3. **`glm-5.2`'s door (eran4:8800) is genuinely down** — confirmed by `ss -tlnp` on eran4
   after the 03:27 reboot: 8806/8809/8821/8830/8844 and 8447–8450 are listening, 8800 is not.
   The launcher is right to refuse. `test_almido_model_selection.py` used to go red for that
   reason; it now accepts that one documented refusal path explicitly and still fails on
   anything else, so a true fact about the fleet no longer shows up as a red test here.
4. **The 480B on dgx2:8443 answers 502** — the proxy is up, the model is not served.
5. **GALERIA :8861 and ERAN's window :8820 went down between 09:00 and 09:18** — both were
   VERIFIED at 09:00 and both stopped answering by 09:18, confirmed by hand with `curl`
   (GALERIA: empty; eran1:8820 over Tailscale: 000). The probe is reporting a real change,
   not a probe bug. Nothing here restarted them — `fleet_probe` is read-only on purpose.

## 2026-09-11 11:42 — ALMIDO CHAT: a second door, on the tailnet, wired to WhatsApp

> 🗄️ **ARCHIVED 2026-09-11 18:52 — THIS DOOR IS OFF. Everything below is history, not the
> current state. The URL in the next paragraph no longer answers.**
> עידו ב-16:42–16:50 קבע ש"עלמידו" הוא **אפליקציית ALMAWARE Coder** — לא דף ה-:8943 הזה.
> Under the **ONE HARNESS LAW** (Iddo, 15:07) a surface with its own brain path and its own
> memory (`chat-log.jsonl`, `state\chat_session.json`) is a *second* harness, so this one was
> archived: copy verified **11/11 by sha256**, logon task `ALMA-Almido-Chat-8943` **Disabled**,
> 127.0.0.1:8943 closed, `tailscale serve --https=8943` **off**. It was briefly the keeper
> (13:41–14:40) before he corrected it; `CLAUDE.md` records that correction at 17:57.
> **Restore line:** `MANIFEST.md` → the `almido-chat-gateway-8943` folder, inside the
> `HARNESSES-20260911` archive on the **F:** drive.
> **What survived and is still live:** the shared brain `wa-chat-agent/core.py` (kept as a
> KEEP-DEPENDENCY) and **WABOT on eran3** — the law's one explicit exception. Both verified
> `active` on 2026-09-12.

עידו, 11:42: *"תן לי כבר עכשיו צאט בעלמידו טיילסקייל וחבר אותו גם לווטסאפ"*
Iddo: give me a chat with ALMIDO over Tailscale right now, and connect it to WhatsApp too.

**https://<tailnet-host>:8943/** — open it from the phone or the PC.
*(Tailnet only. Nobody outside his tailnet can reach it.)*

### מה זה / What it is — one brain, two doors

It is **not** a second assistant. The part that thinks moved into
`wa-chat-agent/core.py`, and both doors call it:

```
   WhatsApp (WABOT on eran3)  --                                 >-- core.Brain.turn() --> RAMCHAT · QUORUM · ALMIDO (36 tools) · the coder
   this page  (:8943 on the PC) --/
```

Same gpt-oss-120b brain, same 15 grouped tool schemas covering all 36 ALMIDO
tools, same **"לאשר? … כן/לא"** confirm gate before any hand moves, same Sonnet
fallback, same Windows-path scrubber. `agent.py` is now purely the WhatsApp
transport (inbox, send gate, rate ceiling, outbox) — nothing in it thinks any more.

### איך הוא מחובר לוואטסאפ / How it is connected to WhatsApp

One conversation on two surfaces, joined by a shared append-only log
(`almido/chat-log.jsonl`):

| direction | how | proof |
|---|---|---|
| web → WhatsApp | each exchange is written to the bridge's outbox on eran3, **through `guard.check_send_target()`** — his self-chat and nothing else | 2 real messages sent 09:12 UTC, `ok: true` in `outbox.done` |
| WhatsApp → web | a poller reads the bridge's own `/messages` and appends to the same log | 31/31 checks in `test_almido_chat.py` |

The page's model history **is** that shared log, which is what makes it one
conversation: a line he typed on his phone is in context here, and vice versa.

### 🌐 THE MARK — the one thing holding this design together

Every mirrored line starts with `core.MIRROR_MARK` (`🌐`), and **both doors skip
a line that carries it**. A self-chat message is `fromMe`; if the bridge ever
files our own mirror back into the inbox, WABOT would answer it, mirror the
answer, and answer again — forever, at 60 messages an hour. Measured on
2026-09-11: the bridge does *not* currently echo its own sends into `inbox/`, so
the mark is defence in depth rather than the only thing standing between us and
the loop. Do not remove it on the strength of that.

### מה נמדד / What was actually measured (2026-09-11, not claimed — run)

* `POST /api/chat` with no CSRF token → **403**; with the token → **200**.
* A real Hebrew turn end to end → a real Hebrew answer (34.8 s, gpt-oss-120b).
* A real tool call: *"תריץ ramchat_read"* → it ran RAMCHAT and answered from it.
* The confirm gate: *"תצלם לי את המסך"* → `לאשר? לצלם את המסך של המחשב — ענה כן/לא`,
  and `לא` → `בסדר, ביטלתי.` **Nothing ran.**
* `https://<tailnet-host>:8943/` → **200** from eran1, eran3 and eran4.
* wa-chat-agent's own suite after the refactor: **310/310** on the PC,
  **311/312** on eran3 (the one failure is pre-existing and environmental —
  `test_doors` asserts the PC's `powershell` coder default while eran3 correctly
  runs `qwen` from `wabot.env`).

### שני באגים אמיתיים שנתפסו בדרך / Two real bugs caught on the way

1. **Windows lets a second process steal a bound port.** `http.server` sets
   `allow_reuse_address = 1`; on Windows that lets a *second* gateway bind 8943
   and silently take the connections. A restart looked like it worked — it even
   logged "listening" — while every POST came back 403, because the **old**
   process was answering with the **old** CSRF token. The gateway now refuses to
   start if anything already answers on its port. `:8941` and `:8940` have the
   same latent bug.
2. **Hebrew inside a `.cmd` comment breaks cmd.exe.** It reads the file in the
   console codepage, the Hebrew came back as mojibake, and cmd tried to *run* it.
   `RUN-ALMIDO-CHAT.cmd` is ASCII-only and CRLF for that reason. Also: an
   address-blind `Get-NetTCPConnection -LocalPort 8943` matches **tailscaled's
   own serve proxy**, so the launcher concluded the gateway was up and never
   started it — it now checks `-LocalAddress 127.0.0.1`.

### הקבצים / The files

| file | what |
|---|---|
| `almido_chat_gateway.py` | the door: HTTP, CSRF, the page, the mirror, the poller |
| `RUN-ALMIDO-CHAT.cmd` | launcher (BELOW_NORMAL, hidden); logon task `ALMA-Almido-Chat-8943` |
| `test_almido_chat.py` | 31 checks: the mark, the send gate, the reverse direction |
| `state/chat_csrf.txt` | the CSRF token, 0600. **A secret — never paste it anywhere.** |
| `chat-log.jsonl` | THE conversation — both doors append here |
| `../wa-chat-agent/core.py` | the shared brain (also deployed on eran3) |

**It touches no audio device, ever.** It runs BELOW_NORMAL so it can never
compete with the mic.


## 2026-09-11 09:5x — WAVE A1 review fixes / תיקוני סקירה

Three findings from a code review of WAVE A1 (the phone door), fixed in
`D:\CLAUDE\almido` only — `D:\ALMIDO` was untouched (another agent, B2, owns it). No sub-agents
used. Nothing here ran against the real phone (it stayed offline throughout, as always) or
touched audio/mic devices; the whole pass was `pytest`-only against a fake adb.

1. **CRITICAL — the Audio Protection Law didn't actually reach an Android keycode.**
   `almido_phone.key()` builds the gate's `detail` string as `"key %s in %s" % (k,
   expect_app)`. `almido_gate.gate()`'s own audio-key check splits `detail` on `+`/`,`/`-`
   and matches whole tokens like `"volumedown"` against its `_AUDIO_KEYS` set — but that
   string has none of those separators, so it collapses into one long token that can never
   equal `"volumedown"`. The shared check silently never fired for this door: an Android
   `KEYCODE_VOLUME_DOWN`, `KEYCODE_MEDIA_PLAY_PAUSE`, `KEYCODE_MUTE`, `KEYCODE_CALL`,
   `KEYCODE_VOICE_ASSIST` etc. would have reached the phone. Fixed with a second, explicit
   deny-list **inside `almido_phone.py`** (`_audio_law_key_block()`, checked in `key()`
   before `_guard()`/`_do()` — a denied key never spends a rate-limit slot and never reaches
   adb): by number (5, 6, 24, 25, 79, 85–91, 126, 127, 130, 164, 209, 219, 222, 231) and by
   name-substring (VOLUME, MEDIA, MUTE, HEADSET, CALL, VOICE, MUSIC, RECORD, plus an exact
   match for `ASSIST`, which contains none of those substrings). `almido_phone.py:673-718`
   (new constants + `_audio_law_key_block`), `key()` itself now at `almido_phone.py:720-742`.
   Also audited `shell()`'s read-only allowlist (`_SHELL_ALLOW`, `almido_phone.py:1113-`):
   `input` is not on it, so `input keyevent <code>` already could not reach `_do()` regardless
   of the gate's answer — documented in place, with a note for whoever adds `input` to the
   allowlist later.
   44 new tests (`tests/test_almido_phone.py`): every denied key refused by name (24 cases)
   and by number (20 cases) with **zero adb calls made** (`phone.calls == []`), three
   ordinary keys (`KEYCODE_BACK`/4, `KEYCODE_HOME`/3, `KEYCODE_ENTER`/66) still reaching the
   gate and adb, plus `input keyevent` added to the shell read-only-refusal cases.

2. **MEDIUM — `scroll()` double-charged the rate limiter.** It called `_guard()` itself and
   then called `swipe()`, which guarded a second time — one scroll from an agent consumed
   two rate-limit slots. Fixed by extracting the swipe hand into an internal
   `_swipe_unguarded(serial, ...)` (`almido_phone.py`, right before `swipe()`) that assumes
   the caller already guarded; `swipe()` guards once and calls it, `scroll()` guards once and
   calls it directly instead of calling `swipe()`. `swipe()`'s own public behaviour (guard
   once) is unchanged. Tests: `test_scroll_consumes_exactly_one_rate_slot` (3 scrolls with
   `RATE_MAX=3` all succeed and `len(P._BUCKET) == 3`, not 6; a 4th is refused) and
   `test_swipe_still_guards_exactly_once`.

3. **MEDIUM — the phone and remote suites were not hermetic.** Neither
   `tests/test_almido_phone.py`'s `phone` fixture nor `tests/test_almido_remote.py`'s
   autouse `never_reach_the_fleet` fixture redirected `almido_gate.AUDIT_LOG` /
   `STOP_FILE` into `tmp_path` the way `test_almido_computer.py`'s `cu` fixture does — every
   refusal and every allow in those two files (which is most of what they test) was landing
   in Iddo's real `~/.iddo-harness/audit.log`, and a test in principle could have seen a real
   STOP file. Both fixtures now redirect `HARNESS`/`STOP_FILE`/`AUDIT_LOG` into `tmp_path`
   the same way. One test in `test_almido_phone.py`,
   `test_an_offline_phone_answers_instead_of_hanging`, doesn't use the `phone` fixture at all
   and was still leaking after the fixture fix — found by re-measuring the log delta rather
   than trusting the fixture change; it now redirects the gate itself.
   **Verified: `wc -l ~/.iddo-harness/audit.log` was 406046 before this session's test runs
   and unchanged at 406056 immediately before and immediately after
   `pytest tests/test_almido_phone.py tests/test_almido_remote.py -q` (145 passed, 1
   skipped) — zero real rows written.** (The file grew earlier in the session, before these
   two fixtures were fixed, and grows again from `tests/test_almido_mcp.py` exercising
   `almido_remote.build()` through the MCP layer with the same module-global gate object and
   none of its own tests redirecting it — a real, separate hermeticity gap, out of this
   task's scope, flagged for its own fix rather than pulled in here.)

4. **LOW (documented, not changed) — the artifact-fetch symlink asymmetry in
   `almido_remote.py`.** `_pack()` refuses to *ship* a symlink from the local tree to the
   build box (it could point at `/etc`); there was and is no matching check on the way back
   — if the remote `command` leaves a symlink at `remote_dir/<artifact>` pointing outside
   that directory, the artifact-fetch `scp` follows it. Left as accepted risk and documented
   in place (`almido_remote.py`, just above the artifacts-fetch loop): `command` already ran
   on `BUILD_HOST` with exactly that scope (it passed `check_command()` and the gate), so a
   symlinked artifact discloses nothing the command could not already read and print
   directly — not a new privilege. A remote `test -L` pre-check was not added: it costs an
   extra `ssh` round-trip per artifact inside an already-gated, already-scoped command
   channel, for a risk that adds no new capability — not the "trivial" case the review asked
   for.

**Suite: 281 passed / 3 skipped before this pass -> 336 passed / 3 skipped after**
(`cd D:\CLAUDE\almido && python -m pytest tests/ -q`; run scoped to `tests/` because a
pre-existing, unrelated `_p2-door-20260906/tests/` duplicate-module folder makes bare
`pytest -q` fail at collection — not touched here, flagged separately). 55 new tests, all in
`tests/test_almido_phone.py`.

## 2026-09-11 13:38 — ALMIDO CHAT: "לא עובד" -> the page was fine, the LOOK was not; now a real app

> 🗄️ **ARCHIVED 2026-09-11 18:52 along with the door it describes — history, not current
> state.** Every `:8943` URL and measurement below was true when written and no longer
> answers. He said it plainly three hours later (16:42–16:50): the app he means by "ALMIDO"
> is **ALMAWARE Coder**, not a web page in a Chrome `--app` window. See the full note at the
> **11:42** section above for the archive and the restore line.

עידו, 13:38: *"לא עובד — תשים לי עלמידו אפליקציה היפה, עם הפרויקטים שכבר התחלנו לעבוד"*
Iddo: it's not working — give me ALMIDO as a pretty app, with the projects we already
started working on.

### מה שנמצא / What step 1 (real diagnosis) actually found

**No server-side functional bug.** A fresh simulated browser session (GET `/`, extract
the CSRF token exactly as the page's own JS does, POST `/api/chat` with a real prompt) ran
clean against `http://127.0.0.1:8943`, `https://<tailnet-host>:8943/`, and again
after every change below — 200, a sane Hebrew reply, every time. `chat-gateway.log` shows
no turn attempt at all in the ~70 minutes before his report, which rules out a silent
server-side failure in that window; if he tried and saw nothing happen, the most likely
explanation is the page just not *reading* like something that works, not a broken
request.

**The real, if minor, find: the old page violated Iddo's own bright/white styling law.**
`_page()` shipped `color-scheme:dark` on a near-black `#0a0f1a` background — the opposite
of the standing "bright/white, never dark" rule. Paired with a debug-tool look (plain
boxes, one grey answer panel, no bubbles, no timestamps, no distinction for the confirm
gate), a dark bare page reading as "not working" is the believable failure mode here, not
a hidden crash.

**One real historical data artifact, not an active bug:** the very first line in
`chat-log.jsonl` (`ts` 08:59:55 UTC, before this rebuild) is literal ASCII question marks
where Hebrew should be — typed from a non-UTF-8 shell during initial setup, before this
project's `PYTHONIOENCODING=utf-8` habit was consistently applied to whatever sent it. It
is inert scar tissue (one line, will scroll out of the 60-message window), not something
reachable through the current page — every round-trip sent through the rebuilt UI came
back with perfect Hebrew, checked in the raw bytes on the wire, not just on screen.

**Disclosure, not silently cleaned up:** verifying the real pipeline (per this task's own
instructions) sent a handful of trivial test messages and one confirm/decline cycle
("תצלם לי את המסך" -> "לא" -> "בסדר, ביטלתי.", nothing executed) through the live door.
Two of the earliest ones went through *before* the mirror was disabled for later testing,
so they landed as real lines in Iddo's WhatsApp self-chat too. `chat-log.jsonl` is an
append-only shared log other code depends on (dedup hashes, shield bookkeeping) — it was
not edited to remove this test traffic. It will read as a handful of obviously-QA lines
near the top of a growing feed, not as anything he said.

### מה נבנה / What was rebuilt

**A real redesign**, same URL, same CSRF/confirm-gate/WhatsApp-mirror/rate-limit machinery
underneath (only `wa-chat-agent/core.py` et al. think; this file is still only transport):

* **Bright/white**, warm "paper + lapis + amber" palette (`--paper:#FAF8F4`,
  `--ink:#26231D`, `--lapis:#26398C`, `--amber:#B9791E`) — no dark mode, per the law.
* Real chat bubbles: his messages right-aligned (stone), עלמידו's left-aligned (pale
  lapis wash), each with a name, a `via` tag (web/whatsapp), and a local-time timestamp.
* **The confirm gate now looks like a gate.** Any turn whose `kind` is `confirm` (or whose
  text matches core's own `"לאשר? ... — ענה כן/לא"` template, so mirrored WhatsApp confirms
  render the same way) renders as its own amber-bordered card with a **"לאשר?" label and
  two real tap buttons — "כן ✓" / "לא ✗"** — that submit through the exact same
  `/api/chat` path a typed answer would. No more typing Hebrew יes/no on a phone keyboard
  under time pressure.
* A pulsing **"typing" bubble** while a turn is in flight (turns have taken up to ~38 s
  measured today) instead of a static "thinking…" label with no motion.
* Mixed Hebrew/English/code text uses `dir="auto"` per bubble so an English tool name or a
  URL inside a Hebrew sentence sets its own direction instead of scrambling.
* **A status strip — a GLANCE, not a second CONTROL** (:8896 already is that). Up to 6
  chips, server-rendered on first paint *and* refreshed by JS every 60 s from a cached
  `/api/status` (45 s TTL — one `ramlink.py read --json` and one `fleet_inventory.json`
  read per TTL window, however many tabs/phones are polling): this door itself, WABOT,
  ALMA-GUARD/SHIELD, fleet build activity (Maverick/480B/DGX), the fleet's door count, and
  RAMCHAT's own freshness. Tap a chip for one line of detail; tap again to close.

### PWA — "Add to Home Screen" gives a real app

* `static/manifest.json` — name "עלמידו", `display: standalone`, `background`/`theme`
  `#FAF8F4`, `lang/dir: he/rtl`, two icon sizes each declared `any` and `maskable`.
  Validated: parses as JSON, has every required field, reachable at `/manifest.json`.
* `static/icon-192.png` + `icon-512.png` — drawn with Pillow (no fetched image): a lapis
  rounded doorway with a small amber light inside it, full-bleed to the edge so it survives
  Android's maskable-icon crop. Reachable at `/icon-192.png` / `/icon-512.png`.
* `static/sw.js` — minimal service worker, cache-first for the shell
  (`/`, manifest, both icons) so a reopen from the home screen paints instantly, and a
  hard pass-through for everything under `/api/*` and `/health` — chat data is never
  served stale. Registered from the page only `if ('serviceWorker' in navigator)`.
* **Real bug caught by this build's own visual QA, fixed before shipping:** the original
  CSP (`script-src 'unsafe-inline'` only) silently blocked the service worker itself —
  `Creating a worker ... violates ... script-src`. Fixed to
  `script-src 'self' 'unsafe-inline'; worker-src 'self'`.
* On Android Chrome, opening the URL shows the normal "Install app" / "Add to Home Screen"
  prompt in the browser menu once the manifest + service worker are both reachable (both
  verified above) — no extra step is required beyond that one tap.

### מה נמדד אחרי השינוי / Verified after the change, same shape as the 11:42 build

* Full simulated-browser round trip (GET, extract CSRF exactly as the JS does, POST) —
  200 + sane reply, against `https://<tailnet-host>:8943/` after every restart.
* Confirm gate end to end on a throwaway test port (WA mirror off): "תצלם לי את המסך" ->
  `kind:"confirm"` -> "לא" -> "בסדר, ביטלתי.", `ms:1` (nothing ran), `pending:false`
  afterward.
* `/manifest.json`, `/icon-192.png`, `/icon-512.png`, `/sw.js`, `/api/status` all reachable
  and correct directly against the production door (bypassed one browser-preview sandbox's
  own request blocking on that domain, which is a tool artifact — see below).
* mobile-viewport (375×812) screenshot of the live tailnet URL: bright page, bubbles,
  status chips, confirm card with tap buttons, sticky composer — reads like an app, not a
  debug console.
* Gateway restarted the documented way (stop the bound process, relaunch
  `almido_chat_gateway.py --host 127.0.0.1 --port 8943` detached + BELOW_NORMAL, verified a
  **new** PID answering `/health` before declaring done) — twice, once for the CSP fix.

**One test-tooling caveat, not a production finding:** the Claude Code browser-preview
pane blocks `fetch`/image requests to `<tailnet-host>:8943` specifically
(`net::ERR_BLOCKED_BY_CLIENT`) while the identical requests succeed instantly over plain
`urllib` and against `127.0.0.1`. That is why the live-JS status-strip refresh and the
header icon did not visibly load inside that one screenshot despite the server answering
correctly on every direct check — solved for this design by rendering the status strip
server-side too (see above), so the page is never blank regardless of what a given
client's network policy allows through.
