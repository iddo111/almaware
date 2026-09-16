> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

# Eran3 AntVoice Cutover Plan

## Current state

Status: **STAGED — NO CUTOVER HAS OCCURRED**.

- `/home/eran3/antvoice-190m` is present and its 33 static tests pass.
- Both training launchers remain dry-run by default.
- No corpus, checkpoint, service, timer, or active release was created.
- `nemotron-super` remains running with restart policy `unless-stopped`,
  restart count zero, HTTP health success, and model identity
  `nemotron-3-super`.

## Allocation

- Eran1 + Eran2: dual-node full-parameter Qwen qualification and training.
- Eran3: random-initialized AntVoice training after this cutover gate passes.
- Eran4: Colibri/GLM inference and coding harness.

## Required corpus gate

Do not stop Nemotron until a manifest passes every item below:

1. Every WAV is mono, 16-bit, uncompressed PCM at 16 kHz.
2. Every file hash matches its manifest SHA256.
3. Every speaker has recorded consent and verified training rights.
4. Every record is audited as Hebrew with
   `language_audit_status=VERIFIED_HEBREW`.
5. Train and evaluation sets have no shared speaker or session.
6. Exact duplicate audio is removed.
7. No transcript, text, phoneme, character, prompt, or response field exists.
8. The ambient `voice_history` archive remains excluded unless separately
   reviewed and rebuilt as a new approved corpus.

## Pre-cutover checks

Run read-only checks immediately before the maintenance window:

```bash
sudo docker inspect \
  --format '{{.State.Status}} {{.RestartCount}} {{.HostConfig.RestartPolicy.Name}}' \
  nemotron-super
curl -fsS --max-time 10 http://127.0.0.1:8000/health
curl -fsS --max-time 10 http://127.0.0.1:8000/v1/models
nvidia-smi
df -h /home/eran3
cd /home/eran3/antvoice-190m
PYTHONPATH=src python3 -m unittest discover -s tests -v
python3 -m antvoice.manifest /data/antvoice/manifest.jsonl \
  --audio-root /data/antvoice/audio \
  --require-verified-hebrew
```

Abort before any service change if the manifest, storage, temperature, code,
or current-service evidence is not exactly as expected.

## Reversible maintenance cutover

Only after the corpus gate and pre-cutover checks pass:

```bash
sudo docker stop --time 120 nemotron-super
```

Confirm that the container is stopped and the GPU has sufficient free memory.
Then run only the bounded tiny-model real-audio canary:

```bash
cd /home/eran3/antvoice-190m
EXECUTE=1 \
PROJECT_DIR=/home/eran3/antvoice-190m \
MANIFEST=/data/antvoice/manifest.jsonl \
AUDIO_ROOT=/data/antvoice/audio \
RUN_ROOT=/home/eran3/antvoice-runs/canary-001 \
bash scripts/run_real_canary.sh
```

The canary must produce all of the following fresh evidence:

- real manifest-selected WAV input;
- finite nonzero gradients in all six neural components;
- changed tensor count greater than zero;
- different before/after model-state and checkpoint hashes;
- improved held-out real-audio loss;
- learned unit IDs with nonzero codebook use;
- exact label `PARTIAL_NOT_ANT_FARM_ACCEPTANCE`.

## Rollback

If the canary exits nonzero, a guard fires, output is missing, or any evidence
is ambiguous, do not start the 190M trainer:

```bash
sudo docker start nemotron-super
curl -fsS --retry 60 --retry-delay 5 --max-time 10 \
  http://127.0.0.1:8000/health
curl -fsS --max-time 10 http://127.0.0.1:8000/v1/models
```

Rollback acceptance requires the container to be running with restart count
unchanged or explained, HTTP health success, and the returned model identity
to remain `nemotron-3-super`.

## Production-training gate

Start the 188,665,858-parameter trainer only after independently reviewing a
passing canary report:

```bash
cd /home/eran3/antvoice-190m
EXECUTE=1 \
PROJECT_DIR=/home/eran3/antvoice-190m \
MANIFEST=/data/antvoice/manifest.jsonl \
AUDIO_ROOT=/data/antvoice/audio \
RUN_ROOT=/home/eran3/antvoice-runs/production-001 \
RESUME_LATEST=1 \
bash scripts/run_full_train.sh
```

Each session is bounded and resumable. Checkpoints remain in the shadow tree,
carry the complete random-init ancestry, and cannot automatically replace an
active model. A watchdog failure, stale heartbeat, disk threshold, thermal
threshold, non-finite loss, or corrupt lineage blocks continuation.

## Product acceptance

Real full-weight training is not full Ant Farm acceptance. Acceptance still
requires learned syllable-like acoustic behavior on held-out Hebrew, grounded
meaning and approved memory, generated waveform speech, and a directly
observed Hebrew audio-in to Hebrew audio-out conversation.
