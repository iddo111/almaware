# -*- coding: utf-8 -*-
"""
> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

THE GATE, RUN ON THE SHARPENED ROOM. Same ruler, harder room.

`oneroom/gate.py` measures TZELEM on a stock `tzelem.stage.Stage` over the
workshop's boxes: flat Lambert, no shadow, no texture. This file is that file with
ONE line different - the stage is `occlusion.ShadedStage`, which bakes contact
shadow, ambient occlusion and surface texture into the g-buffer's ALBEDO and
inherits `Stage.shade` untouched.

Why that is the honest way to test a sharpening pass:

  * `Stage.shade` is the ruler. It is not modified, not wrapped, not bypassed. The
    fidelity column is still an MSE against the same function, evaluated on a
    richer albedo. Verified by `freeze.py`, which hashes its source.
  * the PAINTER's strokes come from `anatomy.scatter`, which reads
    `stage.shade(gbuffer)`. So the truth and the painting receive the SAME
    darkening from the SAME line. Neither side is given an advantage.
  * a textured, shadowed room is a HARDER room to paint than a flat one: BLANK,
    the single best flat colour, has more variance to fail to explain, but so does
    TZELEM. If the coherence ratio holds up here it holds up for real.

`one_pair` and `verdict` are imported from `godot_gate` verbatim, exactly as
`oneroom/gate.py` imports them, so a difference in the numbers cannot be a
difference in the formula.
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

import occlusion                                          # noqa: E402
import room                                               # noqa: E402
from godot_gate import one_pair, verdict                  # noqa: E402  the SAME gate
from sharpness import lapvar_array, lapvar_norm_array     # noqa: E402
from stage import Box                                     # noqa: E402
from workshop import NON_BLOCKING, TUBE_POS, WINDOW_POS   # noqa: E402

OUT = os.path.join(HERE, "gate-out")
WIDTH, HEIGHT = 1920, 1080
STROKES, SIZE, SEED = 30_000, 0.006, 5
POSES = 5


def boxes():
    return [Box(np.array(b["lo"]), np.array(b["hi"]), np.array(room.MAT[b["mat"]]))
            for b in room.BOXES]


def sharp_stage(state: str, **kw):
    s = room.STATES[state]
    blockers = np.array([b["kind"] not in NON_BLOCKING for b in room.BOXES])
    lp = WINDOW_POS if state == "dark" else TUBE_POS[0]
    return occlusion.ShadedStage(
        boxes(), ground_albedo=(0.40, 0.395, 0.38),
        light_dir=s["light_dir"], ambient=s["ambient"],
        light_pos=lp, blockers=blockers, softness=0.34, shadow_samples=3,
        ao_rays=kw.pop("ao_rays", 8), ao_reach=0.55,
        ao_strength=kw.pop("ao_strength", 0.80),
        shadow_strength=kw.pop("shadow_strength", 0.70),
        texture_strength=kw.pop("texture_strength", 0.30), **kw)


def run(state: str, stage, label: str, save: bool) -> dict:
    t0 = time.time()
    cams = room.rail_poses(POSES, WIDTH, HEIGHT)
    pairs, keep = [], None
    for i in range(len(cams) - 1):
        a, b = cams[i], cams[i + 1]
        r = one_pair(stage, a, b, STROKES, SEED + i, SIZE)
        imgs = r.pop("_images")
        if keep is None:
            keep = imgs
        r["step_m"] = round(float(np.linalg.norm(np.asarray(b.eye)
                                                 - np.asarray(a.eye))), 3)
        pairs.append(r)
        print(f"  [{label}/{state}] {i}->{i+1} floor "
              f"{r['coherence']['FLOOR_repaint_every_frame']:.5f}  TZELEM "
              f"{r['coherence']['TZELEM_world_anchored']:.5f}  "
              f"valid {100*r['valid_px']/r['total_px']:.1f}%  "
              f"{time.time()-t0:.0f}s", flush=True)

    def agg(f, k):
        return float(np.mean([p[f][k] for p in pairs]))
    co = {k: agg("coherence", k) for k in pairs[0]["coherence"]}
    fi = {k: agg("fidelity_mse", k) for k in pairs[0]["fidelity_mse"]}
    ok, lines = verdict(co, fi)
    for l in lines:
        print(f"  [{label}/{state}] {l}", flush=True)

    sharp = {k: {"lapvar": round(lapvar_array(v), 1),
                 "lapvar_norm": round(lapvar_norm_array(v), 1)}
             for k, v in keep.items()}
    print(f"  [{label}/{state}] lapvar  truth {sharp['truth_b']['lapvar']:.1f}  "
          f"TZELEM {sharp['tz_b']['lapvar']:.1f}  (norm "
          f"{sharp['tz_b']['lapvar_norm']:.1f})", flush=True)

    made = {}
    if save:
        os.makedirs(OUT, exist_ok=True)
        from PIL import Image
        for name, img in keep.items():
            p = os.path.join(OUT, f"gate-{label}-{state}-{name}.jpg")
            Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8)).save(
                p, quality=92, subsampling=0)
            made[name] = p
    del keep
    return {"label": label, "state": state, "coherence": co, "fidelity_mse": fi,
            "pass": ok, "verdict": lines, "sharpness": sharp,
            "steadier_than_floor": co["FLOOR_repaint_every_frame"]
            / max(co["TZELEM_world_anchored"], 1e-12),
            "better_than_blank": fi["BLANK_best_flat_colour"]
            / max(fi["TZELEM_world_anchored"], 1e-12),
            "seconds": round(time.time() - t0, 1), "made": made}


def main() -> None:
    rec = {"when": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "settings": {"resolution": [WIDTH, HEIGHT], "strokes": STROKES,
                        "size": SIZE, "poses": POSES},
           "runs": []}
    for state in ("dark", "lit"):
        rec["runs"].append(run(state, room.plain_stage(state), "PLAIN", True))
        rec["runs"].append(run(state, sharp_stage(state), "SHARP", True))
    os.makedirs(OUT, exist_ok=True)
    p = os.path.join(OUT, "gate-sharp.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(rec, f, indent=2, ensure_ascii=False)
    print("\nwrote " + p, flush=True)
    for r in rec["runs"]:
        print(f"  {r['label']:<6}{r['state']:<5} pass={r['pass']}  "
              f"steadier x{r['steadier_than_floor']:.2f}  "
              f"vs blank x{r['better_than_blank']:.2f}  "
              f"lapvar {r['sharpness']['tz_b']['lapvar']:.1f}", flush=True)


if __name__ == "__main__":
    main()
