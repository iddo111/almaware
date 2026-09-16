#!/usr/bin/env bash
set -euo pipefail

readonly IMAGE='vllm-ray-nemotron-pp:v0.20.0-rankfix'
readonly CONTAINER='nemotron-ray-head'
readonly MODEL_DIR='/home/eran1/models/NVIDIA-Nemotron-3-Super-120B-A12B-NVFP4'

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
  --volume /tmp/ray:/tmp/ray \
  --env VLLM_HOST_IP=<fabric-ip> \
  --env GLOO_SOCKET_IFNAME=enp1s0f1np1 \
  --env NCCL_SOCKET_IFNAME=enp1s0f1np1 \
  --env NCCL_IB_DISABLE=1 \
  --env NCCL_MIN_NCHANNELS=1 \
  --env NCCL_MAX_NCHANNELS=1 \
  --env RAY_memory_usage_threshold=0.98 \
  --entrypoint ray \
  "$IMAGE" \
  start --head --node-ip-address=<fabric-ip> --port=6379 \
    --dashboard-host=0.0.0.0 --block

