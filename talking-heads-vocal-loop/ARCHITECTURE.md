# Architecture

## One head

```text
target /a/ recordings
        |
        v
feature extractor: pitch, F1, F2, spectral envelope, SPL, stability
        |
        v
bounded learner/controller ---> actuator command envelope
        |                              |
        |                              v
        |                   pump -> regulator -> artificial glottis
        |                                      -> vocal tract -> sound
        |                                                       |
        +<--- score + telemetry <--- microphone + pressure + airflow
```

### Physical voice path

- Quiet low-pressure air pump and small reservoir.
- Mechanical regulator, pressure sensor, airflow sensor, relief valve.
- Replaceable artificial-larynx cartridge with two opposed silicone membranes.
- Glottal-gap actuator and independent membrane-tension actuator.
- Initially fixed 3D-printed `/a/` vocal tract; later add jaw, tongue and lip
  degrees of freedom.
- Reference microphone inside the chamber and a calibration microphone outside.

The first prototype should not use balloons as the final vocal folds. Balloon
rubber is useful for quick acoustic exploration but varies with temperature,
fatigue and manufacturing. A clamped, replaceable silicone membrane cartridge
gives measurable geometry and repeatable tension.

### Learning loop

Start with system identification, not unconstrained reinforcement learning:

1. Calibrate safe actuator and pressure ranges.
2. Sweep one parameter at a time and record audio plus telemetry.
3. Fit a surrogate mapping from controls to acoustic features.
4. Use bounded Bayesian optimization or CMA-ES to approach the `/a/` target.
5. Re-test the best candidate against held-out recordings and fresh starts.
6. Save the controller only if it improves quality without violating limits.

Every trial receives a unique ID and stores anatomy version, actuator commands,
sensor traces, raw WAV, extracted features, score, decision and artifact hashes.

## Farm topology

```text
Head 01 chamber -- local learner --\
Head 02 chamber -- local learner ----> Tribal Fireplace ---> Queen validator
Head 03 chamber -- local learner --/          |                    |
       ...                                    v                    v
Head NN chamber -- local learner       shared replay/evals   signed recipe
                                                                  |
                                  <----- staged distribution <-----+
```

### Tribal Fireplace

A shared, append-only knowledge layer containing:

- Successful and failed trial summaries.
- Normalized acoustic targets and evaluation recordings.
- Anatomy-aware controller recipes.
- Counterexamples and failure signatures.
- No automatic actuator commands.

### Queen validator

The Queen does not average all weights blindly. It:

1. Receives candidate recipes from individual heads.
2. Replays them in simulation and on a designated reference head.
3. Rejects candidates that exceed pressure, travel, temperature or SPL limits.
4. Requires reproducible improvement across multiple trials.
5. Signs a versioned recipe for opt-in rollout to compatible heads.

Heads retain local identity and anatomy-specific calibration. Shared knowledge is
transferred as observations, priors, evaluation cases and compatible controller
deltas—not as an unverified global overwrite.

## Network services

- `head-agent`: owns one chamber, sensors, actuators and trial log.
- `fireplace`: append-only dataset and artifact registry.
- `queen`: evaluation scheduler, compatibility checks and signed promotion.
- `observer`: read-only dashboard with live waveform, spectrogram and telemetry.

All physical actions remain behind a local safety controller. LAN commands may
request a trial but cannot bypass pressure, actuator, duration or sound limits.
