# ALMA Optical Perceptron (Mark-II) — Design Spec
**2026-08-08 · ALMAWARE · לזכרה של עלמה ז"ל**
Approved direction: Iddo, 2026-08-08 ("go on optical perceptron - write the spec").

## 1. What this is

A 4-input, 1-output perceptron whose synaptic weights are stored **in photochromic
film** — the self-darkening material of transition sunglass lenses. Violet light
darkens a film patch and the darkening persists: a non-volatile, light-programmable
optical attenuator. The dot product happens in physics (light through film onto
detectors); the perceptron learning rule runs as measured doses of violet light.
Weights are literally visible: a strong synapse is dark glass.

Successor to the VERIFIED digipot neuron builds (which become the control
experiment); predecessor to Mark-III on Knowm SDC memristors.

## 2. Success criteria

- **S1**: A single synapse's transmission is repeatably programmable to ≥5
  distinguishable levels via dosed violet exposure.
- **S2**: The 4-input network learns AND from all 16 input patterns in ≤50
  physical training epochs, then relearns OR in ≤50 epochs.
- **S3**: A learned function still classifies ≥14/16 patterns correctly 30 minutes
  after training stops (quantifies photochromic relaxation = "forgetting").
- **S4**: Same task run on the digipot Mark-I rig for a published side-by-side.
- **S5**: The learning session is filmed; weight darkening is visible on camera.

## 3. Architecture

### 3.1 Optical synapse (4 inputs + 1 bias = 5 bipolar pairs, 10 patches total)

```
input LED ──► [E patch] ──► LDR_E   (excitatory rail)
   (green)└─► [I patch] ──► LDR_I   (inhibitory rail)
violet write LED aimed at E patch ─┐ dosed exposure = weight DOWN on that patch
violet write LED aimed at I patch ─┘ (darkening E lowers w; darkening I raises w)
```

- Weight of synapse i: `w_i ∝ T(E_i) − T(I_i)` (difference of transmissions).
- Photochromic film only darkens under violet/UV and relaxes slowly on its own —
  monotonic per patch. The E/I pair makes the *net* weight bidirectional without
  waiting for relaxation.
- Slow ambient relaxation (minutes–hours) brightens both patches equally →
  weights decay toward zero = homeostatic forgetting. Measured in S3, not fought.

### 3.2 Read path — two stages, built in this order

- **v1.0 (build first):** each of the 10 patches gets its own LDR, read
  sequentially by the MCU ADC; sum and threshold computed in firmware. Fully
  debuggable; proves the optics.
- **v1.1 (the flagship claim):** all LDR_E in series-parallel onto one summing
  rail, all LDR_I onto another; two op-amp transimpedance stages; comparator on
  the difference = **activation computed entirely in analog light and current**.
  MCU only reads the final bit during inference.

### 3.3 Write path

- 10× violet LEDs (405 nm, ~5 mW class), one per patch, driven via ULN2803
  darlington array (or logic-level MOSFETs), PWM-dosed.
- Exposure quantum `q` = dose producing ~2–4% transmission drop at calibration;
  determined per patch in calibration mode (§5, T1).

### 3.4 Input path

- 4× green LEDs (~525 nm: good LDR sensitivity, negligible photochromic
  activation — the read light must not write). Pulsed only during reads.
- Chopped reading: sample LDRs with input LEDs ON then OFF, use the difference —
  cancels ambient leak and LDR dark drift.

### 3.5 Mechanical

- Light-tight housing printed on the K2 Plus in **matte black PLA**: 5 isolated
  channels × (E,I) cells (4 inputs + bias); film patches slide into slots (replaceable, ~10×10 mm);
  press-fit LED and LDR pockets; lid.
- Crosstalk requirement: <2% signal bleed between any two cells (T3).
- Optional (Mark-II.5): CNC-polished acrylic light guides on the FoxAlien XE Pro.

### 3.6 Controller & firmware

- ESP32 dev board (ADC + PWM + WiFi for logging into RAMCHAT later).
- State machine: `CALIBRATE → IDLE → READ → TRAIN_STEP → REPORT`.
- Perceptron rule mapping, per training example (x, y):
  - ŷ = step(Σ w_i·x_i − θ);  err = y − ŷ
  - err < 0 (fired, shouldn't): for each active input i, expose **E_i** by q.
  - err > 0 (didn't fire, should): for each active input i, expose **I_i** by q.
  - err = 0: no light. θ implemented as a 5th fixed-input bias synapse pair.
- Serial console + heartbeat JSON log (`session.jsonl`) for every epoch:
  per-patch readings, prediction, error, doses fired.

## 4. Bill of materials (~$70 new; much already on hand)

| Item | Qty | Note |
|---|---|---|
| Photochromic film sheet A4 (or 2× photochromic lens blanks) | 1 | cut into ≥14 patches incl. spares |
| Green LEDs 525 nm | 5 | 4 inputs + 1 bias |
| Violet LEDs 405 nm | 12 | 10 write + spares |
| LDR GL5528 | 12 | 10 + spares |
| ULN2803A | 2 | write-LED drivers |
| ESP32 dev board | 1 | on hand |
| MCP3008 (if ADC channels short) | 1 | optional |
| Op-amp LM324 + comparator LM393 | 1+1 | v1.1 analog rails |
| Matte black PLA | ~150 g | housing, printed on K2 Plus |
| Resistors, proto board, wire | — | on hand |

## 5. Test plan

- **T1 Dose–response**: per patch, plot transmission vs cumulative violet dose;
  derive q; verify ≥5 levels (S1). Repeat after 24 h — aging note.
- **T2 Read repeatability**: 100 chopped reads of a static patch; σ < 1.5% of span.
- **T3 Crosstalk**: one channel lit, all others measured; <2% bleed.
- **T4 AND learning**: full 16-pattern epochs until 16/16, ≤50 epochs (S2).
- **T5 Relearn OR** from the AND-trained state, ≤50 epochs (S2).
- **T6 Retention**: 30-min pause post-training, re-test (S3); log decay curve.
- **T7 Control**: identical protocol on digipot Mark-I; publish table (S4).

## 6. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Film relaxes fast (weights fade in minutes) | Measure τ in T1; if τ < 10 min, switch film brand / use UV-darkening acrylic blanks; also periodic refresh doses |
| Patch-to-patch variability | Per-patch calibration table from T1; patches are replaceable by design |
| Ambient light leakage | Light-tight housing + chopped reads (T2/T3 verify) |
| LDR nonlinearity/memory | Calibrate through the LDR (dose→ADC directly); LDRs are per-patch so matching cancels |
| Violet LED aging changes dose | Recalibrate q at session start (30 s routine) |
| 405 nm eye safety | Housing closed during operation; LEDs interlocked to lid switch in firmware |

## 7. Milestones

1. **M1 — one living synapse** (film patch + write/read proves S1) — first bench day.
2. **M2 — 4+bias network learns AND/OR** (v1.0 MCU-sum) — S2.
3. **M3 — analog rails** (v1.1): activation computed wholly in light+current.
4. **M4 — the film & the comparison**: side-by-side vs digipot Mark-I (S4, S5);
   footage for the perceptron-movie project.
5. **M5 — Mark-III bridge**: same firmware drives Knowm SDC pulses when the kit
   arrives; this spec's `TRAIN_STEP` abstraction is the shared interface.

## 8. Non-goals (YAGNI)

No multi-layer networks, no imaging-grade optics, no waveguide photonics, no
speed/efficiency claims vs digital, no wireless app — the screen is the glass.

## 9. Open items (owner: Iddo)

- Order photochromic film sheet (or donate two old transition lenses).
- Confirm ESP32 on hand (else Arduino Mega fallback — 8 ADC channels needed
  minimum for v1.0).
