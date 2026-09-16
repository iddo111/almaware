#!/usr/bin/env bash
# WINSTON organ — stage 2 on eran4: the pin tests + one real gallery sitting.
#
# > BROKEN WINDOWS LAW: test the REAL output.
#
# Mirrors the organ + the alma substrate to eran4, runs the eran4-only pin
# tests (numpy body == winston.py torch body), then one sitting on a real
# photo with propose/behold/hear_back and a 1024px render for Iddo.
# GPU is busy with training — everything here is frozen forwards, seconds.
# eran3 is the SOURCE of forever/painter.pt only (scp one-way, service
# untouched). eran1 gets nothing, ever.
#
# Usage (from the PC, Git Bash):   bash run_eran4.sh [photo-on-eran4.jpg]
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
DEST=eran4
ROOT='~/eran-holobrain'

echo "== mirror the organ + alma substrate to $DEST =="
ssh $DEST "mkdir -p $ROOT/winston/tests $ROOT/alma-language $ROOT/winston/state $ROOT/winston/weaves"
scp -q "$HERE"/*.py "$DEST:$ROOT/winston/"
scp -q "$HERE"/tests/*.py "$DEST:$ROOT/winston/tests/"
scp -q "$HERE"/state/alef-row.npz "$DEST:$ROOT/winston/state/" 2>/dev/null || true
scp -qr /d/CLAUDE/alma-language/alma "$DEST:$ROOT/alma-language/"
scp -q /d/CLAUDE/eran-brain/holobrain/ear-human.npz "$DEST:$ROOT/" 2>/dev/null || true

echo "== fetch the frozen painter from eran3, RELAYED through the PC =="
echo "   (eran4 cannot reach eran3 directly — no fabric, eran3 is behind eran2's NAT)"
TMP="$(mktemp -d)"
if scp -q eran3:~/winston-family/forever/painter.pt "$TMP/painter.pt" 2>/dev/null \
   || scp -q eran3:~/winston-family/out/fam01_IMG_2418/painter.pt "$TMP/painter.pt" 2>/dev/null; then
  scp -q "$TMP/painter.pt" "$DEST:$ROOT/painter.pt"
else
  echo '  (no painter.pt reachable on eran3 - propose will be skipped)'
fi
rm -rf "$TMP"

echo "== pin tests (15, 16) — CPU only, the GPU belongs to training =="
ssh $DEST "cd $ROOT/winston && \
  WINSTON_ERAN4=1 \
  WINSTON_SRC=\$HOME/eran-holobrain/winston-src \
  EYE_SRC=\$HOME/eran-eye \
  WINSTON_PAINTER=\$HOME/eran-holobrain/painter.pt \
  ERAN_EYE=\$HOME/eran-eye/state/eye.pt \
  EAR_NPZ=\$HOME/eran-holobrain/ear-human.npz \
  CUDA_VISIBLE_DEVICES='' \
  PYTHONIOENCODING=utf-8 PYTHONPATH=$ROOT/alma-language:$ROOT/winston \
  python3 -m pytest tests/test_eran4_pin.py -v" || echo "PIN TESTS DID NOT ALL PASS - read the output above, do not trust the numpy body until they do"

PHOTO="${1:-}"
if [ -n "$PHOTO" ]; then
  echo "== one real sitting: $PHOTO at 128px, gaze on, 1024px render =="
  ssh $DEST "cd $ROOT/winston && PYTHONIOENCODING=utf-8 \
    WINSTON_SRC=\$HOME/eran-holobrain/winston-src EYE_SRC=\$HOME/eran-eye \
    EAR_NPZ=\$HOME/eran-holobrain/ear-human.npz CUDA_VISIBLE_DEVICES='' \
    PYTHONPATH=$ROOT/alma-language:$ROOT/winston \
    python3 - <<'PY'
import os, sys
sys.path.insert(0, '.')
from easel import Easel
import gaze
e = Easel('$PHOTO', n_strokes=400, size=128, name='winston-eran4')
try:
    e.gaze = gaze.teach_gaze(e.atelier,
        os.path.expanduser('~/eran-holobrain/painter.pt'),
        os.path.expanduser('~/eran-eye/state/eye.pt'))
    e._schedule()
except Exception as ex:
    print('gaze unavailable, painting without it:', ex)
e.sitting()
gaze.render_big_png(e.atelier, 1024, 'weaves/eran4-1024.png')
print('-> weaves/eran4-1024.png')
PY"
  scp -q "$DEST:$ROOT/winston/weaves/eran4-1024.png" "$HERE/weaves/" && \
    echo "pulled weaves/eran4-1024.png back to the PC"
fi
echo "done."
