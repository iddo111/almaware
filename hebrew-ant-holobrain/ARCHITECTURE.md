# Voice-first Queen/Ant Holobrain architecture

## Non-negotiable truth contract

1. Every learned tensor begins from the ant's recorded random seed.
2. Fixed signal transforms may be used, but no pretrained learned encoder,
   tokenizer, codec, ASR, TTS, vision backbone, language model, or policy may
   enter a checkpoint.
3. A model is not "Hebrew speaking" because it emits a WAV. It must produce
   intelligible held-out Hebrew audio that independent listeners can identify.
4. A model is not "reasoning" because it has recurrent layers. It must improve
   on held-out causal, spatial, memory, and counterfactual tasks.
5. A service, GPU process, loss curve, or training label is not competence.

## Topology

```text
Community A                               Community B
approved sources A                       approved sources B
       |                                        |
     Queen A                                  Queen B
       |                                        |
   Ant A1  Ant A2                          Ant B1  Ant B2
 active/shadow each                       active/shadow each
       |                                        |
       +------ bridge CLOSED by default --------+
```

Each Queen is a separate neural model with a separate optimizer. It learns only
its community's temporal patterns, chooses local curricula, detects local data
gaps, and evaluates local candidates. It never averages or directly edits ant
weights.

There is no all-seeing global Queen because that would silently join the closed
communities. A future bridge may exchange reviewed, provenance-labelled event
summaries. It may never copy weights, optimizer state, private replay, raw
voices, or unreviewed sensory streams.

## Persistent identity and no reproduction

Every Queen and ant has an immutable identity record. Training creates a new
checkpoint version under that same identity; it does not create a child model.
The active version can be rolled back or restored to replacement hardware, but
the lineage continues.

For the current phase:

- the identity roster is fixed;
- `allow_spawn=false`;
- deletion is forbidden;
- automatic reproduction, crossover, cloning, and population replacement are
  forbidden;
- "evolution" means real gradient updates and evaluated checkpoint promotion
  inside one permanent identity.

## Developmental stages

### Stage 0 — hearing, turn-taking, and babble

Input is waveform only. The ant learns acoustic continuity, speaker/session
variation, rhythm, silence, turn boundaries, and numeric vocal controls. No
letters, transcripts, captions, ASR labels, images, or text rewards enter the
model.

Promotion gate:

- held-out real-audio discrimination beats fixed baselines;
- train/calibration/evaluation sessions are disjoint;
- generated audio is non-silent and not a copied training clip;
- delayed retention passes;
- independent listeners identify the target syllables above the preregistered
  threshold.

### Stage 1 — audiovisual grounding

Add synchronized operator-owned camera frames and Isaac Sim camera/contact/IMU
observations. The ant predicts cross-modal temporal events: voice turn, object
persistence, approach/retreat, contact, occlusion, and cause/effect.

Promotion gate:

- retrieval succeeds on unseen sessions and unseen simulator scenes;
- performance drops under deliberate audio/video misalignment;
- visual predictions beat static and shuffled baselines.

### Stage 2 — syllables, words, and letters

Only after stable audio units exist, attach Hebrew glyphs to already learned
spoken and visual referents. Letters do not define the original sound units.

Promotion gate:

- spoken-to-glyph and glyph-to-spoken transfer pass on held-out speakers,
  objects, and recording sessions;
- the model can reject a wrong letter/sound pairing;
- no transcript or pretrained tokenizer has leaked into prior stages.

### Stage 3 — language model and reasoning workspace

The recurrent global workspace learns longer episodes, compositional language,
episodic recall, causal prediction, planning, and internal evaluation.
Reasoning is trained and scored through observable answers/actions; private
hidden traces are not exported as explanations.

Promotion gate:

- held-out causal, spatial, temporal, memory, and counterfactual suites improve;
- ablations show the recurrent workspace materially contributes;
- answers remain grounded in perceptual episodes rather than memorized text.

### Stage 4 — motor cortex in Isaac Sim

Attach camera, contact, pose, and IMU observations to a bounded simulated body.
The ant first learns reaching and locomotion in Isaac Lab, with action,
collision, energy, and joint-limit constraints.

Promotion gate:

- deterministic simulation evaluation across unseen seeds and scenes;
- collision, joint-limit, and unsafe-action rates remain below thresholds;
- sim-to-real is separately authorized and never follows automatically.

## Continuous training without inference corruption

Each ant has:

- `active`: immutable weights used for inference;
- `shadow`: the candidate trained continuously;
- `replay`: provenance-scoped recent and long-term episodes;
- `eval`: locked tests not visible to the trainer;
- `rollback`: the previous accepted active checkpoint.

The Queen may schedule data and evaluations 24/7. An ant may update only its
shadow weights. Promotion is atomic and occurs only when:

1. data provenance passes;
2. locked evaluation improves by the required margin;
3. safety and regression suites pass;
4. a rollback checkpoint exists.

This architecture permits autonomous learning while preventing a bad batch from
destroying the live speaking ant.

## Data substitutions

Google Maps Platform terms prohibit using Street View/Maps content to train,
test, validate, or fine-tune AI models. Use:

- synthetic streets and rooms generated in Isaac Sim;
- operator-owned walk/dashcam/room recordings;
- datasets with explicit machine-learning rights.

YouTube URLs are discovery metadata only. Training audio must arrive as a local
operator-owned or explicitly licensed file with evidence. No scraper or
downloader is part of this project.

## Realistic speed

The architecture can start training immediately, but intelligible emergent
Hebrew is not a one-day guarantee. Fast safe progress comes from:

- short curriculum stages;
- many clean, diverse sessions of the operator's voice;
- four independent experiments instead of cloned weights;
- parallel Isaac environments;
- automatic evaluation and rollback;
- never wasting compute on unlicensed or contaminated data.
