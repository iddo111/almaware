# Hebrew Ant Holobrain

This is the neural successor to the character n-gram Ant Farm. It starts every
learned parameter from a new random seed. It does not load Qwen, Whisper, a
speech codec, a vision encoder, a tokenizer, LoRA, or any other pretrained
weight.

## Society contract

- Each closed community has its own **Queen**, approved-data ledger, curriculum,
  evaluation suites, and community memory. There is no global omniscient Queen.
- Four **ants** are separate neural models. Each has its own seed, weights,
  optimizer, replay memory, checkpoints, voice controls, and motor policy.
- The Queen can offer an experience or curriculum. It cannot write an ant's
  weights or silently merge ant checkpoints.
- Each ant performs inference from an immutable active checkpoint while a
  separate shadow checkpoint trains. Promotion requires an evaluation gain,
  provenance approval, and a rollback checkpoint.
- Voice develops before vision grounding, symbols, language reasoning, and
  simulated motor control.
- Identities are permanent. A checkpoint may evolve, fail, roll back, or move
  to replacement hardware, but the ant ID is never deleted or replaced.
- Reproduction and model spawning are disabled.
- Community storage, data, replay, Queen, ants, and evaluations are isolated.
  Cross-community exchange begins disabled.

## Current implementation

`holobrain.model.TinyHolobrain` is a real random-initialized multimodal neural
network with:

- waveform encoder;
- visual encoder, gated off during the voice-only stage;
- symbol embeddings, gated off until symbol grounding;
- recurrent global workspace and later recurrent reasoning;
- numeric vocal-motor controls;
- latent world prediction;
- simulated motor-action head.

`holobrain.training.AutonomousAnt` keeps active inference and shadow training
weights separate. `holobrain.society.SocietyRuntime` creates two isolated
communities, each with its own Queen, and proves every identity and
initialization fingerprint is distinct.

This is a runnable architecture slice, not a trained Hebrew mind. No claim of
speech, reasoning, vision understanding, or motor competence is valid until the
stage-specific held-out tests pass.

## Run

```powershell
cd D:\CLAUDE\hebrew-ant-holobrain
python -m unittest discover -s tests -v
python scripts\bootstrap_society.py
```

Bootstrap writes random-initialized checkpoints under `state\bootstrap`. Those
files are identities, not trained models.

## Data boundary

- User-owned voice: allowed after recording-session provenance is attached.
- YouTube/podcasts: only operator-owned media or material with written/open
  training rights. This project does not download from YouTube.
- Heder/child recordings: blocked by default. Written institution/guardian
  consent and a privacy review are mandatory.
- Google Street View: prohibited as training data.
- Vision substitutes: operator-owned camera recordings, explicitly licensed
  datasets, and synthetic Isaac Sim output.

See `ARCHITECTURE.md` and `config/source-policy.json`.
