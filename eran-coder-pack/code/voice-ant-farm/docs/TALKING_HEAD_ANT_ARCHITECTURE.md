# Talking-Head Ant Architecture

Status: **PLANNED / UNVERIFIED**. This is an additive physical-speech lane for
the Hebrew Voice Ant Farm. No talking head has been built or accepted yet.
The existing waveform acoustic-unit learner remains Stage 1 and is not proof
of speech, meaning, or conversation.

## What it takes to make an “AH”

An actuator does not directly vibrate the vocal folds at audio frequency. It
sets their tension and closure; controlled airflow should make the paired
membranes self-oscillate. The sound then becomes an “AH” only after an acoustic
tract shapes that buzzing source.

The minimum physical instrument therefore has three coupled blocks:

1. **Breath source:** a quiet variable-speed blower, intake silencer, compliant
   plenum, pressure and flow sensors, check valve, and mechanical relief valve.
2. **Phonation valve:** two symmetric thin silicone membranes or molded folds,
   a small repeatable pre-gap, and coupled left/right tension and adduction
   adjustment. Balloon rubber can support an early disposable experiment, but
   its aging, thickness, and hysteresis make it a poor repeatable final fold.
3. **Vocal tract:** a modular pharynx/oral tube with open jaw and lip aperture,
   plus an adjustable tongue/formant-shaping insert. The folds provide the
   periodic source; the tract resonances provide the vowel identity.

Do not use a high-pressure compressor or gas canister. This is a low-pressure,
low-voltage, guarded bench instrument and must never be connected to a person.

## One-ant physical stack

### Actuators

- blower PWM or closed-loop flow command;
- symmetric left/right fold tension, mechanically coupled where possible;
- fold adduction/pre-gap adjustment;
- jaw angle;
- tongue/formant-shaper position;
- optional lip aperture and tract-length adjustment.

Linear actuators may set slow geometry. A servo, voice coil, or stepper may be
chosen after measuring required travel, force, backlash, and response time.
Self-oscillation—not actuator buzz—is the primary phonation mechanism.

### Sensors

- subglottal/plenum pressure and airflow;
- differential pressure across the folds;
- internal reference microphone and external listener microphone;
- optical or magnetic fold-displacement sensing where practical;
- actuator position/current and blower current;
- temperature and humidity;
- enclosure camera for geometry and failure inspection.

The camera is an observation channel, not evidence of acoustic success. The
external microphone is the authoritative user-heard output.

### Hard safety layer

An MCU owns real-time limits independently of AI or LAN availability:

- normally-open emergency vent and mechanical pressure relief;
- fixed pressure, flow, current, temperature, and actuator-travel ceilings;
- mesh/debris guard around membranes and moving parts;
- watchdog that vents, closes the blower command, and de-energizes actuators;
- physical emergency stop and a safe boot state;
- bounded trials with cooldown and inspection intervals.

AI may request only commands inside the MCU safety envelope. A model, Queen,
network service, or operator UI cannot raise hard limits during an episode.

## Control and learning loop

```text
target recording / learned acoustic target
                 |
                 v
       DGX policy + optimizer
                 |
      bounded actuator trajectory
                 |
                 v
   safety MCU -> blower/folds/tract -> external sound
        ^                                  |
        |                                  v
 pressure/flow/position             microphones/camera
        |                                  |
        +---------- synchronized trace ----+
                           |
                           v
            features + waveform units + score
                           |
                  replay / next episode
```

The first objective is a stable sustained open vowel—not a word. Score a trial
using oscillation onset, pitch stability, amplitude stability, spectral tilt,
harmonic-to-noise measures, target-relative formants, repeatability, energy,
and all safety margins. Learn target ranges from approved reference recordings;
do not treat one universal formant number as “the” human AH.

Use bounded episodes rather than continuous uncontrolled training:

0. identify the safe plant with low-energy sweeps and leak tests;
1. find stable self-oscillation and map onset/offset hysteresis;
2. match a chosen sustained /a/ reference across separate trials;
3. learn controlled transitions between acoustic-unit candidates;
4. train a unit-to-actuator synthesizer and evaluate on held-out targets;
5. only later couple perception, grounded meaning, and spoken interaction.

The learner must retain raw synchronized traces and output waveform hashes.
ASR spelling “ah” is optional diagnostics and never the acceptance metric.

## Farm topology: Fireplace and Queen

```text
 Ant A box --\
 Ant B box ---+--> authenticated experience bus --> Tribal Fireplace
 Ant C box ---+                                   (append-only exchange)
 Ant D box --/                                             |
                                                            v
                                             Queen validation service
                                               /      |       \
                                      quarantine  registry   rollback
                                                     |
                                          signed canary release
                                                     |
                                 one ant -> one tribe -> all compatible ants
```

Each isolated box contains one physical head, safety MCU, microphones, camera,
and a thin LAN gateway. Training and inference run on approved DGX/cloud
compute; the Windows operator machine remains a thin client. All commands and
artifacts use authenticated identities, authorization policy, audit records,
and replay protection.

The **Tribal Fireplace** is the append-only place where ants exchange signed
experience bundles, evaluation challenges, failures, and candidate artifacts.
It preserves competing discoveries rather than averaging them immediately.

The **Queen** is a validator and release coordinator, not a single personality
or unquestioned controller. It verifies provenance, runs held-out and cross-ant
tests, rejects unsafe or incompatible results, promotes signed versions, and
retains a rollback path.

## What is shared and what stays individual

Share only after validation:

- a common waveform feature specification and reference anchor set;
- representation/model improvements proven on multiple ants;
- safe exploration priors and successful actuator trajectories normalized to
  physical units;
- evaluation suites, failure cases, and grounded sensor-event associations;
- global synthesis policy plus hardware-family adapters.

Keep per ant:

- hardware revision and immutable safety limits;
- calibration, transfer function, actuator zeroes, and local adapter;
- private recordings unless their release was explicitly approved;
- local replay buffer, held-out split, and rollback pointer.

Do **not** naïvely merge VQ codebooks or assume unit 17 means the same event in
two independently trained ants. Unit labels are arbitrary. Align them with a
shared approved anchor-audio set, learned cross-codebook maps, or teacher-to-
student distillation, and then prove transfer on held-out audio.

## Signed experience bundle

Every Fireplace submission should contain at least:

```text
schema_version, ant_id, episode_id, timestamp
hardware_revision, firmware_hash, calibration_hash, safety_profile_hash
environment: temperature, humidity, enclosure configuration
target_audio_hash and target feature specification
bounded actuator trajectory and synchronized sensor trace
output_audio_hash, acoustic-unit sequence, acoustic metrics
safety events, trial outcome, train/held-out membership
model/checkpoint parents, code version, provenance, signature
```

Large waveform/video objects can remain in content-addressed storage while the
bundle carries hashes and access policy. Never publish private audio merely
because it improved a score.

## Cumulative and synergistic learning

1. Each ant explores locally inside hard limits and submits full successes and
   informative failures.
2. The Fireplace deduplicates by content hash but keeps lineage and hardware
   context.
3. The Queen evaluates candidates on the submitter's held-out set, shared
   anchors, and compatible recipient ants.
4. Robust aggregation or distillation produces a challenger without erasing
   per-ant adapters.
5. A release must improve the declared acoustic objective with no safety or
   previously passed-task regression.
6. Deployment progresses as a canary: one ant, one compatible tribe, then the
   farm. Any failed gate automatically restores the prior signed version.
7. Diversity quotas preserve different tract shapes, exploration policies,
   and solution families so the farm does not collapse into one fragile voice.

This makes learning cumulative: every validated episode expands the common
evidence base. It makes learning synergistic: a discovery by one head can seed
other compatible heads while their independent tests expose overfitting.

## Initial build modules (no purchase or fabrication authorized here)

- quiet low-pressure blower, silencer, plenum, tubing, and relief hardware;
- two replaceable silicone fold cartridges and a measurable gap/tension frame;
- pressure, differential-pressure, flow, current, temperature, and humidity
  sensors;
- modular printed vocal tract with jaw/tongue/formant inserts;
- two microphones and synchronized audio interface;
- safety MCU, drivers, emergency stop, fused low-voltage supply;
- acoustically treated enclosure with removable inspection panels.

CAD should begin only after a dimensioned sketch establishes airflow path,
target pressure range, fold cartridge dimensions, actuator travel/force,
sensor ports, service access, and the acoustic-box internal dimensions.

## Acceptance ladder

1. **Safety acceptance:** leak test, relief/vent test, watchdog test, hard travel
   stops, and safe loss-of-LAN behavior pass without phonation.
2. **Phonation acceptance:** repeatable self-oscillation over separate cold
   starts with pressure, audio, and displacement evidence.
3. **AH acceptance:** a fresh hidden target is submitted; the exact head emits
   nonempty external-microphone audio with stable target-relative acoustic
   metrics across repeated trials. The waveform is listened to and inspected.
4. **Learning acceptance:** training changes a sealed artifact and improves a
   speaker/session-separated held-out objective without safety regression.
5. **Transfer acceptance:** a signed candidate from one ant improves a different
   compatible ant after calibration, versus its frozen baseline.
6. **Ant Farm acceptance:** real audio maps to learned acoustic units, grounded
   meaning, unit-to-physical-speech output, and a fresh spoken Hebrew loop.

Passing an earlier rung never implies a later one. In particular, a convincing
“AH” is physical phonation calibration, not evidence of Hebrew speech or an
accepted Ant Farm.

## Relevant physical-model precedents

- Ishizaka and Flanagan, two-mass vocal-fold model:
  <https://doi.org/10.1121/1.396326>
- Experimental/self-excited physical vocal-fold work:
  <https://doi.org/10.1299/jsmecs.2005.43.65>
- Talking-robot artificial vocal-tract precedent:
  <https://doi.org/10.1109/IROS.2003.1248923>

These are starting points for design review, not validation of this proposed
instrument.
