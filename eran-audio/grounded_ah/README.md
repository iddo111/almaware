# Grounded "ah" Training Pipeline

**Goal:** Train Eran to produce a clean `/a/` vowel sound when shown Iddo's face.

Picture (Iddo's face) → embedding (512-d) → MLP → waveform logits → vocoder → `.wav` file

## Pipeline Overview

1. **Vision**: Load Iddo's face embedding from `D:\CLAUDE\eran-faces\enroll\iddo\` (insightface model)
   - Falls back to a mock embedding if no enrollment exists yet
   
2. **Model**: Small MLP that maps picture embedding → `/a/` waveform
   - Input: 512-d face embedding
   - Hidden: 128-d ReLU layer
   - Output: 9600 samples (0.6s @ 16kHz) waveform logits

3. **Target**: Synthetic `/a/` formant or real recording from `target_ah/` folder
   - Formants: F1≈730Hz, F2≈1090Hz, F3≈2440Hz (reused from obedience training)

4. **Neuromodulation** (Part 1b): Minimal correctness judge + neuromodulator state
   - Correctness judge: analyze formants F1/F2/F0 and envelope
   - Dopamine reward: based on acoustic correctness
   - Oxytocin bonus: fires when Iddo's multisensory context is present
   - Three-factor Hebbian rule: Δw ∝ eligibility × neuromod factor

5. **Output**: Generated `.wav` files saved each training step so you can **listen to training progress**

## How to Run

### Quick Test (default 10 steps)
```bash
cd D:\CLAUDE\eran-audio\grounded_ah
python grounded_ah.py
```

### Custom Step Count
```bash
python grounded_ah.py 50
```

### With Specific Device
```bash
python grounded_ah.py 100 --device cuda
```

## Output Files

- **`output/step_NNN.wav`**: Generated `/a/` waveform at each training step (listen to hear learning)
- **`output/final_ah.wav`**: Final trained output
- **`checkpoints/latest.pt`**: Model checkpoint with architecture and weights
- **`training_log.json`**: Loss history and metrics (MSE, BPB bits-per-byte)

## Enrollment: Add Iddo's Face

To use a real face embedding instead of a mock:

1. **Add a photo of Iddo**:
   ```
   D:\CLAUDE\eran-faces\enroll\iddo\
   ```
   Copy a clear, front-facing JPG or PNG of Iddo's face into this folder.

2. **Enroll Iddo's face**:
   ```bash
   cd D:\CLAUDE\eran-faces
   python family.py --enroll iddo
   ```

3. **Verify enrollment**:
   ```bash
   python family.py --status
   ```
   You should see: `iddo ENROLLED (1 face(s))`

4. **Re-run training**:
   ```bash
   cd D:\CLAUDE\eran-audio\grounded_ah
   python grounded_ah.py 20
   ```
   The script will now load Iddo's real 512-d embedding from `embeddings/iddo.npz`.

## Provide Real Target Sound

To train on Iddo's actual voice instead of synthetic formants:

1. **Create target folder**:
   ```
   mkdir D:\CLAUDE\eran-audio\grounded_ah\target_ah\
   ```

2. **Record Iddo saying "ah"**:
   - Clear, sustained /a/ sound (0.5-0.8 seconds)
   - Mono, 16kHz WAV preferred (will auto-resample if needed)
   - Save as: `target_ah/iddo_ah.wav`

3. **Re-run training**:
   ```bash
   python grounded_ah.py 30
   ```
   The script will load your recording instead of the synthetic target.

## Neuromodulation Details

See `neuromod.py` for the correctness judge and neuromodulator state:

- **Correctness Judge**: Analyzes output formants (F1, F2, F0) and envelope RMS
  - Dopamine reward fires if: F1 ∈ [700, 1100], F2 ∈ [1100, 1700], F0 ∈ [80, 150]
  - Confidence weighted by spectral power in formant bands
  
- **Neuromodulator Channels**:
  - dopamine (DA): reward for correct /a/
  - oxytocin (OXT): bonding when Iddo's multisensory context present
  - acetylcholine (ACh): attention/salience
  - norepinephrine (NE): arousal
  - serotonin (5HT): mood/homeostasis
  - cortisol: stress (inhibits learning)
  - endorphin: pain/pleasure

- **Three-Factor Rule**:
  ```
  Δw = lr · eligibility_trace(pre, post) · M(DA, OXT, ACh, NE, 5HT, cortisol)
  ```
  where M is the combined neuromod factor.

- **Live State**: Neuromodulator state written to:
  ```
  D:\CLAUDE\eran-nursery\state\gentle_state.json
  ```
  (readable while training runs)

## Multisensory Binding

See `senses.py` for the sensory context layer:

- **Vision**: Face embedding from insightface
- **Hearing**: Voice embedding (speaker-ID placeholder)
- **Smell**: Deterministic olfactory signature per person
- **Touch**: Reciprocal haptics (placeholder for hardware)

When all 4 senses co-occur for Iddo → oxytocin bonus fires (strong bonding moment).

Later phases will extend this to:
- Multimodal learning (picture + voice + touch → coordinated response)
- Real speaker-ID integration
- Real haptic feedback from hardware

## Metrics

The training loop reports:

- **loss**: MSE between predicted and target waveform
- **mse**: Mean squared error (absolute)
- **rmse**: Root mean squared error
- **bpb**: Bits per byte (conceptually: entropy of the quantized prediction)

## Troubleshooting

### "No Iddo enrollment found"
- Ensure a photo is in: `D:\CLAUDE\eran-faces\enroll\iddo\`
- Run: `python family.py --enroll iddo`
- Check: `python family.py --status`

### Generated wav sounds like noise
- Normal in early steps! Training starts from random weights.
- After ~50 steps with real data, you should hear formant structure forming.
- Listen to `output/step_NNN.wav` in sequence to watch learning happen.

### Model not converging
- Increase steps: `python grounded_ah.py 200`
- Check that target is loaded: look for `[grounded_ah] loaded target /a/ from ...` in output
- If using mock embedding, try enrolling real face for better variation

### OutOfMemory on GPU
```bash
python grounded_ah.py 50 --device cpu
```
CPU is slower but will work for this small model.

## Files in This Directory

- **grounded_ah.py**: Main training script (picture → /a/)
- **neuromod.py**: Correctness judge + neuromodulator state (Part 1b)
- **senses.py**: Multisensory binding layer (vision, hearing, smell, touch)
- **checkpoints/**: Model checkpoints (`.pt` files)
- **output/**: Generated `.wav` files per step + final output
- **training_log.json**: JSON log of all training runs (losses, metrics, timestamps)

## Next Steps (Phase 2)

- Real speaker-ID integration (not just placeholder)
- Full neuromodulator three-factor learning (implement weight updates with eligibility traces)
- Extend to multiple commands (not just /a/, but /ba/, /pa/, etc.)
- Embodied learning: link picture → voice → motor command (not just sound generation)
- Add real haptic feedback from touch hardware

---

**Status**: Part 1a + 1b pipeline built. Ready to enroll face + provide real sound + train.
