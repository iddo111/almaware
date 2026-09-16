#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-/opt/antvoice-190m}"
MANIFEST="${MANIFEST:-/data/antvoice/manifest.jsonl}"
AUDIO_ROOT="${AUDIO_ROOT:-/data/antvoice/audio}"
RUN_ROOT="${RUN_ROOT:-}"
RESUME_LATEST="${RESUME_LATEST:-1}"
EXECUTE="${EXECUTE:-0}"

command=(
  python -m antvoice.train
  --model-config "${PROJECT_DIR}/configs/antvoice_190m.json"
  --run-config "${PROJECT_DIR}/configs/real_audio_train.json"
  --manifest "${MANIFEST}"
  --audio-root "${AUDIO_ROOT}"
  --run-root "${RUN_ROOT:-<required-persistent-run-root>}"
)

if [[ "${RESUME_LATEST}" == "1" ]]; then
  command+=(--resume-latest)
fi

if [[ "${EXECUTE}" != "1" ]]; then
  printf 'DRY_RUN: no training or files were created.\n'
  printf 'Set EXECUTE=1 and RUN_ROOT only after canary acceptance.\n'
  printf 'Command:'
  printf ' %q' "${command[@]}"
  printf ' --execute\n'
  exit 0
fi

if [[ -z "${RUN_ROOT}" ]]; then
  printf 'BLOCKED: RUN_ROOT is required for resumable training.\n' >&2
  exit 2
fi

exec "${command[@]}" --execute
