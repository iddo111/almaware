#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${repo_dir}"
# shellcheck source=/dev/null
source "${repo_dir}/launch/fabric.env"

die() {
  printf 'BLOCKED: %s\n' "$*" >&2
  exit 2
}

DRY_RUN="${DRY_RUN:-1}"
[[ "${NODE_ROLE:-}" == "eran1" || "${NODE_ROLE:-}" == "eran2" ]] ||
  die "set NODE_ROLE to eran1 or eran2"

case "${NODE_ROLE}" in
  eran1)
    MACHINE_RANK=0
    FABRIC_IP="${ERAN1_FABRIC_IP}"
    PEER_FABRIC_IP="${ERAN2_FABRIC_IP}"
    FABRIC_IFACES="${ERAN1_FABRIC_IFACES}"
    FABRIC_ADDRS="${ERAN1_FABRIC_ADDRS}"
    PEER_FABRIC_ADDRS="${ERAN1_PEER_ADDRS}"
    ;;
  eran2)
    MACHINE_RANK=1
    FABRIC_IP="${ERAN2_FABRIC_IP}"
    PEER_FABRIC_IP="${ERAN1_FABRIC_IP}"
    FABRIC_IFACES="${ERAN2_FABRIC_IFACES}"
    FABRIC_ADDRS="${ERAN2_FABRIC_ADDRS}"
    PEER_FABRIC_ADDRS="${ERAN2_PEER_ADDRS}"
    ;;
esac

export MACHINE_RANK FABRIC_IP PEER_FABRIC_IP FABRIC_IFACES
export FABRIC_ADDRS PEER_FABRIC_ADDRS
export MASTER_ADDR="${ERAN1_FABRIC_IP}" MASTER_PORT
export NCCL_SOCKET_IFNAME="${FABRIC_IFACES}"
export GLOO_SOCKET_IFNAME="${FABRIC_IFACES%%,*}"
export NCCL_IB_DISABLE=0
export NCCL_NET_GDR_LEVEL=PHB
export NCCL_ASYNC_ERROR_HANDLING=1
export TORCH_NCCL_BLOCKING_WAIT=1

: "${RUN_ID:?set a unique RUN_ID}"
: "${MODEL_KEY:?set a model key from configs/model-catalog.json}"
: "${MODEL_DIR:?set a staged local absolute model directory}"
: "${DATASET_MANIFEST:?set a staged local absolute dataset manifest}"
: "${OUTPUT_ROOT:?set a local absolute output root}"

export NODE_ROLE MODEL_DIR DATASET_MANIFEST OUTPUT_ROOT RUN_ID
bash "${repo_dir}/launch/preflight.sh"

command=(
  accelerate launch
  --config_file "${repo_dir}/configs/accelerate-deepspeed.yaml"
  --machine_rank "${MACHINE_RANK}"
  --main_process_ip "${MASTER_ADDR}"
  --main_process_port "${MASTER_PORT}"
  "${repo_dir}/training/fullweight_train.py"
  --catalog "${repo_dir}/configs/model-catalog.json"
  --model-key "${MODEL_KEY}"
  --model-dir "${MODEL_DIR}"
  --dataset-manifest "${DATASET_MANIFEST}"
  --training-config "${repo_dir}/configs/training-defaults.json"
  --output-dir "${OUTPUT_ROOT}/${RUN_ID}"
  --run-id "${RUN_ID}"
)

printf 'DRY_RUN=%s\n' "${DRY_RUN}"
printf 'NODE_ROLE=%s MACHINE_RANK=%s MASTER_ADDR=%s\n' \
  "${NODE_ROLE}" "${MACHINE_RANK}" "${MASTER_ADDR}"
printf 'COMMAND:'
printf ' %q' "${command[@]}"
printf '\n'

if [[ "${DRY_RUN}" != "0" ]]; then
  printf 'PLANNED: dry-run only; no training started.\n'
  exit 0
fi

die "runtime execution remains BLOCKED until multimodal/MoE and distributed-save canaries pass"

[[ "${ALLOW_FULLWEIGHT_TRAINING:-NO}" == "YES" ]] ||
  die "ALLOW_FULLWEIGHT_TRAINING=YES is required"
[[ "${ACK_NO_EXISTING_WORKLOAD_DISPLACEMENT:-NO}" == "YES" ]] ||
  die "ACK_NO_EXISTING_WORKLOAD_DISPLACEMENT=YES is required"
[[ "${ACK_MODEL_AND_DATA_DIGESTS_MATCH:-NO}" == "YES" ]] ||
  die "ACK_MODEL_AND_DATA_DIGESTS_MATCH=YES is required"
[[ "${APPROVED_RUN_ID:-}" == "${RUN_ID}" ]] ||
  die "APPROVED_RUN_ID must exactly match RUN_ID"
[[ "${MAX_STEPS_OVERRIDE:-2}" =~ ^[1-9][0-9]*$ ]] ||
  die "MAX_STEPS_OVERRIDE must be a positive integer"
[[ "${MAX_STEPS_OVERRIDE:-2}" -le 10 ]] ||
  die "scaffold launcher permits at most 10 qualification steps"

export DGX_FULLWEIGHT_EXECUTION=YES
export MAX_STEPS_OVERRIDE
exec "${command[@]}"
