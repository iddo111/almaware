# -*- coding: utf-8 -*-
"""
> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

THE RULER DID NOT MOVE. Three ways of proving it, not one.

Every fidelity number TZELEM has ever published is an MSE against
`tzelem.stage.Stage.shade`. A sharpening pass that quietly edited that function
would raise every score and mean nothing, so this file refuses to let that happen
silently:

  1. SOURCE  - the exact bytes of `Stage.shade` and `Stage.gbuffer`, hashed.
  2. NUMBERS - `ShadedStage` with every strength set to zero must reproduce
               `Stage`'s image to the last bit, on the same camera.
  3. GIT     - `stage.py` must have no uncommitted modification.

Run it before and after any change to the occlusion path.
"""
from __future__ import annotations

import hashlib
import inspect
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")

import canvas                                                # noqa: E402
import occlusion                                            # noqa: E402
import stage as S                                           # noqa: E402

# Recorded 2026-09-06 from the working tree, and cross-checked against the copy in
# git HEAD (`git show HEAD:...stage.py`) so this is the committed ruler, not a
# hash of whatever happened to be on disk when the occlusion work began.
EXPECTED = {
    "Stage.shade": "2ee51c66396f8300",
    "Stage.gbuffer": "6cd34e73af85f531",
}


def painter_audit() -> int:
    """TZ-4: DID THE PAINTER MOVE UNDER THE STORED NUMBERS?

    `freeze.py` pinned the RULER and did its job -- when gate 1 was re-run on
    2026-09-06 the two numbers that never pass through `canvas.render`, BLANK
    (0.057028126) and valid_px (116279), reproduced to the last digit. But NOTHING
    pinned the PAINTER, and canvas.py had moved +511/-240 uncommitted lines, so every
    stroke-derived number in every stored gate JSON was made by code that no longer
    exists (TZELEM fidelity 0.025025459 -> 0.022898981, -8.5%).

    The painter is SUPPOSED to change -- it is the thing under development. What is
    not allowed is a stored number that cannot name the painter that made it. So every
    gate now writes `canvas.source_hashes()` into its result, and this walks the
    results and says which ones are stale.
    """
    import json
    now = canvas.source_hashes()
    print("  PAINTER   " + "  ".join(f"{k}={v}" for k, v in sorted(now.items())))
    stale = 0
    for d in (os.path.join(HERE, "out"), os.path.join(HERE, "out-night"),
              r"D:\CLAUDE\oneroom\out"):
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            if not f.endswith(".json"):
                continue
            try:
                rec = json.load(open(os.path.join(d, f), encoding="utf-8"))
            except Exception:                                  # noqa: BLE001
                continue
            found = []

            def walk(o):
                if isinstance(o, dict):
                    if "painter" in o and isinstance(o["painter"], dict):
                        found.append(o["painter"])
                    for v in o.values():
                        walk(v)
                elif isinstance(o, list):
                    for v in o:
                        walk(v)

            walk(rec)
            if not found:
                print(f"  UNSIGNED {os.path.basename(d)}/{f}"
                      f"   — predates canvas.source_hashes(); its numbers cannot be "
                      f"tied to a painter")
                continue
            bad = [p for p in found if p != now]
            if bad:
                stale += 1
                print(f"  STALE    {os.path.basename(d)}/{f}"
                      f"   — painted by a canvas.py that is not the one on disk")
            else:
                print(f"  OK       {os.path.basename(d)}/{f}")
    return stale


def h(fn) -> str:
    return hashlib.sha256(inspect.getsource(fn).encode("utf-8")).hexdigest()[:16]


def main() -> int:
    bad = 0
    got = {"Stage.shade": h(S.Stage.shade), "Stage.gbuffer": h(S.Stage.gbuffer)}
    for k, v in got.items():
        known = EXPECTED.get(k)
        mark = "RECORD" if known in (None, "") else ("OK" if known == v else "CHANGED")
        if mark == "CHANGED":
            bad += 1
        print(f"  {mark:<8} {k:<16} {v}")

    # 2. the numbers, on the stage the ruler was born on
    cam = S.orbit(0.0, 320, 240)
    plain = S.Stage()
    null = occlusion.ShadedStage(shadow_strength=0.0, ao_strength=0.0,
                                 texture_strength=0.0)
    a = plain.shade(plain.gbuffer(cam))
    b = null.shade(null.gbuffer(cam))
    same = np.array_equal(a, b)
    print(f"  {'OK' if same else 'DIFFERS':<8} ShadedStage(all strengths 0) == Stage"
          f"   max|diff| {np.abs(a - b).max():.3e}")
    if not same:
        bad += 1

    # 3. the file itself
    try:
        p = os.path.abspath(S.__file__)
        r = subprocess.run(["git", "status", "--porcelain", "--", p],
                           cwd=os.path.dirname(p), capture_output=True, text=True,
                           timeout=30)
        dirty = r.stdout.strip()
        print(f"  {'OK' if not dirty else 'DIRTY':<8} git status stage.py"
              f"   {dirty or '(clean)'}")
        if dirty:
            bad += 1
    except Exception as e:
        print(f"  SKIP     git status unavailable: {e}")

    # TZ-4: the ruler is pinned; the PAINTER only has to be NAMED. A stale stored
    # number is reported, not counted as a frozen-ruler failure -- they are different
    # sins and collapsing them would hide the one that matters.
    stale = painter_audit()
    if stale:
        print(f"  {stale} stored result(s) were painted by a different canvas.py — "
              f"re-run those gates before quoting them")
    print("FROZEN" if not bad else f"{bad} PROBLEM(S) -- the ruler moved")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
