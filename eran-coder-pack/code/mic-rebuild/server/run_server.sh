#!/usr/bin/env bash
# KESHEV STT server launcher (eran1) — K10.
# Bakes the K2 verdict's runtime requirement (~/keshev-spike/README-K2-VERDICT.md):
# the source-built CUDA CTranslate2 and the pip-wheel cuDNN 9 must BOTH be on
# LD_LIBRARY_PATH or ctranslate2 falls back to the CPU-only PyPI stub / fails to import.
set -euo pipefail

KESHEV_HOME="$(cd "$(dirname "$0")" && pwd)"
SPIKE="$HOME/keshev-spike"
VENV="$SPIKE/venv"

export LD_LIBRARY_PATH="$SPIKE/ct2-install/lib:$VENV/lib/python3.12/site-packages/nvidia/cudnn/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export PYTHONUNBUFFERED=1

exec "$VENV/bin/python" -u "$KESHEV_HOME/stt_server.py" --config "$KESHEV_HOME/server.json"
