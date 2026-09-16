# -*- coding: utf-8 -*-
"""PROOF TZ-10 — a stroke behind the camera is never handed the earliest beat

Run it against the code on disk:      python proof_TZ-10.py
Run it against the pre-fix backup:    python proof_TZ-10.py <dir-with-the-old-modules>
It must FAIL on the old code and PASS on the new. That is the whole point of it.
"""
import os
import sys
import warnings

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import numpy as np


def main():
    import anatomy
    depth = np.array([1.0, 2.0, np.inf, np.inf])
    tile = np.array([0, 1, -1, -1])
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        beats = anatomy._delays(depth, tile)
    casts = [x for x in w if "invalid value encountered in cast" in str(x.message)]
    assert not casts, (
        "np.inf is still being cast to int64 (INT64_MIN) on every real frame: "
        f"{[str(x.message) for x in casts]}")
    assert beats[2] != 1 and beats[3] != 1, (
        f"an off-screen stroke was handed beat {beats[2]} — the EARLIEST slot. "
        f"'farther is never earlier' was being upheld by an unrelated guard.")
    assert beats[2] < 0 and beats[3] < 0, beats
    assert beats[0] >= 1 and beats[1] >= 1, beats

    # and the empty case refuses by NAME, not with a bare numpy error
    from stage import Camera
    n = 12
    pts = np.zeros((n, 3))
    pts[:, 2] = -50.0                       # every stroke behind the eye
    s = anatomy.Strokes(point=pts, normal=np.tile([0.0, 1.0, 0.0], (n, 1)),
                        rgb=np.full((n, 3), 0.5), radius=np.full(n, 0.02))
    cam = Camera(eye=np.array([0.0, 0.0, 5.0]), target=np.array([0.0, 0.0, 6.0]),
                 width=32, height=24)
    try:
        anatomy.weave_for(s, cam, tiles=4)
    except ValueError as e:
        assert "in front of this camera" in str(e), (
            f"the refusal is not named: {e!r}")
    else:
        raise AssertionError("weave_for accepted a camera with nothing in front of it")
    print(f"PASS  {ROOT}")
    print(f"      depth [1, 2, inf, inf] -> beats {list(beats)}  (no cast warning)")
    print("      weave_for refuses an empty view by name")


if __name__ == "__main__":
    try:
        main()
    except BaseException as e:                                    # noqa: BLE001
        print(f"FAIL  {ROOT}\n      {type(e).__name__}: {e}")
        sys.exit(1)
    sys.exit(0)
