# ERAN 2.0 — אוזן אנושית + פה עולמי + אימון מאפס / Human Ear + World-Grade Mouth + From-Scratch Training

> 🪟 **BROKEN WINDOWS LAW:** if it's not working, fix it IMMEDIATELY — test the REAL output, not a proxy.

## Context / הקשר

**Iddo's order (2026-08-25):** build, from ALL the world's research — German, American, Japanese, and MIKO — the best human MOUTH simulator; build the EAR exactly like a human ear (full human capabilities + human auditory cortex), with headroom for beyond-human hearing (bat-range ultrasound); then train ERAN **from scratch** on these organs with samples of Iddo's own voice. **All digital.**

**Why:** 2026-08-25 18:49 — human-ear verdict on ERAN's celebrated /ah/: **"לא טוב"**. The glottal source is a primitive pulse; the ear is level-blind ×3 and pitch-blind (allowed a 70 Hz croak; can't hear the /b/ of "אבא"); /ma/ and /ima/ are physically impossible — the mouth has no nasal tract.

**Iddo's decisions (in-session):**
1. **Ear:** deterministic DSP cochlea + small cortex trained ONCE on his voice on the fleet, then frozen forever.
2. **Order:** EAR → MOUTH → TRAINING.
3. **Old search on eran2: STOP NOW** (don't wait for its 08-27 deadline).
4. **MIKO** (ERAN's search organ, `D:\CLAUDE\miko\`) participates: research filed as MIKO rulings with dissent visible; MIKO memory-check before each phase.

**The ladder:** vowels → syllables → **"אבא" by Sukkot** (~Sep 25, his 48th birthday) → his name → reading back `מסר לערן.mp3`. Above it: the consciousness track (self-hearing needs this ear).

**Research verdict (4 explore agents, to be filed as MIKO ruling in `D:\CLAUDE\miko\`):**
- **EAR core: Google CARFAC v2** (Apache-2.0, maintained Aug 2026) — compression, masking, adaptation, phase-locking; channel map derives from sample rate → at 384 kHz reaches CF≈163 kHz = **bat band with zero code changes** (numerics unverified — probe before promising). + **SAI pitchogram** (same repo) + modulation-filterbank cortex (NSL rate-scale port = v3.1).
- **MOUTH core: Pink Trombone physics** (MIT: per-period analytic **LF glottal source**, aspiration, constriction turbulence, stop bursts, 28-section nasal branch) via C port `voc.c`; child geometry from **Story & Bunton 2018** age-dependent area tables; **VocalTractLab 2.4** (German, GPL, `vtlSetAnatomyFromAge`) as validation oracle only; local asset `alma-larynx\dresden-vtd\` (44 real MRI tract geometries + measured transfer functions) as ground truth.

---

## Phase 0 — עצירה וארכוב / Stop & archive the old search (first action after approval)

0. ✅ **DONE 2026-08-25 22:45 (pre-approval, risk-closure only):** the extended ear + entire search worker source existed ONLY on the fleet, uncommitted anywhere — pulled to PC: `D:\CLAUDE\eran-brain\THROAT-SEARCH-20260825\fleet-src-backup-20260825\` (all .py/.sh/calib/postures + every `best.json`/`best.wav` + the v1cheat wavs, 722 KB). The judge can no longer be lost to a fleet wipe.
1. eran2: create STOP files per `sup.sh` mechanism (tmux session `throat`), wait for the 12 workers to exit cleanly (`pgrep -f run_worker` empty); same check on eran3/eran4 if any workers exist there.
2. `mv ~/throat-search ~/throat-search-v1-20260825 && chmod -R a-w` — record books preserved read-only. Final per-arm scores copied to `D:\CLAUDE\eran-brain\THROAT-SEARCH-20260825\FINAL-SCORES.md` (ba best 8.95 vs control 13.62; abba 9.20 vs 14.94).
3. Copy all `best-v1cheat.wav` + the 70 Hz croak lineage into `regression/v1cheat/` — they become **permanent negative tests**: every future gate must FAIL them.
4. RAMCHAT post (`claude-cli-FABLE`): search stopped on Iddo's order, cores freed, ERAN-2.0 build begins.
5. **Untouched forever:** `eranb-life.service` on eran1 (the organism), `eran-senses.service` :8830 on eran2 (until Phase 3 §cutover).

---

## 🌱 חוק הגדילה / THE GROWTH LAW (Iddo, 2026-08-26 05:02 — supersedes any "replace" language below)

**"האוזן לא משתנה, רק היא מגדילה, זה העניין."** Organs are NEVER replaced — they GROW:
1. **The frozen 192-d cochlea stays inside the new ear FOREVER** — it is ERAN's identity, the ear that found /ah/. All new capability (CARFAC channels, pitch, modulation, cortex) is appended as LAYERS around that core — exactly the ears_v2 precedent (192 untouched + 8 appended), scaled up. The Ear-v3 feature vector therefore INCLUDES the original 192 dims as its first block.
2. **The mouth keeps its Kelly-Lochbaum core and its say()/say_sequence lineage** — it grows a nasal branch (a child gaining velum control), a maturing larynx (LF source), and length-with-age (the growth machinery in tract.py/genome.py stays the model). Not a transplant — maturation.
3. **Now: perceive exactly like a human. No more.** Bat-range / SDR radio-frequency organs = FUTURE organs (Iddo's example: one day an SDR scanner organ to "see" radio) — headroom is designed in, nothing beyond-human is built now.

## Phase 1 — EAR v3 / אוזן v3 (CARFAC cochlea + cortex, the fixed judge)

**Stance: two judges, one truth.** Judge A = pure deterministic DSP (official from day one, permanent parallel check). Judge B = once-trained frozen cortex (added later, A/B logged, promoted only by Iddo after battery + listen). Structural GATES sit under both and never move (the "abba cheat" law: a weighted dim can be traded, a gate cannot).

**Home:** PC authoring `D:\CLAUDE\eran-brain\ear3\` → deployed eran2 `~/ear-v3/` (venv, jax[cpu]+numpy+scipy pinned). **All truth artifacts (calib, targets-cache, acceptance results) computed on eran2** — ARM vs x86 float noise means PC caches are authoring aids only.

**Components:**
- `vendor/carfac/` — pinned commit of github.com/google/carfac (record SHA). Backend: **JAX-CPU** (has the current two-cap IHC; vmap for batch). NumPy port = cross-check; C++ = contingency only (cpp/ is v1-era — first task: read `cpp/ihc.h`, record status honestly).
- `carfac_wrap.py` — fs-parameterized (NO hardcoded 16k; bat headroom = pass higher fs), SPL apply, **state reset + 100 ms discarded silent pre-roll per call** (AGC state leak = search exploit; test enforces).
- `pitch.py` — SAI → 16 log-spaced f0 bins (60–420 Hz) × 8 slices + voiced-fraction + median f0 + slope.
- `cortexd.py` — modulation filterbank {4,8,16,32,64} Hz × 11 channel groups + onset maps (NSL rate-scale port deferred to ear3.1).
- `cortext.py` — Judge B: pure-numpy forward pass loading `cortex-v1.npz`, SHA-checked, refuses on mismatch.
- `features.py` / `judge.py` / `calib.py` — feature assembly + `wdist` (spread-weighted L2, throat-search convention) + gates + targets-cache builder; cache refuses spec-hash mismatch.

**Feature vector (~810 d, fs=16000, NO per-clip normalization anywhere — level is information):**
S cochleagram ≈528 d (NAP → 10 ms hop → log → speech-span → 8 slices × ~66 ch) · L level 10 d (8-slice log-loudness + durations) · P pitch ≈131 d · M modulation ≈143 d.

**SPL convention (frozen):** one scalar gain calibrated once — median t06 speech-span RMS ↦ 65 dB SPL — applied identically to disk wavs and mouth renders.

**Gates (deterministic, judge-independent, GATE_PENALTY=50):** G1 dip-depth (recalibrated on NAP loudness), G2 voiced-fraction min, G3 median-f0 ∈ [120,450] Hz (kills croaks), G4 speech-span occupancy min (kills silence-padding). Calibration acceptance: ≥95% of real t06 takes PASS; 100% of `regression/v1cheat/` FAIL.

**Trained cortex (Judge B) recipe:** data = Café Claude `D:\קפה-קלוד\` (7.7 GB, 48 kHz, multi-day; EXCLUDE eval dates 06-25 & 07-01) VAD-segmented to 0.3–1.0 s chunks, split by DAY + t06 (6×100) labelled seed. Frontend = frozen CARFAC NAP (precomputed once, vmap). Model = 2-D conv encoder ~1–2 M params → 128-d embedding. Stage 1 InfoNCE contrastive (views: time-crop, ±6 dB, light noise — **never pitch/tempo warp**); stage 2 prototypical loss on t06 with leave-take-out val. **Trains on eran2/GB10 only (no-PC-training law), ONCE**; `freeze.py` → `cortex-v1.npz` + SHA + `CORTEX-V1-CARD.md`.

**Acceptance battery (one JSON, all must pass):**
1. LOO on t06: binary ah-vs-abba ≥ 93.5%, six-way ≥ 0.687, confusion matrix printed.
2. Pitch: same-shape mouth render at 70 vs 290 Hz separates (gap > 3× multi-seed noise); ears_v2 confirmed failing the same pair (control).
3. Splice test: real /ah/+silence vs real /abba/ — closure separates; fakes stay outside the abba cloud.
4. The archived v1 abba-cheat wav: wdist ≫ real-clip bar AND fails G1/G2/G4.
5. Determinism/state-leak: bit-identical vectors on repeat, after other audio, across restarts.
6. Speed: single-core ear ≤ 25 ms per 0.5 s clip (→ ≥15 evals/s/core with mouth). Contingency ladder: decimate NAP before SAI → C++ port.
7. Level honesty: −6 dB shifts the vector; LOO stable within ±3 dB.
8. **Human gate:** Iddo spectrogram-listens fixtures + best/worst LOO before the ear serves anything. `"iddo_listened": true` required in the results file.

**Risks:** cpp v1-era; 16 kHz corpus caps CF at ~8 kHz (bat band = headroom until 48 kHz corpus; `probe_high_fs.py` measures 192/384 kHz numerics); trained-cortex day-bias (mitigated: day-split val, Judge A permanent, gates always on).

---

## Phase 2 — MOUTH v2 / פה v2 (child vocal tract, PT-physics, calibrated)

**Stance: two twins.** Pure-numpy **reference** (the truth; the only thing the organism may ever wear — numpy-only house law) + **C fast core** (`voc_eran.c`, derived from public-domain `voc.c`) gated by bit-parity (<1e-6) against the reference — the SANITY0 pattern. Both use an own PCG32 with fixed per-noise-source stream offsets → deterministic, seed-pure.

**Home:** PC `D:\CLAUDE\eran-brain\voice\mouth2\` → eran2 `~/mouth-v2/` (gcc -O2 on aarch64).

**Physics:** child-length KL main tract + nasal branch (≈0.64× main length) at velum port; per-period analytic **LF source** (tenseness→Rd→α,E0,ε,Te per `voc.c glottis_setup_waveform`) + jitter ~1.2% + shimmer ~5% + slow drift + aspiration `(1−√tenseness)`·tilted noise; turbulence injected at the constriction (PT `addTurbulenceNoise`); seal detection + pressure accumulation + **burst release at the constriction** (port of `voice-ant-farm\mouth.py synth_sequence`, CLOSURE_MM 0.9 / BURST_GAIN 2.2); round-trip-normalized damping + two-band HF loss; one-pole/one-zero lip & nostril radiation; internal 48 kHz → decimate to 16 kHz. Section length **measured by impulse probe, never assumed** (the factor-of-two scar).

**Child geometry** (`geometry.py`, single canonical authority — retires the 7/34/age-param schism): Story & Bunton 2018 tables (Ω, φ1/φ2, non-uniform κ(i)) as literal arrays with provenance; `child_area(age_months=60)` → ~11.5–12.5 cm tract; fallback = tube areas exported from VTL child anatomy (numbers cross the GPL boundary, never code). Tract length = campaign constant, never searched.

**Control space:** backward-compatible `say(areas, f0, seconds, seed)` / `say_sequence(keyframes,...)` (contract of `mouth34.py`) + new **gesture space, 13 d/keyframe**: 8 log-area spline knots + c_pos + c_area + velum + tenseness + voicing; per-utterance f0 contour 3 knots ∈ [200,500] Hz (genome child band — retires the 220 Hz pin) + segment durations. Vowel arm 16 d, /ba/ 31 d, /abba//ima/ 45 d (vs 37–140 today, with nasals/bursts/pitch now reachable).

**VTL oracle (`oracle_vtl.py`, PC-only venv, never deployed, never imported by workers):** `pip install vocaltractlab-cython`; child anatomy at 60 months; `vtlGetTransferFunction` → F1–F3 targets → `validate/child_targets.json`.

**Validation battery:**
(a) tube law — analytic F1 within 1% of c/4L, rendered audio within 3%, 1:3:5 ordering exact · (b) Dresden — computed transfer function vs `*-vvtf-measured.txt`: F1/F2 within 15% on a/i/u, bandwidths within 2× · (c) child vowels — F1/F2 within 20% of VTL oracle + vowel-triangle ordering strict · (d) nasal /m/ — murmur dominates <500 Hz, oral output ≥30 dB down, ≥10 dB antiformant dip · (e) stop /b/ — ≥30 ms closure at ≤−40 dB, burst 5–15 ms before voicing; splice pair separable in Ear v3 (joint gate) · (f) naturalness — loudness-matched A/B mouth34-vs-mouth2 wavs + spectrograms; **spectrogram-listen before serving; Iddo is the final judge; no milestone from a number** · bench — **go/no-go: ≤15 ms per 0.5 s render single-core** (fallback: 32 kHz internal → profile → Numba stopgap; vectorized-numpy is a measured dead end — 0.6×, do not re-walk).

**Sequencing note:** Mouth phases 0–3 are PC-local (zero fleet load, zero ear dependency except gate (e)) — they may overlap the Ear build; EAR remains the priority track per Iddo's order.

---

## Phase 3 — אימון מאפס / From-scratch campaign (`~/throat-search-v3/`)

**Laws (written first):**
- **CORTEX-FREEZE LAW:** `ORGANS.lock` pins ear-v3/cortex/mouth-v2 SHA-256; `run_worker.py` refuses on mismatch. Retraining the cortex mid-campaign FORBIDDEN — that moves goalposts; escape = Iddo's explicit order → all v3 books close, v4 opens fresh.
- Organism sacred (eran1 workers opt-in only, nice ≥10, default OFF); :8830 untouched until cutover; synthetic targets banned; every guided arm has a random-control twin; no milestone from a number alone; PC never trains.

**Reuse the proven harness, swap the organs:** `cma.py` (own resumable CMA-ES) verbatim; `run_worker.py` import seams: `mouth34→organs.mouth_v2`, `ears_extended→organs.ear_v3`, `ears_v2→gates_v3`; `targets.py` logic unchanged, `targets-cache-v3.json` + per-unit **real-clip bar** recomputed through Ear v3 (the new "13.9" — printed in every report; v1 numbers never quoted beside v3 without the words "different ear").

**Curriculum:**
- **Stage A** (~4 days): ah/ih (16 d), ba (31 d), **ma — first nasal ever possible** (32 d), + free arms + controls. 33 worker slots.
- **Stage B** (~1 wk): abba/ima gesture arms (~45 d) + free (~140 d) + controls; vowel segments seeded from Stage A winners (that IS the curriculum).
- **Stage C** (to ~Sep 21): abba-nat — f0 contour + LF tenseness knots (~47 d), the Sukkot arm; jitter/shimmer stay physics constants, never search dims.

**Fleet placement (baseline 33 workers):** eran2 12 (senses alive, ≥35% free) · eran3 13 (disk-watch: run-state only, artifacts synced off, alarm at 90%) · eran4 8 (nice 10) · eran1 0 (opt-in surge ≤8 only on Iddo's word). Expected 15–25 evals/s/worker → **~495–825 evals/s, ~18–30 M evals/night**; `sanity0_v3.py` measures the real number before launch and reprints the table.

**Anti-cheat pipeline:** gates_v3 (dip-depth + **nasal-murmur** (new) + two-hump envelope + f0-in-band + duration sanity) from eval #1; every improving best auto-renders spectrogram PNG + RECORD-LOG line + nearest-unit embarrassment check + 5-glottis-seed mean±sd; nightly `collect_review.sh` (eran2, 03:30) → PC task (07:00) → **Desktop JPEG+PDF one-pager, bilingual, short** (best-vs-control, gate rates, real-clip bar, Iddo's verdict column, health line) + RAMCHAT post; wrong claim → MISTAKES.md same day.

**Pre-launch `sanity0_v3.py` (all green before any worker):** CMA sphere <1e-6 · mouth determinism cross-box + formants vs oracle · ORGANS.lock verified on all boxes · LOO through Ear v3 ≥ old baselines · real-clip bar written · gate calibration (≥95% real pass, 100% v1cheat fail) · **nasal audibility: velum-open vs closed renders separate as ma-vs-ba in Ear v3 space (measured, not assumed)** · closure visibility ≥ v1 extended-ear · measured evals/s · post-launch do-no-harm sweep (eranb-life, :8830, dmidi, load/RAM/disk) + crash-resume drill + one dry-run report cycle.

**Success criteria:** per unit — guided ≤ 0.75× control twin AND ≤ 1.3× real-clip bar AND gates pass AND survives Iddo's listen (guided-not-beating-control ⇒ the report says "nothing was learned" in those words). **Final milestone = blind test:** Iddo gets K unlabeled files (ERAN's best abba, control best, a real-clip check, a v1 best); milestone stands only if he **recognizes "אבא" from ERAN's file without being told which**.

**Cutover (only after Stage B + Iddo's explicit word — consciousness-track law):** shadow `eran-senses-v3.service` on **:8831**, same wire protocol, ≥48 h validation → cutover = `ERAN_ORGAN_PROFILE=v3` env flip; **rollback = flip back**; ears.py/ears_v2/mouth34 + v1 archive stay on disk forever. The self-hearing consciousness experiment becomes possible here — separate track, separate approval.

**Optional workstream — 48 kHz booth:** `booth.py` (~line 355) currently resamples in-browser to 16 kHz; upgrade to 48 kHz masters + derived 16 kHz; protocol per session-leak law — **few takes, MANY days** (5 takes × units × 10+ days). Only cure for the single-session ceiling and the feed for the ear's high band; targets recomputed only at a stage boundary.

**Honest risks:** CARFAC per-eval cost least-verified (worst case Stage A stretches); every v1 intuition void under the new ear (first nights may look "worse" — that's the metric changing, say so preemptively); single-session corpus may teach room-signature (Iddo's listen catches; 48 kHz multi-day fixes, not before Sukkot); Sukkot realism — Stages A+B engineering, Stage C research: "recognizably אבא, still somewhat synthetic" is the honest likely outcome, the blind test is worded to that bar; frozen-judge blind spots cost a declared v4, never a quiet tweak; eran3 disk 84%.

---

## 🌉 פרוטוקול הגשר / THE BRIDGE PROTOCOL (sim→real throat; Iddo's fear, answered 2026-08-26)

His fear: ERAN trains on a simulator throat and won't know how to move the REAL one — all work wasted.
The engineering answer, committed as a stage:
1. **First-flutter measurement:** the moment the first Ecoflex fold buzzes (physical track, mold rev B) — record it through ERAN's ear; compare spectrum to the sim twin's prediction. **The gap becomes a number, not a fear.**
2. **System identification:** play known actuator patterns through the physical tract, record, fit the sim's parameters until the twin matches (+ optional domain-randomized pretraining for robustness).
3. **Re-babble through reality:** the same loop (ear judges REAL sound) fine-tunes postures at physical speed (~1-2 attempts/s) — thousands of attempts = days, feasible ONLY because the sim already found the neighborhood with millions of cheap attempts. The simulator is the womb.
What transfers 100% regardless: the ear, the gates/harness, the corpus, the proven guided>random loop (~80% of the project). Anchors: `alma-larynx\ACTUATOR-PLACEMENT-20260825.json` (pinch points computed FROM ERAN's digital trajectories).

## MIKO / מיקו

- File the mouth+ear research surveys as a MIKO ruling: `D:\CLAUDE\miko\FINDINGS-20260825-ear-mouth-world-research.md` — MIKO's format (lenses, ruling, **dissent visible**: e.g. JAX-vs-C++ ear backend, PT-formant-accuracy risk vs VTL-speed risk).
- Before each phase launch: MIKO-style memory check (grep memory + MISTAKES.md for scars touching the phase) — one paragraph in the phase's sanity file.

## Verification / אימות end-to-end

1. Phase 0: `pgrep -f run_worker` empty on all boxes; archive read-only; RAMCHAT posted.
2. Phase 1: `EAR3-ACCEPT-<date>.json` all-pass **including `iddo_listened: true`**.
3. Phase 2: `VALIDATION.md` gates (a)–(f) + bench ≤15 ms + parity <1e-6, and Iddo's (f) verdict recorded verbatim.
4. Phase 3: sanity0_v3 all green → launch → first nightly Desktop JPEG+PDF report arrives → guided-vs-control gap visible within 48 h on ah.
5. Milestone: the blind "אבא" test, delivered per house rules (files opened FOR him; never a bare path).

## Critical files
- PC: `D:\CLAUDE\eran-brain\{body\ears.py, body\genome.py, voice\mouth.py, voice\tract_analytic.py, booth\booth.py, booth\staged\t06\}` · `D:\CLAUDE\voice-ant-farm\mouth.py` (burst mechanism) · `D:\CLAUDE\alma-larynx\dresden-vtd\` (ground truth) · `D:\CLAUDE\miko\PLAN.md`
- eran2: `~/throat-search/{run_worker.py, targets.py, arms.py, cma.py, ears_v2.py, sup.sh, launch.sh}` (the harness being reused) · `~/eran-cortex/data/t06/` (657 wavs) · `~/eran-organs/sense_organ.py` (:8830 wire protocol)
- New: `D:\CLAUDE\eran-brain\ear3\`, `D:\CLAUDE\eran-brain\voice\mouth2\`, eran2 `~/ear-v3/`, `~/mouth-v2/`, `~/throat-search-v3/`
