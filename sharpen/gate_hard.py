# -*- coding: utf-8 -*-
"""
> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

THE GATE ON THE HARD COMPOSITOR - the test the existing gate cannot run.

`godot_gate.one_pair` calls `canvas.render` with its defaults, so every gate number
TZELEM has ever reported is a number about the SOFT path. The fix found tonight IS
the compositor, so the gate as written cannot say whether the fix costs anything,
and a sharpening that quietly destroys coherence would be worse than the blur.

There is a real reason to worry. Soft blending is a natural temporal smoother: when
the camera moves a little, the alpha weights shift a little and the pixel changes a
little. On the hard path a pixel belongs to exactly ONE stroke, and at a boundary
that ownership can FLIP between frames — which is the classic way a hard renderer
buys sharpness and pays in shimmer. This file measures that, on the same four
contestants, with `ruler._resid` and `ruler._mse` imported verbatim so a difference
cannot be a difference in the formula.

The only line that differs from `godot_gate.one_pair` is `soft`.
"""
from __future__ import annotations

import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")

import canvas                                             # noqa: E402
import room                                               # noqa: E402
from anatomy import scatter                               # noqa: E402
from godot_gate import verdict                            # noqa: E402
from ruler import _mse, _resid                            # noqa: E402
from sharpness import lapvar_array                        # noqa: E402

OUT = os.path.join(HERE, "gate-out")
WIDTH, HEIGHT = 1920, 1080
STROKES, SIZE, SEED, POSES = 30_000, 0.006, 5, 5


def one_pair(stage, cam_a, cam_b, n_strokes, seed, size, soft=True):
    """`godot_gate.one_pair`, with `soft` threaded through to every render."""
    kw = {"style": "painterly", "soft": soft}
    truth_b = stage.shade(stage.gbuffer(cam_b))
    flow = stage.flow(cam_a, cam_b)

    world = scatter(stage, cam_a, n=n_strokes, seed=seed, size=size)
    tz_a = canvas.render(stage, cam_a, world, **kw)
    tz_b = canvas.render(stage, cam_b, world, **kw)
    fl_a = canvas.render(stage, cam_a,
                         scatter(stage, cam_a, n=n_strokes, seed=seed, size=size),
                         **kw)
    fl_b = canvas.render(stage, cam_b,
                         scatter(stage, cam_b, n=n_strokes, seed=seed + 1,
                                 size=size), **kw)

    ce_b, seen = canvas.warp(tz_a, flow)
    w_tz, _ = canvas.warp(tz_a, flow)
    w_fl, _ = canvas.warp(fl_a, flow)
    m = flow["valid"] & seen
    m3 = np.repeat(m[..., None], 3, axis=2)
    h, w = truth_b.shape[:2]
    blank = np.tile(truth_b.reshape(-1, 3).mean(axis=0), (h, w, 1))
    return {
        "valid_px": int(m.sum()), "total_px": int(m.size),
        "coherence": {"FLOOR_repaint_every_frame": _resid(fl_b, w_fl, m3),
                      "TZELEM_world_anchored": _resid(tz_b, w_tz, m3),
                      "CEILING_warp_only": _resid(ce_b, w_tz, m3)},
        "fidelity_mse": {"BLANK_best_flat_colour": _mse(blank, truth_b),
                         "FLOOR_repaint_every_frame": _mse(fl_b, truth_b),
                         "TZELEM_world_anchored": _mse(tz_b, truth_b),
                         "CEILING_warp_only": _mse(ce_b, truth_b)},
        "lapvar_tzelem_b": round(lapvar_array(tz_b), 1),
        "lapvar_truth_b": round(lapvar_array(truth_b), 1),
    }


def run(state, soft):
    stage = room.plain_stage(state)
    cams = room.rail_poses(POSES, WIDTH, HEIGHT)
    label = "SOFT" if soft else "HARD"
    t0, pairs = time.time(), []
    for i in range(len(cams) - 1):
        r = one_pair(stage, cams[i], cams[i + 1], STROKES, SEED + i, SIZE, soft)
        pairs.append(r)
        print(f"  [{label}/{state}] {i}->{i+1} floor "
              f"{r['coherence']['FLOOR_repaint_every_frame']:.5f}  TZELEM "
              f"{r['coherence']['TZELEM_world_anchored']:.5f}  "
              f"lapvar {r['lapvar_tzelem_b']:.1f}  {time.time()-t0:.0f}s",
              flush=True)

    def agg(f, k):
        return float(np.mean([p[f][k] for p in pairs]))
    co = {k: agg("coherence", k) for k in pairs[0]["coherence"]}
    fi = {k: agg("fidelity_mse", k) for k in pairs[0]["fidelity_mse"]}
    ok, lines = verdict(co, fi)
    for l in lines:
        print(f"  [{label}/{state}] {l}", flush=True)
    return {"label": label, "state": state, "coherence": co, "fidelity_mse": fi,
            "pass": ok, "verdict": lines,
            "lapvar_tzelem": float(np.mean([p["lapvar_tzelem_b"] for p in pairs])),
            "steadier_than_floor": co["FLOOR_repaint_every_frame"]
            / max(co["TZELEM_world_anchored"], 1e-12),
            "better_than_blank": fi["BLANK_best_flat_colour"]
            / max(fi["TZELEM_world_anchored"], 1e-12),
            "seconds": round(time.time() - t0, 1)}


def main():
    rec = {"when": time.strftime("%Y-%m-%dT%H:%M:%S"), "runs": []}
    for state in ("dark", "lit"):
        for soft in (True, False):
            rec["runs"].append(run(state, soft))
    os.makedirs(OUT, exist_ok=True)
    p = os.path.join(OUT, "gate-hard.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(rec, f, indent=2, ensure_ascii=False)
    print("\nwrote " + p, flush=True)
    for r in rec["runs"]:
        print(f"  {r['label']:<5}{r['state']:<5} pass={r['pass']}  steadier "
              f"x{r['steadier_than_floor']:.2f}  vs blank "
              f"x{r['better_than_blank']:.2f}  lapvar {r['lapvar_tzelem']:.1f}",
              flush=True)


if __name__ == "__main__":
    main()
