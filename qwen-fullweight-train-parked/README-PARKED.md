# Qwen full-weight training — PARKED (Iddo 2026-08-13)

> 🪟 BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY.

Prepared in parallel with the film, **on purpose does not touch the GPU** — pure config, zero conflict with video.

## Status: PARKED. Launch only when the movie is done and the fleet is free.
Video and training fight for the same 4 GPUs + fabric. The film comes first (Iddo).

## The plan (verified sizing for 4x GB10 ~480GB unified):
- **Qwen2.5-14B full-weight** = comfortable. ZeRO-3 + CPU offload + gradient checkpointing.
- **Qwen2.5-32B** = technical stretch, slow (GB10 is memory-rich, bandwidth-modest).
- **72B** = LoRA only, not full-weight.

## To launch (later):
1. Free the fleet: `systemctl --user stop comfyui` on all nodes; ensure Qwen/video down.
2. Provide a dataset: `export DATA=/path/to/train.jsonl`
3. On each node run launch_qwen14b_fullweight.sh with its RANK (0..3).
   (train_sft.py is a standard HF SFT trainer — drop yours in, or I'll write one on launch.)

Files: deepspeed_zero3_offload.json (ZeRO-3+offload), hostfile (4 nodes over QSFP), launch script.
