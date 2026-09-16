#!/usr/bin/env bash
# serve_eran4.sh -- SCAFFOLD ONLY. INERT. Do NOT run until the final go.
#
# eran4 is OFF the training fabric (LAN <lan-ip>). Its job: serve the LATEST
# training checkpoint for live testing while eran1/2/3 keep training. It pulls
# the consolidated HF checkpoint (checkpoints/latest-hf, written by train.py with
# ZeRO-3 16-bit gather-on-save) from eran1 over the LAN, then serves it.
#
# HARD RULE: do NOT touch eran4's ollama (gpt-oss:120b, qwen3-coder-next) or
# ComfyUI. Serve on a DISTINCT port, claim it in RAMCHAT first, and cap GPU
# memory so it coexists with whatever ollama has resident.
set -euo pipefail

ERAN1_HOST="eran1@<lan-ip>"           # LAN path PC->eran1; from eran4 use its own route
CKPT_REMOTE="~/qwen-fleet-train/checkpoints/latest-hf"
CKPT_LOCAL="$HOME/qwen14b-live"            # on eran4
SERVE_PORT="${SERVE_PORT:-8781}"           # CLAIM in RAMCHAT before binding
GPU_FRAC="${GPU_FRAC:-0.35}"               # leave room for ollama/comfy on the 121GB pool

pull() {
  echo "[serve_eran4] pulling $CKPT_REMOTE -> $CKPT_LOCAL"
  rsync -a --delete -e ssh "$ERAN1_HOST:$CKPT_REMOTE/" "$CKPT_LOCAL/"
}

serve_vllm() {
  # Option A (preferred): vLLM, memory-capped so it does not evict ollama.
  python3 -m vllm.entrypoints.openai.api_server \
    --model "$CKPT_LOCAL" \
    --port "$SERVE_PORT" \
    --gpu-memory-utilization "$GPU_FRAC" \
    --max-model-len 4096 \
    --served-model-name qwen14b-iddo-live
}

# Hot-reload loop: re-pull every N minutes; restart the server only if weights changed.
watch_loop() {
  local interval="${1:-600}"
  while true; do
    pull
    # (restart-if-changed logic goes here at launch time)
    sleep "$interval"
  done
}

echo "INERT scaffold. Intended sequence at launch:"
echo "  1) claim port $SERVE_PORT in RAMCHAT"
echo "  2) pull          (rsync latest-hf from eran1)"
echo "  3) serve_vllm    (capped at GPU_FRAC=$GPU_FRAC, port $SERVE_PORT)"
echo "  4) watch_loop 600  (re-pull every 10 min, restart on change)"
