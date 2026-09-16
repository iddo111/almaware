#!/usr/bin/env bash
set -euo pipefail

readonly IMAGE='vllm-ray-nemotron-pp:v0.20.0-rankfix'
readonly CONTAINER='nemotron-cluster'
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
  --volume /tmp/ray:/tmp/ray \
  --volume "$MODEL_DIR:/model" \
  --env VLLM_HOST_IP=<fabric-ip> \
  --env GLOO_SOCKET_IFNAME=enp1s0f1np1 \
  --env NCCL_SOCKET_IFNAME=enp1s0f1np1 \
  --env NCCL_IB_DISABLE=1 \
  --env NCCL_MIN_NCHANNELS=1 \
  --env NCCL_MAX_NCHANNELS=1 \
  --env RAY_ADDRESS=<fabric-ip>:6379 \
  --entrypoint vllm \
  "$IMAGE" serve \
  --model /model \
  --served-model-name nvidia/nemotron-3-super \
  --host 0.0.0.0 \
  --port 8000 \
  --distributed-executor-backend ray \
  --tensor-parallel-size 1 \
  --pipeline-parallel-size 3 \
  --dtype auto \
  --kv-cache-dtype fp8 \
  --trust-remote-code \
  --gpu-memory-utilization 0.88 \
  --max-model-len 131072 \
  --enable-chunked-prefill \
  --max-num-seqs 2 \
  --moe-backend marlin \
  --mamba-ssm-cache-dtype float16 \
  --quantization fp4 \
  --enforce-eager \
  --attention-backend TRITON_ATTN \
  --reasoning-parser-plugin /model/super_v3_reasoning_parser.py \
  --reasoning-parser super_v3 \
  --enable-auto-tool-choice \
  --tool-call-parser qwen3_coder

