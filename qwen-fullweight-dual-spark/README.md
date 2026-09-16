> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

# Qwen Full-Parameter Training on Eran1 + Eran2

Status: **PLANNED / NOT DEPLOYED / NOT TRAINING**

This is an isolated scaffold for genuine full-parameter Qwen training across two
DGX Sparks. It does not download a model, configure a node, or start a job.
Launchers default to dry-run and require explicit, matching safety gates on both
nodes. Non-dry-run launch is currently hard-blocked: the multimodal
preprocessor, sparse-MoE proof hooks, and distributed checkpoint save/restore
have not passed their real two-DGX runtime canaries.

## What “full-parameter” means here

- No PEFT, LoRA, QLoRA, parameter freezing, or adapter-only optimizer groups.
- Every model parameter has `requires_grad=True`.
- Every trainable tensor must receive a finite, nonzero gradient during the
  entire bounded qualification run. Sparse MoE experts may need a longer and
  more diverse bounded run.
- A tensor-level before/after checkpoint comparison must show every model tensor
  changed. A changed checkpoint directory hash alone is not enough.

## Qualification ladder

| Gate | Checkpoint | Role | Promotion condition |
|---|---|---|---|
| Q0 | none | static scaffold | JSON, AST, shell syntax, policy tests pass |
| Q1 | `Qwen/Qwen3.5-2B-Base` | multimodal two-node smoke | 2–10 steps, no OOM/NaN, vision/language gradient proof |
| Q2 | `Qwen/Qwen3.5-9B-Base` | dense multimodal current target | Q1 passes, measured memory headroom, all parameter tensors change |
| Q3-T | `Qwen/Qwen3-30B-A3B-Base` | text-only maximum candidate | measured fit, all experts covered over proof window |
| Q3-V | `Qwen/Qwen3.5-35B-A3B-Base` | multimodal maximum candidate | image+text manifest, vision and language gradients proven |

The official 9B and 35B names refer to their language-model portions. Memory
planning uses the complete Hugging Face checkpoint sizes—approximately 10B and
36B respectively—so the vision tower is not silently omitted.

All listed Qwen3.5 base checkpoints are vision-language checkpoints. The 2B,
9B, and 35B entries therefore require compatible image+text data for
whole-checkpoint full-parameter training. Text-only loading of only their
language submodel is not accepted as training the full checkpoint. With
text-only data, the maximum candidate is Qwen3-30B-A3B-Base.

“Maximum candidate” is not “verified to fit.” Promotion requires fresh measured
peak memory, throughput, thermals, fabric counters, and a successful checkpoint
save/restore on Eran1 and Eran2.

## Optimizer and memory policy

The first qualification uses BF16, activation checkpointing, ZeRO-3 or FSDP,
and factored Adafactor with no first moment. No CPU/NVMe optimizer offload is
enabled. DGX Spark unified memory makes “CPU offload” share the same 128 GB
physical pool, while NVMe adds severe I/O and wear; neither is allowed until
measurement justifies a reviewed change.

`tools/memory_estimator.py` provides planning bounds, not a fit guarantee.
The Qwen3.5 catalog parameter counts are language-model lower bounds and do not
fully account for the vision tower.
Factored Adafactor state depends on tensor shapes, so the final decision must use
measured peak memory from the exact checkpoint and sequence length.

## Data contract

Training reads an immutable local dataset manifest conforming to
`schemas/dataset-manifest.schema.json`. Each shard is a local absolute POSIX
path with a SHA-256 digest. The launcher refuses network URLs and the training
entrypoint uses `local_files_only=True` for model and processor loading.

- `text` manifests contain JSONL records with a nonempty `text` field.
- `image_text` manifests contain JSONL records with nonempty `text` (the user
  prompt), `target` (the assistant answer), and `image` fields. Every image path
  must be local and listed with its own digest in the manifest assets. The
  official chat template must expose a nonempty assistant-token mask; prompt,
  padding, and visual-placeholder tokens are excluded from loss.

The examples contain placeholders and cannot pass the launch gate.

## Safe workflow

1. Stage a base checkpoint and immutable dataset separately on both DGXs.
2. Reconfirm the evidence recorded in `launch/fabric.env`: Eran1/Eran2 have
   two Linux paths over one physical QSFP cable. The physical ceiling is 200G,
   not 2×200G. The fresh concurrent TCP benchmark reached 197 Gbit/s aggregate
   with zero retransmissions; NCCL still requires its own acceptance test.
3. Run `python3 tools/memory_estimator.py --catalog-key smoke_2b`.
4. Run `python3 tools/static_validate.py` on a non-training host.
5. On both DGXs, run `bash launch/preflight.sh`; preserve its evidence.
6. Run each node launcher with `DRY_RUN=1` and compare the rendered commands.
7. Set the execution gates only for the approved Q1 smoke, then invoke
   `bash launch/two-node.sh` separately on each node.
8. Apply every gate in `ACCEPTANCE.md` before promotion.

No command in this repository kills workloads, rewrites network configuration,
installs drivers, downloads weights, or deletes checkpoints.

## Framework choices

- `configs/accelerate-deepspeed.yaml` +
  `configs/deepspeed-zero3-adafactor.json`: preferred first qualification.
- `configs/accelerate-fsdp.yaml`: alternative after a separate Q1 comparison.
- `training/fullweight_train.py`: DGX-only reference loop with local-only,
  partition-aware model loading, post-wrapper gradient hooks, official
  multimodal chat-template processing, and distributed-state checkpointing.

The training loop saves resumable ZeRO-3/FSDP distributed state. It deliberately
does not gather a full model onto one rank. A consolidated Safetensors export is
a separate acceptance operation after a measured memory canary; DeepSpeed
offline FP32 consolidation can require roughly twice the final checkpoint size
in host/unified memory.

For MoE checkpoints, a nonzero gradient on a stacked expert tensor proves too
little. The proof also requires every router to select every expert during the
window and the checkpoint comparator hashes each expert slice along axis 0.

## Runtime gates still blocked

- Post-wrapper parameter hooks, explicit MoE leaf behavior, and distributed
  save/restore still require a real two-DGX Q1 canary. Static checks cannot
  prove those runtime interactions.
- The reference loop does not yet compute held-out loss before and after
  training. Promotion beyond the smoke remains blocked until that evaluator is
  implemented and run against the immutable validation split.
- Consolidated export remains blocked until a measured memory canary proves it
  is safe; the qualification loop saves distributed resumable state only.

`configs/training-defaults.json` records these runtime capabilities as false,
the Python entrypoint checks them before creating an Accelerator, and the shell
launcher blocks every non-dry-run invocation. Removing those blocks requires a
separate reviewed canary harness and fresh evidence; an approval string alone
does not make a framework path verified.

The Python entrypoint intentionally contains Torch imports. Under the workspace
law it must never be imported or executed on the Windows PC. Local validation
parses its AST as text and never imports it.
