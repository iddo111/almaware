# 🪟 BROKEN WINDOWS LAW — חוק החלונות השבורים: if it's not working, fix it IMMEDIATELY. Test the REAL output, not a proxy (`health: ok` ≠ working).

# qwen-fleet-train — 3-node full-weight fine-tune of Qwen3 on the DGX fabric

**Status: PREPARED, NOT LAUNCHED.** Everything here is reversible and does NOT
disturb the running 480B. The irreversible launch (480B down → train) needs a
final human go. Prepared 2026-08-21.

Order (Iddo): biggest dense Qwen, **full weights**, 3 machines training
(eran1+eran2+eran3 over the QSFP fabric), eran4 serves the live checkpoint (separate).

---

## 1. VERDICT — Qwen3-14B, not 32B

Measured on the fleet (all 3 nodes: aarch64 GB10, **one UNIFIED 121 GB pool**
shared by CPU+GPU, torch 2.13.0+cu130, deepspeed 0.19.3 / accelerate 1.14.0 /
transformers 5.12.1). **Because memory is unified, CPU-offload adds ZERO capacity**
— it is the same physical RAM. That is the fact that kills 32B.

Full-weight training footprint = weights + grads + optimizer, sharded by ZeRO-3
across N=3 nodes. Qwen3-14B has **14.77 B params** (verified from config: hidden
5120, 40 layers, 40 heads / 8 KV, intermediate 17408, vocab 151936, untied
embeddings). Qwen3-32B has 32.8 B (next dense size up; there is nothing between).

| model | optimizer | bytes/param | total | **/3 nodes resident** | +overhead* | fits in ~118 GB usable? |
|---|---|---|---|---|---|---|
| **Qwen3-14B** | **bf16 Adam (standard)** | 16 | 236 GB | **78.8 GB** | ~90–95 GB | ✅ **YES, ~25 GB headroom** |
| Qwen3-14B | 8-bit Adam | 10 | 148 GB | 49.2 GB | ~62 GB | ✅ very comfortable |
| Qwen3-32B | bf16 Adam | 16 | 525 GB | **174.9 GB** | — | ❌ **exceeds 121 GB physical** |
| Qwen3-32B | 8-bit Adam | 10 | 328 GB | **109.3 GB** | ~122–124 GB | ❌ **over the ~118 GB cliff** |

*overhead (per node, NOT sharded): activations w/ grad-checkpointing (~2–3 GB),
ZeRO-3 all-gather+prefetch buckets (~3–4 GB), CUDA ctx/allocator/NCCL (~3–5 GB),
OS resident (~5–8 GB).

**Recommendation: Qwen3-14B, full weights, DeepSpeed ZeRO-3, standard bf16
mixed-precision Adam (16 B/param).** It fits with ~25 GB/node headroom AND needs
no exotic optimizer — which also removes the bitsandbytes-on-aarch64 risk
(bitsandbytes is not installed and has no verified GB10 wheel). 32B full-weight
does NOT fit on three 121 GB unified nodes: even the aggressive 8-bit path lands
at ~109 GB resident + overhead, on the wrong side of the memory cliff, with zero
safe margin. To do 32B full-weight you would need a 4th fabric node — and eran4
is off-fabric (LAN only), so there is no 4th node. **14B is the biggest that fits.**

---

## 2. The exact multi-node launch

One rank per node (1 GPU/node), WORLD_SIZE=3, master = eran1 (<fabric-ip>:29500).
Fabric interfaces measured 2026-08-21:

| rank | node | fabric iface(s) | fabric IP |
|---|---|---|---|
| 0 | eran1 | `enp1s0f0np0` | <fabric-ip> |
| 1 | eran2 | `enp1s0f1np1`,`enp1s0f0np0` | <fabric-ip> / <fabric-ip> |
| 2 | eran3 | `enp1s0f1np1` | <fabric-ip> |

**Critical NCCL env (in `env_common.sh`): `NCCL_NET=Socket`** — the routed
eran1↔eran3 hop hairpins through eran2, and the RDMA/IB plugin hangs on it;
TCP-Socket works every time. Plus `NCCL_IB_DISABLE=1`, per-node
`NCCL_SOCKET_IFNAME` (see table), multi-stream Socket tuning.

Run on each node (within the rendezvous window):
```bash
cd ~/qwen-fleet-train
./launch_node.sh 0      # on eran1
./launch_node.sh 1      # on eran2
./launch_node.sh 2      # on eran3
```
`launch_node.sh` sets the per-rank iface and execs:
```
torchrun --nnodes 3 --node_rank <R> --nproc_per_node 1 \
         --master_addr <fabric-ip> --master_port 29500 train.py \
         --model_path ~/models/Qwen3-14B --deepspeed ds_zero3.json \
         --data_dir data/packed --output_dir checkpoints \
         --seq_len 2048 --micro_batch 1 --grad_accum 16 ...
```

Global batch = 3 × 1 × 16 = 48 windows/step = **98,304 tokens/step**. grad_accum
is deliberately large to amortize the expensive ZeRO-3 all-gathers over many
tokens (the Socket-transport mitigation). Gradient checkpointing ON, bf16, SDPA
attention (flash-attn not installed — not needed).

---

## 3. What is staged

- ✅ **Qwen3-14B downloaded** to `eran1:~/models/Qwen3-14B` (28 GB, 8 safetensors
  shards + index + tokenizer, verified complete).
- ✅ Scaffold on PC `D:\CLAUDE\qwen-fleet-train\` mirrored to `eran1:~/qwen-fleet-train/`.
- ❌ 32B intentionally NOT downloaded — it cannot run full-weight here, so 65 GB
  of it would be dead weight. Download only if the plan changes.

---

## 4. Corpus (assembled, dry-run verified — see build_corpus.py)

`build_corpus.py` (PC) → `data/corpus.jsonl`; `tokenize_pack.py` (eran1) →
`data/packed/*.npy` (int32, seq_len windows). Measured dry-run:

| source | records | chars |
|---|---|---|
| codex chats (recall.db) | 2,234 | 51.7 M |
| claude chats (recall.db) | 2,171 | 27.0 M |
| grok chats (recall.db) | 815 | 23.4 M |
| café-claude transcripts | 6 | 2.7 M |
| Claude memory | 342 | 1.1 M |
| KESHEV typed (Hebrew) | 3 | 0.07 M |
| **TOTAL** | | **106 M chars ≈ 30.3 M tokens** |

Sources: `alma-recall/recall.db` (209 k msgs / 5,599 sessions of AI chat logs),
KESHEV typed manifests (`mic-rebuild/state/corpus-sent/*/manifest.jsonl`),
café-claude `D:\קפה-קלוד\*.txt`. **Held-out eval dates 06-25 / 07-01 are
excluded** per project law. gemini/perplexity are currently filtered out by role
— relax `KEEP_ROLES` in build_corpus.py to include them (+~10 M chars) if wanted.
This is a **fine-tune / adaptation** corpus (personal + fleet style), not a
from-scratch pretrain set. Not finalized — run with `--write` at launch.

---

## 5. eran4 serving (scaffold only — serve_eran4.sh, INERT)

train.py saves a **consolidated HF checkpoint** every 200 steps
(`checkpoints/latest-hf`, via ZeRO-3 `stage3_gather_16bit_weights_on_model_save`).
eran4 (LAN <lan-ip>, off-fabric) rsyncs that dir and serves it with a
**separate, memory-capped vLLM on a distinct port** — **without touching eran4's
ollama (gpt-oss:120b, qwen3-coder-next) or ComfyUI**. Claim the port in RAMCHAT
first. A watch-loop re-pulls every ~10 min and restarts on change.

---

## 6. Throughput / time estimate (MEASURE FIRST)

Steps/epoch ≈ 30.3 M / 98,304 ≈ **~308 optimizer steps/epoch**.
Compute floor ≈ 8·P FLOP/token → ~32–48 s/step at 3× GB10; Socket comms on the
routed hop adds overhead → realistic **~60–120 s/step ≈ 900–1,600 tok/s**.

- **~1 epoch ≈ 3–10 hours** (most likely ~5–8 h). 3 epochs ≈ 1–2 days.
- The dominant unknown is Socket fabric throughput on the routed hop — **measure
  the first 20–50 steps, read real tok/s, then set the epoch count.** The corpus
  is small enough that even the pessimistic case is a small number of hours/epoch.

---

## 7. FINAL LAUNCH SEQUENCE (needs human go — do NOT run yet)

1. **Human go** + confirm nobody needs the 480B.
2. Take the 480B down: `docker stop qwen480-pp` on eran1 (frees ~110 GB/node).
   Verify `free -g` shows ~110+ GB free on all three.
3. Finalize data: `python build_corpus.py --write` (PC) → copy `data/corpus.jsonl`
   to eran1 → `python3 tokenize_pack.py ...` (eran1) → `data/packed/*.npy` on all
   three nodes (rsync packed dir to eran2/eran3, or use a shared path).
4. Launch: `./launch_node.sh 0|1|2` on eran1|eran2|eran3 within the rendezvous window.
5. Watch first 50 steps: ring forms, loss decreasing, per-node mem < ~110 GB, tok/s.
6. Start eran4 serving once `checkpoints/latest-hf` first appears (~step 200).

## 8. Risks (honest)
- **Socket transport throughput** on the routed eran1↔eran3 hop is the #1 unknown
  (mesh "passed" before, but throughput was not the metric). Mitigation: large
  grad_accum; if too slow, raise grad_accum / seq_len, or try idle fabric-B.
- **aarch64 multi-node**: env is identical across nodes (good), but flash-attn is
  absent (using SDPA) and no multi-node ZeRO-3 run has been *timed* on this fleet.
- **Rendezvous reachability**: eran3→<fabric-ip> routes through eran2; if the store
  won't form, fall back to master_addr=<fabric-ip> (eran2, adjacent to both).
- **Unified memory**: no offload escape hatch — 14B has margin, 32B does not.
