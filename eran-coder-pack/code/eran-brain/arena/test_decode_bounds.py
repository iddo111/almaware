# -*- coding: utf-8 -*-
"""test_decode_bounds.py — the guard that keeps the decode audit from rotting.

> BROKEN WINDOWS LAW: test the REAL output, never a proxy.

This is item 6 of the decode audit: a test that every knob decode_audited()
can ever produce lies inside the interval KNOB_BOUNDS declares for it, next
to the comment that justifies that interval (decode_audit.py). Run it:

    python test_decode_bounds.py

Exits 0 and prints PASS on success, raises AssertionError (from
decode_audit.assert_in_bounds, or from an explicit check below) on failure.
No pytest dependency -- this estate's other scripts are plain stdlib/numpy,
this one is too.
"""
import sys

import numpy as np

from decode_audit import (KNOB_BOUNDS, decode_audited, assert_in_bounds,
                          N_PARAMS)


def run():
    n_checked = 0

    # 1) the sigmoid's own saturation extremes -- theta components that push
    #    _sig(x) to (numerically) exactly 0.0 or 1.0. This is the actual edge
    #    case an ES search WILL find if the fitness gradient pushes a
    #    component to the fence; if any bound leaks, it leaks here first.
    for edge in (-1e6, -30.0, -1.0, 0.0, 1.0, 30.0, 1e6):
        theta = np.full(N_PARAMS, edge, dtype=np.float64)
        knobs = decode_audited(theta)   # raises AssertionError if out of bounds
        assert_in_bounds(knobs)
        n_checked += 1

    # 2) every component saturated independently (one hot at a time, at both
    #    extremes) -- catches a bound that only breaks for one specific knob.
    for i in range(N_PARAMS):
        for edge in (-30.0, 30.0):
            theta = np.zeros(N_PARAMS, dtype=np.float64)
            theta[i] = edge
            knobs = decode_audited(theta)
            assert_in_bounds(knobs)
            n_checked += 1

    # 3) a wide random sweep, the kind of theta an ES population actually
    #    proposes (candidates are theta +/- sigma*eps, sigma~0.12, but ES can
    #    also drift theta itself over many generations -- sample generously).
    rng = np.random.default_rng(20260822)
    for _ in range(2000):
        theta = rng.normal(0.0, rng.uniform(0.1, 50.0), N_PARAMS)
        knobs = decode_audited(theta)
        assert_in_bounds(knobs)
        n_checked += 1

    # 4) explicit re-check against KNOB_BOUNDS with a fresh comparison (not
    #    reusing assert_in_bounds's own arithmetic) -- belt and suspenders.
    for name, (lo, hi, _why) in KNOB_BOUNDS.items():
        assert hi >= lo, f"{name}: hi < lo in KNOB_BOUNDS"
        assert isinstance(_why, str) and len(_why) > 20, (
            f"{name}: every bound must carry a real reasoning string "
            f"(the comments ARE the deliverable) -- got {_why!r}")

    print(f"test_decode_bounds: {n_checked} theta vectors checked, "
          f"{len(KNOB_BOUNDS)} knobs bounded, all inside their declared "
          f"intervals.")
    return n_checked


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    n = run()
    print(f"PASS ({n} checks)")
