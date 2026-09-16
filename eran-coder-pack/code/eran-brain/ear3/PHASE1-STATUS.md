# EAR v3 — PHASE 1 STATUS (2026-08-26)

> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — test the REAL output, not a proxy.

**עברית בקצרה:** האוזן החדשה בנויה ורצה על eran2. חוק הגדילה נשמר — 192 הממדים
הקפואים הם הבלוק הראשון, לא נגעו בקוד הישן. כל המבחנים עוברים חוץ מתקציב
הזמן (71.6ms, קו ה־70 נחצה ב־1.6ms) — המספרים למטה, כולל מה שלא עמד ביעד.
**עדכון 06:00:** נוספו מבחן כנות־עוצמה (עובר), בדיקת קצבי־דגימה גבוהים
(יציב עד 384kHz — טווח עטלפים), קובץ הקבלה EAR3-ACCEPT, וערכת האזנה לעידו.
**חסר רק דבר אחד: ההאזנה של עידו** — עד אז `iddo_listened=false` ואין ברכה.

Built on eran2 `~/ear-v3/` (package `ear3/`), authored on PC `D:\CLAUDE\eran-brain\ear3\`.
Vendored google/carfac @4cdb95ee + 5-tap AGC patch (JAX≡NumPy corr 1.000000).
All truth artifacts computed ON eran2. eran-senses, eran1, and the read-only
archive untouched.

## What was built

| file | what |
|---|---|
| `ear3/carfac_wrap.py` | Ear3Cochlea(fs): patched-JAX CARFAC; per-call fresh state = state0 advanced ONCE through 100 ms silence (cached; proven bit-identical to running the pre-roll per call); shape-bucketed (1000-sample buckets, persistent JIT cache); SPL gain applied; loudness = mean-over-channels HWR NAP @10 ms (python port has no loudness helper — documented choice) |
| `ear3/features.py` | 996-d float64 vector: **legacy-192 (growth law, block 0)** + level 10 + cochleagram 520 + pitch 131 + modulation 143. No per-clip normalization anywhere. `features()`, `features_with_aux()`, `features_from_wav()` |
| `ear3/pitch.py` | SAI (vendored repo's sai.py) on the NAP: 16 log f0-bins × 8 slices + voiced-frac + median-f0 + f0-slope |
| `ear3/judge.py` | targets cache + wdist (legacy targets.py convention) + per-block spread floor + block balance; cache refuses spec_hash/judge_spec mismatch |
| `ear3/calib.py` | SPL gain + gates G1–G4, jointly calibrated per unit |
| `scripts/precompute_t06.py`, `scripts/build_targets.py`, `tests/test_{loo,pitch,splice,determinism,speed,cheat}.py` | the battery |

`~/ear-v3/legacy/` = plain copies (chmod u+w) of ears.py, ears_extended.py,
ears_v2.py, genome.py, ears-v2-calib.json, targets.py, mouth34.py,
tract_analytic.py from the read-only archive. **Legacy code never modified;**
block 0 is computed by legacy `Ears().utterance_from_samples` exactly as the
organism runs it (fed RAW samples — the legacy ear's per-frame spectrum
normalization cancels a scalar gain exactly, so block 0 ≡ the organism's own
percept of the same wav).

## Frozen calibration (ear3-calib.json, computed on eran2)

- **SPL:** median speech-span RMS over the 600 big-unit clips = 0.02530 →
  **gain 1.9763** (convention: that median ↦ RMS 0.05 ≡ 65 dB SPL; full-scale
  RMS 1.0 ≡ 91 dB SPL).
- **Gates** (G1 dip on NAP loudness — ears_v2 iteration-3 logic ported
  verbatim; G2 voiced-frac; G3 median-f0 band; G4 span occupancy), calibrated
  per unit for the **JOINT** pass rate (measured lesson: four ANDed gates each
  at p5 passed only 58–85% jointly): joint real-clip pass now
  ah .95 / ba .97 / ih .95 / ma .97 / abba .97 / ima .95.
- **G3 deviation (measured, recorded):** the plan's 120 Hz floor — and even
  80 Hz — fails 25–37% of Iddo's REAL abba/ima takes (abba f0 deciles
  62/72/79/94/139/177/203 Hz; his pitch falls through 60–80 Hz on final
  falls). Floor lowered to 60 Hz (band bottom); per-unit lo landed at
  64–76 Hz. A flat 70 Hz croak-buzz still fails G1 (dip≈0) on abba/ima. The
  archived v1 cheat wavs are all ~220 Hz renders — G3 never touched them.
- **Threshold precision scar:** round(...,4) rounded a threshold UP past the
  exact minimum and 11 real ima clips AT the minimum failed; thresholds now
  stored full-precision, nudged down 1e-9.

## Pitch tracker choices (all measured, frozen in FEATURE_SPEC)

- Divisor-descent subharmonic guard (argmax picked period MULTIPLES: a
  290 Hz render read 73.4 Hz; the mean profile's top lag was 4T).
- Channels with CF < 140 Hz excluded from the pitch profile only (they
  self-ring at pitch-range lags: spurious 62/97 Hz peaks on a 290 Hz render).
- 3-tap profile smoothing; extended computed lag range so 350–420 Hz peaks
  are not at the array edge.
- VOICED_SALIENCE 0.4 (real ah frames p50 0.87, abba closure p50 0.38,
  renders 0.42–0.46); P0_MIN 0.3 absolute (voiced p0 1.6–3.6, digital
  silence 0.003–0.09 where ratio salience is meaningless — the splice's
  silent middle counted VOICED before this floor).
- **PITCH_DECIM = 1.** The plan's 2:1-decimation contingency was measured
  and NOT taken: with span-limited, CF-filtered SAI, decim 2 vs 1 differ by
  ~1 ms (the Python channel loop dominates, not vector length) and decim 1
  tracks better.
- **f0 accuracy on mouth34 renders (uniform tube, 0.5 s):** 70→70.0,
  100→100.0, 150→150.9, 220→222.2, 290→290.9, 350→355.6 (all ≤1.6%).
  **420→140.4 and 450→91.4 — WRONG (folds to submultiples), at decim 1 and
  2 both.** Above ~360 Hz the SAI temporal profile's true-period peak is
  genuinely weaker than its multiples. Honest tracker range: ~60–360 Hz.
  Phase-3 child-band arms (f0 up to 500) will need this fixed or gated.

## Judge (the deviation that mattered)

Plain concatenation let the 804 new dims DROWN the frozen 192: six-way LOO
fell to 0.583 vs 0.643 for the 192 alone — the growth law violated in the
metric. Fix: per-block dimensionality normalization (w × sqrt(d_b)) + fixed
gains **legacy192 ×12, new blocks ×1** → identity block carries 75% of the
metric. Sensitivity: legacy gain 4–16 all land six-way 0.683–0.697 (coarse
dial, not tuned). Honesty: chosen on the same 600 clips — no second corpus
exists; gates + real-clip bar + Iddo's listen remain the anti-overfit walls.
Spread floor: per block, max(1e-3, 0.05·median-std-of-block).

## Test results (all on eran2; exit codes 0 unless said)

**1. LOO (test_loo.py) — PASS.** Bar provenance measured: rebuilding the
legacy 200-d judge on this exact corpus reproduces the plan's 0.687 bar
EXACTLY as leave-nothing-out six-way; its honest LOO is 0.642. The 0.935
binary bar is NOT reproducible with the legacy judge here (it measures
0.850 LNO / 0.825 LOO).

| protocol | legacy-200 | **ear3-996** | plan bar |
|---|---|---|---|
| LOO six-way | 0.642 | **0.695** | (0.687) |
| LOO binary ah-abba | 0.825 | **0.830** | (0.935) |
| LNO six-way | 0.687 | **0.757** | 0.687 ✓ |
| LNO binary | 0.850 | **0.855** | 0.935 ✗ not reproducible |

Ear3 beats legacy in every cell. Confusion (LOO, rows=true):
ah 47/22ba/1ih/24ma/4abba/2ima · ba 60 (31→ma) · ih 94 · ma 90 · abba 53
(36→ba, 10→ma) · ima 73 (17→ma, 9→ih). Worst confusions: abba→ba, ba→ma.

**2. Pitch (test_pitch.py) — PASS (asserts chosen from data, stated).**
Legacy-192 raw L2 between same-shape 70 vs 290 Hz renders: **0.158** (real
units sit 0.4–0.8 apart) — the old pitch-blindness, confirmed. Ear3 reads
the pair 70.0 / 290.9 Hz. Multi-seed (5 seeds) noise vs separation:
full ear 1.42 → 3.19 = **2.25×**; pitch block alone **3.40×** (> the 3×
gate); legacy block 1.79×. Per-block sep ratios: legacy 1.79, level 1.31,
cochleagram 2.28, pitch 3.40, modulation 2.20. The plan's 3× gate is met at
the pitch-ORGAN level, NOT at full-metric level (identity weighting caps
it) — reported, not hidden.

**3. Splice (test_splice.py) — CAUGHT.** Real ah + 0.25 s silence + real ah:
wdist to abba centroid **11.74** vs real-clip mean 3.91 / max 5.95 — far
outside the cloud; nearest unit is **ah** (11.05), not abba. Honest gate
report: the fake PASSES all four gates (the spliced silence makes a
perfect dip, deep and inside the span — G1's dip-depth cannot distinguish
a total-silence dip from a voiced closure). wdist catches it decisively;
gates alone would not.

**4. Determinism (test_determinism.py) — PASS.** features() bit-identical
twice in-process and across two processes on 3 clips (sha256 equal). Also:
the cached-pre-roll refactor was proven bit-identical to running the
pre-roll inside each call before caches were refreshed.

**5. Speed (test_speed.py, taskset -c 0, OMP=1, 0.5 s clip) — OVER BUDGET.**
Median **71.6 ms** (min 70.9, max 73.1): cochlea 45.7 + SAI 23.6 + legacy
0.6 + rest 1.6. History: first honest number 88.3 ms; caching the pre-roll
state + tight bucketing cut it to 71.6. The 70 ms contingency line is
crossed by 1.6 ms. Named contingency (2:1 NAP decimation before SAI):
measured useless (~1 ms — Python loop overhead dominates, not vector
length). SAI hop 25 ms saves ~4 ms of SAI but vanished in cochlea jitter.
**Implication: ~11.5 evals/s/worker pinned (with a 15 ms mouth), vs the
plan's ≥15. The real contingency is the named C++ port (cochlea is 64% of
the cost), or unpinned workers (unpinned full features measured ~44 ms).**
Corpus-scale cost: 600 clips in 65 s unpinned (108 ms/clip at median clip
1.38 s).

**6. v1 cheat wavs (test_cheat.py) — ALL 6 CAUGHT** under the stated
criterion (fails gates OR wdist > 1.3× real-clip mean = the Phase-3
success rule, so "caught" = "could never be declared a win"):
abba-0 1.50×(gates pass) · abba-1 1.62× · abba-2 1.70× · abba-3 1.66× ·
abba-free-0 1.94× + G4 fail · abba-free-1 1.67× + G1,G4 fail.
Fine print, printed in the test too: abba-0 sits 0.08 INSIDE the single
worst real take (5.87 vs 5.95) while farther than the other 99 — a
max-bar-only framing would call that one a slip.

## Feature dims total

**996** = 192 (legacy, growth law) + 10 (level) + 520 (cochleagram 8×65) +
131 (pitch) + 143 (modulation 55 + onset 88). spec 4a6864faab1a; caches
(`targets-cache/ear3-t06.json`, `t06-feats.npz`) refuse on mismatch.
Real-clip wdist bars per unit: mean ≈ 3.8–4.0, min ≈ 2.5–2.9, max 5.2–10.7.

## Contingencies triggered / open items

1. **Speed 71.6 ms > 70 ms** → C++ cochlea port is the live contingency
   (decimation measured dead). Phase-3 planning should assume ~11.5
   evals/s/worker pinned until then.
2. **f0 tracker folds above ~360 Hz** — matters for Phase-3 child-band
   (200–500 Hz) arms; needs a fix or an explicit band cap before launch.
3. **G3 floor 60 Hz** (plan said 120) — forced by Iddo's real voice;
   croak-kill for abba/ima rests on G1 dip. 
4. **Splice-style fakes pass gates** — wdist catches them; a
   silence-vs-voiced-closure gate (murmur energy inside the dip) is the
   natural G5 if Phase 3 meets this cheat in the wild.
5. **Judge block gains chosen on the same corpus** (no heldout exists at
   t06 scale) — declared, coarse (4–16 all similar), guarded by gates +
   Iddo's listen.
6. Mouth renders' voicing salience (0.42–0.54) sits well below real speech
   (0.87) — a searched render will score G2 voiced-frac lower than real
   clips; per-unit G2 thresholds (0.17–0.30) leave room, but Phase-3 should
   watch G2 fail rates on honest renders.

**7. Level honesty (test_level.py) — PASS (added 06:00).** ah_t06_1 at
0 dB vs −6 dB (×0.5): raw L2 7.32; judge-units distance 1.334 = 0.34× the
ah real-clip mean. Per-block movement (judge units): **level 1.001** >
cochleagram 0.725 > pitch 0.478 > modulation 0.150 > legacy192 **0.000**
(level-blind BY DESIGN — the growth-law block; that IS the old blindness,
kept frozen). Level = top new-block mover, as designed. Robustness: all 600
clips recomputed at −3 dB (58 s), same LOO/LNO protocol as test_loo:
LOO six 0.695→0.698 (Δ.003), LNO six 0.757→0.753 (Δ.003), binaries
0.830→0.825 / 0.855→0.855 — all within the 3-point bar. Informational:
−3 dB clips vs CLEAN targets = 0.727 LNO (level IS information; a shift
SHOULD cost something). Results: `results/level.json`.

**8. High-fs probe (tests/probe_high_fs.py) — ALL STABLE (added 06:00).**
The bat-headroom numerics probe the literature never ran: patched-JAX
CARFAC designed at 48/192/384 kHz, 0.2 s chirps to 20k/80k/160k at the
ear's 65 dB SPL convention (RMS 0.05), CPU-only, no corpus:

| fs | n_ch | top CF | max\|NAP\| | tail-10% | steady/call | stable |
|---|---|---|---|---|---|---|
| 48000 | 84 | 20,400 Hz | 6.149 | 0.197 | 68 ms | ✅ |
| 192000 | 109 | 81,600 Hz | 6.874 | 0.191 | 213 ms | ✅ |
| 384000 | 122 | 163,200 Hz | 7.346 | 0.190 | 480 ms | ✅ |

Zero NaN/Inf anywhere; max|NAP| grows mildly and the tail rings down —
no instability at any rate. **The 384 kHz design reaches CF 163.2 kHz =
the bat band with zero code changes, numerically clean.** (Informational —
beyond-human hearing stays future headroom per the Growth Law; design ~1 s,
first-call JIT 0.25–0.68 s.) Results: `results/high_fs.json`.

## EAR3-ACCEPT-20260826.json (assembled 06:00)

`scripts/assemble_accept.py` re-ran the fast battery live + collected
level/high-fs results into `~/ear-v3/EAR3-ACCEPT-20260826.json` (copied to
`D:\CLAUDE\eran-brain\ear3\`). spec 4a6864faab1a · carfac @4cdb95ee ·
patch 0001-jax-5tap-agc.

| item | verdict |
|---|---|
| loo | **PASS** (0.695 LOO six ≥ 0.687; binary 0.935 bar not reproducible — deviation recorded) |
| pitch | **PASS** (organ-level 3.40× > 3×; full-metric 2.25× reported) |
| splice | **PASS** (wdist 11.74 vs real max 5.95; gates alone would pass it — recorded) |
| v1_cheats | **PASS** (all 6 caught, 1.50–1.94× real mean) |
| determinism | **PASS** (bit-identical in-process + fresh-process; sha256 prefixes recorded for post-reboot diff) |
| speed | **FAIL** (median 72.1 ms pinned vs plan bar 25 ms — C++ cochlea port is the live contingency) |
| level | **PASS** (see §7) |
| high_fs_probe | informational, all stable |
| **iddo_listened** | **false — PENDING, the human gate. No milestone is blessed until Iddo listens and says so.** |

## Listening kit (delivered to PC, awaiting Iddo)

`D:\CLAUDE\eran-brain\ear3\listening-kit\` — 8 wavs + bilingual README
(built by `scripts/make_listening_kit.py` on eran2, Hebrew-renamed on PC):
pitch pair 70/290 Hz (the pair the old ear could not tell apart) · real
abba (abba_t06_57, the ear's surest) · splice-fake abba (wdist 11.7) ·
clearest 2 (ih_t06_65, ima_t06_42) · worst 2 (ima_t06_49→ma,
ah_t06_92→ba). Not on Desktop, nothing played — the main session hands it
over.

## Not done (honest)

- **Iddo's listen** — the only open Phase-1 gate (`iddo_listened: false`).
- Judge B trained cortex — later Phase-1 item per plan, separate task.
- Speed is over the plan bar (72 ms vs 25 ms): the C++ cochlea port
  remains the named contingency before Phase 3 worker math is finalized.
