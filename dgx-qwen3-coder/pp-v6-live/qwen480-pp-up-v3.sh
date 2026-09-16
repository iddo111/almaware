#!/bin/bash
# Qwen3-Coder-480B AWQ - vLLM PP x3, v3: full clean rebuild with Bearer-auth serve script
# from the FIRST launch (no incremental serve.sh patching -- that produced stale Ray
# actor-handle/job-id pollution across repeated in-place restarts). Same topology as v2.
# Iddo's order 2026-09-08 16:50: "תוודא שהדלת דורשת אימות".
set -x
IMG=vllm-ray:26.07
RAYENV="-e RAY_memory_usage_threshold=1.0 -e RAY_memory_monitor_refresh_ms=0"

docker rm -f qwen480-pp 2>/dev/null
docker run -d --restart unless-stopped --name qwen480-pp --network host --gpus all --shm-size 16g \
  -v /home/eran2/models/qwen480b-awq:/model \
  -e VLLM_HOST_IP=<fabric-ip> -e NCCL_SOCKET_IFNAME=enp1s0f0np0 -e GLOO_SOCKET_IFNAME=enp1s0f0np0 \
  -e VLLM_ALLOW_LONG_MAX_MODEL_LEN=1 -e VLLM_USE_DEEP_GEMM=0 $RAYENV \
  --entrypoint sleep $IMG infinity

SSH3="ssh -o StrictHostKeyChecking=no eran3@<fabric-ip>"
$SSH3 "docker rm -f qwen480-pp 2>/dev/null; docker run -d --restart unless-stopped --name qwen480-pp --network host --gpus all --shm-size 16g -v /home/eran3/models/qwen480b-awq:/model -e VLLM_HOST_IP=<fabric-ip> -e NCCL_SOCKET_IFNAME=enp1s0f1np1 -e GLOO_SOCKET_IFNAME=enp1s0f1np1 -e VLLM_ALLOW_LONG_MAX_MODEL_LEN=1 -e VLLM_USE_DEEP_GEMM=0 -e RAY_memory_usage_threshold=1.0 -e RAY_memory_monitor_refresh_ms=0 --entrypoint sleep vllm-ray:26.07 infinity"

SSH4="ssh -o StrictHostKeyChecking=no -i /home/eran2/.ssh/fleet_ed25519 eran4@<lan-ip>"
$SSH4 "docker rm -f qwen480-pp 2>/dev/null; docker run -d --restart unless-stopped --name qwen480-pp --network host --gpus all --shm-size 16g -v /home/eran4/models/qwen480b-awq:/model -e VLLM_HOST_IP=<lan-ip> -e NCCL_SOCKET_IFNAME=enP7s7 -e GLOO_SOCKET_IFNAME=enP7s7 -e NCCL_IB_DISABLE=1 -e VLLM_ALLOW_LONG_MAX_MODEL_LEN=1 -e VLLM_USE_DEEP_GEMM=0 -e RAY_memory_usage_threshold=1.0 -e RAY_memory_monitor_refresh_ms=0 --entrypoint sleep vllm-ray:26.07 infinity"

sleep 3
docker exec qwen480-pp bash -c 'export RAY_memory_usage_threshold=1.0 RAY_memory_monitor_refresh_ms=0; ray start --head --port=6379 --node-ip-address=<fabric-ip> --disable-usage-stats'
sleep 5
$SSH3 "docker exec qwen480-pp bash -c 'export RAY_memory_usage_threshold=1.0 RAY_memory_monitor_refresh_ms=0; ray start --address=<fabric-ip>:6379 --node-ip-address=<fabric-ip> --disable-usage-stats'"
$SSH4 "docker exec qwen480-pp bash -c 'export RAY_memory_usage_threshold=1.0 RAY_memory_monitor_refresh_ms=0; ray start --address=<fabric-ip>:6379 --node-ip-address=<lan-ip> --disable-usage-stats'"
sleep 8
docker exec qwen480-pp ray status

docker exec qwen480-pp pip install --root-user-action=ignore 'transformers==5.6.1' 2>&1 | tail -2
$SSH3 "docker exec qwen480-pp pip install --root-user-action=ignore 'transformers==5.6.1' 2>&1 | tail -2"
$SSH4 "docker exec qwen480-pp pip install --root-user-action=ignore 'transformers==5.6.1' 2>&1 | tail -2"

# api-key: generate fresh, push to all 3 (only eran2/head actually serves, but keep parity)
mkdir -p /home/eran2/.config/qwen480
cp /home/eran2/.config/qwen480/api-key /home/eran2/.config/qwen480/api-key.bak 2>/dev/null
docker exec qwen480-pp mkdir -p /root/.config/qwen480
docker cp /home/eran2/.config/qwen480/api-key qwen480-pp:/root/.config/qwen480/api-key

docker cp /home/eran2/qwen480-serve-v3.sh qwen480-pp:/tmp/serve.sh
docker cp /home/eran2/qwen480-wd-v3.sh qwen480-pp:/tmp/wd.sh
docker exec qwen480-pp chmod +x /tmp/serve.sh /tmp/wd.sh
docker exec -d qwen480-pp bash -c 'setsid bash /tmp/serve.sh >> /tmp/vllm-v3.log 2>&1 < /dev/null'
docker exec -d qwen480-pp bash -c 'setsid bash /tmp/wd.sh > /dev/null 2>&1 < /dev/null'
echo "[up-v3] serve launched (Bearer-gated) - model load takes ~10-25 min; watch: docker exec qwen480-pp tail -f /tmp/vllm-v3.log"
