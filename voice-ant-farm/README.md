# Hebrew Voice Ant Farm

This is the new voice-first line. It does not import the retired character
n-gram workers and does not use text, letters, ASR transcripts, or browser TTS
as learning tokens.

## Four independent ants

Each ant owns a separate random seed, acoustic codebook, and checkpoint files.
No weights or codebooks are shared. DGX placement, episodic memory, automated
rollback, and physical heads remain future deployment work.

The current implementation is deliberately narrow:

1. validate mono PCM WAV recordings;
2. derive frame-level acoustic features from waveforms;
3. learn a vector-quantized acoustic codebook from training recordings;
4. emit timestamped integer unit IDs;
5. compare quantization error on session-separated held-out audio;
6. promote a checkpoint only when held-out error improves over its incumbent;
7. preserve a real training-waveform exemplar for each learned unit;
8. train four independent ants and let the Queen select by held-out error
   without merging their codebooks;
9. reconstruct audio from unit sequences and learned exemplars.

These units are **acoustic-unit candidates**. They may be called
“syllable-like” only after boundary and repeatability evaluation with real
recordings. Exemplar reconstruction is an acoustic proof, not generative
speech. Grounded meaning, a causal world model, and complete spoken
conversation are not yet implemented.

## Planned physical speech lane

The proposed low-pressure talking-head ant, its “AH” calibration ladder, and
the cumulative Fireplace/Queen multi-ant topology are specified in
[`docs/TALKING_HEAD_ANT_ARCHITECTURE.md`](docs/TALKING_HEAD_ANT_ARCHITECTURE.md).
That document is a planned architecture, not current product acceptance. The
current four ants remain independent and share no weights or codebooks.

## Acceptance

Run:

```powershell
pwsh -NoProfile -File .\load_stage1.ps1
python -m unittest discover -s tests -v
python corpus.py index --root recordings --speaker iddo1 --train-session 2026-06-18 --heldout-session 2026-06-25 --evaluation-session 2026-07-01 --output recordings/manifest.json
python colony.py train --recordings recordings --manifest recordings/manifest.json --state state
python acoustic_units.py evaluate --checkpoint state/ant-a/current.json --heldout recordings/evaluation
python acoustic_units.py encode --checkpoint state/ant-a/current.json --wav sample.wav
python acoustic_units.py synthesize --checkpoint state/ant-a/current.json --wav sample.wav --output outputs/reconstruction.wav
python acceptance.py --project . --output state/acceptance-current.json
```

Training reads exactly the `.wav` files sealed in the manifest and refuses
empty datasets, incompatible PCM, unindexed files, overlapping raw or canonical
decoded-PCM hashes, and speaker/session leakage between train, held-out, and
evaluation splits. The local manifest contains provenance and hashes but no
transcripts or text-derived learning tokens.

Checkpoints and the Queen manifest are sealed with SHA-256 digests and written
atomically. Independent evaluation rejects any recording whose audio hash
appeared in training or checkpoint-selection held-out data. Unit IDs are
namespaced by checkpoint hash because independently learned codebook labels are
not semantically aligned. Evaluation is recorded but never used for checkpoint
promotion or Queen selection. Synthetic tones in tests prove only software
mechanics; they are never Ant Farm acceptance.
The acceptance report deliberately remains `PARTIAL` and keeps the conversation
layer `BLOCKED` until the grounded meaning/reasoning/memory/spoken-response loop
exists and passes a fresh microphone-to-speaker test.

## Boundary and repeatability evidence

`boundary_repeatability.py` computes candidate-only metrics after a human
provides a sealed annotation JSON file. It does not train or change the corpus,
checkpoints, state, or acceptance report:

```powershell
python boundary_repeatability.py evaluate --checkpoint state/ant-a/current.json --manifest recordings/manifest.json --recordings recordings --annotations annotations/boundary-repeatability.json --output outputs/boundary-repeatability.json
```

The annotation document is sealed by `annotations_sha256` and bound to the
exact corpus-manifest and checkpoint hashes. Its `entries` must cover every
held-out and evaluation WAV. Each entry repeats the manifest `path`, `split`,
`speaker_id`, `session_id`, `audio_sha256`, and `pcm_sha256`, adds exactly one
of `boundaries_samples` or `boundaries_seconds`, and uses only an opaque
`repetition_group_id` of the form `rg-` plus 32 lowercase hex digits. At least
two groups are required, and every group must span both held-out and evaluation
sessions. Text, transcripts, letters, words, labels, and incomplete coverage
are rejected. Boundary precision/recall/F1 uses a fixed 20 ms tolerance;
repeatability uses checkpoint-namespaced collapsed-unit Levenshtein similarity.
The result remains acoustic-unit candidate evidence, never syllable or
conversation acceptance. No real-corpus result exists until the annotations
are independently supplied and sealed.
For boundary scoring, a prediction is the start time of the first 10 ms feature
hop whose unit ID differs from the preceding frame. The reported
precision/recall/F1 is pooled across every annotated recording, with one-to-one
time-ordered matches at the fixed 20 ms tolerance. Repeatability collapses
consecutive duplicate unit IDs before deterministic alignment and reports both
within-group and between-group cross-session pairs.

## Recording gate

Populate `recordings/train`, `recordings/heldout`, and
`recordings/evaluation` with real mono 16-bit PCM WAV recordings. Use different
recording sessions and speakers where possible. Never copy or resample the same
utterance across splits: byte-level hash rejection cannot detect an acoustically
identical re-encoding. Do not commit private recordings without explicit
authorization.
