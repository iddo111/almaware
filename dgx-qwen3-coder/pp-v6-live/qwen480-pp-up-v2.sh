#!/bin/bash
# Qwen3-Coder-480B AWQ - vLLM PP x3, v2 topology: head=eran2, workers=eran3+eran4
# Adapted 2026-09-08 by claude-cli-FABLE-480b from eran1's qwen480-pp-up.sh (head was eran1),
# on Iddo's 15:08 order ("תוריד אולמה מערן4","תכין הכל לקודר") to free eran1 for
# ERAN + coder-train + winston-forever (all migrated there this morning). eran1 UNTOUCHED -
# its own copies of these scripts were never modified.
#
# TOPOLOGY NOTES (measured 2026-09-08, do not trust old assumptions):
#  - eran2 (head) fabric-facing addr <fabric-ip> (enp1s0f0np0) <-> eran3 <fabric-ip> (enp1s0f1np1):
#    real 200G QSFP fabric, same physical link class as the original eran1-eran2-eran3 setup.
#  - eran4 has NO fabric NIC at all. Reached from eran2 over 10GbE LAN at its own IP
#    <lan-ip> (enP7s7). A static route on eran4 (<fabric-ip>/30 via <lan-ip>, persisted
#    via fabric-route.service) also lets eran4 address eran2's fabric IP <fabric-ip> directly
#    (verified: ping RTT 0.19-0.92ms, i.e. effectively local delivery - eran2's kernel
#    delivers packets for its own <fabric-ip> regardless of which physical NIC they arrive on).
#  - VERIFIED eran3<->eran4 ALSO have direct LAN reachability: eran3's wlP9s9 is UP at
#    <lan-ip>/24 (contra the stale memory claim that eran3 has "no LAN of its own" -
#    that was true for enP7s7 specifically, but wlP9s9 is up and IS eran3's default route).
#    ping eran3->eran4 3.0-3.9ms, eran4->eran3 3.1-7.1ms. This means the 3 nodes form a
#    genuine full mesh, not a fragile forced chain - any pipeline-rank pairing Ray/vLLM
#    picks will be able to open a direct connection. eran4's leg (10GbE, whichever peer)
#    is the bandwidth bottleneck regardless of pairing - say so honestly, don't hide it.
#  - RAY_memory_usage_threshold=1.0 / RAY_memory_monitor_refresh_ms=0 mandatory on every
#    node (root-fixed scar 2026-08-20: Ray's memory monitor SIGKILLing PP workers at 95%).
#  - transformers==5.6.1 pin re-applied after container start on every node (scar 2026-08-21:
#    an -U xgrammar cascaded transformers to 4.57.6 and broke vllm's config loader). Do NOT
#    let anything upgrade it or add xgrammar.
#  - gpu-memory-utilization 0.78 unchanged - same GB10 hardware (121GB unified) on all 3
#    nodes regardless of which physical box hosts which pipeline stage.
set -x
IMG=vllm-ray:26.07
RAYENV="-e RAY_memory_usage_threshold=1.0 -e RAY_memory_monitor_refresh_ms=0"

# --- eran2 (local / head) ---
docker rm -f qwen480-pp 2>/dev/null
docker run -d --restart unless-stopped --name qwen480-pp --network host --gpus all --shm-size 16g \
  -v /home/eran2/models/qwen480b-awq:/model \
  -e VLLM_HOST_IP=<fabric-ip> -e NCCL_SOCKET_IFNAME=enp1s0f0np0 -e GLOO_SOCKET_IFNAME=enp1s0f0np0 \
  -e VLLM_ALLOW_LONG_MAX_MODEL_LEN=1 -e VLLM_USE_DEEP_GEMM=0 $RAYENV \
  --entrypoint sleep $IMG infinity

# --- eran3 (fabric worker) ---
# NOTE: eran2's LOCAL ssh config has a stale "eran3" alias pointing at the wrong IP
# (<lan-ip>, which is actually eran1's LAN address) - use the explicit fabric
# address instead, which is the already-trusted key path used by the original
# eran1 script's nested proxy-jump.
SSH3="ssh -o StrictHostKeyChecking=no eran3@<fabric-ip>"
$SSH3 "docker rm -f qwen480-pp 2>/dev/null; docker run -d --restart unless-stopped --name qwen480-pp --network host --gpus all --shm-size 16g -v /home/eran3/models/qwen480b-awq:/model -e VLLM_HOST_IP=<fabric-ip> -e NCCL_SOCKET_IFNAME=enp1s0f1np1 -e GLOO_SOCKET_IFNAME=enp1s0f1np1 -e VLLM_ALLOW_LONG_MAX_MODEL_LEN=1 -e VLLM_USE_DEEP_GEMM=0 -e RAY_memory_usage_threshold=1.0 -e RAY_memory_monitor_refresh_ms=0 --entrypoint sleep vllm-ray:26.07 infinity"

# --- eran4 (LAN-only worker, no fabric NIC) ---
# NOTE: same stale-alias problem ("eran4" on eran2 points at <lan-ip>, unreachable).
# eran4's authorized_keys only trusts eran2's fleet_ed25519 key (not the default id_ed25519),
# so it must be named explicitly here too.
SSH4="ssh -o StrictHostKeyChecking=no -i /home/eran2/.ssh/fleet_ed25519 eran4@<lan-ip>"
$SSH4 "docker rm -f qwen480-pp 2>/dev/null; docker run -d --restart unless-stopped --name qwen480-pp --network host --gpus all --shm-size 16g -v /home/eran4/models/qwen480b-awq:/model -e VLLM_HOST_IP=<lan-ip> -e NCCL_SOCKET_IFNAME=enP7s7 -e GLOO_SOCKET_IFNAME=enP7s7 -e NCCL_IB_DISABLE=1 -e VLLM_ALLOW_LONG_MAX_MODEL_LEN=1 -e VLLM_USE_DEEP_GEMM=0 -e RAY_memory_usage_threshold=1.0 -e RAY_memory_monitor_refresh_ms=0 --entrypoint sleep vllm-ray:26.07 infinity"

sleep 3
docker exec qwen480-pp bash -c 'export RAY_memory_usage_threshold=1.0 RAY_memory_monitor_refresh_ms=0; ray start --head --port=6379 --node-ip-address=<fabric-ip> --disable-usage-stats'
sleep 5
$SSH3 "docker exec qwen480-pp bash -c 'export RAY_memory_usage_threshold=1.0 RAY_memory_monitor_refresh_ms=0; ray start --address=<fabric-ip>:6379 --node-ip-address=<fabric-ip> --disable-usage-stats'"
$SSH4 "docker exec qwen480-pp bash -c 'export RAY_memory_usage_threshold=1.0 RAY_memory_monitor_refresh_ms=0; ray start --address=<fabric-ip>:6379 --node-ip-address=<lan-ip> --disable-usage-stats'"
sleep 8
docker exec qwen480-pp ray status

# --- transformers pin guard (scar 2026-08-21, reapplied on every node) ---
docker exec qwen480-pp pip install --root-user-action=ignore 'transformers==5.6.1' 2>&1 | tail -2
$SSH3 "docker exec qwen480-pp pip install --root-user-action=ignore 'transformers==5.6.1' 2>&1 | tail -2"
$SSH4 "docker exec qwen480-pp pip install --root-user-action=ignore 'transformers==5.6.1' 2>&1 | tail -2"

docker cp /home/eran2/qwen480-serve-v2.sh qwen480-pp:/tmp/serve.sh
docker cp /home/eran2/qwen480-wd-v2.sh qwen480-pp:/tmp/wd.sh
docker exec qwen480-pp chmod +x /tmp/serve.sh /tmp/wd.sh
docker exec -d qwen480-pp bash -c 'setsid bash /tmp/serve.sh >> /tmp/vllm.log 2>&1 < /dev/null'
docker exec -d qwen480-pp bash -c 'setsid bash /tmp/wd.sh > /dev/null 2>&1 < /dev/null'
echo "[up] serve launched - model load takes ~25-40 min; watch: docker exec qwen480-pp tail -f /tmp/vllm.log"
