# PHASE 1 — ועדת חקירה: Microphone Rebuild Inquiry Brief

> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

**Date:** 2026-08-12 · **Order:** Iddo, 08:08 — "archive all the microphones, rebuild from scratch — slowly, clean, and the best."
**Inputs:** 7 investigator lanes — log history (71,538 lines / 18 days), alma-mic code archaeology, config-drift archaeology (22 .bak files), voice-input predecessor autopsy, environment characterization, institutional memory & laws, DGX offload feasibility.
**Status of old mics:** alma-mic stays live as crutch until the new mic passes acceptance; all old mic apps archived (not deleted) at cutover. No one else takes mic work.

---

## תקציר בעברית

**למה כל מיקרופון נשבר?** לא בגלל ה-STT עצמו. שלושה רוצחים חוזרים:

1. **טעינת המודל היא נקודת המוות.** טעינות שהיו 10–40 שניות הידרדרו ל-4–6.5 דקות; כל דיבור בזמן טעינה נזרק בשקט (141 פינויי תור היום); מופעים כפולים טענו שני מודלים במקביל על כרטיס של 8GB. כל "תקוע" של היום — 07:52–08:01 — התחיל בטעינה.
2. **ריבוי מופעים ומלחמות watchdog.** שני משגרים (Startup + Scheduled Task), supervisor שמחייה גופות (393 respawns ביום אחד), קוד אכיפה שמעולם לא רץ. חוק ה-ONE-MIC נשבר חמש פעמים מתועדות.
3. **אובדן שקט ושקרים של "הצלחה".** `TYPED ok` בזמן ש-UIPI זרק את כל ההקלדות; תור מלא שזרק דיבור חדש; clipboard restore שהדביק תוכן ישן; config שנמחק בשקט ביציאה.

**הסביבה עוינת:** CPU בן 4 ליבות מוגבל ל-80% ורץ על 100%; GPU של 8GB שכבר 4.6GB תפוסים ע"י שולחן העבודה; סופת עלייה של 17 קיצורי Startup + 10 משימות logon.

**המלצה:** **אופציה B (מתוקנת ע"י הוועדה)** — לקוח דק על ה-PC (לכידה + VAD + הקלדה בלבד, אפס טעינת מודל גדול ב-boot) + שרת STT על DGX ב-systemd (מארח מועדף: **eran1**, לא ה-hub), עם **fallback מקומי קטן שיושב חם ב-GPU** (מודל CT2-int8 קטן, ~1GB, טעון פעם אחת ולעולם לא נפרק). ה-fallback חייב להיות חם כי הצי מאותחל **כל לילה ב-02:00** — failover הוא אירוע יומי מתוזמן, לא חירום נדיר. זה מוציא מה-PC את שני הרוצחים האמיתיים — מחזור טעינת המודל הגדול ותחרות ה-GPU של מודל 3GB — במחיר כן ומוצהר של ~1GB קבועים. דורש אישור של עידו לחריגה ממדיניות הצי (DGX 1-3 = Qwen בלבד).

**חשוב עכשיו (לפני ה-rebuild):** ה-config החי של alma-mic מכיל `"avoid": []` — אפס הגנת Bluetooth ברגע שה-BRIO מתנתק. הפרת חוק השמע הקדוש פעילה היום. לתקן מיד.

---

## 1. VERDICT — Ranked Root Causes

### RC-1: Model load/reload lifecycle is the killer, amplified by GPU contention (SEVERITY: CRITICAL)

Every catastrophic "stuck mic" episode is a load-phase event, not an inference event.

- Load time degraded 10–20x over the log's life: 10–40s early → 216–315s **on the same turbo model** before the LoRA switch → 100–394s now. Full readiness worst case: **483.7s (8 minutes)** after launch. (Log lanes: lines 58269/63885/64139/68852-68854.)
- Speech captured during a load is **silently thrown away**: 141 of the log's 143 QUEUE FULL evictions happened today, all bracketing load windows; 62 evictions in 67 seconds at 07:53. Plus 10 STALE skips of segments that waited 157–162s.
- **~5.5 model (re)loads per day** (100 MODEL READY events / 18 days) multiply the outage: every reload = minutes of deaf mic.
- Double-loads confirmed 5 times: two interleaved loader threads today at 07:54:17 (offsets +132.6s/+106.6s) each loading HE+EN pairs on the 8GB card; three MODEL READY lines list the EN model **twice**; the app once held **three** models (line 67081). Mechanism found in code: a shared stop Event cleared by the next start() revived "stopped" threads (pipeline.py:67-84), and join(timeout=2s) can't kill a thread stuck in a 2-minute import.
- Decode-time collapse under contention: p50 462ms but p99 9.1s, max **180.5s for a 2.3s utterance**; today 29.6s for 1.5s of speech. Successful-decode realtime factor p10 is 0.6 — slower than realtime.
- Environment lane confirms: measured decode is x0.9–x2.8 realtime at steady state with a single instance — **"the rebuild's enemy is startup and contention, not throughput."**

### RC-2: Multi-instance sprawl and watchdog wars (SEVERITY: CRITICAL)

- ONE-MIC LAW broken 5 documented times (2026-06-20 three mics at once; 06-21 two Startup shortcuts; 06-30 supervisor respawn after retirement; 08-08 "שני מיקרופונים רצים במקביל"; 08-09 double-typing). 2026-08-06: THREE instances (pids 30112/22816/27688) each loading large-v3-turbo on the 8GB card — the "500 years to answer" bug.
- voice-input's supervisor: 631 child starts, 509 quick exits, a **393-respawn storm in one day**; its `_enforce_single_mic` countermeasure was **dead code — defined, never called**. Two watchdog systems each authorized to kill the other's processes.
- The supervisor respawned an ImportError-corpse for **38 days** (07-01→08-08) because "process started" was its only health signal.
- Fossil record in the Startup folder today: `ALMA Mic LKG.lnk.disabled-duplicate-launc...`, `ALMA-MIC.lnk.disabled-canonical`, alongside the still-running ALMA-MIC-Elevated task.

### RC-3: Silent data loss + lying success signals (SEVERITY: HIGH)

- **UIPI:** SendInput returns success while elevated windows silently discard every keystroke — "TYPED ok lied for weeks" (MSDN-documented; selftest_uipi.py:1-23).
- **Queue policy:** drop-newest on full = "I speak and nothing happens"; a 100s decode typed sentences minutes late into whatever had focus.
- **Clipboard restore race:** restoring 120–230ms after Ctrl+V made slow apps paste the user's PREVIOUS clipboard — a whole night of Hebrew dictation lost (2026-08-07).
- **Per-char SendInput loses events** in long bursts (79-char utterance arrived with all spaces stripped); terminals discard KEYEVENTF_UNICODE entirely.
- EMPTY decodes were a silent `continue` while Iddo saw "not working". Meta-lesson from the code lane: *success return values lie; only round-trip verification of what the receiver got counts.*

### RC-4: Config drift, silent corruption, and uncalibrated knob-churn (SEVERITY: HIGH)

- `Config.save()` = `json.dump(asdict(self))` on exit → **any key not in the running schema is silently deleted** (beam_size vanished and returned across three baks; en_model's default was made non-empty specifically to survive its own deletion — the config system is designed around its own corruption bug).
- `speech_rms_gate` drifted through SIX values in 5 weeks with zero calibration records; at 0.001 it sat **inside the measured ambient band for 4 days** → 13,332 EMPTY decodes wasted 172 minutes of GPU and saturated the pipeline (RC-1's fuel).
- 22 one-symptom fixes in 23 days pulled overlapping knobs in opposite directions (lang_confidence 0.6→0.85→1.01→0.55 by different sessions); code comments contradict live values.
- **ACTIVE VIOLATION TODAY:** `"avoid": []` in live config.json since 2026-08-06 — zero Bluetooth protection at the config layer the moment the BRIO unplugs. Survived 16 subsequent fixes including a BT-incident fix. (Mitigated only by the hard-coded `_NEVER_MIC` tuple in audio.py and exact-name pinning.)
- Silent fallback to defaults on corrupt config yields gate=0.070 — ~12x above measured speech RMS → a **completely deaf mic with no error message**.

### RC-5: Hostile environment never designed for (SEVERITY: HIGH — a constraint, not a bug)

- CPU: 4-core i7-7700K, administratively capped at **80% clock** (thermal), measured at **100% load**. Competitors won't yield: chrome ~1,830 CPU-s, claude.exe ~2,360 CPU-s, audiodg 824 CPU-s, ~25 resident python processes.
- GPU: 8GB RTX 3070 Ti in WDDM mode with **4.6GB already consumed** by desktop compositing at near-idle → ~3.6GB budget for STT, into which the app loaded 2–3 models.
- **Logon boot storm:** 17 active Startup items + 10 logon-trigger scheduled tasks firing in ~90 seconds; the mic burns 105–132s on imports before loading even begins. The calendar of this PC is rewritten weekly (ant tournament moved, Hybrid-Watchdog fires every 10 min forever).

### RC-6: Device-resolution fragility (SEVERITY: MEDIUM — mostly solved in alma-mic, must carry over)

- 7 prior inquiries all reduced to wrong/dead/reset device: MME silent for USB mics; WASAPI shared-mode rejects forced 16kHz (-9997); WDM-KS exclusive-only (-9999); Windows reboot reset BRIO capture level 100%→69% (all-GATED signature); hard avoid-filters twice left ZERO microphones; default-follower aliases (Sound Mapper) grabbed the wrong mic; 136 device-loss events in one child log.
- The Bluetooth trap created the SACRED AUDIO LAW: opening a BT headset mic flips A2DP→HFP and wrecks Iddo's audio. Two past "fixes" un-banned the headset and caused exactly this.

### RC-7: Memory-unsafety by architecture (SEVERITY: MEDIUM — proven fixed pattern exists)

- voice-input leaked **113 MB/min** (never survived past 23.7h; exits: -1, heap corruption 0xC0000374, access violation 0xC0000005); the "fix" was gc.collect() on ~30 return paths + EmptyWorkingSet cosmetics.
- alma-mic's bounded-queue + copy-out design soaked at 300 inferences with flat RSS (+0MB) — the correct pattern is known and proven.

### RC-8: Privacy exposure of an always-on mic (SEVERITY: MEDIUM, standing)

- Formal inquiry 2026-06-16: the mic captured third parties' private conversations (incl. Iddo's mother) into transcripts and the LoRA corpus (~1,500 contaminated lines); content landed in local git history. Owner-only speaker gate existed in code but was never enabled by config.

---

## 2. SCAR REGISTER — Constraints the Rebuild MUST Honor

Deduplicated from all 7 lanes. Each scar is law; each carries its "why". Grouped, numbered continuously.

### A. Process & instance discipline

1. **Single instance via named kernel mutex** (e.g. `Global\ALMA_MIC_SINGLE`), held for process life; a second instance exits <1s with a log line. *Why:* three simultaneous instances on 2026-08-06; kernel mutex is OS-released on death, lock files are not.
2. **Exactly ONE launch mechanism** — a scheduled task OR a Startup shortcut, never both; at install, disable/archive every other mic's persistence (Startup .lnk, tasks incl. ALMA-MIC-Elevated pattern, Run keys, supervisors). *Why:* two logon launchers caused instance accumulation; retired mics came BACK via surviving persistence.
3. **No auto-respawn watchdog that fights the user.** Max N restarts with a circuit breaker ON from day one, rate-limited (≤1 per 10 min), and ONE obvious human override that stops everything and stays stopped. *Why:* 509 quick-exit respawns incl. a 393-storm; the escalation ended in `taskkill /F /IM python.exe` nuking every python on the PC.
4. **No rival enforcement/kill-wars; enforcement code must be proven to run** (test that it executes). *Why:* `_enforce_single_mic` was dead code while double-typing raged; coordination code written but never wired in is worse than none.
5. **Health = real output, not process-alive:** watchdog verifies device-open + transcription heartbeat end-to-end. *Why:* a corpse was respawned for 38 days on "process started".
6. **Fail LOUDLY at startup** if a dependency is missing — visible error, no path-hunting imports. *Why:* the 06-27 folder reorg silently killed the mic for 38 days via a 5-path sys.path hunt.
7. **Watchdog restarts wait for confirmed clean shutdown** of the previous generation. *Why:* today's collapse began with two DEVICE starts 26s apart spawning concurrent loaders.

### B. Model lifecycle (the RC-1 laws)

8. **Single-flight, idempotent model loading** behind a lock; pause/resume or device-restart must NEVER spawn a second loader or stack a second model in VRAM; assert exactly one HE + (optionally) one EN model resident. *Why:* 5 double-load episodes; EN model listed twice in one MODEL READY line; doubled VRAM = decode-time collapse.
9. **Load once, keep resident; device changes reconnect audio WITHOUT touching the model.** If a reload is unavoidable: **blue/green swap on the DGX server side only** (it has the memory for two models); on the PC's ≤3GB budget blue/green is VRAM-impossible — local swap is explicit-unload → buffer-to-ring → load, with the GUI honestly showing LOADING and the DGX path (or nothing) serving meanwhile. *Why:* every reload now costs 4–6.5 min and 100% of today's speech loss happened inside reload windows; two resident models on the 8GB card is the RC-5 disease, not a cure.
10. **Fresh stop-Event per pipeline generation;** never assume join(timeout) means dead. *Why:* shared-Event zombie revival = two captures on one mic + two models + double-typed text.
11. **Validate CUDA with a real dummy inference** before trusting it (CUDA can "load" with no cuBLAS/cuDNN DLLs). Secondary model loads in background so the primary goes live immediately. *Why:* Windows CPU-torch trap; serial cold boot blocked readiness 2–3.5 min.
12. **Decouple boot from readiness:** capture and buffer audio within ~2s of launch with zero model loaded; show honest LOADING vs READY state; budget for model-ready up to 8 min after logon. *Why:* boot-storm measurements; the mic must never depend on winning the logon race.
13. **Hard per-segment decode timeout (5–10s) with REAL cancellation — which mandates the local decoder run in a killable SUBPROCESS.** A CT2 decode is a blocking C++ call; a Python thread cannot cancel it, and this inquiry's own evidence proves join(timeout) leaves zombies (pipeline.py). Therefore: local decode engine = separate process (own CUDA context), timeout = kill the subprocess and respawn it (subprocess death frees VRAM deterministically); the DGX path cancels by abandoning the HTTP request with a request-id so a late reply is discarded (scar 53). Latency watchdog: if 1-min decode p50 > ~2s, alert and restart the decode worker — **kill-and-respawn for a stuck decode** (a stuck decode never drains by definition), drain-first only for graceful config swaps. *Why:* one 180.5s runaway decode stalls the whole pipeline and reads as "stuck"; the zombie-thread mechanism must be architecturally impossible, not merely discouraged.
14. **VRAM budget ≤ ~3GB total, one model resident at a time preferred,** explicit unload before swap, startup VRAM probe that degrades gracefully instead of OOM-ing. *Why:* 8GB card minus 4.6GB desktop compositing; the app once held three models.
15. **Investigate load-time root cause** (disk/page-cache/VRAM fragmentation/thermal cap) as its own work item — degradation happened on the SAME model before any LoRA switch. Target: cold load <60s, warm reconnect <5s, measured. **Scoping (committee): the warm-resident fallback decision (scar 57) takes this OFF Option B's critical path — the fallback never cold-loads in operation — but it remains a HARD GATE before any Option-A promotion (where the local large model's load lifecycle returns), and a gate on trusting criterion 5's cold-load number.** *Why:* environmental degradation shrinks every outage even when other bugs occur; unexplained 100–394s loads must not be waved through into any primary path.

### C. Never lose speech; never lie

16. **Never drop speech silently:** audio captured while the recognizer is unavailable goes to a disk-backed ring buffer (minutes deep) and is decoded on recovery. **Recovery policy (resolves the 16↔17 contradiction found in review): recovered backlog older than the stale threshold is decoded but routed to a reviewable transcript file (`recovered.txt` + GUI notice "N recovered utterances, click to view") — NEVER typed into the live focus.** Only segments fresher than the stale threshold type live. If dropping raw audio is ever forced, the user is told the mic is deaf RIGHT NOW via a non-audio, in-eyeline signal (tray flash + toast; never a sound — Sacred Audio). *Why:* 141 evictions of live speech today experienced as "stuck" with zero feedback; but typing minutes-old sentences into whatever has focus is the RC-3 disaster — "zero words lost" and "never type stale" can only both hold if stale recovery goes to a file, not the typer.
17. **Segment queue: bounded, EVICT-OLDEST on full only after spilling the evicted segment to the ring buffer/transcript path, timestamped, stale guard** (segments >~25s old when fresher speech waits are diverted to the recovered-transcript file per scar 16, not silently skipped), every eviction/diversion logged. *Why:* drop-newest was the freeze; stale typing minutes late reads as "frozen"; `except queue.Full: pass` was silent loss; a "skip" that discards words violates criterion 4 — divert, don't drop.
18. **Every silent drop leaves a log line** (gated, empty, evicted, stale, focus-fail, type-fail) with decode ms + realtime factor + rms + avg_logprob. Ship the diagnostic decision tree (all-GATED = level problem; TYPED-ok-but-nothing = UIPI) in the repo. *Why:* "log showed nothing while Iddo saw not working"; latency must be a number to be fixable.
19. **Never trust success return values — round-trip verify.** UIPI self-test types through the real typer into a same-integrity child and reads back what it RECEIVED. *Why:* SendInput/MSDN: neither return value nor GetLastError indicate UIPI drops; "TYPED ok" lied for weeks.
20. **Structured telemetry by design:** full dates in every log line, per-minute heartbeat (queue depth / VRAM / decode p50), BEGIN/END session markers with session id, rotating size-capped logs. *Why:* this inquiry had to infer 18 days from midnight rollovers and detect double instances from interleaved offsets; mic-child.log hit 10.1MB unrotated with a leaked handle per spawn.

### D. Device law (SACRED AUDIO — non-negotiable)

21. **USB wired mics ONLY (BRIO primary, Scarlett fallback). Hard-coded, source-level `_NEVER_MIC` deny-list** — bluetooth, hands-free, headset, wh-1000xm4, a2dp, hfp, airpods — plus loopback list (stereo mix, loopback, virtual, audiorelay, Sound Mapper, Primary Sound Capture), applied BEFORE any probe/open. **Enforcement point named explicitly: the source-level `_NEVER_MIC` tuple is the SOLE authority — the device layer checks it directly, unconditionally, with no config input to that check. The config-layer deny-list is purely additive-cosmetic (extra user entries only); no merge logic in config-loading code may ever stand between the tuple and the device open** (merge logic is itself config-layer code of the kind that was silently emptied on 2026-08-06). If no allowed mic is live: IDLE, honestly announced — no fallback, ever. *Why:* BT mic use flips A2DP→HFP and wrecks Iddo's audio (happened; law of 2026-08-09); the avoid list was emptied by config in 2026-08-06 and is STILL empty — safety must live above the config layer.
22. **Never open, claim, duck, mute, or degrade any audio OUTPUT device.** *Why:* Sacred Audio Law; music = Iddo's flow state; audiodg belongs to him.
23. **Device selection by evidence:** rank host APIs WASAPI > DirectSound > WDM-KS, never MME; prove liveness with an RMS probe (floor 0.0008 over 0.5s); "avoid" is a soft demotion never a pre-probe veto; **an explicit user-chosen mic wins unconditionally and is not probe-gated;** same-physical-mic fallback chain across host APIs with 3 open retries + 0.4s sleep. *Why:* MME silent for USB; hard filters twice left zero mics; probe-gating the chosen mic wandered to the BT headset; transient WASAPI "Unanticipated host error".
24. **Open at the format the device accepts** (try 16k mono → native → 48k/44.1k), downmix, and resample to 16kHz in-callback with an anti-aliasing windowed-sinc FIR (cutoff ~0.45×16k, state carried across callbacks). *Why:* BRIO rejects forced 16kHz (-9997); aliased HF energy makes Whisper hallucinate; FIR discontinuities click at seams.
25. **Silent-but-open devices trigger periodic re-resolve; re-check/restore Windows endpoint capture level after reboot.** *Why:* the 69% level reset silently killed the RMS gate (all-GATED signature); 136 device-loss events in one log.

### E. Silence, noise & hallucination defense (proven layered order)

26. **Gate noise BEFORE the GPU** — cheap CPU-side energy gate + real VAD pre-enqueue; target noise-to-speech decode ratio near 1:1 (today: 10.5:1). *Why:* 13,332 EMPTY decodes wasted 172 min of GPU and caused the latency collapse.
27. **Defense in depth, in this exact order:** (1) energy gate drops silence pre-model; (2) auto-gain peak-normalizes quiet-real speech ONLY when original rms ≥ floor (~0.004, cap 40x); (3) Silero VAD inside the Hebrew decode; (4) decode guards: temperature [0,0.2], beam 1, condition_on_previous_text=False, compression_ratio 2.4, no_speech 0.6; (5) post-hoc avg_logprob < -1.0 drop; (6) hallucination filter; (7) off-whitelist language drop. *Why:* every layer exists because a prior layer alone failed — Silero is NOT amplitude-invariant (faint speech = silent empty decodes); amplifying ambient noise typed "חחח".
28. **Multilingual hallucination blocklist incl. Hebrew attractors** (תודה family, כתוביות, subscribe-junk, amara.org, CJK/Russian) matched on FULL normalized text; plus detectors for repeat-loops, 8+ char-runs, low-variety, 1–2-char junk, AND 3–5-char laughter blobs (חחח/אהה) while guaranteeing real words (אבא/אמא) pass. **The guard runs as the FINAL step before typing, after all text mutation; exactly ONE copy of the guard code.** *Why:* laughter blobs sat below the char-run thresholds and typed all night; guards ran on raw_text while text mutated afterwards; three drifting copies of hebrew_stt.py caused silent regressions.
29. **Language routing:** never use the Hebrew fine-tune as a language detector (it tags English "he" p≈1.0 and transliterates). Stock multilingual model detects; whitelist he/en locked; failed detection falls back INSIDE the whitelist (never `language=None` — "the single line that let noise come back as Icelandic"); confidence ~0.85 with re-decode tie-break; low confidence defaults to Hebrew; EN decodes run WITHOUT inner Silero VAD + script-mismatch retry (>50% Hebrew chars in an en decode → re-decode). *Why:* all measured on real failing clips (ווי פאי, "flying corals", טוקינג אינגליש).
30. **Never feed context back as initial_prompt.** *Why:* Whisper regurgitates it verbatim — prior conversations typed into later utterances (2026-06-14).

### F. Typing & focus (SendInput has no destination)

31. **Paste-first for EVERY window** (clipboard + Ctrl+V = 4 events, atomic); per-char Unicode SendInput only as fallback with surrogate-pair support. *Why:* long bursts silently lose events (spaces stripped from a 79-char utterance); terminals discard KEYEVENTF_UNICODE entirely.
32. **NO automatic clipboard restore** (opt-in only; wait ≥1.0s; restore only if the clipboard still holds exactly what was pasted). *Why:* the 120–230ms restore race pasted STALE content for a whole night; "Iddo lost a whole day to this."
33. **Clipboard ctypes discipline:** c_void_p handles (int truncation → ERROR_INVALID_HANDLE), wstring_at reads (c_wchar_p segfaults), ~12x OpenClipboard retry. *Why:* each was a crash or silent failure in production.
34. **Focus guard:** hard-block the app's own window and title-less windows even in "anywhere" mode; restore focus to last-external target via a 0.25s focus-watcher (Z-order-behind first, memory second) and VERIFY the change; compare windows by HWND+PID+image-path, **never title** (terminal spinner glyphs rewrite titles every tick); strip Unicode Cf controls; deny browser top-levels in allowlist mode; double-snapshot foreground immediately before SendInput. *Why:* every rule maps to a real mis-type: into its own window, sticky-to-Claude, the desktop (renamed files), or wrongful refusal on spinner-title changes.
35. **Refuse to type if focus cannot be verified** — report a real error, park the text, offer re-type. *Why:* 173 TYPE FAILED events were recoverable text discarded; blocked-guard cases (OpenWith.exe, explorer) are transient.
36. **Auto-Enter as a SEPARATE burst after ~0.35s** that re-verifies the same target. *Why:* single-burst Enter raced slow apps and submitted empty/half lines.
37. **Elevation decided once, up front — and recorded as a TRADEOFF, not a settled fact:** the default is elevated launch (elevated can type into elevated terminals; the reverse is UIPI-impossible), but the committee notes this makes a network client that POSTs audio always-elevated — a larger blast surface, and the same shape as the ALMA-MIC-Elevated fossil (RC-2). The alternative (non-elevated default + elevated helper on demand) is parked as a documented option; if the elevated default is kept, the audio-POSTing engine SHOULD run in the non-elevated decode subprocess where the process split allows it. UIPI failure must be detected and reported, never silent; ALT-tap + AttachThreadInput restore_focus with verification polling. *Why:* UIPI ate all keystrokes into elevated terminals (2026-06-30); SetForegroundWindow from Task Scheduler fails silently.
38. **The mic never launches apps or steals focus:** no os.startfile, no window-opening voice commands without a wake word, window never topmost/foreground; global pause hotkey retained. *Why:* bare-word commands opened Notepad which stole foreground and swallowed dictation; topmost made the mic type into itself.

### G. Config & change management

39. **No rewrite-on-exit, no asdict round-trip.** Config written only by explicit "config set"; runtime state in a separate file; unknown keys PRESERVED; every write bumps a revision + appends old→new diff with reason to config_history.jsonl; compare-and-swap refuses stale writes. *Why:* asdict-on-exit is the proven key-drop mechanism (beam_size vanished; en_model default engineered around its own deletion); concurrent multi-agent edits must be loud, not silent.
40. **No silent fallback to defaults:** corrupt/missing config → HALT with visible error. *Why:* the fallback path yields gate=0.070 which deafens the mic with zero output.
41. **Calibration-carrying thresholds:** every perceptual knob stored as {value, calibrated_at, method, measured_floor, measured_speech, author}; app refuses a gate inside its own recorded noise band or above measured speech; startup drift check compares configured gate vs live measured floor and warns loudly. *Why:* gate=0.001 sat inside the ambient band for 4 days unnoticed; the data to catch it existed and was never compared.
42. **One knob per failure mode, schema-validated (0..1 etc.), --reason required;** config lives in git — no .bak-suffix copies, no parallel LKG snapshot systems. **The ONE LKG mechanism is a git tag (`lkg`) moved only by a passing acceptance run; "one-command restore" (scar 43) = `git checkout lkg` — the same mechanism, not a second one.** *Why:* 22 unlabeled interventions in 23 days pulling overlapping knobs in opposite directions; out-of-range hacks (1.01); archaeology took a full lane; the 42↔43 ambiguity as originally written is exactly the kind that spawned 22 .bak files.
43. **One canonical directory, no live hot-patching;** debug on the offline replay rig (mic-debug-vm pattern), deploy once verified; LKG = the git tag of scar 42, restored by one command. *Why:* three files hot-patched the same morning the mic fought the boot storm made environment vs code failures indistinguishable; standing order since 2026-06-26.

### H. Resources & environment

44. **Memory correctness by architecture:** single-owner audio buffers with deterministic lifetime, bounded frame queue (~200) drop-on-full, copy out of driver buffers immediately, context-managed close, drain on exit; **the restartable STT subprocess is MANDATED, not considered** (it is the only real cancellation mechanism — scar 13 — and its death frees everything); RSS self-monitored with graceful self-restart at threshold. **No gc.collect() sprinkling, no EmptyWorkingSet cosmetics.** *Why:* 113 MB/min leak, ~24h max survival, heap corruption exits; the bounded design soaked flat (+0MB over 300 inferences).
45. **CPU budget: ≤~1 sustained core** of a thermally-capped 4-core; all decode compute off the CPU; ABOVE_NORMAL priority for the capture thread only, never realtime; explicit decode timeouts/backpressure because contention WILL happen. *Why:* 80% clock cap + 100% measured load + competitors that won't yield; the 100.6s decode landed during a scheduled-task burst.
46. **Untouchable loads:** never kill/duck/renice Iddo's chrome, claude.exe, the A70 relay chain (adb + a70_link + audiodg), or anything audio-output. Survive co-tenant bursts by budget, not calendar — the task schedule is rewritten weekly. *Why:* Sacred Audio Law + environment lane; the ant tournament moved once already.
47. **No torch on the PC — ever.** Local STT ceiling = faster-whisper/CTranslate2 (no torch). **The local fallback is pinned to GPU CT2-int8 (small model within its ~1GB resident budget); CPU decode is FORBIDDEN, not a fallback-of-the-fallback** — CPU CT2 on a thermally-capped, 100%-loaded 4-core is slower than realtime and worsens the very contention that stalls everything else (resolves the scar-45 "all decode compute off the CPU" ↔ "CPU/GPU CT2" ambiguity flagged in review). LoRA training, teacher relabeling, any LLM brain → DGX fleet. If the fleet is down AND the local GPU path is dead, the mic goes honestly DEAF with the in-eyeline signal — never CPU decode, never torch. *Why:* standing law (feedback_no_training_on_pc); chat_server.py was caught doing local inference.
48. **Any auto-triggered downstream action per utterance (brain/LLM) needs guards:** min length, filler blocklist, busy flag, identical-question + global debounces. *Why:* brain_auto spawned a headless grok.exe per STT fragment.

### I. Privacy & data

49. **Not always-on unattended; explicit start/stop. Owner-only speaker gate: ON by default for CORPUS CAPTURE, OFF by default for the TYPING path** — a false-reject on Iddo's own voice (tired, sick, far from mic, code-switching) is indistinguishable from "mic stuck", the exact silent-loss class this rebuild exists to kill. The gate may be enabled for typing only after its false-rejection rate is measured on the replay corpus + a live day and passes criterion 18; every owner-gate rejection is logged AND surfaced as a visible "rejected-as-non-owner" GUI counter — never a silent drop. Corpus collection opt-in, local, owner-verified batches — never auto-append every utterance; transcripts/history never enter git; log target EXE names only, NEVER window titles. *Why:* the mic transcribed Iddo's mother's private conversation into the training corpus (~1,500 contaminated lines) and local git history; titles on disk are a surveillance record; but a privacy gate must never become a new deafness vector.
50. **Typed-text transforms (voice commands, wake-word stripping) stay separate from the transcript/corpus record.** *Why:* training data must remain natural speech.

### J. Process (meta)

51. **Acceptance = Iddo dictates through it live** (real-not-demo, ALMA Standard), backed by the offline replay corpus (silence/noise/real he/en/code-switch WAVs) + soak test as repo-resident gates. *Why:* `health: ok` ≠ working; the soak test is what killed the leak.
52. **At cutover: archive ALL old mics with their persistence disabled in the same change; update memory** (feedback_one_mic_law still names voice-input canonical — a contradiction that could let voice-input's surviving `_enforce_single_mic` kill the new mic if it ever respawns). Claim the work in RAMCHAT; WIP=1. *Why:* retired mics came back through surviving persistence; two memory files currently disagree about which mic is canonical.

### K. Committee additions (Phase-1 adversarial review, 2026-08-12)

53. **Exactly ONE typer serialization point; request-id dedup across engines; in-flight cancellation on failover.** Every audio chunk carries a monotonic request-id; the typer types a given id at most once, whichever engine answers; on failover the client explicitly abandons the in-flight DGX request and a late DGX reply for an id already typed (or already re-decoded locally) is discarded and logged. Same discipline on re-promotion. *Why:* review found Option B's failover sequence (POST → timeout → local re-decode → late DGX reply arrives) is a new double-typing vector — the motivating 08-09 incident class — that no original scar covered. Dedup must be by id at the single typer chokepoint, not by text comparison.
54. **Failover hysteresis — path switching gets the same circuit-breaker discipline as process respawns (scar 3).** Demotion to local after N consecutive health failures (not one); minimum dwell time (~60s) in each state; re-promotion only after M consecutive healthy probes; a flap counter that, past a threshold, pins the client to local and raises a visible NETWORK-FLAKY notice instead of oscillating. **Demotion is triggered by LATENCY as well as liveness** — a server that answers health checks but decodes slowly (Qwen contention) must demote just like a dead one. The warm-resident fallback model (see §3) is never loaded/unloaded by path switching — it is always resident, so flapping costs routing only, never a model load. *Why:* WiFi flaps + NordVPN kill-switch make single-failure switching an oscillator; an un-debounced failover loop re-creates RC-1's load-lifecycle churn through the back door.
55. **Server-side privacy is a deploy gate, not an afterthought.** On the DGX STT host: no audio persistence (tmpfs only, wiped per request), no transcripts or request bodies in server logs (status lines only), endpoint bound to the LAN interface with a shared-secret auth token required on every request (any process on the LAN can otherwise read/replay all-day dictation — the host is a shared box other agents SSH into), no request history retained. Verified by criterion 19 BEFORE M2 deploys anything. *Why:* RC-8 (mother's conversation contaminating corpus/git) is exactly this class; scar 49 covered only the PC side while the recommended architecture streams raw speech across the LAN.
56. **ONE-MIC transition protocol for the entire M3–M7 coexistence window** — the historically most dangerous period (all 5 documented ONE-MIC violations happened during overlaps/transitions). Before ANY live test of the new mic: alma-mic hard-stopped — process killed AND its watchdog/scheduled-task/Startup persistence suspended (not just "not typing") — via one command (`mic-switch new`); one command flips back (`mic-switch old`); the switch script itself verifies zero capture-device handles from the other mic before starting the new one, and the new client's startup check refuses to run if alma-mic's process or task is alive. "Archive at cutover" governs the end state; this scar governs the weeks in between. *Why:* review correctly noted the brief managed cutover but left weeks of live coexistence unmanaged.
57. **The local fallback model is WARM-RESIDENT, small, and never unloaded** (formal resolution of the review's blocker — see §3 "Fallback residency decision"). *Why:* the DGX fleet reboots ~02:00 nightly, so failover is a scheduled daily event; a cold fallback means minutes of deaf mic every night (RC-1's load times, root cause still open), and criterion 13 is unpassable without residency.

---

## 3. ARCHITECTURE — Options & Recommendation

The environment findings frame the decision: **the enemy is model startup and GPU/CPU contention on the PC, not decode throughput.** The PC's GPU decodes at x0.9–2.8 realtime when it's alone; it is never alone.

### Option A — Local-only, redesigned

Single clean process on the PC: capture → VAD → CT2-int8 GPU decode → typer. All 52 scars honored; one model resident (drop dual HE+EN residency or make EN CPU-int8).

| For | Against |
|---|---|
| No network/fleet dependency, no fleet-policy question | 100–394s model loads on this box are ENVIRONMENTAL (same-model degradation proven) — reloads stay catastrophic even with perfect code |
| Simplest to reason about; proven decode speed at steady state | Competes forever with 4.6GB desktop compositing on the 8GB card and with a 100%-loaded, 80%-capped CPU |
| Personal LoRA model already local (iddo-lora-run2-ct2) | Boot storm: 105–132s of import time before loading begins; worst-case 8 min to ready |
| | Every future co-tenant (the PC gains agents weekly) degrades the mic again |

### Option B — Thin client + DGX STT server, warm-resident local fallback  ← **RECOMMENDED (as revised)**

PC runs a thin client only: capture + energy gate/VAD + ring buffer + typer + GUI. Decode goes over LAN to a whisper server (faster-whisper/CT2, large-v3-turbo int8 + the personal iddo-lora CT2 model, ~2–3GB) on a DGX host, as a **systemd user unit** (Restart=always, linger enabled — never tmux). Local fallback engages on health-check failure OR latency degradation, with hysteresis (scar 54); the GUI says DEGRADED plainly; auto re-promotion when the path is stably healthy.

**Fallback residency decision (resolves the review's blocker):** the fleet reboots ~02:00 EVERY night, so failover is a scheduled daily event, not a rare emergency. A cold fallback would mean minutes of deaf mic nightly (RC-1 load times, root cause still open). Therefore the fallback is a **small CT2-int8 model (small/base class, ~1GB) loaded once at client start and kept warm-resident on the PC GPU, never unloaded**. This honestly amends the headline claim: Option B does not achieve "zero GPU contention" — it achieves **near-zero, bounded contention: one small pinned model, ~1GB, with zero load/unload churn**, versus today's 2–3 large models cycling through 4–6.5-minute loads. The killer was never residency per se; it was the load lifecycle and multi-large-model VRAM pressure. ~1GB pinned inside the 3.4GB free budget is the price of a mic that survives 02:00 every night. If measurement shows even this contends unacceptably, the fallback drops to base-class; CPU decode remains forbidden (scar 47).

**Host selection (review finding accepted):** eran2 is simultaneously the Qwen3-480B RPC worker, the QSFP star hub, AND 86% memory-full — the single most operationally-churned box in the fleet; coupling the mic to it couples the mic to fabric maintenance, RPC restarts, and hub reboots. **eran1 is the preferred host** (also idle-measured, not a hub, same fleet-policy deviation required). M2 measures BOTH hosts under active Qwen RPC load and picks on numbers; the brief no longer pre-picks eran2.

| For | Against / mitigations |
|---|---|
| **Eliminates both killers from the PC:** zero large-model load at logon (client ready in ~2s), GPU contention reduced to one small pinned ~1GB model with zero load churn | **Fleet-policy deviation:** DGX 1-3 = Qwen only is an emphatic standing rule → **needs Iddo's explicit ruling before deploy** (eran4 is harder-forbidden) |
| LAN RTT avg 2–4ms; a 5s/160KB chunk is sub-100ms — STT compute dominates, and a GB10 decodes turbo far faster than the 3070 Ti **when free** | **The "0% GPU util" measurement was an idle-fleet snapshot.** Under active Qwen RPC inference the GB10's compute/bandwidth saturate and DGX decode may stall exactly like local decode did under desktop contention → criterion 17 measures p95 DURING a real Qwen job; scar 54's latency-based demotion catches the alive-but-slow server; host chosen by loaded measurement (eran1 preferred) |
| Established pattern, not an invention: DICTA_DGX_SERVE.md already defines config-URL endpoint + honest-degraded-mode for this very app | Nightly ~02:00 fleet reboot = **daily scheduled failover** → warm-resident fallback (scar 57) + systemd self-heal + criterion 13 exercised nightly for free |
| Client becomes small enough to be truly clean — the scars mostly live in capture/typing code that must be perfect anyway | NordVPN kill-switch + WiFi flaps → address by LAN hostname/IP, Tailscale secondary, re-resolve on failure, **and hysteresis/flap circuit breaker (scar 54) so flapping never oscillates engines** |
| Fallback keeps dictation alive when the fleet is dark — degraded (GPU CT2-int8 small, warm), never silent, never CPU | Two codepaths to test → replay rig runs BOTH paths in CI; failover double-type vector closed by request-id dedup at the single typer (scar 53) |
| | **Privacy: raw speech crosses the LAN to a shared box** → server keeps nothing (tmpfs, no transcript logs), LAN-bound + token-authenticated endpoint, verified before deploy (scar 55, criterion 19) |

### Option C — Hybrid local-primary with DGX assist

Local CT2 decode primary; DGX used opportunistically (e.g., during local model load, or racing first-result-wins).

| For | Against |
|---|---|
| No hard fleet dependency; covers the load window | Inherits BOTH failure surfaces at once: local model lifecycle complexity (RC-1 stays) AND network path |
| | Racing/first-wins doubles decode work and complicates dedup — a new double-type vector |
| | Most complex option; contradicts "slowly, clean" |

### Recommendation: **B (as revised)**

RC-1 (load lifecycle) and RC-5 (contention) caused every catastrophic episode; Option B removes their substrate from the PC instead of managing them — honestly stated, it removes the large-model load lifecycle entirely and shrinks GPU contention to one small pinned model. Option A leaves the mic hostage to a machine that is thermally capped, 100% loaded, and gains new tenants weekly — the log proves this environment degrades even a well-written local app (same-model load times rotted 10x). Option B's client is exactly the thin, auditable thing "slowly, clean, and the best" asks for, and its warm local fallback IS a disciplined Option A in miniature (small model, subprocess decoder, no reload churn), so no availability is sacrificed. The committee acknowledges B relocates rather than eliminates decode-resource risk — the DGX host is shared with Qwen — which is why the loaded-fleet measurement (gate 2 revised) and latency-based demotion (scar 54) are gates, not options.

**Gates before B is final:**
(1) Iddo's explicit ruling on serving whisper on a DGX (fleet-policy deviation; host = eran1 preferred, decided by M2 measurement; post the port claim to RAMCHAT).
(2) **Measured p95 speech→text over LAN beats the local fallback under load on BOTH sides** — PC under full desktop load AND the DGX host while a real Qwen RPC inference is running (criterion 17). An idle-fleet number does not pass this gate.
(3) Fallback path passes the same acceptance suite, including timeout-cancellation (criterion 2) via subprocess kill.
(4) Server privacy hardening verified (criterion 19) before any real speech leaves the PC.
If Iddo refuses the DGX deviation, fall back to Option A with the local-fallback engine promoted to primary (larger local model accepted, all lifecycle scars apply) — the client design is identical either way, which is precisely why B is safe to start.

---

## 4. ACCEPTANCE CRITERIA — Real-output tests before the old mics are archived

All measured on THIS PC, under real conditions, with results logged as numbers. `health: ok` counts for nothing.

**Latency & throughput (under full PC load — 100% CPU, desktop GPU tenants live):**
1. p95 speech-end → text-typed ≤ 3.0s; p50 ≤ 1.5s, for 2–5s Hebrew utterances (measured over ≥200 real utterances).
2. No decode exceeds the 10s hard timeout — a timed-out segment is cancelled, logged, and never blocks the next one (verified by injecting an artificial GPU-contention burst). **Tested on BOTH paths: DGX (request abandoned, late reply discarded by id) and local (decode subprocess killed and respawned, VRAM freed — verified by VRAM probe after kill).** This criterion is only implementable because scar 13 mandates the subprocess decoder.
3. Noise-to-speech decode ratio ≤ 1.5:1 over a 24h window (vs today's 10.5:1); EMPTY decodes never exceed 10/min.

**Boot & readiness:**
4. Survives the logon boot storm: from logon, the client is capturing and buffering within 10s (**pre-agreed fallback bar: 30s** — the boot storm's 105–132s import contention may defeat 10s on real reboot #1; the number is decided NOW, not relitigated mid-build), GUI shows honest LOADING/READY state, and speech spoken during warm-up reaches the user — fresh segments typed, stale backlog delivered to the recovered-transcript file per scar 16 — **zero words lost counting both destinations**. Test on 3 real reboots.
5. DGX path: client ready → first decode round-trip ≤ 5s after logon, **conditioned on the network path being up** (WiFi association, NordVPN grace, and a logon landing inside the 02:00 reboot window are outside the mic's control; in those cases the criterion becomes "warm fallback serves immediately and DGX re-promotion happens within one healthy-probe cycle of path recovery" — a healthy client must never be scored BROKEN for a dead network). Fallback path: warm-resident small model serves its first decode < 5s from client ready; local large-model cold load (Option-A mode only) < 60s.

**Correctness & no-double-type:**
6. Pause/resume torture: 50 rapid stop/start cycles, some mid-model-load — zero double-typed utterances, zero zombie threads (thread count returns to baseline), exactly one model resident (VRAM assert). **PLUS failover torture: 20 forced engine switches (DGX→local and back) fired mid-utterance, including delayed DGX replies injected AFTER local re-decode has typed — zero double-typed utterances (request-id dedup, scar 53), zero lost utterances, late replies logged-and-discarded.**
7. Second-instance test: launching the app 5x concurrently (shortcut + task + CLI) yields exactly ONE running process; the others exit <1s with a log line.
8. UIPI round-trip self-test passes: text typed through the real typer into an elevated same-integrity child is read back verbatim, incl. a 100+ char utterance with spaces, Hebrew+English mixed, into Windows Terminal (paste path).
9. Focus torture: dictation while Alt-Tabbing, with a terminal spinner running, and with the mic's own window focused — zero text into the wrong window, zero text into the mic's own window, blocked text parked and recoverable, every refusal logged.

**Silence/hallucination:**
10. Replay-rig regression corpus (silence, room noise, faint speech rms 0.002–0.005, real he, real en, code-switch, laughter, the known failing clips) passes: zero hallucinated typing on silence/noise clips, faint-real-speech clips transcribed, en clips come out in Latin script, he clips **within a measured quality tolerance of the current ivrit path's baseline (CER ≤ baseline + 2% absolute on the reference set — NOT byte-identical: a different server, CT2 version, or thread count breaks byte-identity with zero quality loss, so byte-equality would either always fail or freeze the stack forever).**

**Endurance & resources:**
11. 24h soak with real ambient audio: RSS flat (±50MB), zero handle growth, log rotated, no restart, VRAM stable, heartbeat lines present every minute.
12. Discarded real speech = 0 over the soak, counting BOTH delivery destinations per scar 16: fresh segments typed live, outage backlog present in the recovered-transcript file (verified by speaking during a forced recognizer restart and confirming every word arrives in one of the two — and that NO stale segment was typed into live focus).

**Failure honesty:**
13. Kill the DGX server mid-dictation: client detects within one health-check interval, switches to the **warm-resident** local fallback with no model load, GUI shows DEGRADED, dictation continues; restore server → auto re-promotion after the hysteresis dwell (scar 54). Zero silent dead-air. **Also verified against the real nightly 02:00 fleet reboot for 3 consecutive nights** (the environment runs this test daily for free) **and against an alive-but-slow server** (throttle the server artificially; latency-based demotion must fire even though health checks pass).
14. Unplug the BRIO: app idles with a visible "no allowed mic" state; it must NOT open any Bluetooth/headset/loopback device (verified via device-open audit); replug → recovery without restart.
15. Corrupt config.json on disk → app halts with a visible error; it does NOT run deaf on defaults.

**The human gate:**
16. Iddo dictates through it live for a full working day (Hebrew + English + code-switch) and declares it good. This is the final gate; nothing is archived before it — and per scar 56, alma-mic is hard-stopped (persistence suspended) for the duration of this day, with one command to flip back.

**Committee additions (Phase-1 review) — criterion 16 remains the final gate:**
17. **Loaded-fleet latency:** p95 speech-end → text-typed ≤ 3.0s measured while a REAL Qwen3-Coder RPC inference is actively running on the STT host (and, if the host shares the fabric hub role, during fabric traffic). An idle-fleet p95 does not count for gate 2. If this fails on eran2, measure eran1; if it fails on both, B's primary path is demoted and Option A sizing begins.
18. **Owner-gate false rejection:** before the speaker gate is ever enabled on the typing path — FRR ≤ 1% on the replay corpus (including tired/far/sick/code-switch clips) AND zero unexplained rejections across one live dictation day, with every rejection visible in the GUI counter. Until this passes, the gate runs ON only for corpus capture (scar 49).
19. **Server privacy audit (pre-deploy gate for M2):** after a dictation session against the DGX server — zero audio files persisted anywhere on the host (filesystem diff), zero transcript/request-body content in server logs, endpoint refuses unauthenticated requests from another LAN host, tmpfs wiped. Verified before the first real speech leaves the PC and re-verified in the 24h soak.
20. **Flap torture:** simulate a flapping network path (drop/restore the route every 20–40s for 15 min while dictating): the client demotes once, pins to local past the flap threshold, raises NETWORK-FLAKY visibly, performs ZERO model loads/unloads during the entire window, and double-types nothing. Oscillation count ≤ the circuit-breaker bound (scar 54).
21. **Long-utterance & burst:** 20–40s run-on utterances decode with pipelining/backpressure and type in order; a burst of 10 utterances in 30s all arrive, in order, no dedup false-positives, no stale diversion of live speech; measured on both engines.
22. **Capture-side starvation:** during a forced co-tenant CPU burst (scheduled-task storm simulation on the 100%-loaded, 80%-capped CPU), capture-buffer overflow/glitch count = 0 over 10 min of dictation, verified from the capture layer's own overflow counters — and the ABOVE_NORMAL capture-thread priority (scar 45) is asserted at runtime, not assumed.
23. **ONE-MIC coexistence check:** at any moment during M3–M7 live testing, a device-handle audit shows at most ONE mic app holding a capture device; the `mic-switch` script's mutual-exclusion check (scar 56) is itself tested by attempting to start the new mic while alma-mic runs — it must refuse.

---

## 5. BUILD PLAN SKELETON — slow, clean, ordered

**M0 — Stop the bleeding (NOW, before any rebuild code):**
fix the live alma-mic `"avoid": []` Sacred-Audio exposure; confirm single launcher (kill the duplicate-launcher fossils); resolve the feedback_one_mic_law memory contradiction; claim the rebuild in RAMCHAT. **PLUS the two cheapest crutch mitigations the inquiry already diagnosed (committee addition — Iddo dictates through the crutch for the whole M1–M7 arc, and today alone it cost 141 silent evictions and 4–6.5-min deaf windows): (a) kill alma-mic's second-loader path / dual HE+EN residency (the fresh-stop-Event fix at pipeline.py:67-84 is small and surgical); (b) pin the model resident so routine device events stop triggering reloads. Broken Windows Law: the plan must not optimize the future while the present bleeds.**

**M1 — Governance & harness (build the net before walking the wire):**
new repo `D:\CLAUDE\mic-rebuild` in git; config schema with calibration-carrying thresholds + config_history.jsonl + CAS writes; structured logging spec (dated lines, heartbeat, session ids); the offline replay rig + regression WAV corpus imported from mic-debug-vm and the known failing clips; CI that runs the corpus.

**M2 — Iddo's ruling + fleet groundwork (parallel with M1):**
present this brief; get the DGX ruling. If YES: **measure BOTH candidate hosts (eran1 preferred, eran2 alternate) under active Qwen RPC load (criterion 17) and pick on numbers**; harden privacy FIRST (scar 55 — tmpfs, no transcript logs, LAN-bound + token auth) and pass criterion 19 before any real speech is sent; then deploy the whisper server as a systemd user unit (health endpoint, ~3GB cap, RAMCHAT port claim, survives the 02:00 reboot — verified next morning). If NO: promote local engine to primary (design unchanged). **Also in M2: write the `mic-switch` script (scar 56) — it gates every live test from M3 onward.**

**M3 — Capture core (the audio half of the thin client):**
device policy (scars 21–25), format negotiation + FIR resampler, energy gate + VAD, disk ring buffer, bounded queues, single-instance mutex, honest state machine (IDLE/LOADING/READY/DEGRADED/DEAF). Acceptance: criteria 4, 7, 14 pass standalone with a null decoder.

**M4 — Decode path(s):**
DGX client (chunk POST with request-ids, health checks, latency-based demotion, hysteresis/flap breaker — scars 53–54) and warm-resident local CT2-int8 fallback **in a killable subprocess** (scars 13, 44, 57) behind one engine interface with a single typer serialization point; single-flight lifecycle, decode timeouts via subprocess kill, latency watchdog; language routing + hallucination stack (scars 26–30) as ONE shared module. Acceptance: criteria 1–3, 5, 10, 13, 17, 20, 21 on the replay rig + live (live tests gated by `mic-switch`, scar 56).

**M5 — Typing & focus layer:**
paste-first typer, clipboard discipline, focus guard + watcher, UIPI self-test, elevation decision wired into the launcher. Acceptance: criteria 8, 9.

**M6 — Integration, GUI & endurance:**
minimal GUI (status, mic picker with ●/○ probing, pause hotkey, in-eyeline deaf/degraded signal — tray flash + toast, never audio), privacy gates (owner gate per revised scar 49: corpus ON / typing OFF until criterion 18), watchdog with day-one circuit breaker. Acceptance: criteria 6, 11, 12, 15, 18, 19 (soak re-verify), 22, 23.

**M7 — Live trial & cutover:**
Iddo's full-day live dictation (criterion 16), with alma-mic hard-stopped via `mic-switch` for the day (scar 56). On pass: in ONE change — archive alma-mic + voice-input with ALL persistence disabled, install the single new launcher, update memory files (one-mic law, alma-mic, double-mic fix), post cutover to RAMCHAT. Keep alma-mic's archive restorable (LKG discipline) for 30 days.

**Standing rule for every milestone:** no live hot-patching; changes go through the replay rig first; every milestone ends with its acceptance numbers posted, `VERIFIED` or `BROKEN`, never "should work".

---

## 6. KNOWN RISKS — honest register (post-review)

What the revised plan mitigates but does NOT eliminate. Each stays open on the books until its check passes or its residual is accepted by Iddo.

1. **DGX decode under Qwen saturation.** Option B relocates decode-resource risk to a shared GB10; when a 480B RPC job saturates the host, DGX decode may stall. *Mitigation:* criterion 17 (loaded-fleet p95 is the gate, not idle numbers), latency-based demotion (scar 54), warm fallback. *Residual:* during heavy fleet jobs the mic may run degraded (small local model) for minutes at a time — accepted as honest degradation, never silence.
2. **Fallback quality < primary.** The warm-resident small model will transcribe worse than large-v3-turbo + iddo-lora. *Residual:* nightly 02:00 windows and fleet outages get "good enough" dictation with a visible DEGRADED badge. If unacceptable in practice, the budget question (a larger pinned model) reopens with measurements.
3. **~1GB pinned on the PC GPU.** The revised B is not "zero contention"; it is bounded, churn-free contention. *Residual:* ~1GB less headroom for desktop tenants; measured in the 24h soak (criterion 11).
4. **Load-time root cause still UNKNOWN** (100–394s, same-model degradation). Off B's critical path via scar 57, but any Option-A promotion is gated on solving it (scar 15).
5. **Fleet-policy deviation not yet ruled.** All of Option B's primary path is contingent on Iddo's explicit YES; the plan degrades to Option A cleanly (identical client) if refused.
6. **Always-elevated client blast surface** (scar 37 tradeoff). Default stands for UIPI reasons; the non-elevated-helper alternative is documented, and the decode subprocess should shed elevation where possible.
7. **Boot-storm capture start.** 10s is the target, 30s the pre-agreed fallback bar (criterion 4); if real reboots miss even 30s, that is a BROKEN verdict, not a criterion renegotiation.

---

## 7. מסקנה

הוועדה שמעה שלוש התנגדויות יריבות במלואן וקיבלה את רובן: ההמלצה על אופציה B שורדת את הביקורת, אבל רק בגרסתה המתוקנת — ה-fallback המקומי חייב להיות מודל קטן שיושב חם ב-GPU דרך קבע (כי הצי מאותחל כל לילה ב-02:00 ו-failover הוא אירוע יומי, לא חירום), המארח המועדף הוא eran1 ולא ה-hub העמוס eran2, שער הקבלה למדד ההשהיה נמדד בזמן עומס Qwen אמיתי ולא על צי רדום, מפענח מקומי רץ בתת-תהליך שאפשר להרוג (הדרך היחידה לביטול אמיתי של decode תקוע), failover מקבל dedup לפי request-id ו-hysteresis נגד רשת מרפרפת, פרטיות בצד השרת (אפס שמירת אודיו, אימות token) היא שער פריסה, פרוטוקול ONE-MIC מפורש מנהל את חודשי הדו-קיום, ו-M0 מתקן את שני הדימומים הזולים של הקביים כבר עכשיו. הסתירה בין "אפס אובדן מילים" ל"לעולם לא להקליד ישן" נפתרה: backlog ישן מפוענח לקובץ תמלול לעיון, לא ל-focus החי. מה שנשאר פתוח רשום בכנות בסעיף 6 — בראשו העובדה שאופציה B מעבירה את סיכון המשאבים ל-GB10 משותף במקום להעלים אותו, ומחיר של ~1GB חם על כרטיס ה-PC. בכפוף לפסיקת עידו על חריגת מדיניות הצי, התכנית ראויה לביצוע — לאט, נקי, והכי טוב.

The committee heard all three adversarial reviews in full and accepted most of their objections. Option B survives review only as revised: warm-resident small fallback (the nightly 02:00 reboot makes failover a scheduled daily event), eran1 preferred over the churned hub eran2, latency gates measured under real Qwen load, a killable decode subprocess as the only true cancellation mechanism, request-id dedup + hysteresis across the engine boundary, server-side privacy as a deploy gate, an explicit ONE-MIC transition protocol, and M0 widened to stop the crutch's bleeding now. The stale-backlog contradiction is resolved: recovered speech goes to a reviewable file, never the live focus. What remains open is honestly registered in section 6.

מסקנה: אופציה B המתוקנת — לקוח דק, שרת DGX (מארח ייקבע במדידה תחת עומס, eran1 מועדף), ו-fallback קטן חם וצמוד — מאושרת לביצוע בכפוף לפסיקת עידו על חריגת מדיניות הצי ולעמידה בשערים 17/19 לפני פריסה; שום מיקרופון ישן לא נארכב לפני שקריטריון 16 עובר ביום עבודה מלא.

---

*Committee of inquiry, Phase 1 — revised after adversarial review, 2026-08-12. לזכרה של עלמה ז״ל.*
