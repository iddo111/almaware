#!/usr/bin/env bash
set -euo pipefail

die() {
  printf 'BLOCKED: %s\n' "$*" >&2
  exit 2
}

[[ "$(uname -s)" == "Linux" ]] || die "DGX Linux only"
[[ -r /proc/driver/nvidia/version ]] || die "NVIDIA driver evidence missing"
[[ "${NODE_ROLE:-}" == "eran1" || "${NODE_ROLE:-}" == "eran2" ]] ||
  die "NODE_ROLE must be eran1 or eran2"
[[ -n "${FABRIC_IP:-}" && "${FABRIC_IP}" != REQUIRED_* ]] ||
  die "fresh FABRIC_IP is unresolved"
[[ -n "${FABRIC_IFACES:-}" && "${FABRIC_IFACES}" != REQUIRED_* ]] ||
  die "fresh FABRIC_IFACES is unresolved"
[[ -n "${FABRIC_ADDRS:-}" && "${FABRIC_ADDRS}" != REQUIRED_* ]] ||
  die "fresh FABRIC_ADDRS is unresolved"
[[ -n "${PEER_FABRIC_ADDRS:-}" && "${PEER_FABRIC_ADDRS}" != REQUIRED_* ]] ||
  die "fresh PEER_FABRIC_ADDRS is unresolved"
[[ -n "${MODEL_DIR:-}" && "${MODEL_DIR}" == /* && -d "${MODEL_DIR}" ]] ||
  die "MODEL_DIR must be a staged local absolute directory"
[[ -n "${DATASET_MANIFEST:-}" && "${DATASET_MANIFEST}" == /* &&
   -f "${DATASET_MANIFEST}" ]] ||
  die "DATASET_MANIFEST must be a staged local absolute file"
[[ -n "${OUTPUT_ROOT:-}" && "${OUTPUT_ROOT}" == /* && -d "${OUTPUT_ROOT}" ]] ||
  die "OUTPUT_ROOT must be an existing absolute directory"
[[ -n "${RUN_ID:-}" && "${RUN_ID}" =~ ^[A-Za-z0-9._-]+$ ]] ||
  die "RUN_ID is missing or unsafe"
[[ ! -e "${OUTPUT_ROOT}/${RUN_ID}" ]] ||
  die "output already exists; never overwrite a run"

IFS=',' read -r -a interfaces <<< "${FABRIC_IFACES}"
IFS=',' read -r -a addresses <<< "${FABRIC_ADDRS}"
IFS=',' read -r -a peer_addresses <<< "${PEER_FABRIC_ADDRS}"
[[ "${#interfaces[@]}" -eq "${#addresses[@]}" &&
   "${#interfaces[@]}" -eq "${#peer_addresses[@]}" ]] ||
  die "fabric interface/address evidence arrays do not align"
for index in "${!interfaces[@]}"; do
  interface="${interfaces[$index]}"
  address="${addresses[$index]}"
  peer_address="${peer_addresses[$index]}"
  [[ -r "/sys/class/net/${interface}/operstate" ]] ||
    die "interface ${interface} missing"
  [[ "$(<"/sys/class/net/${interface}/operstate")" == "up" ]] ||
    die "interface ${interface} is not up"
  ip -o addr show dev "${interface}" | grep -Fq "${address}" ||
    die "${address} is not assigned to ${interface}"
  ip route get "${peer_address}" | grep -Fq "dev ${interface}" ||
    die "${peer_address} route is not bound to ${interface}"
done

python3 - "${DATASET_MANIFEST}" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
manifest = json.loads(path.read_text(encoding="utf-8"))
if manifest.get("modality") not in {"text", "image_text"}:
    raise SystemExit("BLOCKED: unsupported dataset modality")
if not manifest.get("license", {}).get("training_allowed"):
    raise SystemExit("BLOCKED: training permission missing")
if not manifest.get("consent", {}).get("sensitive_data_reviewed"):
    raise SystemExit("BLOCKED: sensitive-data review missing")
for split in ("train", "validation"):
    if not manifest.get("splits", {}).get(split):
        raise SystemExit(f"BLOCKED: empty {split} split")
print("dataset_manifest_structure=PASS")
PY

printf 'node_role=%s\n' "${NODE_ROLE}"
printf 'hostname=%s\n' "$(hostname --fqdn)"
printf 'fabric_ip=%s\n' "${FABRIC_IP}"
printf 'fabric_ifaces=%s\n' "${FABRIC_IFACES}"
printf 'fabric_addrs=%s\n' "${FABRIC_ADDRS}"
printf 'peer_fabric_addrs=%s\n' "${PEER_FABRIC_ADDRS}"
printf 'driver=%s\n' "$(tr '\n' ' ' </proc/driver/nvidia/version)"
printf 'python=%s\n' "$(python3 --version 2>&1)"
printf 'disk=%s\n' "$(df -B1 --output=avail,target "${OUTPUT_ROOT}" | tail -n 1)"
printf 'preflight=PASS\n'
