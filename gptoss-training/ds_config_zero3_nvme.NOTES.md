# ds_config_zero3_nvme.json — justification for every value

JSON cannot carry comments, so this companion note maps each field to the
measurement that sized it. All measurements are from the 2026-08-05
qualification reports (DeepSpeed install, NCCL/RoCE fabric, memory/NVMe
reality) on eran1/eran2/eran3. Values marked **[derived]** are arithmetic on
measured numbers; **[choice]** are engineering choices whose *constraint* is a
measured number; **UNKNOWN** means not measured — no estimate substituted.

## Model facts the sizing rests on (all measured/derived in qualification)

| Fact | Value | Source |
|---|---|---|
| Parameter count | 116,829,156,672 | independently derived from all 687 tensor headers across 15 shards; matches claimed count exactly |
| BF16 upcast weights | 233.66 GB (116.83B x 2 B) | derived; 98.14% of params are MXFP4 expert weights that must be upcast |
| BF16 grads | 233.66 GB | derived |
| Working set (weights+grads) | 467.3 GB; 155.8 GB/node sharded 3 ways | derived; exceeds both the 369 GB measured aggregate and the 121 GiB (130 GB) per-node pool — **this is why both offload sections say `nvme`** |
| Largest single tensor | `gate_up_proj_blocks`: 128 experts x 5760 x 2880 = 2,123,366,400 elements/layer | shard-header scan |
| Per-layer expert params | 114,661,785,600 / 36 = 3,185,049,600 params = 6.37 GB bf16/layer | derived |
| Measured NVMe sequential write | eran1 4.4 GB/s, eran2 4.6 GB/s, eran3 4.2 GB/s (8 GiB, oflag=direct; best-case /dev/zero) | measured |
| Measured free NVMe | eran1 840G, eran2 1.5T, eran3 1.6T | measured 2026-08-05 |
| Measured 3-node all-reduce (only working config: TCP) | 4.53 GB/s algbw @ 2 GB messages | measured |
| Measured available RAM/node | 114-115 GiB (snapshot; shrinking under GLM bring-up) | measured |

## Field-by-field

### Top level
- `train_micro_batch_size_per_gpu: 1` — **[choice]** minimum possible. Activation
  memory is UNKNOWN (no dataset exists, so no sequence length was measured);
  with the pool already oversubscribed, anything >1 is unjustifiable.
- `gradient_accumulation_steps: 16` — **[choice]** the measured per-step floor is
  ~2-4 min of NVMe+network overhead per *optimizer* step (53-106 s disk +
  30-60+ s network); accumulation amortizes that fixed cost over more tokens.
  16 is a starting point, not a measurement.
- `gradient_clipping: 1.0` — convention, not a measurement.
- `wall_clock_breakdown: true` — we predicted minutes/step from measured I/O;
  this makes DeepSpeed print the actual per-step decomposition as evidence.
- `bf16` — the upcast target. fp16 disabled: MXFP4 scales are E8M0-style
  block scales; bf16 shares the fp32 exponent range.
- `zero_allow_untested_optimizer: true` — the optimizer is a **client-side
  Adafactor** (transformers 5.12.1, measured installed), passed in code. There
  is deliberately NO `optimizer` block: DeepSpeed-native Adam m,v would be
  ~934 GB fp32 (derived) — the whole point of Adafactor is its ~0.5 GB factored
  state (derived: ~68M factored + ~55M full-v fp32 elements).
  **CAVEAT (unmet precondition, see GO_NO_GO.md):** DeepSpeed's NVMe optimizer
  swap path is engineered around its own optimizer family; only `async_io` and
  `cpu_adam` were proven built on this fleet. Adafactor-through-NVMe-swap is
  UNVERIFIED.

### zero_optimization
- `stage: 3` — required: parameters themselves must be partitioned/offloaded;
  stages 1-2 leave full bf16 weights (233.7 GB) resident per node vs 121 GiB.
- `reduce_bucket_size: 500000000` (elements = 1.0 GB bf16 messages) —
  **[choice constrained by measurement]** the fabric's all-reduce bandwidth
  rises with message size (2-node RoCE: 2.35 GB/s @1 MB -> 17.58 @64 MB ->
  22.63 @2 GB; the 3-node TCP figure 4.53 GB/s was measured at 2 GB). 1 GB
  buckets sit near the large-message regime while bounding resident comm
  buffers to ~2 x 1 GB.
- `sub_group_size: 1000000000` (elements) — optimizer-state processing/swap
  granularity: 1e9 fp32 master elements = 4 GB per subgroup = ~0.9 s per swap
  direction at the measured 4.4 GB/s. Larger subgroups would pin more of the
  121 GiB unified pool per swap.
- `stage3_max_live_parameters: 1000000000` (= 2 GB bf16 live window) —
  **[choice]** bounds unpartitioned params resident at once. 2 GB ~= one
  layer's expert third (6.37 GB/layer / 3) — the pool cannot afford more
  alongside pinned buffers and activations.
- `stage3_max_reuse_distance: 0` — do NOT retain params hoping for reuse; the
  155.8 GB/node shard cannot be cached in a 121 GiB pool (measured/derived).
  This trades I/O (the minutes/step cost, stated honestly in GO_NO_GO.md) for
  fitting at all.
- `stage3_prefetch_bucket_size: 200000000` (elements = 0.4 GB bf16) — at the
  measured 4.4 GB/s NVMe read this is ~91 ms per prefetch bucket; keeps the
  prefetch pipeline shallow so resident stays bounded.
- `stage3_param_persistence_threshold: 100000` — keeps only tiny tensors
  (norms: 210,240 elements total across the model, measured) permanently
  resident; negligible bytes.
- `stage3_gather_16bit_weights_on_model_save: false` — gathering 233.7 GB of
  bf16 weights onto one 121 GiB node at save time is impossible (measured pool
  size). Checkpoints must stay sharded; convert offline with `zero_to_fp32`.

### offload_param (device: nvme)
- `device: "nvme"` — mandatory, not optional: 467.3 GB working set vs 369 GB
  measured-available aggregate (1.27x over), and 155.8 GB/node vs 121 GiB.
  "CPU offload" is meaningless on GB10: CPU and GPU share the same unified
  121 GiB pool (measured: `device_count()=1`, single pool, no separate VRAM).
- `nvme_path: "__NVME_PATH__/param"` — token substituted per node by launch.sh
  (`/home/<node>/gptoss_ds_offload`). The measured free-space figures (840G /
  1.5T / 1.6T) were taken on the filesystem hosting $HOME; whether that is the
  optimal NVMe namespace is an ASSUMPTION flagged in GO_NO_GO.md.
- `buffer_size: 720000000` (elements) — must hold the largest partitioned
  parameter: largest tensor is 2,123,366,400 elements (`gate_up_proj_blocks`,
  from the shard-header scan) / 3 ranks = 707,788,800 -> 720,000,000 with 1.7%
  headroom. In bf16 that is 1.44 GB per buffer.
- `buffer_count: 5` — DeepSpeed default; 5 x 1.44 GB = 7.2 GB pinned from the
  unified pool per node — affordable inside the measured 114-115 GiB available.
- `max_in_cpu: 0` — on GB10 a "CPU-side" param cache occupies the SAME
  121 GiB pool as the GPU (measured platform fact). Caching there adds zero
  capacity; force everything to NVMe.
- `pin_memory: true` — pinned buffers also come from the unified pool; they
  are counted in the launcher's memory budget.

### offload_optimizer (device: nvme)
- `device: "nvme"` — fp32 master weights are 467.3 GB (derived); grads spill
  through this path too. Same unified-pool argument as above.
- `buffer_count: 4`, `pipeline_read/write: true` — overlap swap I/O with
  compute; 4 in-flight subgroups x 4 GB = ~16 GB pinned (derived from
  `sub_group_size`, not separately measured).
- `fast_init: false` — no measurement supports the fast path; conservative.

### aio
- `block_size: 8388608` (8 MiB), `queue_depth: 16`, `thread_count: 2`,
  `overlap_events: true` — **[choice constrained by measurement]** the ceiling
  they aim for is the measured 4.2-4.6 GB/s O_DIRECT sequential write. Large
  blocks + queue depth are how async_io approaches sequential behavior.
  Whether THIS tuple reaches the ceiling was NOT measured (`ds_io` benchmark
  not run — listed as an unmet precondition). The async_io extension itself is
  PROVEN: JIT-built and loaded on all three nodes
  (`~/.cache/torch_extensions/py312_cu130/async_io/async_io.so`).

## Per-node NVMe footprint this config implies (derived)

| Item | GB/node |
|---|---|
| bf16 param shard | 77.9 (233.66/3) |
| fp32 master shard | 155.8 (467.3/3) |
| grad spill (bf16 shard) | 77.9 |
| Adafactor state shard | ~0.2 (0.5 GB total /3) |
| **Total** | **~312 GB** -> launcher gates on >= 400 GiB free (headroom for staging/checkpoint) |

Measured free NVMe passes this gate on all three nodes (840G / 1.5T / 1.6T).
Capacity passes; **bandwidth does not** — streaming ~234-467 GB/node/step at
the measured 4.2-4.6 GB/s is 53-106 s of pure disk per step. That is stated,
not hidden: see GO_NO_GO.md.
