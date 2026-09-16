# FENCE CHANGE 2026-08-26 — f0 fence lowered 200-500 → 90-350 Hz

> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

## The broken window / החלון השבור

The Stage-A search fence forced every f0 knot into **[200, 500] Hz** (the
"genome child band" from the plan) while the target corpus — **t06, Iddo's own
voice — sits at 60-90 Hz median f0** (Ear-v3 calibration measured his real
/abba/ f0 deciles at 62/72/79/94/139/177/203 Hz). The search was **physically
forbidden from sounding like its targets**. The judge could hear the mismatch;
the mouth was not allowed to fix it.

**Iddo's verdict / הפסק של עידו:** he listened to a 340 Hz Stage-A candidate
and rejected it outright — **"רע ברמות"**. (Already on 2026-08-25 he had
called a flat 220 Hz render "too high" / לא טוב.) His standing order: restart
as many times as needed.

New fence **[90, 350] Hz**: the ear pitch block covers 60-420 Hz, so the whole
new fence is fully observable by the judge. Physics unchanged; judge unchanged.

## The edited fence lines (as deployed on eran2/eran3/eran4)

`~/throat-search-v3/arms_v3.py`:

```python
F0_LO, F0_HI = 90.0, 350.0         # see the F0 FENCE note in the docstring
```

`~/mouth-v2/mouth2.py`:

```python
F0_MIN, F0_MAX = 90.0, 350.0        # fence follows the campaign (lowered 2026-08-26); physics unchanged
```

`~/throat-search-v3/ORGANS.lock`: mouth2.py sha256 re-pinned
`c75132c1...` → `031900418107761e83cedb4ec6419455eaec992b35da61a07dd858dba291a76a`,
plus a `fence_change_20260826` note field (what/why/"judge unchanged"). All
other hashes untouched.

## What was done / מה נעשה

1. Fence lowered in arms_v3.py + mouth2.py, docstring note rewritten (both
   clip layers — arms fence AND say_gesture's clip — moved together).
2. ORGANS.lock re-pinned; `organs_lock.py verify` → **VERIFIED, backend=c**.
3. All workers stopped cleanly (STOP file → `pkill run_worker` → sup loops
   saw STOP and exited → tmux throat3 killed) on eran2, eran3, eran4.
4. Fence-1 record books archived on every box:
   `run/` → `run-fence1-20260826/`, `review/` → `review-fence1-20260826/`;
   fresh empty `run/` + `review/`; STOP removed.
5. Sanity render on eran2 (ear-v3 venv, backend="c"): open vowel with
   `f0_knots [120, 110, 95]` → 9600 samples @16 kHz, peak 0.700, **autocorrelation
   f0 = 109.6 Hz** (inside 95-125 expected band). Manual worker ran 25 s:
   lock check passed, heartbeats flowed (gen 43, 516 evals), killed, temp cleaned.
6. Relaunched Stage A: **eran2 = 12 workers, eran3 = 13, eran4 = 8** — all
   heartbeats flowing at 09:18Z.

eran1, the :8830 sense organ, and the throat-search-v1 archives were not touched.

---

# Fence change 2: G5 HNR clean-voicing gate / גדר 2: שער HNR לקול נקי (2026-08-26, ~11:30Z)

## Why / למה

Iddo's ears rejected two review candidates the wdist objective liked:

| candidate | f0 | wdist | his verdict |
|---|---|---|---|
| `review-fence1-20260826/ah-1kf-0-*` (eran2) | ~340 Hz | 5.05–5.08 | "רע ברמות" (robotic) |
| `review/ah-1kf-1-*` (eran2, today) | ~136 Hz | 5.12 | "כחכוח של ווקי-טוקי" (walkie-talkie crackle) |

**Diagnosis:** the t06 target recordings carry room noise and breath; wdist
rewards matching that noise, so candidates learn to crackle. **Remedy:** a
deterministic harmonics-to-noise gate (G5) calibrated on the REAL clips'
voiced spans. Objective gate only — **judge unchanged**.

## The G5 recipe (gates_v3.py, numpy only, deterministic)

Speech span by the stage-A rule (10 ms windows, live > 10% of peak RMS);
32 ms frames every 10 ms; per frame the normalized autocorrelation peak r in
the 60–360 Hz lag band; frames with r > 0.3 are voiced, frame HNR =
10·log10(r/(1−r)); **clip HNR = p90 over voiced frames** ("the take's
cleanest sustained voicing"); no voiced frame → −99 dB. Gate: clip HNR ≥
per-unit `hnr_min`, else the standard GATE_PENALTY = 50.

## The honest tightening / ההחמרה הכנה

The plan said clip-MEDIAN + 5th percentile. **Measured: that gate failed
NEITHER rejected candidate** — on the median statistic the robotic one sits
at the **37th percentile** of Iddo's real ah takes and the crackle at the
11th (his room recordings are that noisy; median real ah HNR ≈ 0 dB).
Failing both on the median would have thrown away 37% of his real voice.
On the **p90-of-frames** statistic real takes always have SOME clean voicing
(real ah clip-p90 p10 = 1.42 dB, median 4.97) while the renders never voice
cleanly anywhere. So: **statistic = p90 of voiced frames, threshold = 10th
percentile of real takes** (90% of real clips pass). Said in full in the
gates_v3.py docstring and in ORGANS.lock `g5_hnr_20260826`.

## Thresholds (calib/hnr-calib.json, all three boxes)

| unit | hnr_min (dB) | real min | real p5 | real median | real max |
|---|---|---|---|---|---|
| ah   | **1.423** | −0.86 | 0.67 | 4.97 | 25.17 |
| ba   | **0.462** | −0.88 | 0.31 | 2.91 | 10.66 |
| ih   | **2.510** |  0.04 | 2.07 | 4.55 |  9.86 |
| ma   | **2.044** |  0.10 | 1.49 | 5.01 | 17.62 |
| abba | **0.066** | −1.13 | −0.13 | 2.33 |  7.34 |
| ima  | **0.805** | −0.49 | 0.37 | 2.30 | 10.88 |

## Regression anchors — the two rejected candidates (must always FAIL G5)

| candidate | clip HNR (p90 stat) | vs ah hnr_min 1.423 |
|---|---|---|
| robotic 340 Hz, `ah-1kf-0-*` (5 wavs) | **0.86 – 1.17 dB** | FAIL (margin 0.25–0.56) |
| crackle 136 Hz, `ah-1kf-1-*` (4 wavs) | **−0.49 dB** | FAIL (margin 1.91) |

(On the abandoned median statistic they measured −1.08…−1.37 and
−1.66…−1.67 dB — inside the real range; that is why the statistic changed.)

## Cost, measured / המחיר, נמדד

Joint G1–G5 pass on the real corpus: **ah .87, ba .88, ih .86, ma .88,
abba .87, ima .88** (was .95–.97 with G1–G4). ~12–14% of Iddo's real takes
now pay the gate — the honest price of refusing the crackle.

## What was done

1. `gates_v3.py`: G5 implemented (hnr_db + calibrate-hnr CLI + check/penalty
   wiring); `run_worker.py`: `gate_stats(aux)` → `gate_stats(aux, y)` (2 call
   sites). gates_v3 is not organ-pinned; ear3 + mouth2 untouched.
2. Calibrated on eran2 over all 600 t06 big-unit clips → `calib/hnr-calib.json`.
3. Sanity on eran2: real ah clip passes full G1–G5 path (hnr 25.17, pen 0);
   BOTH rejected candidates fail G5 through the full path (pen 50); manual
   worker ran 37 s — lock verified, heartbeats flowed (67 gens, 804 evals,
   ~22 eval/s), `best.json` gate_detail carries `G5_hnr`, exit 99 clean.
4. Objective changed → record books restarted per house law: STOP → pkill →
   sup exits → tmux throat3 killed; `run/` → `run-fence2-20260826/`,
   `review/` → `review-fence2-20260826/`, fresh empty dirs, STOP removed —
   on eran2, eran3, eran4.
5. Synced byte-identical (md5-verified) `gates_v3.py`, `run_worker.py`,
   `ORGANS.lock` (+`g5_hnr_20260826` note), `calib/hnr-calib.json` to
   eran3 + eran4; `organs_lock.py verify` → VERIFIED on all three.
6. Relaunched: **eran2 = 12 workers, eran3 = 13, eran4 = 8** — all
   heartbeats flowing at 11:26Z.

eran1, the :8830 sense organ, and the v1/fence1 archives were not touched.

---

# Fence change 3: G6 duration + G7 clean-tail + G8 voiced-dominance / גדר 3 (2026-08-26, ~16:20Z)

## Why / למה — two verdicts in one afternoon

| candidate | wdist | his verdict |
|---|---|---|
| `review-fence3/ma-free-1-2026-08-26T155605Z` (eran4) | 3.849 | "בסוף יש הרבה חריקת אוויר, והמָא קצר מדי" |
| `review-fence3/ah-free-0-2026-08-26T160658Z` (eran3) | 4.056 | "אוויר ו-10% אה — לא ברור מה זה" |

Both wavs are preserved as regression anchors in
`~/throat-search-v3/regression/rejected-20260826/` on all three boxes.
Objective gates only — **judge unchanged**.

## The gates as shipped (calib/duration-calib.json, all three boxes)

- **G6_duration** — **MEASURED DEVIATION, in the open** (the G3_LO_FLOOR
  precedent). Ordered: speech-span duration in [p10, p90] of real takes.
  Measured: the rejected ma's span is **0.450 s = the 36th percentile** of
  real ma spans — his real takes trail off in long natural breath that keeps
  the stage-A span alive (real ma spans bimodal: p10 0.34, median 1.18).
  No honest percentile of span duration fails a candidate at p36. What DOES
  separate: the **strong-voiced core** — frames voiced per the exact G5
  recipe AND frame RMS ≥ 25% of the take's peak frame RMS. Rejected ma core
  0.182 s = below 99/100 real takes. **G6 = core_s ∈ [p5, p95]** of real
  takes (p5/p95, not the ordered p10/p90, so the marginal cost stays 10%).
- **G7_clean_tail** — as ordered: RMS(after the LAST voiced frame → clip
  end) / RMS(voiced span) ≤ p90 of real takes. **Honest finding: catches
  NEITHER rejected candidate** — their squeak is QUIETER than Iddo's natural
  breath (ma tail ratio 0.115 = real p15). Also measured and rejected: the
  ordered alternative (max 32 ms-frame RMS vs voiced median — candidate at
  ~p40), tail tonal-fraction, tail centroid, tail duration — real tails
  overlap the squeak on every one. G7 stays as the guard it CAN be
  (louder-than-breath tails) — and it newly catches **4 of the 6 v1cheat
  wavs, which pass G1–G5** (they previously failed only the campaign wdist
  criterion).
- **G8_voiced_dominance** — as ordered: voiced_frac (r>0.3 frames / span
  frames) ≥ p10 AND voiced-energy-share ≥ p10 of real takes. **Honest
  finding: catches neither rejected candidate** — their "air" is TONAL
  (autocorrelates at r>0.3, so the G5-recipe voicing rule counts it as
  voiced): the ah sits at **vf p27 / ves p41** of the real distribution; the
  honest tightening that would reach it (p28+) throws away 28% of Iddo's
  real voice. G8 stands against the APERIODIC-air render (true breath-noise
  filler, vf → 0), which is the root-cause variant it was designed for.

**Both rejected candidates fail the joint gate check via G6, decisively.**

## Thresholds / הספים

| unit | G6 core [lo, hi] s | G7 tail_max (rms ratio) | G8 vf_min | G8 ves_min |
|---|---|---|---|---|
| ah   | 0.162 – 0.961 | 0.3831 | 0.713 | 0.855 |
| ba   | 0.181 – 0.512 | 0.3282 | 0.612 | 0.836 |
| ih   | 0.301 – 1.363 | 0.6555 | 0.674 | 0.888 |
| ma   | 0.252 – 1.303 | 0.4830 | 0.758 | 0.884 |
| abba | 0.242 – 1.065 | 0.4629 | 0.603 | 0.689 |
| ima  | 0.290 – 1.363 | 0.7533 | 0.693 | 0.729 |

## Regression anchors — the rejected candidates' numbers (must always FAIL joint)

| measure | ma-free-1 (unit ma) | ah-free-0 (unit ah) |
|---|---|---|
| core_s | **0.182 → FAIL G6** (< 0.252) | **0.122 → FAIL G6** (< 0.162) |
| span_s | 0.450 (real p36 — why the ordered G6 recipe was deviated from) | 0.470 |
| tail_rms_ratio | 0.1153 (thr 0.4830 — passes; real p15) | 0.3768 (thr 0.3831 — passes by 0.006) |
| tail_max_ratio | 0.4012 | 1.2925 |
| voiced_frac | 0.7619 (min 0.7582 — passes by 0.004) | 0.7727 (min 0.7134 — passes; real p27) |
| voiced_energy_share | 0.9904 (min 0.8844 — passes) | 0.9841 (min 0.8550 — passes; real p41) |
| clip HNR (G5) | 17.33 dB — passes | 8.64 dB — passes |
| joint G1–G8 | **FAIL** (G6) | **FAIL** (G6) |

## Cost, measured / המחיר, נמדד — the ordered ≥90% joint bar is NOT met

Joint G1–G8 pass on the real corpus: **ah .73, ba .66, ih .68, ma .70,
abba .68, ima .68** (was .86–.88 at G1–G5, .95–.97 at G1–G4). The ordered
"≥90% joint" is arithmetically unreachable: G5 costs 10% (p10), G6 10%
(p5+p95), G7 10% (p90), G8 13–18% (two p10 conditions), and the failures
are mostly independent clips. Per-gate marginal costs are exactly the
constructed ones; nothing is hidden. The v1cheat regression: **6/6 still
fail** (4 via G7-new, 1 via G4, 1 via G1+G4+G6+G7).

## What was done

1. `gates_v3.py`: span_tail_stats() (span_s, core_s, tail ratios, vf, ves) +
   calibrate-durtail CLI + check/penalty wiring → G6/G7/G8 live in the
   objective (run_worker unchanged — it already passes y). Calibrated on
   eran2 over all 600 t06 clips → `calib/duration-calib.json` (both tail
   measures' and both duration measures' distributions recorded for audit).
2. Verified through the full features_with_aux path: both rejected wavs FAIL
   joint (via G6), 6/6 v1cheats fail, per-unit joint rates as above.
3. House restart: STOP → pkill run_worker[.]py → sup loops exited → tmux
   throat3 killed; `run/` → `run-fence3-20260826/`, `review/` →
   `review-fence3-20260826/`, fresh dirs, STOP removed — eran2/eran3/eran4.
4. ORGANS.lock: `g6_g7_g8_20260826` note added (judge unchanged; gates_v3
   still not organ-pinned; ear3+mouth2 hashes untouched). Synced
   byte-identical (md5-verified) gates_v3.py + hnr-calib.json +
   duration-calib.json + ORGANS.lock + regression anchors to eran3/eran4.
5. Sanity on eran2: manual worker 73 s — 105 gens, 1470 evals (~20 eval/s),
   heartbeat flowed, `best.json` gate_detail carries G6_duration,
   G7_clean_tail, G8_voiced_dominance, exit 99 clean.
6. Relaunched for the overnight run: **eran2 = 12 workers, eran3 = 13,
   eran4 = 8** — all 33 heartbeats within 1 s of wall clock at 16:23Z.

eran1, the :8830 sense organ, and the v1/fence1/fence2 archives were not touched.
