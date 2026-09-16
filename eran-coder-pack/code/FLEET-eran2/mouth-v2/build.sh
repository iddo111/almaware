#!/bin/sh
# build.sh -- build the MOUTH v2 fast C twin on eran2 (aarch64, gcc).
#
# -ffp-contract=off is REQUIRED: fused multiply-adds change bits and the
# parity gate (validate/v_parity.py) is a bit-level diff against the
# pure-numpy reference. NO -ffast-math, ever, for the same reason.
set -e
cd "$(dirname "$0")"
gcc -O2 -shared -fPIC -ffp-contract=off -fno-fast-math \
    -o libvoc_eran.so voc_eran.c -lm
echo "built libvoc_eran.so:"
ls -la libvoc_eran.so
