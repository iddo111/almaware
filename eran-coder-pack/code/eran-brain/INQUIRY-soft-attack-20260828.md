# 🪟 BROKEN WINDOWS LAW — חוק החלונות השבורים: if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy.

# INQUIRY — the attack is soft on EVERY unit, not just /b/

**Opened 2026-08-28 16:45 by claude-cli-VR. Nothing was restarted; v4 is untouched and running (28 workers, eran2/3/4).**

## The measurement

Metric: the largest rise of the short-time envelope (4 ms window, 1 ms hop) across any
15 ms span, with the envelope floor **clamped at 45 dB under the clip peak**, so leading
digital silence cannot manufacture a rise the mouth never made. Same code, same clamp,
applied identically to real clips and to ERAN renders.
Script: `eran2:/tmp/burst.py` + `/tmp/floor.py`.

| | clamped 15 ms rise | pre-onset floor rel. peak |
|---|---|---|
| HUMAN ba (n=100) | **21.3 dB** | −35.0 |
| HUMAN ma (n=100) | 20.9 dB | −30.4 |
| HUMAN ah (n=100) | 22.1 dB | −35.7 |
| ERAN ba-cv-2 best (v4, wdist 4.107) | **14.1 dB** | −28.7 |
| ERAN ba, all 9 live arms | 10.9 – 15.5 dB | −27 to −36 |
| ERAN ma-nasal / ah-1kf / ih-1kf | 10.3 – 15.1 dB | −12 to −26 |

## What it says

1. **The deficit is ~8 dB and it is on EVERY unit — including /ah/, which has no burst at
   all.** So it is not a property of the lip release. The metric does not discriminate ba
   from ah in humans either (21.3 vs 22.1) — it measures *attack*, and ERAN's attack is
   soft everywhere.
2. **The burst dials are already near their limits and did not close it.** The ba-cv-9
   winner chose `gain 45.6` of a 60 ceiling, `tau_s 0.00214` sitting on the 0.002 **floor**,
   `glide 0.0616` near the 0.02 **floor**. The search is pushing as hard as the fences
   allow. Widening those fences again is therefore unlikely to be the answer.
3. Fourth time in two days that a stall looked like a search problem and was not
   (velum → glide → burst → this).

## Where to look next — NOT yet done, no code touched

Upstream of the burst: the amplitude envelope that `say_sequence` applies between
keyframes, and the glottal-source onset. If the whole clip ramps in, a fast lip release
cannot show, because the loudness behind it is still climbing.

## The other clean fact — from ERAN's own ear, not my metric

`run/ba-cv-9` review 13:20 UTC: `nearest` = **ba 4.2863**, **ma 4.3084**.
**A margin of 0.022.** `review_flagged: true`.
His best /ba/ is still, to his own ear, barely not /ma/.

## What this is NOT

One invented metric, written down so it can be checked and argued with. It is **not** the
`wdist` objective and must not be substituted for it. And it is not Iddo's ear, which is
the only judge that closes a unit.

Related: `CAMPAIGN-v3-CLOSED-20260828.md`, `INQUIRY-nasal-ba-20260827.md`.

---

## ⛔ 2026-08-28 17:5x — the leading hypothesis is REFUTED, and two claims above are corrected

### The hypothesis
`mouth2.py:276` hardcodes a **10 ms one-pole low-pass on the glottal intensity envelope**
(`c_v = exp(-1/(0.010*FS))`, comment: *"no clicks"*). A fixed constant capping how fast
loudness may rise, in exactly the place a dial belongs — the fifth instance of the pattern.
It looked like the answer.

### The test
`~/mouth-v2` was **copied** to `/tmp/mouth-probe` (never edited in place — ORGANS.lock and
the CORTEX-FREEZE LAW), the constant made env-tunable, and the **same gesture** rendered at
five time constants. `tenseness_knots` had to be supplied as `[0.6]*3` (see the gap below),
so the absolute value is not the winner's clip — but the comparison across tau is clean,
because only tau changed.

| onset tau | clamped 15 ms rise |
|---|---|
| **0.010 s (shipping)** | **12.4 dB** |
| 0.005 s | 8.9 dB |
| 0.002 s | 8.8 dB |
| 0.001 s | 8.8 dB |
| 0.0002 s | 8.8 dB |
| *human ba* | *21.3 dB* |

**Making the onset 50× faster does not sharpen the attack — it makes it slightly duller.**
The 10 ms smoother is not the bottleneck. **Do not touch it.** The soft attack comes from
somewhere else — the tract/burst physics, not the intensity envelope.

### Correction 1 — "the burst dials are pinned near their limits" was a one-snapshot claim
`review/ba-cv-9-2026-08-28T132016Z.json` had `gain 45.6` of a 60 ceiling. The **14:50**
review of the same arm has **`gain 1.0` — the floor** — and `tau_s 0.0224`. The search is
**exploring** the range, not pinned to it. The original bullet 2 above overstated a single
sample as a trend. It is withdrawn.

### Correction 2 — a winner cannot be re-rendered from its own review file
The 08-28 note in `run_worker.py` says *"RECORD WHAT YOU CHANGE"* and added `burst`. But
the recorded gesture is `[keyframes, durations, f0_knots, glide, burst]` — **`tenseness_knots`
is still missing**, and `say_gesture` requires it. So no review record is self-sufficient.
Worth one line in the writer.

### What is still true
The measurement stands: **~13 dB vs ~21 dB, on every unit including /ah/.** The deficit is
real and it is not specific to /b/. The cause is still unfound.


---

# 2026-08-28 23:1x — IDDO'S EAR CLOSED IT. The defect is the VOWEL, not the burst.

**He heard the live clip over Tailscale (eran2:8845) and gave three items, verbatim:**
*"בבה חסר יותר פיצוץ / יותר אה אחרי זה / ויש נזליות אנפוף להוריד אותו."*
(1) not enough burst · (2) more /ah/ after it · (3) nasality, remove it.
**The same two remarks he made on 08-27.** The velum fence and the burst dials did not fix
what his ear hears.

## The measurement his ear pointed at

Onset peak vs vowel RMS (vowel = everything 60 ms after onset), same code both sides:

| | burst peak | vowel RMS | **burst : vowel** |
|---|---|---|---|
| ERAN, 6 live ba arms | 0.218 – 0.700 | **0.041 – 0.056** | **+12.9 to +23.5 dB** |
| HUMAN, 6 real clips | 0.021 – 0.476 | 0.021 – **0.158** | **−2.1 to +9.6 dB** |

**ERAN's onset-to-vowel balance is 15–25 dB away from human.** His absolute burst is not
small — 0.22 to 0.70. **His vowel is roughly 3× too quiet for it.**

## What this makes of the three remarks — one defect, not three

- **"more ah after it"** — measured, and the largest single gap. His vowel carries a third
  of the energy a human vowel carries relative to the onset.
- **"not enough burst"** — the onset is *loud* but *slow*: 13 dB rise over 15 ms against a
  human 21 dB (see above). Loud-and-slow does not read as a plosive; it reads as a swell.
- **"nasality"** — a slow onset followed by a weak vowel **is** the acoustic signature of
  /m/. This is why the nearest-unit margin to `ma` is now exactly **0.0000** while `wdist`
  fell **below** the human mean (3.8240 vs 3.9115). The metric fell; the identity did not
  arrive.

## The mechanism to examine next — NOT yet tested, nothing touched

`mouth2.py:85-86` peak-normalises the whole clip: `m = max(|y|); y = y/m*0.7`.
For a /ba/ the peak sits at or near the onset, so **every dB added to the onset is a dB
taken from the vowel.** That is a direct structural trade-off between remark (1) and
remark (2) — the synth cannot currently give him both, which is exactly what he asked for.

**Do not "fix" this by removing the normalisation** — the ear's targets were calibrated
against it (`ear3/calib.py`, one SPL applied identically to disk wavs and mouth renders).
Changing it invalidates every number ever recorded. The question to answer first is whether
the vowel deficit is in the *gesture* (too short / too closed a vowel segment) or in the
*normalisation headroom*, and that is answerable on a copy without touching the live search.

## Refuted, for the record
The 10 ms one-pole on the glottal intensity envelope (`mouth2.py:276`) was tested on a copy
at `/tmp/mouth-probe`: tau 0.010 → 0.0002 moved sharpness 12.4 → **8.8 dB**. **Faster is
duller. Not the cause. Do not touch that constant.**

Verdict filed: `eran-brain/judging/iddo-verdicts.jsonl`, verdict=2 (reject).
