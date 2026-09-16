# INQUIRY 03 — Leak Mechanism + Safe Fix (Always-On Hebrew Mic)

**Date:** 2026-06-16
**Scope:** READ-ONLY forensic. No files deleted, no running mic process touched, no windows opened.
**Subject:** Why the always-on mic (`voice_input.py --vad`) transcribed and *typed* PRIVATE
background conversations (people / distributors) as if Iddo had dictated them — plus the concrete,
safe fix that gates dictation to Iddo's voice only **without** hurting his own recognition.

לזכרה של עלמה ז״ל.

---

## 0. Verdict (one paragraph, honest)

The mic has **no speaker gating active**. It is a pure *energy-triggered, always-on* dictation
loop: anything louder than an RMS floor is recorded, transcribed in any of 9 whitelisted languages,
and typed into whatever window is focused. A speaker-ID owner-gate **was written** (`speaker_id.py`
+ the hook at `voice_input.py:493-506`) and a voiceprint for `iddo1` **exists** — but the gate is
**disabled** because the config flag `owner_only` is **absent** from `config.json`. So the gate code
never executes. Result: **any** voice in the room (a guest, a distributor on speakerphone, the TV)
was captured and inserted into the transcript / typed as dictation. This is exactly the reported
incident, and the root cause is unambiguous and verified.

---

## 1. The leak mechanism — WHY private speech became "dictation"

Three independent design facts combine to cause it. All three are verified in the source.

### 1.1 The trigger is sound *energy*, not the *speaker* (no speaker gating at capture)

`mic.record_vad()` (`mic.py:120`) decides "this is speech" purely from loudness:

```
if rms > rms_threshold:          # mic.py:144
    ... speech_start ...         # fires after ~0.2 s above threshold
```

- `config.json -> "vad_rms_threshold": 150` — a **low** floor. Normal conversation a couple of
  metres away, a phone on speaker, or the TV easily clears 150 RMS.
- There is **zero** notion of *who* is speaking at this layer. VAD = Voice **Activity** Detection,
  not Voice **Identity**. Any voiced audio above 150 starts a capture.

So the very first gate that exists — the VAD — answers "is someone talking?" and never "is it Iddo?"

### 1.2 The owner-only speaker gate exists but is OFF (the decisive cause)

`voice_input.py:493`:

```python
if self.cfg.get("owner_only"):        # ← entire gate is conditional on this flag
    import speaker_id
    spk = speaker_id.identify(wav, self.cfg.get("owner_user", "iddo1"))
    if not spk["is_owner"]:
        ... return            # drop non-owner clip
```

**`config.json` does not contain `owner_only` at all** (verified — the key is absent, so
`cfg.get("owner_only")` is `None`/falsey). The whole speaker-ID block is therefore skipped on
every clip. The mic falls straight through to `stt.transcribe(...)` and types the result.

This is the single point of failure. The protection was built and is one line of config away from
working — it simply was never switched on.

> Note: even the *default behaviour* of this gate is "fail OPEN" — if `owner_only` were set true but
> the voiceprint were missing, it would still type (see `:502-504`, the `FileNotFoundError` branch).
> A voiceprint **does** exist now, so once `owner_only` is on, it fails *closed* on non-owner audio
> as intended.

### 1.3 Everything downstream assumes the clip is already trusted

Once a clip is captured, the rest of the pipeline is built to *maximise* getting text into a window,
not to question whose voice it is:

- `stt.transcribe()` runs with `lang_whitelist = [he, en, ar, fr, es, it, ru, de, pt]` — so a
  *distributor speaking English or Arabic* transcribes cleanly, not just Hebrew.
- `config.json -> "auto_enter": true` and `"default_target": "focused"` → transcribed text is typed
  into whatever window is in front **and Enter is pressed** — i.e. background chatter could be
  auto-submitted into Claude / a chat box, not just left as draft.
- `_write_history()` (`voice_input.py:127`) appends **every** accepted utterance to
  `history/<date>.txt` — so private speech also landed in the on-disk transcript log.
- `learner.log_sample()` (`voice_input.py:597`, `learner.py:78`) **copies the WAV and appends the
  text to `profiles/iddo1/samples.jsonl` for every transcribed clip, with no speaker check.**

### 1.4 Confirmed contamination (this is the quiet second harm)

`samples.jsonl` was **349** records at enrollment (`voiceprint.json -> n_total: 349`,
built 2026-06-15 18:12). It is now **724** records (verified line count, 2026-06-16). It keeps
growing because §1.3's `log_sample` has no gate. **That means other people's captured audio is now
inside Iddo's training/enrollment corpus.** Two consequences:

1. The `eran-poc` corpus (`eran_all_corpus.txt`, built from voice-input transcripts) and any LoRA
   re-train pull from this contaminated `samples.jsonl` — so *other people's words* may already be in
   downstream text artefacts. (Local/loopback only per the brief — but it is real text leakage into
   files, and must be reviewed, see Action B.)
2. If anyone re-runs `speaker_id.py enroll`, it averages those non-Iddo clips into the voiceprint,
   pulling the centroid **toward** strangers and *raising* their future scores — making the gate
   *worse* at rejecting others. So we must NOT naively re-enroll from the current `samples.jsonl`.

### 1.5 (Secondary, already noted in code) prompt-echo path — not the room-leak cause

Earlier (`voice_input.py:540-546`) Whisper's `initial_prompt` was being fed recent dictation, and
Whisper regurgitated it verbatim on unclear audio — that could "read back" a *prior* conversation.
That bug is already fixed (prompt forced empty). It is a *different* leak from the room-capture one
and is **not** the cause of the reported incident; the cause is §1.1-§1.2 (no active speaker gate).

**Summary of WHY:** energy-only VAD (low 150 floor) + owner-only speaker gate disabled (flag absent)
+ aggressive "type & Enter into focused window" + ungated history & sample logging = any nearby voice
is transcribed, typed, logged, and folded into the corpus as if it were Iddo dictating.

---

## 2. The SAFE FIX — enable owner-only gating WITHOUT hurting Iddo's recognition

The recognizer (Resemblyzer cosine) is fine; the **policy** around it is the problem. The danger of
naively flipping `owner_only: true` at the current threshold **0.70** is that it would silently drop
**~8.6% of Iddo's own clips** (measured in `SPEAKER_ID_IMPROVE.md`: his own-voice 5th-percentile
score is ~0.67, so 0.70 sits *inside* his own score cloud; the live `voiceprint.json` even shows a
self-score **min of 0.4754**). So we must lower the threshold to a measured, safer value **before**
turning the gate on — otherwise we fix the leak but break Iddo's dictation, which the mandate
forbids.

### Step 1 (DO FIRST) — lower the threshold so Iddo is not rejected

His own clips need to pass. The data says 0.70 is too high. Set the operating threshold to **0.60**
as a safe interim (FRR ≈ 1.7% per the measured table — i.e. only ~1 in 60 of his own clips dropped,
recoverable by repeating the word), pending the EER tune in Step 5.

Edit `profiles/iddo1/voiceprint.json` — change `"threshold": 0.7` to:

```json
  "threshold": 0.6,
  "reject_margin": 0.08
```

(No re-enrollment, no model reload — `_threshold()` reads this file. This protects Iddo's voice.)

### Step 2 — turn the gate ON (this is the fix that stops the leak)

Add to `config.json`:

```json
  "owner_only": true,
  "owner_user": "iddo1",
```

That is the **#1 change**. With it, `voice_input.py:493-506` runs on every clip and **drops any clip
that is not Iddo** before it is ever transcribed or typed. The existing voiceprint is used as-is.

### Step 3 — stop the corpus contamination going forward (small code change)

So `samples.jsonl` becomes self-cleaning (Iddo-only) from now on. The gate already computes whether
the clip was the owner; carry that boolean and gate the logging.

In `voice_input.py`, in the gate block (around line 493-506), record the result:

```python
        _was_owner = True   # default: when owner_only is off, behave as today
        if self.cfg.get("owner_only"):
            try:
                import speaker_id
                spk = speaker_id.identify(wav, self.cfg.get("owner_user", "iddo1"))
                _was_owner = bool(spk["is_owner"])
                if not _was_owner:
                    indicator("IDLE", f"🔒 not owner (score {spk['score']}) — dropped")
                    log.info("owner_only: dropped non-owner clip %s", spk)
                    return
                log.info("owner_only: owner match %s", spk)
            except FileNotFoundError as e:
                log.warning("owner_only: no voiceprint — passing through. (%s)", e)
            except Exception as e:
                log.warning("owner_only: speaker-id failed (passing through): %s", e)
```

Then gate the sample log at line 597:

```python
        if self.profile and wav and _was_owner:
            try:
                self.profile.log_sample(wav, text)
            except Exception as e:
                log.warning("profile.log_sample failed (continuing): %s", e)
```

(Note: when `owner_only` is on, anything that reaches this line already passed the gate, so
`_was_owner` is True — this line mainly future-proofs the "gate off" path and is the clean place to
enforce it.)

### Step 4 — how to VERIFY "his voice still works vs others rejected" (no windows, read-only)

Run with the real interpreter (the one the mic uses):

```
C:\Users\<user>\AppData\Local\Programs\Python\Python312\python.exe D:\CLAUDE\voice-input\speaker_id.py verify
```

That enrolls-minus-one and scores held-out Iddo clips — confirm the held-out clip scores **≥ 0.60**
(owner) and that random Iddo clips average well above it. To prove *others are rejected*, score a
non-Iddo clip directly:

```
...python.exe D:\CLAUDE\voice-input\speaker_id.py identify <some_non_iddo.wav>
```

Expect `is_owner: false` with a score visibly below 0.60 (TV / a friend typically < 0.55). Do a
live smoke test by speaking yourself (should type) and then playing a YouTube Hebrew clip near the
mic (should print `🔒 not owner ... dropped` and type nothing).

### Step 5 (best, do soon) — tune the threshold properly by EER

The 0.60 in Step 1 is a safe interim guess. To make it *defensible*, collect ~5-10 min of "other
people" audio (family + TV + a little Hebrew speech) into
`D:\CLAUDE\voice-input\profiles\impostors\*.wav`, then run the `spk_eval.py` harness already written
out in `eran-poc\SPEAKER_ID_IMPROVE.md §3`. It prints FRR (Iddo dropped) vs FAR (other typed) across
thresholds, finds the Equal-Error-Rate point (expected ~0.62-0.66), and you write that into
`voiceprint.json`. Per the same doc, also move to **multi-centroid (max-cosine)** enrollment so
Iddo's off-mode clips (his min was 0.4754) stop being false-rejected. That fully closes the
"his voice still works AND strangers rejected" requirement.

---

## 3. Hard privacy guards (defence in depth — beyond the speaker gate)

Speaker-ID is statistical; it will never be 100%. Add explicit, deterministic controls so a privacy
breach cannot recur even if speaker-ID is wrong on one clip:

1. **Default to PUSH-TO-TALK, not always-on VAD.** The single biggest privacy win. Run the mic with
   `--ptt` (hold `ctrl+alt+space` to dictate) instead of `--vad`. Then the mic is *deaf* unless Iddo
   is physically holding the key — no background conversation can ever be captured. Keep VAD as an
   opt-in "hands-free" mode that is only safe with `owner_only: true`. Recommended posture:
   **PTT by default; VAD only with owner-gate on.**

2. **Start disarmed / one-tap mute.** The mic already supports arm/disarm
   (`שירי סוף` / `מיקרופון`). Recommend it boot **disarmed** so it never types until Iddo explicitly
   arms it, and put the mute toggle on a global hotkey so guests/calls = instant off.

3. **Raise the VAD floor.** Even with owner-gating, raise `vad_rms_threshold` from **150** toward
   **220-250** so distant/background speech doesn't even trigger capture. Lowers the attack surface
   and CPU.

4. **Never auto-feed transcripts into shared/published artefacts.** This is a standing rule, not a
   one-off:
   - The corpus pipeline (`eran-poc\build_eran_corpus.py` → `eran_all_corpus.txt`) must read only
     **owner-verified** samples. After Step 3, `samples.jsonl` is Iddo-only going forward; for
     existing data, re-build the Eran corpus from the *cleaned* set (Action B) before any further use.
   - Anything that could become public (the ALMAWARE site, web PWA, gists, commits) must **never**
     ingest `history/*.txt` or `samples.jsonl`. Keep transcripts strictly local; add a checklist
     item to any publish step: "no voice transcript / sample data in this artefact."
   - Consider turning `history` logging off (or to a private, .gitignored location) by default, since
     it persists every utterance to disk.

5. **Keep `auto_enter` conservative.** With always-on capture, `auto_enter: true` means stray speech
   can be *submitted*, not just typed. Prefer `auto_enter: false` (type-only, Iddo presses Enter), or
   rely on the explicit walkie-talkie "over"/"עבור" marker for sends.

None of guards 1-5 break Iddo's ability to dictate to Claude: PTT, arm/disarm, and the owner-gate
all still type Iddo's speech into the focused window exactly as today — they only remove *other*
voices and *accidental* capture.

---

## 4. Prioritized action list

| # | Action | Type | Breaks Iddo's dictation? | Effort |
|---|--------|------|--------------------------|--------|
| **A** | Lower `voiceprint.json -> threshold` 0.70 → **0.60** (+ `reject_margin: 0.08`), then add `"owner_only": true`, `"owner_user": "iddo1"` to `config.json`. **This is the fix.** | config | **No** (0.60 ≈ 1.7% self-drop, recoverable) | minutes |
| **B** | Review/quarantine contaminated data: the **375 extra** `samples.jsonl` records (724 now vs 349 enrolled) likely contain non-Iddo speech; rebuild the Eran corpus only AFTER cleaning. Do NOT re-`enroll` from the current `samples.jsonl`. | data review | No | hours |
| **C** | Add the `_was_owner` log-sample gate (§2 Step 3) so the corpus self-cleans going forward. | code | No | minutes |
| **D** | Switch default to **PTT** (`--ptt`) for everyday use; keep VAD only with owner_only on; boot disarmed. | runtime policy | No | minutes |
| **E** | Raise `vad_rms_threshold` 150 → ~220; set `auto_enter: false`. | config | No (type-only) | minutes |
| **F** | Verify: `speaker_id.py verify` (Iddo passes ≥0.60) + `identify` a non-Iddo clip (rejected). Live smoke test. | verify | No | minutes |
| **G** | Proper EER tune + multi-centroid (collect `profiles\impostors\*.wav`, run `spk_eval.py`) per `SPEAKER_ID_IMPROVE.md`. | hardening | No (lowers false-reject) | half-day |
| **H** | Publish hygiene: ensure ALMAWARE site / web / git never ingest `history/*` or `samples.jsonl`; consider disabling on-disk history. | policy | No | minutes |

**Do A first** (stops the leak), **then C+B** (stop & clean contamination), **then D/E/F**
(defence-in-depth + verify), **then G/H** (harden + publish hygiene).

---

## 5. What was checked (chain of custody)

- `voice_input.py` — full read. Gate at 493-506 (disabled), log_sample at 597-601 (ungated),
  VAD loop 857-911, auto_enter/focused typing 760-779.
- `config.json` — full read. `owner_only` **absent**; `vad_rms_threshold:150`, `auto_enter:true`,
  `default_target:"focused"`, 9-lang whitelist.
- `speaker_id.py` — full read. Voiceprint exists; `DEFAULT_THRESHOLD=0.70`; per-profile override via
  `voiceprint.json`.
- `router.py` — full read. Pure command/target parsing; no speaker awareness (expected).
- `learner.py` — full read. `log_sample` (78-95) copies WAV + appends text, **no speaker gate**.
- `eran-poc\SPEAKER_ID_IMPROVE.md` — full read (measured FRR table, EER harness, multi-centroid plan).
- Filesystem: `voiceprint.json` (n_total 349, thr 0.70, self_min 0.4754, built 2026-06-15 18:12);
  `samples.jsonl` now **724** lines (was 349) — contamination confirmed; **no** `profiles\impostors\`
  dir exists (so FAR was never measured).
- No files modified, deleted, or moved. Running mic process untouched.
