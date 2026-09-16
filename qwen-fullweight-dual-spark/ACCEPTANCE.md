> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

# Acceptance Gates

Nothing is accepted from a process list, model roster, health endpoint, or
launcher exit code alone.

## A. Preflight evidence

- Exact node identities are Eran1 and Eran2.
- Both nodes report the expected DGX Spark hardware and 128 GB unified memory.
- The selected direct-fabric interfaces are carrier-up at their verified rate.
- Bidirectional peer traffic is bound to those interfaces; counters increase
  during the test and packet loss is zero in a bounded jumbo-frame probe.
- DGX OS, NVIDIA driver, CUDA, NCCL, Python environment, package lock, and Git
  commit are recorded and compatible.
- No existing workload will be displaced. Free storage exceeds the declared
  model, optimizer, temporary checkpoint, and rollback reserve.
- Base model and dataset manifests have matching SHA-256 digests on both nodes.

## B. Q1 2B multimodal smoke acceptance

- Two-node job completes at least two optimizer steps using BF16.
- No OOM, NaN, Inf, NCCL error, fabric fallback, thermal throttle, or silent
  single-node execution occurs.
- Both ranks contribute samples and gradients under the same run ID.
- The immutable dataset is `image_text`; processor output contains image token
  placement, pixel values, and image-grid metadata.
- The processor supplies a nonempty assistant-token mask for every record;
  prompt, padding, and visual-placeholder IDs are masked from the labels.
- Checkpoint loading reports no missing, unexpected, mismatched, or errored
  tensors.
- Runtime full-weight assertion reports zero frozen parameters.
- `gradient-coverage-proof.py` reports zero missing and zero always-zero
  trainable tensors, zero non-finite gradients, and matching parameter
  inventories across ranks for the bounded run.
- A distributed-state checkpoint is saved and restored into a fresh process
  using the same parallelism.
- A consolidated export is attempted only after a separate peak-memory canary.
  Once safely produced, `checkpoint-tensor-hashes.py compare
  --require-all-changed` reports every parameter tensor changed.
- A held-out loss is computed before and after from the same immutable split.
  The values are evidence; a decrease is required for promotion beyond smoke.

## C. Q2 9B promotion

- All Q1 gates pass.
- Measured peak unified-memory use leaves at least 15% headroom on each node.
- Checkpoint save plus restore fits without swap storm or NVMe offload.
- Sustained fabric, tokens/s, power, and temperature are recorded for at least
  30 minutes without error.
- The manifest is `image_text`, and proof names include nonzero gradients and
  changed tensors for the vision tower.

## D. Q3 maximum-candidate promotion

- `Qwen/Qwen3-30B-A3B-Base` is the maximum text-only candidate.
- `Qwen/Qwen3.5-35B-A3B-Base` is permitted only with an `image_text` manifest.
- A one-step no-save memory probe passes before any longer run.
- A bounded expert-coverage run proves every router selected every expert.
  After safe consolidation, per-expert axis-0 hashes prove every stacked expert
  slice changed. Increase data diversity/window length; never waive gaps.
- Measured memory and checkpoint I/O pass with no NVMe offload.
- Full held-out evaluation, restore, and tensor-change proof pass.

## E. 24/7 gate

Long-running training remains **BLOCKED** until all earlier gates for the
selected model pass and the operator records:

- maximum runtime and checkpoint cadence;
- thermal and disk thresholds with graceful stop behavior;
- retention and rollback budget;
- explicit dataset/license/consent approval;
- a non-destructive workload coexistence decision.
