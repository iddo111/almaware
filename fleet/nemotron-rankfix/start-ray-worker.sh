#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  printf 'Usage: %s NODE_IP MODEL_DIR\n' "$0" >&2
  exit 2
fi

readonly NODE_IP="$1"
readonly MODEL_DIR="$2"
readonly IMAGE='vllm-ray-nemotron-pp:v0.20.0-rankfix'
readonly CONTAINER='nemotron-ray-worker'

if docker container inspect "$CONTAINER" >/dev/null 2>&1; then
  printf 'Refusing to replace existing container: %s\n' "$CONTAINER" >&2
  exit 2
fi

docker run -d \
  --name "$CONTAINER" \
  --restart unless-stopped \
  --network host \
  --ipc host \
  --security-opt label=disable \
  --gpus all \
  --volume "$MODEL_DIR:/model" \
  --env VLLM_HOST_IP="$NODE_IP" \
  --env GLOO_SOCKET_IFNAME=enp1s0f1np1 \
  --env NCCL_SOCKET_IFNAME=enp1s0f1np1 \
  --env NCCL_IB_DISABLE=1 \
  --env NCCL_MIN_NCHANNELS=1 \
  --env NCCL_MAX_NCHANNELS=1 \
  --env RAY_memory_usage_threshold=0.98 \
  --entrypoint ray \
  "$IMAGE" \
  start --address=<fabric-ip>:6379 --node-ip-address="$NODE_IP" --block

