# -*- coding: utf-8 -*-
"""
> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

THE SWEEP. One scene, one camera, four knobs, and the price of each.

Iddo rejected the workshop for being blurred. Before changing anything it is worth
knowing which knob actually buys sharpness and what it costs, so this varies

    stroke RADIUS      (world metres of paint)
    stroke COUNT       (via the planter's dedupe voxel, and by thinning)
    RESOLUTION         (1280 -> 4096 on the long edge)
    the OCCLUSION pass (contact shadow + AO + texture, on or off)

and reports Laplacian variance, seconds and peak RSS for every cell, plus the
COVERAGE fraction - because a picture that got "sharper" by opening holes to the
background is not sharper, it is broken, and only the coverage column can say so.

Camera and scene are frozen: `room.rail_camera(0.30)`, the pose the published
still was made from, so every number here is comparable to the 126 he rejected.

BELOW_NORMAL, numpy only, nothing on the fleet.
"""
from __future__ import annotations

import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")

import workshop as W                                     # noqa: E402
from sharpness import lapvar_array, lapvar_norm_array    # noqa: E402

OUT = os.path.join(HERE, "sweep")
os.makedirs(OUT, exist_ok=True)
STATE = "dark"                    # the room the player actually walks into
T = 0.30
BASE_W, BASE_H = 1600, 900        # the published still's size
rows: list[dict] = []


def rss_mb() -> float:
    try:
        import psutil
        return psutil.Process().memory_info().rss / 1e6
    except Exception:
        return -1.0


def cell(tag: str, pt, nr, rgb, radius, w, h, state, save=None, **extra) -> dict:
    img, secs, cov = W.paint(pt, nr, rgb, radius, w, h, state, t=T)
    lv = lapvar_array(img)
    lvn = lapvar_norm_array(img)
    r = {"tag": tag, "state": state, "strokes": int(len(pt)),
         "radius_m": round(float(radius), 5), "width": w, "height": h,
         "lapvar": round(lv, 1), "lapvar_contrast_normalised": round(lvn, 1),
         "coverage": round(cov, 4),
         "render_s": round(secs, 1), "rss_mb": round(rss_mb(), 0)}
    r.update(extra)
    rows.append(r)
    print(f"  {tag:<34} {len(pt):>9,} r={radius:.4f} {w}x{h} "
          f"lapvar {lv:8.1f} (norm {lvn:8.1f})  cov {cov*100:5.1f}%  {secs:5.1f}s  "
          f"{r['rss_mb']:.0f}MB", flush=True)
    if save:
        from PIL import Image
        p = os.path.join(OUT, save)
        Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8)).save(
            p, quality=93, subsampling=0)
        r["file"] = p
    del img
    return r


def thin(a: dict, n: int, seed: int = 3) -> tuple:
    """The planter's OWN thinning rule, so a smaller set is drawn the same way."""
    m = len(a["point"])
    if n >= m:
        return a["point"], a["normal"], np.arange(m)
    idx = np.random.default_rng(seed).permutation(m)[:n]
    idx.sort()
    return a["point"][idx], a["normal"][idx], idx


def main() -> None:
    try:
        import psutil
        psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
        print("priority BELOW_NORMAL", flush=True)
    except Exception as e:
        print("could not lower priority:", e, flush=True)

    t_all = time.time()
    plants = {}
    for voxel in (0.0165, 0.0090):
        print(f"\n== planting at voxel {voxel} ==", flush=True)
        a = W.anchors(voxel, 2_000_000)
        st = a.pop("stage")
        a["st"] = st
        a["occ"] = W.occlude_anchors(st, a["point"], a["normal"])
        a["occ_sub"] = (lambda occ: lambda i: {k: v[i] for k, v in occ.items()
                                               if k != "seconds"})(a["occ"])
        a["voxel"] = voxel
        a["rgb_plain"] = {s: W.colours(st, a["point"], a["normal"], a["box"], s,
                                       None) for s in ("dark", "lit")}
        a["rgb_occ"] = {s: W.colours(st, a["point"], a["normal"], a["box"], s,
                                     a["occ"]) for s in ("dark", "lit")}
        plants[voxel] = a
        print(f"   voxel {voxel}: {len(a['point']):,} anchors", flush=True)

    base = plants[0.0165]
    fine = plants[0.0090]

    # ---------------------------------------------------------------- baseline
    print("\n== A. the published still, reproduced, and the occlusion pass ==",
          flush=True)
    p340, n340, i340 = thin(base, 340_000)
    for state in ("dark", "lit"):
        cell(f"A0 baseline paint.py [{state}]", p340, n340,
             base["rgb_plain"][state][i340], 0.021, BASE_W, BASE_H, state,
             save=f"A0-baseline-{state}.jpg", occ=False)
        cell(f"A1 +shadow+AO+texture [{state}]", p340, n340,
             base["rgb_occ"][state][i340], 0.021, BASE_W, BASE_H, state,
             save=f"A1-occluded-{state}.jpg", occ=True)
        for part, kw in (("shadow only", dict(ao_strength=0, texture_strength=0)),
                         ("AO only", dict(shadow_strength=0, texture_strength=0)),
                         ("texture only", dict(shadow_strength=0, ao_strength=0))):
            rgb = W.colours(base["st"], p340, n340, base["box"][i340], state,
                            base["occ_sub"](i340), **kw)
            cell(f"A2 {part} [{state}]", p340, n340, rgb, 0.021,
                 BASE_W, BASE_H, state, occ=part)

    # ------------------------------------------------------------ radius sweep
    print("\n== B. stroke RADIUS, everything else frozen ==", flush=True)
    for radius in (0.021, 0.016, 0.012, 0.009, 0.007, 0.005, 0.0035):
        cell(f"B r={radius}", p340, n340, base["rgb_occ"][STATE][i340],
             radius, BASE_W, BASE_H, STATE,
             save=f"B-r{radius}.jpg", occ=True)

    # ------------------------------------------------------------- count sweep
    print("\n== C. stroke COUNT (radius held at the value that just covers) ==",
          flush=True)
    for n in (40_000, 85_000, 170_000, 340_000, 680_000):
        p, nn, i = thin(base, n)
        cell(f"C n={n}", p, nn, base["rgb_occ"][STATE][i], 0.021,
             BASE_W, BASE_H, STATE, occ=True)
    for n in (340_000, 680_000, 1_200_000, len(fine["point"])):
        n = min(n, len(fine["point"]))
        p, nn, i = thin(fine, n)
        cell(f"C fine-voxel n={n}", p, nn, fine["rgb_occ"][STATE][i], 0.012,
             BASE_W, BASE_H, STATE, occ=True, voxel=0.0090)

    # -------------------------------------------------------- resolution sweep
    print("\n== D. RESOLUTION, at the published stroke settings ==", flush=True)
    for w, h in ((1280, 720), (1600, 900), (1920, 1080), (2560, 1440),
                 (3200, 1800), (4096, 2304)):
        cell(f"D {w}x{h}", p340, n340, base["rgb_occ"][STATE][i340], 0.021,
             w, h, STATE, occ=True)

    # ----------------------------------------------- the corner: small + many
    print("\n== E. the corner: SMALL strokes and MANY of them ==", flush=True)
    for radius, n in ((0.012, 680_000), (0.009, 1_200_000),
                      (0.007, len(fine["point"])), (0.005, len(fine["point"]))):
        n = min(n, len(fine["point"]))
        p, nn, i = thin(fine, n)
        cell(f"E r={radius} n={n}", p, nn, fine["rgb_occ"][STATE][i], radius,
             BASE_W, BASE_H, STATE, save=f"E-r{radius}-n{n}.jpg", occ=True,
             voxel=0.0090)

    # -------------------------------------- the confound the ruler cannot see
    print("\n== F. EXPOSURE: what plain brightness is worth on this ruler ==",
          flush=True)
    for g in (1.0, 1.4, 1.9, 2.5):
        rgb = W.colours(base["st"], p340, n340, base["box"][i340], STATE,
                        base["occ_sub"](i340), gain=g)
        cell(f"F gain x{g}", p340, n340, rgb, 0.021, BASE_W, BASE_H, STATE,
             save=f"F-gain{g}.jpg", gain=g, occ=True)
    rgb = W.colours(base["st"], p340, n340, base["box"][i340], STATE,
                    base["occ_sub"](i340), expose=False)
    cell("F no re-exposure (raw occlusion)", p340, n340, rgb, 0.021,
         BASE_W, BASE_H, STATE, occ=True, expose=False)

    rec = {"when": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "camera": f"room.rail_camera(t={T})",
           "ruler": "Laplacian variance, greyscale, long edge capped at 2400 px",
           "reference": {"iddo_document_pages": [1868, 4038],
                         "tzelem_boulevard": 719,
                         "workshop_lit_REJECTED": 126,
                         "workshop_dark_REJECTED": 10.2,
                         "flux_8k_plates": [4.6, 52]},
           "anchors": {str(k): int(len(v["point"])) for k, v in plants.items()},
           "rows": rows, "seconds": round(time.time() - t_all, 1)}
    with open(os.path.join(OUT, "sweep.json"), "w", encoding="utf-8") as f:
        json.dump(rec, f, indent=2, ensure_ascii=False)
    print(f"\nwrote {os.path.join(OUT, 'sweep.json')} in {rec['seconds']}s",
          flush=True)


if __name__ == "__main__":
    main()
