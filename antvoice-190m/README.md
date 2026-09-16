> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

# AntVoice 190M

This is an isolated, non-deployed neural scaffold for the intended Hebrew Ant
Farm. It begins from random weights and consumes raw waveform samples. It has
no text, transcripts, pretrained models, browser speech services, ASR, TTS,
LoRA, or QLoRA in its learning path.

## Truth-gate status

Overall status: **PARTIAL — not Ant Farm acceptance**.

| Gate | Current state | Fresh evidence required for acceptance |
| --- | --- | --- |
| Real audio capture | **BLOCKED** | Real recorded Hebrew WAV files with verified format and hashes |
| Acoustic learner | **UNVERIFIED** | DGX execution showing waveform input produces learned unit IDs |
| Learning changes artifact | **UNVERIFIED** | DGX training on real audio with different before/after checkpoint hashes and changed tensors |
| Held-out evaluation | **BLOCKED** | Speaker- and session-disjoint real evaluation audio, measured before and after |
| Spoken conversation | **BLOCKED** | Real Hebrew audio through learned units, reasoning/memory, and generated waveform response |

The synthetic trainer is only a neural mechanics test. Even if it succeeds, its
own report says `REJECTED_FOR_ANT_FARM_ACCEPTANCE`.

## Architecture

The model path is:

`raw waveform -> strided convolutional encoder -> temporal conformer-like
stack -> learned boundary head -> vector quantizer -> causal unit world model
-> transposed-convolution waveform decoder`

Every trainable tensor is overwritten by
`initialize_from_explicit_seed(model, config.seed)`. Each tensor receives a
stable name-derived sub-seed. There is no checkpoint-loading or pretrained
initialization route in the model source.

Two configurations are provided:

- `configs/tiny.json`: under one million parameters, intended only for a
  bounded DGX mechanics test.
- `configs/antvoice_190m.json`: exactly **188,665,858 trainable parameters** by
  the static layer-accounting function. This is the production-scale candidate,
  not proof that it trains or meets the product gate.

## Real-audio manifest and provenance

The manifest is JSON Lines. Every row must contain only this schema:

```json
{"audio_path":"relative.wav","split":"train","speaker_id":"speaker-001","session_id":"session-001","corpus_id":"consented-hebrew-pilot","rights_id":"rights-001","consent_id":"consent-001","rights_status":"VERIFIED","language_audit_status":"VERIFIED_HEBREW","sha256":"64-lowercase-hex-digits","sample_rate":16000,"num_samples":16000}
```

`language_audit_status` is optional for general validation but is required to
equal `VERIFIED_HEBREW` by both supplied training configurations. All other
fields shown above are required. `rights_id` and `consent_id` must be nonempty,
and `rights_status` must equal `VERIFIED`; there is no training override for
unverified rights.

The validator checks every file against SHA256; opens each WAV; requires mono,
16-bit, uncompressed 16 kHz PCM; rejects duplicate content, unknown metadata,
and text-derived fields; and requires both speaker IDs and session IDs to be
disjoint between `train` and `eval`. The DGX dataset re-hashes every WAV again
when it is read.

The existing ambient `voice_history` corpus is blocked by corpus ID or path by
default. The canary and trainer do not expose an override. It must not be used
unless it receives a separate, explicit provenance review and a new approved
manifest.

On an approved DGX:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python -m antvoice.manifest \
  /data/antvoice/manifest.jsonl \
  --audio-root /data/antvoice/audio \
  --require-verified-hebrew
```

## DGX-only neural smoke

The neural modules intentionally raise before importing PyTorch on Windows.
Copy this isolated directory to an approved DGX, install it there, and run:

```bash
python -m antvoice.smoke_train \
  --config configs/tiny.json \
  --output artifacts/dgx-smoke \
  --device cuda \
  --seconds 0.5
```

A successful DGX mechanics run must show all six component gradient norms are
finite and nonzero, at least one changed trainable tensor, and different SHA256
hashes for `smoke-before.pt` and `smoke-after.pt`. An independent canonical
model-state digest must also change, so checkpoint metadata cannot fake this
proof. It writes `smoke-report.json`, which remains explicitly rejected for
acceptance because the input is synthetic tones rather than real Hebrew speech.

The existing synthetic smoke module and its artifact names are unchanged by
the real-audio pilot.

## Bounded real-audio canary

`antvoice.canary_train` is a separate tiny-model canary. It has hard limits of
five million model parameters, 64 optimizer steps per session, and 900
wall-clock seconds;
the supplied configuration uses eight steps and 300 seconds. It:

1. validates rights, consent, WAV hashes, Hebrew audit, and disjoint splits;
2. measures held-out real-audio losses before training;
3. trains only on manifest-selected real WAV waveforms;
4. requires finite nonzero gradients in all six neural components;
5. saves atomic before/after shadow checkpoints;
6. verifies changed tensors, changed canonical model-state hash, changed
   checkpoint hash, and held-out loss before/after.

Even when every canary check passes, its labels are exactly:

- `truth_gate_status=PARTIAL`
- `acceptance=PARTIAL_NOT_ANT_FARM_ACCEPTANCE`
- `canary_status=REAL_AUDIO_CANARY_VERIFIED`

The spoken-conversation gate remains `BLOCKED`. A canary without held-out
improvement writes a report with `REAL_AUDIO_CANARY_BLOCKED` and exits nonzero;
weight change alone is not silently upgraded to learning acceptance.

The launcher is dry-run by default:

```bash
bash scripts/run_real_canary.sh
```

Execution requires all of `EXECUTE=1`, a new `RUN_ROOT`, a valid manifest, and
an approved DGX. Nothing in this repository runs the canary automatically.

## Resumable longer trainer

`antvoice.train` is a genuinely resumable longer trainer for the 188,665,858
parameter candidate. Each bounded session stops at configured
`steps_per_session` or `max_wall_seconds`; cumulative `global_step` remains in
the checkpoint, so a separately enabled scheduler can start another session
with `--resume-latest` without changing the immutable run-configuration hash.

Every shadow checkpoint contains:

- model, AdamW optimizer, AMP scaler, Python RNG, Torch CPU RNG, all CUDA RNG
  states, exact sampler epoch/cursor, and training counters;
- immutable model/run configuration hashes and the validated manifest hash;
- `initialization_origin=random_explicit_seed`, root seed and root model-state
  hash, exact parent checkpoint hash, and chain depth.
- cumulative named-parameter gradient coverage grouped across encoder,
  temporal stack, boundary head, quantizer, world model, and decoder.

Resume fails closed if any configuration, manifest, artifact label, file hash,
random-init origin, seed, parent field, parent artifact/sidecar hash, or
required state is missing or mismatched. Non-root resume walks the complete
available parent chain back to the random-init root. `num_workers` is fixed at
zero so the saved sampler cursor cannot run ahead through worker prefetch.

Before training, the trainer requires every named parameter to have
`requires_grad=True` and requires the optimizer parameter set to equal the
complete model parameter set. After each backward pass it records which named
parameters have received at least one finite nonzero gradient. Reports claim
all-weight gradient coverage only when every named parameter in all six
components has been directly observed. They do not claim that every tensor
changed, because the longer trainer does not clone and compare all 190M-scale
tensors.

The trainer writes only:

```text
RUN_ROOT/
  shadow/
    checkpoints/
    reports/
    LATEST.json
    heartbeat.json
```

It never writes `RUN_ROOT/active`. Checkpoint payloads first go to a temporary
file, are flushed, then atomically renamed; a checkpoint filename is never
overwritten. Held-out reports compare the current fixed evaluation slice with
the random-initialized baseline and never trigger automatic promotion.

The full launcher is also dry-run by default:

```bash
bash scripts/run_full_train.sh
```

Actual execution requires `EXECUTE=1`, an explicit persistent `RUN_ROOT`, and
the real-audio canary gate to have been reviewed. This staging repository does
not enforce that human review automatically and does not launch training.

## Active promotion separation

`antvoice.promote` is a non-neural, separate command. It accepts only a
hash-matching shadow checkpoint tied to a `VERIFIED` held-out report whose
`promotion_eligible` field is true. It copies the bytes into
`active/releases/<sha256>.pt` without overwriting an existing release, then
atomically updates `active/CURRENT.json`.

Promotion is dry-run by default:

```bash
bash scripts/promote_shadow.sh
```

Promotion changes only model-artifact state. Its product label remains
`PARTIAL_NOT_ANT_FARM_ACCEPTANCE`.

## Operational guards and disabled service examples

Before training and periodically during it, fail-closed guards require:

- both minimum free GiB and minimum free-disk percentage;
- a successful `nvidia-smi` temperature query with every GPU at or below the
  configured maximum;
- an atomically refreshed heartbeat carrying
  `HEARTBEAT_NOT_ACCEPTANCE_EVIDENCE`.

The standalone heartbeat checker rejects missing, malformed, future-dated,
stale, or dead-process heartbeats. Files in `ops/systemd` are examples only:
they have no `[Install]` section, require explicit marker files, and the
trainer service defaults to `EXECUTE=0`. They were not installed, enabled, or
started.

## Local static checks

The local tests do not import PyTorch. They validate configuration arithmetic,
manifest isolation, rights/consent, the default ambient-corpus block, Python
syntax, required architecture classes, random-init/checkpoint lineage,
shadow/active separation, disabled launch behavior, and absence of pretrained
or adapter-loading routes. Static tests also verify that every neural file
checks for Windows before its first `import torch`:

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
```

## Deliberate limitations

- No real Hebrew corpus is included.
- Rights and Hebrew-audit fields are strict manifest declarations; this
  scaffold does not independently query a consent registry or listen to and
  classify the recordings.
- The real-audio canary and longer trainer are staged but have not been run in
  this Windows workspace.
- The longer trainer is single-DGX and single-process; no distributed sharding
  is claimed.
- The boundary target is an acoustic-novelty bootstrap objective. It is not yet
  validated as syllable-like on held-out Hebrew.
- The decoder is a learned waveform reconstruction head, not accepted speech
  generation.
- No reasoning or approved memory layer is connected.
- A passing artifact promotion is not Ant Farm product acceptance.
- No neural code has been executed in this Windows staging workspace.
