# -*- coding: utf-8 -*-
"""test_determinism.py -- features() twice in-process AND across two
processes on 3 clips -> bit-identical (sha256 over the raw float64 bytes)."""
import hashlib
import json
import os
import subprocess
import sys

import _common
from ear3 import features as F

CLIPS = ["ah_t06_1.wav", "abba_t06_1.wav", "ma_t06_1.wav"]

_CHILD = r"""
import hashlib, json, sys, os
sys.path.insert(0, {root!r})
from ear3 import features as F
out = {{}}
for name in {clips!r}:
    v = F.features_from_wav(os.path.join({corpus!r}, name))
    out[name] = hashlib.sha256(v.tobytes()).hexdigest()
print(json.dumps(out))
"""


def main():
    parent = {}
    for name in CLIPS:
        p = os.path.join(_common.CORPUS, name)
        v1 = F.features_from_wav(p)
        v2 = F.features_from_wav(p)
        h1 = hashlib.sha256(v1.tobytes()).hexdigest()
        h2 = hashlib.sha256(v2.tobytes()).hexdigest()
        assert h1 == h2, f"{name}: in-process repeat differs"
        parent[name] = h1
        print(f"in-process  {name:18s} {h1[:16]} == repeat: OK")

    code = _CHILD.format(root=_common.ROOT, clips=CLIPS,
                         corpus=_common.CORPUS)
    child = json.loads(subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True,
        check=True).stdout.strip().splitlines()[-1])
    for name in CLIPS:
        flag = "OK" if child[name] == parent[name] else "MISMATCH"
        print(f"cross-proc  {name:18s} {child[name][:16]} vs parent: {flag}")
        assert child[name] == parent[name], f"{name}: cross-process differs"
    print("DETERMINISM: bit-identical in-process and across processes")


if __name__ == "__main__":
    main()
