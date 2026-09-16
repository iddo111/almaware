> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

# 20 — THE MIC (KESHEV) · המיקרופון

**Measured 2026-09-11 08:21–08:25** on this PC. Everything below has a number and a timestamp.
Iddo said *"עם כל הכשלונות וגם המיק — הכל"* — so the mic is in the pack. **But read the first line:**

> ## ⛔ אל תיגע במיק. NEVER TOUCH THE MIC.
> The mic is **another agent's area** and it is **Iddo's flow state**. You may **READ** everything
> here. You may **not** start it, stop it, restart it, re-point it, change a gate, change a device,
> or write `state\PAUSED`. **The mic has been PAUSED by Iddo himself since 04:23:52 today — leave it
> paused.** Breaking the audio law has cost real money ($100 on 09-09) and real trust.

---

## 1. What is running right now — VERIFIED 2026-09-11 08:21

| piece | state | evidence |
|---|---|---|
| **Window** | KESHEV 6 — `keshev-next\app\gui6.py` | owns the engine, records `state\mic.pid` |
| **Engine** | `keshev-next\app\main.py` | `state\mic.pid` = **17880** |
| **Launched by** | Scheduled task `KESHEV` → `RUN-KESHEV6.cmd` → `tools\preflight6.py` → `state\keshev6-env.cmd` | |
| **Device** | `Microphone (Logitech BRIO)` / `Windows WASAPI` | `state\mic-choice.json` |
| **Heartbeat** | fresh, age **0.1 min**; log age 0.3 min | watchdog `facts` |
| **PAUSED** | **YES — by Iddo, signed, 237.9 minutes** | `state\PAUSED` |
| **Delivery watchdog** | verdict **OK**, 0 alarms, 2 warnings | `tools\watchdogs\keshev-delivery.json` |

The signed pause reads, verbatim:
```json
{ "who": "iddo (pause button in KESHEV 6)",
  "why": "הוא לחץ השהה -- the mic stays off until he presses האזן",
  "at": "2026-09-11T04:23:52.296435",
  "restore": "press האזן in the window, or delete state\\PAUSED" }
```
**That is the SIGN-THE-PAUSE law working.** An unsigned pause would have been auto-cleared in 15
minutes — which is exactly what happened to him on 09-07 and cost 43 minutes of his room being typed
into his chat. Do not delete this file.

### Today's delivery counts (the 3 MB log tail)
`typed 1582 · empty 8351 · skip 12046 · fail 3 · guarded 0 · blocked 0`
**delivery_rate 0.1592** against a measured baseline median of **0.1561** (n=1248 over 23.7 h).
**This is normal, not a fault.** See §4 — `decode=empty` is the honesty guard working.

---

## 2. The decoders — VERIFIED 2026-09-11 08:25

**The decoding happens on the DGX, not on the PC.**

| door | role | probe result |
|---|---|---|
| `eran1:8739` — `keshev6-stt.service` | **PRIMARY** — `ivrit-ai/whisper-large-v3-turbo-ct2` int8_float16 + lexicon prompt | **401** (auth-gated = **alive**) |
| `eran1:8737` — `keshev-stt.service` | **FALLBACK** — old model + `iddo-lora-run2-ct2` | **401** (alive) |
| `PC:8737` | off since 2026-09-05 19:12 | **000** (down, on purpose) |
| `PC:8738` | rescue path for `preflight6` only | **000** (down, on purpose) |

**`401` is the correct answer for "alive".** A bare probe without the token is **not** a liveness
check — this cost a whole deaf night on 08-15.

**The measured reason for the primary/fallback choice** (same 209 of his own segments, 09-05):

| | names right | garbled | CER | p50 |
|---|---|---|---|---|
| **eran1:8739** | **13** | **0** | **18.5%** | **250 ms** |
| PC:8738 | 13 | 0 | 18.5% | 375 ms (contended) |
| eran1:8737 | 0 | 14 | 43% | — |

The fallback is a **deliberate downgrade he can SEE**: gui6 turns the badge amber ("גיבוי!") and
names the server. `KESHEV-STT-PC` is a **disabled** scheduled task **on purpose** — re-enabling it
relaunches an unused 3.2 GB PC decoder at logon and undoes the VRAM saving.

### The lexicon is the source of truth on eran1, not here
`eran1:/home/eran1/keshev6/lexicon.py` is **canonical**. `D:\CLAUDE\keshev-6\lexicon.py` is a **copy**.
On 09-06 they differed by 836 bytes — Iddo's own 04:30 fix (Assassin's Creed / Meshtastic /
Kropotkin) lived only on eran1, and **a redeploy from the PC would have silently reverted it**.
Fingerprint: `LEXICON-DEPLOYED.json`. **Run `tools/lexicon_parity.py --fetch` before any deploy.**

---

## 3. The phone door — VERIFIED 2026-09-11 08:25

| port | what | probe |
|---|---|---|
| `:8893` | `intake\phone_mic_web.py` — the phone mic page (tailscale serve terminates TLS) | **200** |
| `:8892` | `intake\keshev_intake.py` — token-gated, window-locked PC sidecar | **401** (alive) |
| `:8894` | `intake\voice_coder_web.py` — "הקודר בקול", hold-to-talk to the 480B | **200** |
| `:8895` | **NOT mic** — Eran Federation panel | — |

Phone → our STT on eran1 → intake :8892 → `app\typer.py`.
**:8893 still keeps the phone mic stream open for the page's lifetime** — the same pattern that cost
the $100 fine on :8894. It is **flagged and NOT changed unasked**. That is a decision for Iddo.

---

## 4. The gates are NUMBERS, never edits

They live in `RUN-KESHEV6.cmd` with their measurement written beside them:

| gate | value | why that number |
|---|---|---|
| `KESHEV_RMS_FLOOR` | **600** | 08-30: at a lower floor, 1,240 of 2,252 segments (55% of everything he said) were thrown away as "too quiet". The real cause was the Windows input slider. |
| `KESHEV_VAD_MIN` | **0.60** | 08-31: the room hum sits at voiced_ratio 0.47–0.56, his speech at 0.66–0.85. 0.40 let the hum through and produced **1,196 "תודה" drops** in a day. |
| `KESHEV_LOGPROB_FLOOR` | **−0.40** | 09-04: across 33 typed texts, junk fell in −0.93…−0.42 and real speech in −0.29…−0.02 — a perfect empty gap. Re-measured at 18:40 on a live hour, real speech reached **−0.36**: the margin is **0.04**, not 0.11. |

**If his quiet speech gets eaten, LOWER the number — do not touch code.** A −0.95 floor was tried
again on the evening of 09-04 and is **WRONG**: it lets the entire junk band through.

### `decode=empty` (78–87% of segments) is NOT lost speech
30 of 30 "empty" WAVs produced **no Hebrew sentence from three independent decoders** — they are
laughter, breath, and room noise. `no_speech_prob` was 0.0 on all of them and is useless here.
**Empty is the guard working.** *"The 78% empties are the price of never losing a word again."*
**Only Iddo's ear can rule** on whether any real speech hides in the empties — and he has not.

---

## 5. The generations — 5 rebuilds, 13 codebases, ≥80 breakages in 77 days

| generation | dates | state |
|---|---|---|
| `voice-input` | 05-31 | gen 1, Whisper collage. **Retired.** Its `config.json` `never_use_devices` is the reference list. |
| `alma-mic` | 06-28 | gen 2, GPU STT. **Retired.** Its `ALMA-MIC-*` tasks are **Disabled and must stay so.** |
| `mic-rebuild` = **KESHEV A** | 08-12 | 57 scars, its own `.git`, the PC STT server source. **This is the rollback** — it refuses to start while keshev-next lives. |
| `keshev-b` / `keshev-2` / `keshev-4d` / `keshev-qwen` | 08-15…20 | fleet-written experiments. **Dead.** `keshev-b` holds a verdict file literally named `…CONTAINS-FABRICATED-EVIDENCE.md`. |
| `keshev-fable` | 08-18 | a one-day Fable rewrite; `LANG_FLIP` lives here. Was live until 08-25. |
| **`keshev-next` = KESHEV 5000** | 08-25 02:12 | **LIVE** + the `keshev-6` decoder (09-03/04). |

**Every generation hit the same wall** — vanilla Whisper on code-switched Hebrew — and **the same bug
species**: *guards written, tested green, and structurally never in the code path*. There were
**0 native crashes** in the 7 days before the 09-03 commission; **48 engine starts, ~40 of them by
agents**. Every restart is an hour deaf while the model reloads.

---

## 6. The mic laws that bind you

1. **ONE-MIC LAW** — exactly one dictation transcriber on this PC, ever. keshev-next is canonical.
   Doubled typing means a second mic. A second Whisper on the shared GPU **silently starves the real one**.
2. **AUDIO PROTECTION LAW / USB-MIC-ONLY** — never open, claim, duck, mute or play through his
   speakers or headphones. **A listening Bluetooth headset is NEVER a microphone.** The refuse list
   is enforced in `keshev-next/app/main.py` `device_allowed()` and must never be softened.
   On the phone: **opt-in only, bare `{audio:true}`, release the stream after every clip.**
3. **The WINDOW owns the engine.** Restart via WM_CLOSE to the window, never by killing the gui or
   the engine. **Never filter or kill `python.exe` by name on this box.**
4. **PAUSED is sacred and signed** (`who/why/at/restore`). Only the pause buttons write it. An agent
   never writes or deletes it. **Receipts go BESIDE the file, never ON it.**
5. **Never debug on the live mic.** Use the offline replay rig (`mic-rebuild/tools/replay`).
   A GUI fix runs as a console instance with stderr captured **before** his copy is relaunched.
6. **The PC is sacred for CPU too.** Any job over ~10 s runs **BELOW_NORMAL** with a wall-clock cap,
   or on the fleet. The engine is HIGH, the window ABOVE_NORMAL. Check `state\gui.heartbeat` first.
7. **UIPI** — never launch his terminal/CLI/apps from an elevated shell. When he says "it types
   everywhere except X", run `python app/typer.py --selftest` FIRST.
8. **Privacy** — transcripts, WAVs, spool, corpus and tokens **never** enter git or a pack.
   When the mic catches someone else's private talk: **preserve, one line to Iddo, offer to pause.
   No purge operations.**
9. **Device physics** — open by **NAME + host API**, never index. **PortAudio freezes its device list
   at init**: a running engine can never see a replugged BRIO. Never pick a WDM-KS pin.
   **The Quest USB Link and the BRIO must not share a USB controller.**
   **Heartbeat "N blocks": ≈937 = full, ≈34 = starved. `peak_rms` above ~10,000 = clipping.**
10. **KESHEV is NOT for sale.** End-to-end lag ~1.5 s plus a personal LoRA inside. Never on any
    income, launch, or publication list.
11. **Ignore his self-talk.** The mic types everything he mutters. Answer only what is aimed at you.
    `lp < ~−0.45` is unreliable; near −0.1 it really is him.

---

## 7. How ERAN's ear and mouth relate to KESHEV — the part that is actually your business

**They are different organs on different feature spaces. Do not confuse them.**

| | KESHEV | ERAN |
|---|---|---|
| purpose | turn **Iddo's** speech into text he can use now | let a child **learn** to hear and speak |
| ear | Whisper / `ivrit-ai` large-v3-turbo-ct2, a finished ASR model | **Ear v3 (CARFAC)**, 996-d, with the **frozen 192** inside forever |
| mouth | none — it only listens | **mouth2**, a Pink-Trombone-physics adult tract, C twin `voc_eran.c` |
| judge | CER, logprob, and Iddo's frustration | Iddo's **blind** ear, and only his |
| can it train? | LoRA on eran4, nightly, promote only if strictly better | **never on the PC**, fleet only |

**The four places they actually touch:**

1. **They share eran1's RAM, and that has killed ERAN.** `keshev-stt` (146 GB vm) was OOM-killed at
   13:39 on 09-07 and took `eranb-life` with it at 13:40:07. `keshev-stt` and `keshev6-stt` still run
   on eran1 today, beside ERAN, against the law *"eran1 hosts ERAN and nothing else"*.
   **If you add anything to eran1, check `oom_score_adj` first** (ERAN is at −900).
2. **The phone mic (:8893) is the only new supply line for his voice.** ERAN's food problem is that
   there are 3 clips for 19 of the 22 syllables. The booth is the other supply line. Neither has
   produced a second session.
3. **The mic's laws are ERAN's laws, one domain over.** Sign the pause; a watcher may only act on a
   state it can name; a repair never writes into the fault file; gates are numbers with their
   measurement beside them; `health: ok` ≠ working. Both projects learned each rule independently,
   which is the strongest evidence it is real.
4. **`D:\קפה-קלוד` (7.7 GB of his voice) is the standing answer to "we need his voice as data"** —
   use it, never ask him to record. **2026-06-25 and 2026-07-01 are RESERVED eval sessions and must
   never enter any training pool.** It is **not** in this pack: privacy.

---

## 8. What is broken in the mic right now (do not fix without asking)

- 🔴 The delivery watchdog's **receipts sub-check fails every run** — `RAMCHAT\receipts.py` times out
  past its 120 s cap. Open broken window.
- 🟡 `KESHEV-Watchdog` (the old mic-rebuild task) has been **Disabled since 2026-08-18 07:43 and
  nobody noticed** — the watchdog says so itself, in its own warnings. Delete the task or re-purpose it.
- 🟡 `:8893` keeps the phone mic stream open for the page's lifetime — the $100 pattern.
- 🟡 **Owner-voice gating** (only HIS voice types) has been a **binding but unbuilt** requirement
  since 08-18. Until it exists: mute videos while dictating.
- 🟡 The nightly LoRA loop on eran4 has **never recorded a promotion**, and KESHEV-6's public Hebrew
  model now beats the personal LoRA (13 names vs 0). Is the LoRA track still wanted?
- 🟡 **Corrections are the gold and are still NOT captured.**
- 🔵 The **confidence floor was calibrated from only 33 old samples** and currently drops a large
  share of everything decoded. Iddo has been asked for a ~20-minute blind-labelling sitting (80
  segments) so the floor can come from his ear. He has not done it.

## What is in this pack for the mic

`code/keshev-next` · `code/mic-rebuild` (the 57-scar PHASE1 inquiry — **read it**) · `code/keshev-6` ·
`code/keshev-fable` · `code/keshev-2` · `code/keshev-b` · `code/keshev-4d` · `code/keshev-qwen` ·
`code/keshev-lora` · `code/keshev-voicefull` · `code/limud-keshev` · `code/voice-input` ·
`code/alma-mic*` (release, android, android-v2, linux) · `code/tools-watchdogs` ·
`docs/VAADA-KESHEV-20260903.md` · `docs/KESHEV-EMPTY-20260903.md` · `docs/KESHEV-6-20260904.md` ·
`docs/MIC-CHESHBON-20260904.md` · `docs/MIC-HALLUCINATION-*.md` · 38 mic memory files in `memory/`.

**Not in this pack, on purpose:** every `.wav`, `trial.log`, the 48,765 segments (4.9 GB of his
voice), the spools, the corpora, the models, and every token — **and, removed by the 09-11
verification pass, `keshev-6/state/{ref,ablate,join_test,empties_sweep,realspeech_20260904,
vadtest_20260904}.jsonl` and `alma-mic/testset.json`: those hold his DECODED WORDS in their
`ref` / `ref_text` / `new_text` / `solo` fields. A filename rule cannot see that. Scan content.** They are listed as pointers in
`MANIFEST.txt`. You read them **in place on the PC**, never copy them anywhere.
