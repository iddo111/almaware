# INSIGHTS FOR KESHEV 2 — everything A learned, in buildable form

> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

**Purpose:** spec input for the fleet workers building KESHEV 2 (Iddo's order, 2026-08-17 21:05: "קשב א' פלוס... יותר טוב, עם כל התובנות מקשב א'"). Every item below was PAID FOR — a measured failure, not an opinion. KESHEV 2 must honor all of it and beat the baseline in §7.
**תקציר:** כל תובנה מקשב א', מזוקקת לרשימה הנדסית. כל שורה כאן עלתה בכאב אמיתי. קשב 2 חייב לכבד את הכל ולנצח את מדדי הבסיס בסעיף 7.
**Sources:** PHASE1-INQUIRY.md (57 scars — still law), PHASE2-DESIGN.md, git history of this repo, the KESHEV B verdict (D:\CLAUDE\keshev-b\VERDICT-CLOSED-20260817.md).

---

## 1. The 57 scars, distilled to their 12 load-bearing laws

The full register is PHASE1-INQUIRY.md §2 and remains binding. The essence:

1. **Model load lifecycle is the killer, not decode throughput.** Every catastrophic outage was a load event. KESHEV 2 keeps ZERO large-model code on the PC; anything resident is loaded once and never unloaded (scars 8–15, 57).
2. **One instance, one launcher, no watchdog wars.** Kernel mutex; exactly one launch mechanism; any restarter has a day-one circuit breaker and one human override that STAYS stopped (scars 1–7).
3. **Never lose speech, never lie about it.** Write-ahead disk spool BEFORE enqueue; evict = drop the record, keep the file; stale backlog decodes to recovered.txt, NEVER into live focus; every drop journals a line (scars 16–20).
4. **Success return values lie.** SendInput reports ok while UIPI discards everything; `TYPED ok` lied for weeks. Only round-trip verification of what the receiver GOT counts (scar 19; pulse.py and selftest.py are this law as code).
5. **Sacred Audio is above the config layer.** `_NEVER_MIC` is a source-level tuple checked before any open, with zero merge logic — an emptied config cannot re-expose Bluetooth. No audio-output call site exists anywhere; lint gate G6 greps for it (scars 21–25).
6. **Gate noise BEFORE the GPU, in measured layers.** Energy gate → auto-gain → webrtcvad → decode guards → logprob floor → hallucination blocklist → language whitelist. Every layer exists because the previous one alone failed (scars 26–30).
7. **Paste-first typing, focus verified, no clipboard restore, Enter as a separate re-verified burst.** Compare windows by HWND+PID+exe, never title (scars 31–38).
8. **Config: CAS writes only, one writer, unknown keys preserved, HALT on corrupt — no defaults fallback, no write-on-exit, no .bak.** LKG = git tag, nothing else. Calibration values carry their measurement (scars 39–43).
9. **The environment is hostile and gets worse weekly.** 4-core CPU at 80% cap under 100% load; 8GB GPU with 4.6GB taken; 17-item logon storm. Decouple boot from readiness; capture within seconds with zero models loaded (scars 44–48, 12).
10. **Privacy fails closed, deafness fails open.** Corpus capture is gated and opt-in; the typing path is never blocked by an unproven identity claim. Transcripts and voice WAVs never enter git (scars 49–50, 55; re-verified 2026-08-17 — 8 tracked WAVs had to be evicted).
11. **One typer serialization point; request-id dedup; a synchronous router makes double-typing structurally impossible,** not policed (scars 53–54).
12. **Acceptance = Iddo dictates through it live.** `health: ok` counts for nothing (scars 51–52, criterion 16).

## 2. The guard-species taxonomy — guards written but structurally unable to fire

A's most repeated bug class. Four instances paid for, a fifth found 2026-08-17. **The countermeasure is tests/test_wiring_discipline.py: a module (or threshold, or verdict) only its own tests exercise IS NOT SHIPPED.** KESHEV 2 must run an equivalent discipline from K0.

| # | Guard | How it was dead | The cost | The fix |
|---|---|---|---|---|
| 1 | **logprob floor** (textguard layer 5) | Floor -1.0 sat BELOW the entire measured distribution of 138 real decodes (worst: -0.913). Written, wired, journalled, unit-tested — never fired once. | The model said "I'm guessing" (-0.9) and KESHEV typed the guess as confident Hebrew; it invented "רפורמים" and Claude argued religion with him about a word he never said. | Floor recalibrated to -0.6 FROM DATA (drops worst 14%); a test now asserts the floor is REACHABLE by real decodes (commit 941bfb0). |
| 2 | **K15 tray** | State machine, icons, balloons, DEAF red-flash: all built, all tested. The Shell_NotifyIcon DRAWING backend was never built — no icon exists on any screen. | 2026-08-14 17:22: the tray had DEAF exactly right, on a lamp nobody could see, for four hours. | Journalled honestly (`TRAY_BACKEND_HEADLESS`) + the Tk window (client/window.py) as the real visible surface. Icon backend still unbuilt — inherit as a K2 task or kill the tray concept and keep the window. |
| 3 | **inner Silero VAD** (langpolicy) | Guard against hallucination-on-silence, placed INSIDE the HE decode — after the client had already eliminated silence (gate_rms, blip guard, webrtcvad). Nothing it was aimed at could reach it. | It fired on the only thing left: REAL speech. 3 of 8 measured real segments returned EMPTY — "the mic ate my word". | vad=False everywhere since 2026-08-14; silence defense lives on the client, in front. If hallucination returns, tighten the CLIENT, never re-add the inner VAD (langpolicy.py lines 136–151). |
| 4 | **mic-switch audit verdict** | The capture audit computed `can_prove_free` correctly and the switch DECISION didn't consult it — the verdict reached the report, not the refusal. | A flip could proceed on an audit that admitted it couldn't prove the mic was free. | "The verdict must reach the DECISION" test (test_mic_switch.py); fail-closed on unattributable sessions (commits 766e561, 941bfb0 part 2). |
| 5 | **hotkey_pause** (found 2026-08-17) | `parse_hotkey` refused malformed specs with a lecture about silent non-binding — and NO production code ever called RegisterHotKey. A guard around a mechanism that did not exist. | The config promised a pause key since K1; pressing it did nothing, silently. | client/hotkeys.py binds for real; HOTKEY_BOUND / HOTKEY_BIND_FAIL journalled; 9 pump tests (commit e393285). |

**The law for KESHEV 2:** every guard ships with a test that proves it CAN fire on realistic input (reachability), and a wiring test that proves production actually calls it. "Present, correct, not in the path" must be a build failure.

## 3. The 09:46 presence scar and its two answers

**The scar (58):** 2026-08-15 09:46 — Iddo out of the room, a video playing. Eight TYPED events in nine seconds, each with Enter, sent into his chat AS HIM ("Welcome to Art Racer.", "Hola, saludos."). Every existing guard passed, because every guard answered a different question: right device, real speech, not a hallucination, allowed window. **Nobody asked whether the person whose name goes on the message was there.**

**Answer 1 — presence gate (client/presence.py, live since 08-15):** reads the OS last-input clock. Two limits because the harms differ: idle ≥ 120s → type but NEVER Enter (junk in a box is recoverable; SUBMITTING as him is not); idle ≥ 600s → type nothing. Fail-open on type, fail-closed on Enter when the clock is unreadable. 32-bit tick wrap handled (49.7-day mute otherwise).

**Answer 2 — the arm switch (from KESHEV B's verdict, built 2026-08-17):** Qwen's stronger claim — "no body, no key press, no typing" — as an OPTION layered over (never instead of) the presence gate. `presence.ArmSwitch`: ctrl+alt+a toggles, arms expire after 15 min (an arm that never expires re-creates 09:46), disarmed speech is parked never dropped, `ARMED_MODE=False` shipped. **KESHEV 2 decision point:** whether armed mode is the DEFAULT. The idle clock answers "has someone touched this machine"; the arm key answers "did he mean it". B died producing that sentence; don't lose it.

**Event-vocabulary lesson learned on the way:** PRESENCE_REJ ≠ OWNER_REJ ≠ ARM_REJ. Three gates, three questions, three event names — reusing a scored event's name for an unscored gate raised TelemetryFieldError the first time it fired live, and only the end-to-end tests (real Telemetry, not a fake emitter) caught it.

## 4. Language routing — every rule here was measured on his own voice

* **The LoRA NEVER detects language** — it tags English "he" p≈1.0 and transliterates (scar 29).
* **`language=None` is unrepresentable** — "the single line that let noise come back as Icelandic".
* **Low confidence → whitelist ARGMAX, not forced Hebrew.** Measured: median detection confidence on his real dictation is 0.454 (74% of utterances are "low confidence"); forcing he on English audio makes Whisper TRANSLATE — fluent Hebrew he never spoke, invisible to him. A wrong argmax is visibly wrong in the wrong script; he sees it and fixes it. Visibly wrong beats invisibly wrong.
* **vad=False on every decode** (see species #3).
* **A standing lang hint is a standing order, and both values are wrong** — hint=auto transliterated Hebrew ("סוכה"→"suka"); hint=he wrote English in Hebrew letters. He code-switches mid-session. The dual-decode idea (decode ambiguous short clips twice, model confidence picks) is designed but OFF: enabling it on 2026-08-16 12:21 silenced ALL decodes for 1h50m (SEGs flowed, spool spilled, zero DECODE events) — do not re-enable without a test asserting a DECODE event follows a SEG (router.py comment).
* **eran1 decodes his Hebrew at CER 0.000 on the clean fixture set, ~390ms** — when routing is right, the model was never the problem.

## 5. Watchdog / supervision lessons (tools/keshev-watchdog.ps1)

1. **Health = TEXT IN HIS WINDOW,** not process-alive, not even segments-captured. The watchdog printed "healthy — 52 segments in 10 min" through 1h50m of total muteness because it counted HEARING. Verdicts now require the middle of the pipe: MUTE = segs without decodes, spool overflow without drain, decodes without types.
2. **Session scoping:** judge a live process only by journal lines after ITS OWN SESSION_BEGIN — the watchdog's first live run restarted a healthy process on a dead session's errors.
3. **Young sessions get grace** (worker warm-up ≈ 95s journals nothing) — DEAF before the session is old enough is a restart loop.
4. **An alarm nobody sees is the scar with one file's indirection.** ALARM used to be a log line; a whole night of dictation died behind it. Now: any FAULT verdict that ends WITHOUT a restart pops a bright topmost window (keshev-alarm.ps1) — Hebrew+English, Restart-now + Dismiss buttons, VISUAL ONLY (Sacred Audio; a test greps the alarm code for every sound call). Deduped 30 min.
5. **Read-only status must exist** (`-Status`): the question "what do you see?" must never be the thing that restarts the mic.
6. **PowerShell trap:** `Get-Content -Tail` on a one-line file returns a bare string; indexing it yields CHARACTERS and the SESSION_BEGIN scan silently never matches. `@()` everything.
7. **Restart caps:** ≤1 per 10 min, ≤4/hour, then alarm-and-stop. A watchdog that restarts a broken app forever is a fork bomb with patience. It never starts KESHEV while alma-mic lives (ONE-MIC), never touches audio devices, never deletes.

## 6. Operational truths

* **Read the error code before declaring hardware dead.** The BRIO was "dead in hardware" in memory files and probes for a day — its PnP problem code was 22 = CM_PROB_DISABLED: someone had turned it off. Every probe saw silence and promoted the inference to a fact; Iddo was told to buy a new mic for a camera that was switched off. `Get-PnpDevice | select Status, ProblemCode` costs three seconds.
* **pulse.py is the health-check KESHEV 2 should wire in** (EAR: real frames + RMS off the device; BRAIN: known fixture through the real decode path, CER-scored; HAND: UIPI round-trip). It is deliberately UNWIRED in A because EAR opens the capture device — running it beside a live capture is the double-mic scar. KESHEV 2's supervisor may run it ONLY when the app is confirmed down.
* **The schema, the schema file, and the config must move together** — the live lang_hint patch edited two of three and the drift test caught it. New config keys must be OPTIONAL (a required new key HALTs the running mic at its next restart).
* **Live-but-uncommitted is a standing hazard:** twice now (f5aa807, 776fd73) the tree serving Iddo's dictation contained uncommitted fixes. Commit what runs.
* **Never open a second capture of the live mic. Never restart the live process for a refactor.** Stage, and let the owner choose the restart moment.
* **Environmental test honesty:** tests that assert about the REAL machine must corroborate, skip honestly, or probe for a WORKING tool (the suite failed for days on `which bash` finding the broken WSL stub, and on "KESHEV does not exist yet" after it existed).

## 7. ACCEPTANCE BASELINE — KESHEV 2 must beat A, never regress

Measured 2026-08-17, live session `24ca194b` (pid 24032), engine dgx (eran1:8737), all read-only:

| metric | KESHEV A, measured | how measured |
|---|---|---|
| test suite | 878 tests, 0 failures, 19 skips (all environmental), ~177s | `unittest discover -s tests` |
| lint gates | 6/6 clean + 6/6 self-test fire | `tools\lint.py`, `--self-test` |
| DGX decode round-trip (real Hebrew WAV, 2.4s audio) | 407ms wall / 399ms server, rtf 0.166 | POST /v1/transcribe with token + request-id |
| client p50 / p95 decode (live heartbeat) | 387–388ms / 720–758ms | state\events.jsonl HEARTBEAT |
| client RSS / worker RSS / worker VRAM | 68 / 825 / 537 MB | HEARTBEAT |
| dropped capture frames | 0 | HEARTBEAT drop_frames |
| server canary age / uptime | <300s / 2.9 days | GET /health |
| watchdog verdict on the live journal | HEALTHY (seg=57 decode=58 typed=3 / 10 min) | `keshev-watchdog.ps1 -Status` |
| real-he guard regression | CER 0.0000, n=40, 0 guard-dropped | criterion-10 suite line |
| Hebrew decode quality (clean fixtures vs eran1) | CER 0.000 | repo fixture set |

Plus the 23 acceptance criteria of PHASE1-INQUIRY.md §4 — still the bar, criterion 16 (a full live dictation day) still the final gate.

## 8. Open windows in A, honestly (K2 inherits or closes them)

1. Tray icon drawing backend UNBUILT (`TRAY_BACKEND_HEADLESS` in every session) — the window is the real UI.
2. `owner_gate_typing` (voice identity, criterion 18) honestly unbuilt: the config switch exists, configstore REFUSES to flip it without a PASS gate18 report, no ownergate module exists.
3. Config changes reach the typer only on restart — no hot reload, by design; know it when staging fixes.
4. KESHEV logon task NOT installed; the app is launched by hand (RUN-KESHEV.cmd). Boot survival is one `install_client.ps1` run away — deliberately left as the owner's call.
5. KESHEV-Watchdog task exists but is DISABLED (stopped 2026-08-16 during the BRIO outage restart-loop). Re-enable: `Enable-ScheduledTask -TaskName KESHEV-Watchdog` — also the owner's call; it holds Stop-Process authority over the live mic.
6. `dual_decode` OFF pending understanding of the 12:21 postmortem (§4).
7. `ARMED_MODE` OFF — the B-verdict option, awaiting Iddo's ruling on default-on.
8. STATE journal lines carry a stale engine label ("unproven — no decode yet" after thousands of decodes) — cosmetic honesty bug, unfixed.

---

*לזכרה של עלמה ז״ל. Real, not demo. Proof, honest.*
