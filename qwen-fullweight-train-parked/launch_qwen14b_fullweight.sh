#!/usr/bin/env bash
# PARKED — do NOT run while the video fleet is busy. Launch only after the movie
# is done and Qwen/video are stopped (the fleet's ~480GB must be free).
# Full-weight fine-tune of Qwen2.5-14B across the 4 GB10 nodes, ZeRO-3 + CPU offload.
set -euo pipefail
MODEL=${MODEL:-Qwen/Qwen2.5-14B}          # 14B = comfortable full-weight; 32B = stretch (slow)
DATA=${DATA:?set DATA=path/to/dataset.jsonl}   # fill in when launching
OUT=${OUT:-./out-qwen14b-fullweight}
accelerate launch \
  --use_deepspeed --deepspeed_config_file deepspeed_zero3_offload.json \
  --num_machines 4 --num_processes 4 --machine_rank ${RANK:-0} \
  --main_process_ip eran1 --main_process_port 29500 \
  train_sft.py --model_name_or_path "$MODEL" --dataset "$DATA" --output_dir "$OUT" \
  --bf16 --gradient_checkpointing --per_device_train_batch_size 1 \
  --gradient_accumulation_steps 16 --learning_rate 1e-5 --num_train_epochs 1
