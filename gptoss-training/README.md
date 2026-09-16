# gptoss-training — preparation package for gpt-oss-120b training on the eran fleet

**Status: PREPARATION ONLY. The gate verdict is NO-GO for the 3-node
full-weight job — read [GO_NO_GO.md](GO_NO_GO.md) before anything else.**
No model has been loaded, no GPU/unified memory allocated, no training step
run, on any node, at any point. The launcher defaults to dry-run and refuses
to arm while any precondition fails.

## What this is

The complete, honest output of qualifying eran1+eran2+eran3 (GB10 DGX Spark,
1 GPU each, unified 121 GiB pool per node — the pool IS the GPU memory) for
full-weight fine-tuning of gpt-oss-120b (116,829,156,672 params, count
independently re-derived from the shard headers; ships natively MXFP4 —
there is no BF16 release). eran4 is excluded: no RDMA hardware.

## Files

| File | Purpose |
|---|---|
| [GO_NO_GO.md](GO_NO_GO.md) | The gate. Measured bandwidths, memory arithmetic, per-step I/O floor, every unmet precondition, and the blunt verdict: **3-node full-weight = NOT VIABLE; QLoRA on eran2 (~75-85 GB) is the workable path.** |
| [ds_config_zero3_nvme.json](ds_config_zero3_nvme.json) | DeepSpeed ZeRO-3 config: NVMe offload for params AND optimizer, client-side Adafactor (no `optimizer` block — Adam's ~934 GB state is ruled out), bf16. `__NVME_PATH__` is templated per node by the launcher. |
| [ds_config_zero3_nvme.NOTES.md](ds_config_zero3_nvme.NOTES.md) | Field-by-field justification — every buffer size traced to a measured or derived number (largest tensor 2,123,366,400 elements, 4.2-4.6 GB/s NVMe, 121 GiB pool, 4.53 GB/s 3-node collective). |
| [launch.sh](launch.sh) | 3-node torchrun launcher. **Defaults to EXECUTE=0 (dry-run).** Prints the full plan + memory budget, runs read-only gates over ssh, refuses to launch if GLM/inference is running, RAM < 100 GiB available, NVMe < 400 GiB free, model/DeepSpeed/routes/script/dataset missing, or `I_HAVE_READ_GO_NO_GO` != YES. Pins the only proven-working 3-node NCCL env (TCP sockets) and documents the proven 2-node RoCE env. |

## What was measured (one paragraph)

2-node all-reduce over dual-rail RoCE: 22.63 GB/s (92% of the 24.5 GB/s
platform ceiling; per-port caps at ~110 Gb/s on GB10). 3-node RDMA ring:
topologically impossible — the fabric is a LINE (eran1↔eran2↔eran3, no
eran1↔eran3 wire; transit RDMA dies with IBV_WC_RETRY_EXC_ERR). Only working
3-node collective: NCCL over TCP at 4.53 GB/s. DeepSpeed 0.19.3 installed on
all three nodes; async_io JIT-built and load-proven on all three (NVMe offload
is real, not just "compatible"). NVMe: 4.2-4.6 GB/s sequential write, 840G/
1.5T/1.6T free. Memory: 114-115 GiB available per node at snapshot, shrinking
under concurrent GLM-5.2 bring-up on eran1/eran3. Arithmetic: bf16
weights+grads = 467.3 GB vs 369 GB aggregate available → NVMe offload
mandatory → 53-106 s/step disk + 30-60+ s/step network → **~2-4 min per
optimizer step floor**. Hence the NO-GO.

## What is still missing (blocking, in gate order)

1. A dataset + `dataset_manifest.json` (nothing exists; seq length UNKNOWN)
2. The training script `~/gptoss-training/train_full_zero3.py` on each node
3. Node availability — the live 2026-08-06 dry-run found Colibri (`coli
   serve`) running on ALL THREE nodes (available RAM: eran1 24.6 GiB,
   eran2 39.8 GiB, eran3 4.0 GiB vs the 100 GiB gate); even the QLoRA
   path needs ~85 GB vacated on one node first
4. Route persistence (the two cross-rail routes are runtime-only, lost on reboot)
5. Verification that client Adafactor works through DeepSpeed's NVMe optimizer swap
6. A bf16 → MXFP4 re-quantization pipeline for the trained artifact
7. (Hardware, optional but decisive) a direct eran1↔eran3 cable — both ends
   have 2 dark 200G ports; this is what would make 3-node RDMA collectives exist

## Commands

Dry-run (safe, default — prints plan, runs read-only gates, launches nothing):

```bash
bash launch.sh
```

The exact command to run **when — and only when — every gate passes** (today
it will refuse: no dataset, no training script, GLM occupying eran1/eran3):

```bash
EXECUTE=1 I_HAVE_READ_GO_NO_GO=YES \
DATASET_MANIFEST=/path/to/dataset_manifest.json \
bash launch.sh
```

Even fully armed, it re-checks every gate and refuses on any FAIL.

## The recommendation, restated

Do not fight the arithmetic. Run **QLoRA on eran2 alone** (~65.2 GB frozen
MXFP4 base + ~0.4 GB adapters/optimizer + grad-checkpointed activations ≈
75-85 GB, fits in the 121 GiB pool, no fabric involvement, no GLM contention).
The 2-node RoCE pair (22.63 GB/s, env pinned in launch.sh comments) is
qualified if data parallelism is later wanted. What QLoRA gives up — the
98.14% of params in frozen 4-bit experts — is stated plainly in GO_NO_GO.md.
