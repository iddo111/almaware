# -*- coding: utf-8 -*-
"""PROOF TZ-9 — a planter that gets less brush than it asked for says so

Run it against the code on disk:      python proof_TZ-9.py
Run it against the pre-fix backup:    python proof_TZ-9.py <dir-with-the-old-modules>
It must FAIL on the old code and PASS on the new. That is the whole point of it.
"""
import os
import sys
import warnings

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import io
import contextlib

import numpy as np


def main():
    import anatomy
    from stage import Stage, orbit
    st = Stage()
    cam = orbit(0.0, 24, 18)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        s = anatomy.scatter(st, cam, n=100_000, seed=7)
    said = buf.getvalue()
    assert getattr(s, "asked", None) == 100_000, (
        f"the strokes do not carry what was ASKED for (asked={getattr(s,'asked',None)}"
        f", planted={len(s)}). A selector that can quietly return almost nothing is "
        f"the ERAN-starvation shape.")
    assert len(s) < 100_000
    assert "planted" in said and "100000" in said.replace(",", ""), (
        f"scatter planted {len(s)} of 100000 strokes and said nothing: {said!r}")
    print(f"PASS  {ROOT}")
    print(f"      asked {s.asked}, planted {len(s)} — and it said so:")
    print("      " + said.strip())


if __name__ == "__main__":
    try:
        main()
    except BaseException as e:                                    # noqa: BLE001
        print(f"FAIL  {ROOT}\n      {type(e).__name__}: {e}")
        sys.exit(1)
    sys.exit(0)
