# -*- coding: utf-8 -*-
"""
> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

TZELEM'S GATE 1, RUN ON *THIS ROOM'S OWN CAMERA PATH*.

The three numbers on the deliverable page must be measured here, not quoted from
Rothschild Boulevard. So this file imports `godot_gate.one_pair` and
`godot_gate.verdict` **verbatim** — not a copy of them, the functions themselves —
and feeds them a stock `tzelem.stage.Stage` over `room.BOXES` and the five poses of
the rail the player actually walks. Everything downstream of that call is byte for
byte the code that produced the boulevard's 0.01387 / 0.06305 / 0.01984, including
`ruler._resid` and `ruler._mse`.

Settings are the boulevard's, deliberately, so the two runs can be read side by
side: 1920x1080, 30,000 strokes, size 0.006, four consecutive pose pairs.

THE ONE THING THAT IS NOT THE SAME, and it makes this test HARDER, not easier:
the boulevard's four poses came out of Godot and its `shade` was the engine's own
beauty pass. Here `shade` is `Stage.shade` — flat Lambert, untouched — so the
fidelity column is measured against a much flatter truth, and BLANK (the single
best flat colour) is a much stronger opponent than it was outdoors. If TZELEM
still beats a flat colour in a dim interior, that is worth more than beating one
against a sunlit boulevard.

Both light states are measured. `dark` is the room the player walks into.

BELOW_NORMAL, numpy only, nothing on the fleet.
"""
from __future__ import annotations

import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
_TZELEM = r"D:\CLAUDE\eran-brain\holobrain\tzelem"
for p in (_TZELEM, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

sys.stdout.reconfigure(encoding="utf-8")
for v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
          "NUMEXPR_NUM_THREADS"):
    os.environ[v] = "4"

import room                                                   # noqa: E402
import canvas                                                  # noqa: E402
import ruler                                                  # noqa: E402  the SAME bars
from godot_gate import one_pair, verdict                      # noqa: E402  the SAME gate

OUT = os.path.join(HERE, "out")
WIDTH, HEIGHT = 1920, 1080
STROKES, SIZE, SEED = 30_000, 0.006, 5
POSES = 5


def run(state: str, width=WIDTH, height=HEIGHT, save_images: bool = True) -> dict:
    t0 = time.time()
    stage = room.plain_stage(state)
    cams = room.rail_poses(POSES, width, height)
    print(f"[{state}] {len(cams)} poses on the player's rail at {width}x{height}",
          flush=True)

    pairs, keep = [], None
    for i in range(len(cams) - 1):
        a, b = cams[i], cams[i + 1]
        step = float(np.linalg.norm(np.asarray(b.eye) - np.asarray(a.eye)))
        r = one_pair(stage, a, b, STROKES, SEED + i, SIZE)
        imgs = r.pop("_images")
        if keep is None:
            keep = imgs
        r["step_m"] = round(step, 3)
        pairs.append(r)
        print(f"  [{state}] pose {i}->{i+1}  step {step:.3f} m  "
              f"floor {r['coherence']['FLOOR_repaint_every_frame']:.5f}  "
              f"TZELEM {r['coherence']['TZELEM_world_anchored']:.5f}  "
              f"valid {100 * r['valid_px'] / r['total_px']:.1f}%  "
              f"{time.time() - t0:.0f}s", flush=True)

    def agg(field, key):
        return float(np.mean([p[field][key] for p in pairs]))

    co = {k: agg("coherence", k) for k in pairs[0]["coherence"]}
    fi = {k: agg("fidelity_mse", k) for k in pairs[0]["fidelity_mse"]}
    # TZ-2 (2026-09-06): the fidelity tolerance is derived from THIS run's own FLOOR
    # spread, not hand-picked. TZ-3: `verdict` now uses ruler.COHERENCE_MARGIN, so this
    # track finally runs on gate 1's bar instead of one twice as loose.
    _ffl = np.array([p["fidelity_mse"]["FLOOR_repaint_every_frame"] for p in pairs],
                    dtype=float)
    k_fid = ruler.margin_from_spread(float(_ffl.mean()), float(_ffl.std()))
    ok, lines = verdict(co, fi, fidelity_margin=k_fid)
    for l in lines:
        print(f"  [{state}] {l}", flush=True)

    made = {}
    if save_images:
        os.makedirs(OUT, exist_ok=True)
        from PIL import Image
        for name, img in keep.items():
            p = os.path.join(OUT, f"gate-{state}-{name}.jpg")
            Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8)).save(
                p, quality=92, subsampling=0)
            made[name] = p
    del keep

    return {"state": state, "resolution": [width, height], "poses": len(cams),
            # TZ-4: a measurement must name its PAINTER as well as its input.
            "painter": canvas.source_hashes(), "fidelity_margin": k_fid,
            "strokes": STROKES, "size": SIZE, "rail_m": round(
                float(np.linalg.norm(room.RAIL_B - room.RAIL_A)), 3),
            "pairs": pairs, "coherence": co, "fidelity_mse": fi,
            "pass": ok, "verdict": lines,
            "steadier_than_floor": co["FLOOR_repaint_every_frame"] /
                                   max(co["TZELEM_world_anchored"], 1e-12),
            "better_than_blank": fi["BLANK_best_flat_colour"] /
                                 max(fi["TZELEM_world_anchored"], 1e-12),
            "seconds": round(time.time() - t0, 1), "made": made}


def main() -> None:
    try:
        import psutil
        psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
        print("priority BELOW_NORMAL", flush=True)
    except Exception as e:
        print(f"could not lower priority: {e}", flush=True)

    states = sys.argv[1:] or ["dark", "lit"]
    rec = {"when": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "room": "D:/CLAUDE/oneroom/room.py — the workshop at night",
           "boxes": len(room.BOXES),
           "gate": "godot_gate.one_pair + godot_gate.verdict, imported verbatim",
           "boulevard_for_reference": {
               "coherence_floor": 0.06305337175323517,
               "coherence_tzelem": 0.013867577991897658,
               "fidelity_blank": 0.06555384068841175,
               "fidelity_tzelem": 0.01983569156894489},
           "runs": {}}
    for s in states:
        rec["runs"][s] = run(s)
    os.makedirs(OUT, exist_ok=True)
    p = os.path.join(OUT, "gate.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(rec, f, indent=2, ensure_ascii=False)
    print("wrote " + p, flush=True)


if __name__ == "__main__":
    main()
