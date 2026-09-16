# GO / NO-GO — full-weight training of gpt-oss-120b on eran1+eran2+eran3

Date: 2026-08-06. Basis: the 2026-08-05 qualification measurements only
(DeepSpeed install report, NCCL/RoCE fabric report, memory/NVMe report).
No number below is invented; where a measurement was not obtained it says
UNKNOWN. eran4 is out of scope (no RDMA hardware on the PCI bus).

## VERDICT UP FRONT

**Full-weight fine-tuning of gpt-oss-120b across eran1+eran2+eran3 is
NOT VIABLE.** Not "hard" — not worth doing. It is technically constructible
(every component exists and was proven individually) and practically useless:
the working set exceeds total fleet memory, the only functioning 3-node
collective runs at 4.53 GB/s, and the measured NVMe + network floors put every
optimizer step at ~2-4 minutes before any compute happens. A 1,000-step run
would spend 1.5-3 days purely moving bytes.

**The path that works: QLoRA on eran2 alone — ~75-85 GB, fits in one node's
121 GiB pool, touches neither the degraded 3-node fabric nor the GLM-occupied
nodes.** Details at the bottom.

---

## 1. Measured all-reduce bandwidth — does it pass?

| Configuration | 2 GB algbw | 2 GB busbw | Verdict |
|---|---|---|---|
| 2-node RoCE (eran1+eran2), dual rail | **22.63 GB/s** | 22.63 GB/s | **PASS** — 92% of the measured 24.5 GB/s dual-rail RDMA ceiling (per-port caps at ~110 Gb/s on GB10; that IS line rate here) |
| 2-node TCP (control) | 9.44 GB/s | 9.44 GB/s | reference only |
| 3-node RoCE ring | — | — | **FAIL — topologically impossible as cabled.** The fabric is a LINE (eran1↔eran2↔eran3, no eran1↔eran3 wire). NCCL binds one NIC per channel per rank (`ibv_modify_qp failed with 110`), and transit RDMA through eran2's kernel dies (`IBV_WC_RETRY_EXC_ERR`); raw `ib_write_bw -R` over the routed path hangs. RDMA is strictly single-hop on this fabric. No env var fixes topology. |
| 3-node TCP (only working 3-node config) | **4.53 GB/s** | 6.04 GB/s | **FAIL for full-weight training.** Syncing the ~233.7 GB bf16 gradient set at 4.53 GB/s costs ~50+ s/step of pure communication; ZeRO-3 additionally all-gathers ~311 GB inbound/node/step (fwd+bwd) ≈ 30-60+ s/step. 5.0x slower than the 2-node RoCE reference. |

Transport for the 2-node figure was verified RoCE, not TCP, in NCCL debug
output (`NET/IB : Using [0]rocep1s0f0:1/RoCE [1]roceP2p1s0f0:1/RoCE`, 16
channels striped across both rails).

Hardware unlock (not done): eran1 and eran3 each have 2 dark 200G ports. One
direct eran1↔eran3 cable closes the triangle and should lift 3-node
all-reduce into the ~15-22 GB/s class. Until that cable exists, 3-node
uniform data parallelism is dead on arrival.

## 2. Is async_io / NVMe offload actually available? — YES, proven

Not inferred from `ds_report` flags — forced actual JIT compilation and load
on every training node:

- eran1: `/home/eran1/.cache/torch_extensions/py312_cu130/async_io/async_io.so` built + loaded
- eran2: `/home/eran2/.cache/torch_extensions/py312_cu130/async_io/async_io.so` built + loaded
- eran3: `/home/eran3/.cache/torch_extensions/py312_cu130/async_io/async_io.so` built + loaded

DeepSpeed 0.19.3 on all three (aarch64 sdist build, JIT mode). `libaio-dev`
and `python3-dev` gaps were found and fixed during qualification. `cpu_adam`
proven built on eran2 only (deliberate — eran1/eran3 were mid GLM bring-up);
it is compatible and will JIT on first use elsewhere. Launchers MUST export
`PATH=$HOME/.local/bin:/usr/local/cuda/bin:$PATH` or JIT dies on ninja/nvcc.

## 3. Computed per-step NVMe I/O and implied seconds-per-step

Measured NVMe sequential write (8 GiB, O_DIRECT, fdatasync): eran1 4.4 GB/s,
eran2 4.6 GB/s, eran3 4.2 GB/s — best case (/dev/zero is maximally
compressible).

Per full-parameter optimizer step, each node must stream through NVMe at
minimum ~234 GB (grads/optimizer state only) up to ~467 GB (weights spill
too, which this config forces via `stage3_max_reuse_distance=0` because the
155.8 GB/node shard cannot live in a 121 GiB pool):

- **234 GB / 4.4 GB/s ≈ 53 s/step;  467 GB / 4.4 GB/s ≈ 106 s/step — disk alone.**
- Network floor on the only working 3-node transport: **30-60+ s/step.**
- **Combined floor: ~2-4 minutes per optimizer step** before any compute.
  1,000 steps ≈ 1.5-3 days of pure overhead.

NVMe *capacity* passes: per-node footprint ~312 GB (77.9 bf16 param shard +
155.8 fp32 master + 77.9 grad spill + ~0.2 Adafactor) vs measured free 840G /
1.5T / 1.6T. Capacity was never the problem; bandwidth is.

## 4. Memory arithmetic (with the independently derived parameter count)

Parameter count re-derived from all 687 tensor headers across the 15
safetensors shards (65,248,893,184 bytes, byte-identical on all nodes):
**116,829,156,672 — matches the claimed count exactly.** 98.14% of parameters
(114,661,785,600) are MXFP4 expert weights; only 1.86% (2,167,371,072) are
BF16-native (attention, embeddings, lm_head, routers, biases, norms). There
is no BF16 release — full training REQUIRES upcasting.

| Item | Size |
|---|---|
| BF16 weights (116.83B x 2 B) | 233.66 GB |
| + BF16 gradients | **467.3 GB working set** |
| + Adam m,v fp32 (ruled out) | ~934 GB more → ~1.4 TB; + fp32 master → ~1.9-2.3 TB |
| Adafactor state (adopted) | ~0.5 GB (68M factored + 55M full-v fp32) — the only reason this is even arguable |
| fp32 master weights (stability) | +467.3 GB (NVMe-resident) |

Against measured capacity (2026-08-05 snapshot, **shrinking** — GLM-5.2
replicas were actively coming up on eran1/eran3):

- Aggregate available: 344 GiB ≈ 369 GB → 467.3 GB working set is **1.27x over**.
- Per node: 155.8 GB shard vs 121 GiB (130 GB) total pool → over per-node too.
- GB10 has no separate VRAM to add — the unified pool IS the GPU memory, so
  DeepSpeed "CPU offload" adds zero capacity here. NVMe offload is the only
  offload that exists on this platform, and it costs §3's minutes per step.
- DeepSpeed's NVMe swap path exists and async_io is proven, but its optimizer
  swapping is designed around DeepSpeed's own optimizer family; client-side
  Adafactor through that path is **UNVERIFIED** (see §5).

## 5. Preconditions still unmet (every one)

1. **No dataset.** No manifest, no corpus, no tokenized data anywhere.
   `dataset_manifest.json` does not exist. Sequence length therefore UNKNOWN,
   so activation memory per step is UNKNOWN.
2. **No training script.** `~/gptoss-training/train_full_zero3.py` was never
   written on any node.
3. **No node is currently available — including eran2.** The 2026-08-05
   report expected GLM-5.2 on eran1/eran3 only. The live dry-run gate check
   (2026-08-06, `bash launch.sh`) found `coli serve` (Colibri) running on
   ALL THREE nodes, with available RAM measured at: eran1 24.6 GiB,
   eran2 39.8 GiB, eran3 4.0 GiB — all far below the 100 GiB gate. The
   launcher correctly refused. eran1's free NVMe also dropped from the
   840G snapshot to a measured 511.5 GiB (still above the 400 GiB gate).
4. **Cross-rail static routes are runtime-only and lost on reboot.**
   Reapply: eran1 `sudo ip route add <fabric-ip>/30 via <fabric-ip> dev enP2p1s0f0np0`;
   eran3 `sudo ip route replace <fabric-ip>/30 via <fabric-ip> dev enP2p1s0f1np1`.
   No persistence (netplan) was configured.
5. **Adafactor ↔ DeepSpeed NVMe optimizer-swap compatibility UNVERIFIED.**
   Only async_io (all nodes) and cpu_adam (eran2) were proven.
6. **cpu_adam prebuilt only on eran2**; eran1/eran3 will JIT-compile on first
   use (transient RAM cost during GLM occupancy).
7. **NVMe offload path assumption unverified.** The measured free-space and
   dd figures were taken on the filesystem hosting $HOME; whether a separate,
   faster NVMe namespace exists was not checked.
8. **MASTER_ADDR resolution UNKNOWN.** No single RoCE /30 address is reachable
   from both eran1 and eran3; the launcher assumes hostname `eran2` resolves
   on the management network from both spokes — not verified.
9. **aio tuning unbenchmarked.** The config's 8 MiB/qd16/2-thread aio block
   was never run through `ds_io`; 4.2-4.6 GB/s is a dd best case.
10. **No re-quantization pipeline.** The deployable artifact is MXFP4; after
    bf16 training you must quantize back to 4-bit, reintroducing quantization
    error on top of days of training. Nothing for this exists.
11. **fp32 master weights decision open.** Skipping them risks bf16 update
    stability; keeping them adds 467 GB of NVMe traffic per step.
12. **eran1↔eran3 direct cable absent** — the single highest-leverage
    hardware change; without it 3-node RDMA collectives are impossible.

## 6. Blunt verdict

**Not viable.** Not marginal — not viable. The honest chain: 467.3 GB working
set > 369 GB shrinking aggregate (1.27x over, and over per-node too) → NVMe
offload mandatory → 53-106 s/step of disk at measured bandwidth, PLUS the
3-node fabric is a line whose only working collective does 4.53 GB/s → 30-60+
s/step of network → **~2-4 min/step floor, days of overhead for a modest
fine-tune, ending in an MXFP4 re-quantization that partially undoes it.**
Every individual component passes its own test; the composition fails
arithmetic. Do not run this. The launcher in this directory will refuse to,
and saying yes to it would require overriding an explicit acknowledgement
gate on this document.

### The alternative that is actually good: QLoRA on eran2 alone

- Frozen MXFP4 base resident: **~65.2 GB** (stored size — no upcast).
- LoRA r=32 on all attention projections: ~23.9M trainable params; adapters +
  bf16 grads + fp32 Adam m,v + master: **~0.4 GB**.
- With grad-checkpointed activations: **~75-85 GB total — fits on eran2
  ALONE** (121 GiB pool; 115 GiB available at the 2026-08-05 snapshot).
  **Live caveat (2026-08-06 dry-run):** eran2 is currently ALSO running a
  Colibri replica and shows only 39.8 GiB available — even QLoRA waits until
  ~85 GB can be vacated on one node. The fit claim holds for an idle eran2;
  no node is idle right now.
- Sidesteps: the line topology, the software-routed eran1↔eran3 leg, the
  4.53 GB/s TCP collective, the NVMe streaming tax, and the GLM workload.
- If 2-node data parallelism is ever wanted: eran1+eran2 (or eran2+eran3)
  RoCE is qualified at 22.63 GB/s with the exact env pinned in launch.sh.
- Honest limits: the 114.7B expert params (98.14% of the model) stay frozen
  at 4-bit; adaptation flows through the ~1.9% dense/attention path.
  Style/instruction/domain tuning: yes. Teaching the experts substantially
  new knowledge: limited. Expert-targeted LoRA exists in PEFT but multiplies
  adapter size by 128 experts.

Still required even for QLoRA: a dataset and a training script. Neither exists.
