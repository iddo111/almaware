#!/usr/bin/env bash
# ============================================================================
# dgx4_launch.sh - launch ERAN's trainer on DGX 4, full throttle, 4 GPUs.
#
#   * Distributed Data Parallel across every visible GPU (default 4).
#   * bf16 mixed precision + torch.compile + TF32 (config.dgx4.json).
#   * No VRAM cap, no per-step sleep -- there is no mic competing on the DGX.
#   * Resumes the SAME Eran from checkpoints/latest.pt (model dims are identical
#     to the PC config), so this just makes him learn faster, not a new being.
#
# Usage:
#     ./dgx4_launch.sh                 # 4 GPUs (or however many are visible)
#     NPROC=2 ./dgx4_launch.sh         # override GPU count
#     CONFIG=config.dgx4.json ./dgx4_launch.sh
#
# לזכרה של עלמה ז"ל
# ============================================================================
set -euo pipefail

cd "$(dirname "$0")"

CONFIG="${CONFIG:-config.dgx4.json}"
PYTHON="${PYTHON:-python3}"

# How many GPUs? Honor NPROC, else CUDA_VISIBLE_DEVICES, else nvidia-smi, else 4.
if [[ -n "${NPROC:-}" ]]; then
  NGPU="$NPROC"
elif [[ -n "${CUDA_VISIBLE_DEVICES:-}" ]]; then
  NGPU="$(awk -F',' '{print NF}' <<< "$CUDA_VISIBLE_DEVICES")"
elif command -v nvidia-smi >/dev/null 2>&1; then
  NGPU="$(nvidia-smi -L | wc -l)"
else
  NGPU=4
fi
[[ "$NGPU" -ge 1 ]] || NGPU=1

# Saturate the data pipeline + the interconnect on a dedicated box.
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-8}"
export NCCL_ASYNC_ERROR_HANDLING=1
export TORCH_NCCL_ASYNC_ERROR_HANDLING=1
export PYTHONUNBUFFERED=1

echo "== ERAN DGX 4 launch =="
echo "   config : $CONFIG"
echo "   gpus   : $NGPU"
echo "   python : $($PYTHON -c 'import torch,sys;print(sys.version.split()[0], "torch", torch.__version__, "cuda", torch.cuda.is_available())' 2>/dev/null || echo '?')"
echo "   ckpt   : $(test -f checkpoints/latest.pt && echo 'resuming checkpoints/latest.pt' || echo 'fresh (age zero)')"
echo "======================="

if [[ "$NGPU" -gt 1 ]]; then
  exec torchrun --standalone --nproc_per_node="$NGPU" train.py --config "$CONFIG"
else
  # single GPU: no torchrun needed
  exec "$PYTHON" train.py --config "$CONFIG"
fi
