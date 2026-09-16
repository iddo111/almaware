# MOUTH v2 -- status (Phase 2 C twin 2026-08-26; Phases 0-1 below)

> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working).

PC-local Phases 0-1 + Phase 2 (C twin, eran2) of the ERAN 2.0 MOUTH v2
plan (`lazy-knitting-crown.md`, Phase 2). Every number below is from an
actual run on the named machine.

## Phase 2 (2026-08-26) — the fast C twin, deployed eran2 `~/mouth-v2/`

| file | what | state |
|---|---|---|
| `voc_eran.c` | C port of glottis.render + tract_core.render + DC block; pure deterministic double math, NO RNG (noise contract below) | **PARITY 0.0** |
| `fastcore.py` | ctypes wrapper; draws ALL noise in numpy (exact reference streams), computes every derived constant with the reference's own expressions, passes arrays+scalars to C | VERIFIED |
| `build.sh` / `build.ps1` | eran2 gcc 13.3 `-O2 -fPIC -ffp-contract=off -fno-fast-math` (FMA changes bits) / PC: **no usable compiler** (only FPC's i386 gcc 2.95) — PC build SKIPPED, documented in build.ps1 | built eran2 |
| `mouth2.py backend=` | `say/say_sequence/say_gesture(..., backend="ref"\|"c")`; identical param blocks + identical post-processing (decimate, peak-0.7) | VERIFIED |
| `validate/v_parity.py` | 14-render battery, all 3 APIs + extreme fences | **PASS** |
| `validate/v_bench.py` | 0.5 s /abba/ gesture, median of 50, pinned | **PASS eran2** |
| `joint_smoke.py` | mouth-C -> Ear v3 features+wdist, the first end-to-end number | run |

**Noise contract (why parity without PCG64-in-C):** numpy PCG64 is NOT
reimplemented. fastcore pre-draws every stream (seed+1000k, documented
order) and passes arrays: jitter/shimmer/drift as blocks of n//4+2
(n_p>=4 so never exhausted; VERIFIED block==scalar draws bit-identical),
vibrato's 2 uniforms, aspiration's uniform+block, turbulence block; the
flutter VECTOR is computed in numpy so it is bit-identical. C consumes
draws sequentially and does only deterministic float math.

**Parity (eran2, ref-vs-C, float32 out): max |diff| = 0.000e+00 on all
14 battery cases** — bit-identical, not merely <1e-6. (aarch64 libm ==
numpy transcendentals there; every other op is IEEE-exact by matching
the reference's operand grouping; `-ffp-contract=off` is what keeps it
true — an FMA would break it.)

**Bench (0.5 s /abba/ 5-keyframe gesture, full pipeline incl. param
prep + noise draws + resample + normalize):**
- eran2, `taskset -c 0`: **median 13.08 ms** (min 13.01, p90 13.21,
  max 13.44) → **gate ≤15 ms PASS**. Reference same box pinned: 471 ms
  → 36x. `say` C backend pinned: 5.9 ms.
- PC: no C compiler → no PC C bench (honest skip). PC reference: 902 ms.

**Speed scar fixed on the way (measured, the profile ordered it):** the
say_gesture track build made 500 PchipInterpolator constructions per
render — 109 ms of a 113 ms pinned render; the C core itself was 5.2 ms.
Fix: `geometry.spline_knots_to_areas_batch` + `constriction_batch`,
PROVEN bit-identical to the per-block loop (2000 random rows,
array_equal, on BOTH PC and eran2) and proven against the pre-change
reference: PC say/gesture sha256 unchanged (e948a969…, 1d285b9c…),
eran2 ref abba sha256 unchanged (1af89771…).

**Joint smoke (eran2, pinned core 0, OMP=1, steady-state after bucket
warm-up; first call on a NEW 1000-sample ear bucket pays ~1 s JAX JIT):**

| render | dur s | mouth C ms | ear ms | total ms | nearest (wdist) |
|---|---|---|---|---|---|
| ah | 0.55 | 14.0 | 76.6 | 90.6 | ma 8.69 · ih 9.10 · **ah 9.16 (3rd)** |
| ba | 0.48 | 12.1 | 63.4 | 75.4 | ma 8.07 · ah 8.64 · … ba 5th (9.25) |
| ma | 0.56 | 14.2 | 76.4 | 90.6 | **ma 9.24 ✓** · ih 9.53 |
| abba | 0.67 | 16.6 | 94.6 | 111.2 | ba 11.49 · ah 11.75 · **abba 3rd (11.77)** |

Embarrassment check, honest: only /ma/ lands nearest-correct; all four
sit at wdist 8-12 vs real-clip means ~3.8-4.0 — far OUTSIDE the real
cloud. These are hand-authored gestures, no search — information, not a
milestone. Loop cost: **~75-111 ms/eval pinned (~9-13 evals/s/core)**;
the ear dominates (63-95 ms), mouth is 12-17 ms.

## Phase 1 (2026-08-26) — the pure-numpy reference mouth

### What exists

| file | what | state |
|---|---|---|
| `glottis.py` | per-period analytic LF source (PT port) + jitter/shimmer/drift/vibrato + tilted aspiration | VERIFIED |
| `tract_core.py` | KL ladder + PT 3-way nasal junction + seal/pressure/burst + turbulence, 48 kHz -> 16 kHz | VERIFIED |
| `mouth2.py` | `say` / `say_sequence` (mouth34 contract) + `say_gesture` (13-dim space) | VERIFIED |
| `measure.py` | validation-only measurement (Welch peak-pick, NO LPC; HF-aware analytic twin) | used by gates |
| `validate/v_a_tube_law.py` | gate (a) | **PASS** |
| `validate/v_c_child_vowels.py` | gate (c) | **/i/,/u/,triangle PASS; /a/ FAIL (see findings)** |
| `validate/v_d_nasal_m.py` | gate (d) | **PASS** |
| `validate/v_e_stop_b.py` | gate (e) | **PASS** |
| `validate/v_determinism.py` | determinism | **PASS** |
| `validate/v_naturalness.py` | ah/ba/ma/abba renders | written (no quality claim) |

Determinism contract: every noise source owns `Generator(PCG64(seed+1000*k))`,
k = jitter 1, shimmer 2, drift 3, vibrato 4, aspiration 5, turbulence 6;
draw order documented in `glottis.py` for the future C twin.

### Gate numbers (as run)

- **Calibration (measured, never assumed):** impulse probe -> first lip
  arrival N-1 samples, echo spacing exactly 2N -> SECTION_CM = 0.7292 cm
  @48 kHz. End correction measured: HF one-pole in the end reflections
  adds a/(1-a) ≈ 1.25 sections of acoustic length (all resonances came
  out ~7% low before compensation) -> `n_sections_for` subtracts it.
  Child 11.98 cm -> **N=15 main + 11 nasal**, ladder 10.94 cm,
  effective 11.85 cm.
- **(a) tube law:** rendered 744/2242/3720 Hz vs same-termination
  analytic twin 738/2228/3748 -> err **0.74/0.63/0.75%** (gate 3%).
  Overtone ratios **3.015 / 5.003** (odd-multiple law; the old ladder's
  1:2:3 bug is dead). Effective length from rendered F1: 11.77 cm vs
  child 11.98 -> 1.8% (gate 5%).
- **(c) child vowels** (noise probe through the identical path, Welch):
  * /i/ 406/3523 vs target 430/3100 -> err 5.5%/13.6% **PASS**
  * /u/ 469/1622 vs target 480/1400 -> err 2.2%/15.9% **PASS**
  * /a/ 1324/2040 vs target 1000/1600 -> err 32.4%/27.5% **FAIL** --
    the render matches the analytic twin (1334/2074) within 1-2%, so
    this is the GEOMETRY vs the world, not a synthesis bug (below).
  * vowel triangle F1(a)>F1(u), F1(a)>F1(i), F2(i)>F2(a)>F2(u):
    strict **PASS**.
- **(d) nasal /m/** (lips sealed, velum 0.5 cm²): murmur 92.7% of power
  below 500 Hz (gate >50%); nostril-over-oral **41.4 dB** (gate ≥30);
  antiformant dip at **1238 Hz, 63.6 dB** deep (gate ≥10 dB in
  500-2500) vs same-termination twin **1236 Hz / 69.0 dB** -- 2 Hz
  agreement. (Phase-0 44-element ideal prediction was 1008 Hz / 39 dB;
  the shift is the N=15 junction quantization, both engines agree.)
- **(e) stop /b/ in /aba/:** closure **50 ms** at ≤ -40 dB re vowel RMS
  (gate ≥30); burst leads voicing by **10.0 ms** (gate 5-15).
  `validate/v_e_stop_aba.wav` + spectrogram saved.
- **determinism:** all three APIs bit-identical on same seed, differ on
  different seed; two fresh interpreters produce identical sha256.
- **naturalness:** `validate/naturalness/01_ah|02_ba|03_ma|04_abba.wav`
  + PNGs, f0 ~300->248 falling, seed 0. Spectrograms show real closure
  /burst /murmur structure. **No quality claim -- Iddo's ear decides.**

### Findings / scars from this build (all measured, none assumed)

1. **End correction:** the plan's "extra HF damping via one-pole in the
   end reflections" physically lengthens the tube (group delay a/(1-a)
   per bounce). First tube-law run: ALL resonances 7% low, ratios
   perfect. Fixed by measuring it into the anatomy; the analytic twin
   (`measure.twin_transfer`) models the same terminations.
2. **Burst chain — three real bugs found by diff-render** (render with
   BURST_GAIN=0 subtracted; the burst was literally |diff|=0 at first):
   (i) interior-only argmin missed a lip seal at the last section;
   (ii) an injection into the LAST section never reaches the output tap
   (R[N-1] is rebuilt from R[N-2] every sample);
   (iii) the release-block argmin had already jumped away, so the burst
   fired mid-tract -> the seal LOCATION is now remembered in state.
3. **Ant-farm burst number changed, documented:** their `pressure*=0.55`
   @16k (tau ~0.3 ms) assumes frames that snap open; our lips GLIDE, and
   at the seal threshold the lip junction transmits only ~12%, so the
   verbatim port radiated 8x weak. Venting now scales with gap openness
   (flow ~ pressure x conductance), full-open tau 3 ms (real bursts run
   5-25 ms). The only ant-farm number changed; reason recorded in
   `tract_core.py`.
4. **The S&B child /a/ is hot:** Story & Bunton Table-II modes on the
   60-month tract give /a/ F1 1323-1334 Hz through BOTH verified
   engines (published 4-yr column: 1368). Real 5-year-olds measure
   ~1000-1030 (Vorperian & Kent 2007); VTL said 758. The VTL target
   contradicted the measured-children literature (child/adult F1 ratio
   1.13 vs ~1.4) -> `child_targets.json` /a/ REVISED to literature
   1000/1600 (full evidence in its meta.revision_20260826). Even so the
   preset renders ~32% high -- a documented model-class disagreement
   (lossless hard-wall + adult-derived mode coefficients at child
   scale). The render is faithful to its geometry authority; the
   campaign searches gesture space anyway, so ERAN can find milder /a/
   shapes than the preset.
5. **A bilabial burst is LOW-frequency dominant** (radiates through a
   still-narrow lip opening into an F1-heavy tract) -- the first VOT
   detector looked for a >1 kHz click and honestly failed; it now
   detects the full-band spike-then-dip at closure offset.
6. `say_sequence` floor is the AREA FLOOR, not the 0.15 search fence --
   mouth34's own `closed_lips()` uses 0.02 cm²; clipping at 0.15 would
   silently delete every stop gesture ever searched.

### Still owed (Phase 2+ of the mouth plan)

- ~~**C twin** + bit-parity + bench~~ — **DONE 2026-08-26, Phase 2
  section above** (parity 0.0, bench 13.08 ms pinned eran2). Honest
  correction: the reference measures 0.2-0.3 s per say render (PC and
  eran2 unpinned), 471/902 ms for the 0.5 s abba gesture pinned — the
  "~10-20 s" line above was wrong, never re-measured until now.
- **Dresden gate (b):** computed transfer function vs
  `alma-larynx/dresden-vtd/*-vvtf-measured.txt` (F1/F2 within 15% on
  a/i/u, bandwidths within 2x), remembering Dresden is supine +
  hard-wall + closed-glottis.
- **Ear-v3 splice joint test** (gate (e) second half): the /aba/ pair
  must separate in Ear v3 space -- Ear v3 is now LIVE on eran2
  (~/ear-v3, EAR3-ACCEPT-20260826) and joint_smoke.py proves the
  plumbing; the splice-pair test itself is still owed.
- Iddo's (f) listen -- the naturalness set exists for exactly that.

---

## Phase 0 record (2026-08-26, earlier session)

| file | what | state |
|---|---|---|
| `geometry.py` | Story & Bunton 2018 child tract authority (real tables) | VERIFIED |
| `analytic2.py` | branched-tube ABCD transfer function + ladder compat | VERIFIED |
| `oracle_vtl.py` | VTL child oracle (GPL boundary, PC-only venv) | VERIFIED |
| `validate/child_targets.json` | /a i u/ F1-F3 targets + provenance (**/a/ revised in Phase 1**) | written |
| `dresden_check.py` | ground-truth vvtf reading proof (s1 tense /a:/) | VERIFIED |
| `.venv-vtl/` | vocaltractlab-cython 2.4.2 venv (Py 3.12.10) | installed |

Phase 0 numbers (as run then): geometry VTL cross-check 0.00% at every
integer age (length anchored to Table I); 60-month child 11.98 cm,
neutral areas 0.13-2.26 cm²; analytic2 uniform-tube odd law err 0.00%;
ladder-compat vs tract_analytic max err 0.25%; velum=0 reduction exact;
child /m/ antiformant 1008 Hz / 39 dB (44-element ideal); VTL adult
presets textbook (a 669/1193, i 208/2149, u 253/795); dresden_check s1
tense /a:/ 518/1115/2315 vs FEM 515/1105/2304 (≤0.87%).

Phase 0 findings that still stand: the old `tract_analytic` ladder's
overtone series is non-physical (equal spacing, only F1 right); Dresden
ground truth is supine + hard-wall + closed-glottis (its /a:/ F1 ~518);
vocaltractlab-cython segfaults in atexit on Windows (cosmetic).
