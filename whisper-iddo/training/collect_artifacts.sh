#!/usr/bin/env bash
# Pull the small artifacts back to the PC. Checkpoints (3.1 GB each) stay on
# eran3; only histories, eval tables and hypothesis dumps come back.
set -eu
DEST="D:/CLAUDE/whisper-iddo/results"
mkdir -p "$DEST"
scp -o BatchMode=yes -r \
    eran3:'~/whisper-iddo/runs/ft20/history.json' "$DEST/ft20_history.json" || true
scp -o BatchMode=yes -r \
    eran3:'~/whisper-iddo/runs/ft20/summary.json' "$DEST/ft20_summary.json" || true
scp -o BatchMode=yes -r \
    eran3:'~/whisper-iddo/runs/ft50/history.json' "$DEST/ft50_history.json" || true
scp -o BatchMode=yes -r \
    eran3:'~/whisper-iddo/runs/ft50/summary.json' "$DEST/ft50_summary.json" || true
scp -o BatchMode=yes -r eran3:'~/whisper-iddo/results/*' "$DEST/" || true
scp -o BatchMode=yes -r eran3:'~/whisper-iddo/hyps' "$DEST/hyps" || true
echo "artifacts in $DEST"
