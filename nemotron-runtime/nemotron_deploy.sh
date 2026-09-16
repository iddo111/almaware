#!/usr/bin/env bash
# Run one reliable Nemotron 3 Super 120B replica on a DGX Spark / GB10.
set -Eeuo pipefail

ACTION="${1:-start}"
MODEL_DIR="${MODEL_DIR:-$HOME/models/NVIDIA-Nemotron-3-Super-120B-A12B-NVFP4}"
MODEL_ID="${MODEL_ID:-nvidia/nemotron-3-super}"
IMAGE="${VLLM_IMAGE:-vllm/vllm-openai:v0.20.0}"
CONTAINER="${CONTAINER_NAME:-nemotron-120b}"
PORT="${NEMOTRON_PORT:-8000}"
MAX_MODEL_LEN="${MAX_MODEL_LEN:-262144}"
WAIT_SECONDS="${WAIT_SECONDS:-1200}"

if docker info >/dev/null 2>&1; then
  DOCKER=(docker)
elif sudo -n docker info >/dev/null 2>&1; then
  DOCKER=(sudo -n docker)
else
  echo "ERROR: Docker is unavailable to this user (directly or via passwordless sudo)." >&2
  exit 1
fi

status() {
  if ! "${DOCKER[@]}" inspect "$CONTAINER" >/dev/null 2>&1; then
    echo "container=absent ready=false"
    return 1
  fi
  "${DOCKER[@]}" inspect -f 'container={{.State.Status}} restart={{.RestartCount}} oom={{.State.OOMKilled}} started={{.State.StartedAt}}' "$CONTAINER"
  if curl -fsS --max-time 10 "http://127.0.0.1:$PORT/v1/models" >/tmp/alma-nemotron-models.json 2>/dev/null; then
    python3 - "$MODEL_ID" /tmp/alma-nemotron-models.json <<'PY'
import json, sys
model_id = sys.argv[1]
with open(sys.argv[2], encoding="utf-8") as handle:
    payload = json.load(handle)
ids = [item.get("id") for item in payload.get("data", [])]
assert model_id in ids, (model_id, ids)
print("ready=true model=" + model_id)
PY
    return 0
  fi
  echo "ready=false (container may still be loading)"
  return 1
}

case "$ACTION" in
  status) status ;;
  stop)
    "${DOCKER[@]}" stop -t 60 "$CONTAINER"
    ;;
  restart)
    "${DOCKER[@]}" rm -f "$CONTAINER" >/dev/null 2>&1 || true
    exec "$0" start
    ;;
  start)
    if status >/dev/null 2>&1; then
      status
      exit 0
    fi
    if "${DOCKER[@]}" inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null | grep -q true; then
      echo "$CONTAINER is already loading. Use '$0 status' instead of restarting it."
      exit 0
    fi
    python3 - "$MODEL_DIR" <<'PY'
import json, pathlib, sys
root = pathlib.Path(sys.argv[1])
index = root / "model.safetensors.index.json"
if not index.is_file():
    raise SystemExit(f"missing {index}")
data = json.loads(index.read_text())
files = sorted(set(data.get("weight_map", {}).values()))
missing = [name for name in files if not (root / name).is_file()]
if not files or missing:
    raise SystemExit(f"incomplete checkpoint: files={len(files)} missing={missing[:5]}")
print(f"checkpoint_ok files={len(files)} path={root}")
PY
    "${DOCKER[@]}" image inspect "$IMAGE" >/dev/null 2>&1 || "${DOCKER[@]}" pull "$IMAGE"
    "${DOCKER[@]}" rm -f "$CONTAINER" >/dev/null 2>&1 || true
    TAIL_IP="$(tailscale ip -4 2>/dev/null | head -n1 || true)"
    PORT_ARGS=(-p "127.0.0.1:$PORT:8000")
    if [[ -n "$TAIL_IP" ]]; then PORT_ARGS+=(-p "$TAIL_IP:$PORT:8000"); fi
    "${DOCKER[@]}" run -d --name "$CONTAINER" --restart unless-stopped --gpus all --ipc=host \
      "${PORT_ARGS[@]}" \
      -e VLLM_NVFP4_GEMM_BACKEND=marlin \
      -e VLLM_FLASHINFER_ALLREDUCE_BACKEND=trtllm \
      -e VLLM_USE_FLASHINFER_MOE_FP4=0 \
      -v "$MODEL_DIR:/model:ro" \
      "$IMAGE" /model \
      --served-model-name "$MODEL_ID" --host 0.0.0.0 --port 8000 \
      --async-scheduling --dtype auto --kv-cache-dtype fp8 \
      --trust-remote-code --gpu-memory-utilization 0.90 --enable-chunked-prefill \
      --max-num-seqs 4 --max-model-len "$MAX_MODEL_LEN" \
      --moe-backend marlin --mamba-ssm-cache-dtype float16 --quantization fp4 \
      --reasoning-parser-plugin /model/super_v3_reasoning_parser.py \
      --reasoning-parser super_v3 --enable-auto-tool-choice --tool-call-parser qwen3_coder
    deadline=$((SECONDS + WAIT_SECONDS))
    until status; do
      if (( SECONDS >= deadline )); then
        echo "ERROR: model did not become ready within ${WAIT_SECONDS}s" >&2
        "${DOCKER[@]}" logs --tail 120 "$CONTAINER" >&2 || true
        exit 1
      fi
      sleep 10
    done
    ;;
  *)
    echo "Usage: $0 {start|status|stop|restart}" >&2
    exit 2
    ;;
esac
