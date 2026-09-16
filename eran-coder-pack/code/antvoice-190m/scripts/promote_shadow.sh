#!/usr/bin/env bash
set -euo pipefail

RUN_ROOT="${RUN_ROOT:-}"
EVALUATION_REPORT="${EVALUATION_REPORT:-}"
EXECUTE="${EXECUTE:-0}"

command=(
  python -m antvoice.promote
  --run-root "${RUN_ROOT:-<required-run-root>}"
  --evaluation-report "${EVALUATION_REPORT:-<required-evaluation-report>}"
)

if [[ "${EXECUTE}" != "1" ]]; then
  printf 'DRY_RUN: no active release was created or selected.\n'
  printf 'Command:'
  printf ' %q' "${command[@]}"
  printf '\n'
  exit 0
fi

if [[ -z "${RUN_ROOT}" || -z "${EVALUATION_REPORT}" ]]; then
  printf 'BLOCKED: RUN_ROOT and EVALUATION_REPORT are required.\n' >&2
  exit 2
fi

exec "${command[@]}" --execute
