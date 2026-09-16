# -*- coding: utf-8 -*-
"""PROOF TZ-15 — a decimation that misses its budget says so

Run it against the code on disk:      python proof_TZ-15.py
Run it against the pre-fix backup:    python proof_TZ-15.py <dir-with-the-old-modules>
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
    import hero8k
    rng = np.random.default_rng(5)
    tris = rng.uniform(0.0, 1.0, (900, 3, 3))      # cannot be reduced below ~64 cells
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            out, converged = hero8k.decimate(tris, target=10, return_converged=True)
    except TypeError as e:
        raise AssertionError(
            f"decimate cannot say whether it hit its budget: {e}. It returns "
            f"whatever `best` last held after 30 fruitless steps, silently, and "
            f"night.py paints it as if it were the requested budget.")
    assert converged is False, (
        f"decimate claims it converged while returning {len(out)} faces against a "
        f"target of 10")
    assert "did NOT hit the budget" in buf.getvalue(), buf.getvalue()
    ok, c_ok = hero8k.decimate(tris, target=len(tris) + 1, return_converged=True)
    assert c_ok is True
    print(f"PASS  {ROOT}")
    print(f"      target 10, got {len(out)} faces, converged={converged}")
    print("      " + buf.getvalue().strip())


if __name__ == "__main__":
    try:
        main()
    except BaseException as e:                                    # noqa: BLE001
        print(f"FAIL  {ROOT}\n      {type(e).__name__}: {e}")
        sys.exit(1)
    sys.exit(0)
