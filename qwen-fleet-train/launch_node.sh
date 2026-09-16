#!/usr/bin/env bash
# launch_node.sh RANK  -- start ONE training rank. Run on each node with its rank:
#   eran1:  ./launch_node.sh 0
#   eran2:  ./launch_node.sh 1
#   eran3:  ./launch_node.sh 2
# All three must be started within ~the rendezvous timeout of each other.
#
# NOTHING here launches until you run it. This file is inert scaffolding.
set -euo pipefail
RANK="${1:?usage: launch_node.sh <node_rank 0|1|2>}"
HERE="$(cd "$(dirname "$0")" && pwd)"
source "$HERE/env_common.sh"

# Per-node fabric interface carrying the /30 fabric IP (measured 2026-08-21):
#   rank0 eran1  enp1s0f0np0 = <fabric-ip>
#   rank1 eran2  enp1s0f1np1 = <fabric-ip> (to eran1) + enp1s0f0np0 = <fabric-ip> (to eran3)
#   rank2 eran3  enp1s0f1np1 = <fabric-ip>
case "$RANK" in
  0) IFACE="enp1s0f0np0" ;;
  1) IFACE="enp1s0f1np1,enp1s0f0np0" ;;
  2) IFACE="enp1s0f1np1" ;;
  *) echo "rank must be 0,1,2"; exit 1 ;;
esac
export NCCL_SOCKET_IFNAME="$IFACE"
export GLOO_SOCKET_IFNAME="${IFACE%%,*}"   # gloo (torchrun store) wants a single iface

echo "[launch] rank=$RANK host=$(hostname) iface=$IFACE master=$MASTER_ADDR:$MASTER_PORT NCCL_NET=$NCCL_NET"

exec python3 -m torch.distributed.run \
  --nnodes 3 \
  --node_rank "$RANK" \
  --nproc_per_node 1 \
  --master_addr "$MASTER_ADDR" \
  --master_port "$MASTER_PORT" \
  "$HERE/train.py" \
    --model_path "$HOME/models/Qwen3-14B" \
    --data_dir "$HERE/data/packed" \
    --output_dir "$HERE/checkpoints" \
    --deepspeed "$HERE/ds_zero3.json" \
    --seq_len 2048 \
    --micro_batch 1 \
    --grad_accum 16 \
    --lr 1e-5 \
    --warmup_ratio 0.03 \
    --num_epochs 1 \
    --save_steps 200 \
    --save_total_limit 3 \
    --log_steps 5
