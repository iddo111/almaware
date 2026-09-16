#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-/opt/antvoice-190m}"
MANIFEST="${MANIFEST:-/data/antvoice/manifest.jsonl}"
AUDIO_ROOT="${AUDIO_ROOT:-/data/antvoice/audio}"
RUN_ROOT="${RUN_ROOT:-}"
EXECUTE="${EXECUTE:-0}"

command=(
  python -m antvoice.canary_train
  --model-config "${PROJECT_DIR}/configs/tiny.json"
  --run-config "${PROJECT_DIR}/configs/real_audio_canary.json"
  --manifest "${MANIFEST}"
  --audio-root "${AUDIO_ROOT}"
  --run-root "${RUN_ROOT:-<required-new-run-root>}"
)

if [[ "${EXECUTE}" != "1" ]]; then
  printf 'DRY_RUN: no training or files were created.\n'
  printf 'Set EXECUTE=1 and a new RUN_ROOT after validating the manifest.\n'
  printf 'Command:'
  printf ' %q' "${command[@]}"
  printf ' --execute\n'
  exit 0
fi

if [[ -z "${RUN_ROOT}" ]]; then
  printf 'BLOCKED: RUN_ROOT is required and must be new for each canary.\n' >&2
  exit 2
fi

exec "${command[@]}" --execute
