"""TZELEM gate 1, run on a GAME ENGINE's world instead of our own ray caster.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

לזכרה של עלמה ז״ל.

WHY THIS FILE EXISTS
--------------------
Gate 1 proved TZELEM's central claim — *strokes anchored in the WORLD stay put
when the camera moves, and a 2D painter repainting every frame boils* — on
`stage.py`, a hand-written ray caster over a few boxes. That is a fair test and it
is also a small one, and the obvious objection was never answered: **maybe the
claim only holds because our own toy world is simple.**

`out/godot/*.tzg` answers it. Those are four poses of Rothschild Boulevard,
exported from Godot 4.3 by `alma-vr/godot/scripts/tzelem_gbuffer.gd` — ~890,000
distinct depth values, 800k+ triangles of trees, benches, kerbs and facades that
nothing in this folder authored. This script runs the SAME ruler over them.

WHAT IS REUSED AND WHAT IS NOT, said plainly
--------------------------------------------
The arithmetic is imported from `ruler.py` (`_resid`, `_mse`) rather than
rewritten, so a difference in the numbers cannot be a difference in the formula.
What is new is only the STAGE and the camera path: `gbuffer.LoadedStage` answers
`gbuffer(cam)` and `shade(g)` out of the engine's export, and `flow()` is
inherited from `Stage` untouched — it only ever uses gbuffer + projection, so
exact optical flow between two ENGINE frames costs nothing and is still exact.

THE FOUR CONTESTANTS, unchanged from gate 1:
    FLOOR    repaint every frame, as a 2D painter must      (the thing to beat)
    TZELEM   one set of strokes, planted once, re-seen      (the claim)
    CEILING  warp frame a, paint nothing new                (the cheat, must tear)
    BLANK    the single best flat colour                    (the fidelity floor)

WHAT ALREADY EXISTED, so nobody rebuilds either of us
-----------------------------------------------------
`_deliverables/tzelem-sderot/pipeline/` already took TZELEM's rulers off the toy
world once, onto a MapAnything photogrammetric reconstruction of Sderot:
`sderot_measure.py` does **gate 2** (ownership agreement between a 1024 and an
8192 painting) plus fidelity-vs-photograph against BLANK, and `sderot_ab.py`
A/B's four line fixes on the same rulers. Its own header says the quiet part:
gate 1 and gate 2 *"were only ever measured on the lab's synthetic stage.py
world"*.

This file is the piece those could not be. **A photogrammetric still has no
second pose with exact flow**, so nothing there measures gate 1 — temporal
coherence across a camera MOVE, which is TZELEM's actual claim. An engine can be
asked for as many poses of one world as you like, and `flow()` between two of them
is exact. So: sderot closed gate 2 and fidelity on real-world pixels; this closes
**gate 1** on a real-world-sized world. Neither replaces the other.

HONEST LIMITS:
  * The four poses come from ONE Godot run. `boulevard_cafe.gd` does not rebuild
    the same world twice despite its "seed 1933" (810k..969k triangles over five
    runs), so comparing .tzg files ACROSS runs is meaningless. Within a run the
    poses share a world, which is exactly what this measurement needs.
  * The camera path is a short forward dolly (~0.43 m per step), not an orbit.
    A dolly disoccludes less than an orbit does, so this is a GENTLER test of
    coherence than gate 1's 4-degree sweep, not a harder one. Said here so the
    number is not read as more than it is.
  * `LoadedStage.shade` returns the engine's own beauty pass, which carries its
    tonemap and its lighting. That is "what the eye received" — the right thing to
    be judged against — but it is not the flat Lambert `Stage.shade` computes, so
    the fidelity numbers are not comparable to gate 1's line for line.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

try:
    import psutil as _ps
    _ps.Process().nice(_ps.BELOW_NORMAL_PRIORITY_CLASS)
except Exception:
    _ps = None

import canvas                                    # noqa: E402
import gbuffer                                   # noqa: E402
from anatomy import scatter                      # noqa: E402
import ruler                                     # noqa: E402  the SAME bars
from ruler import _mse, _resid                   # noqa: E402  the SAME arithmetic

FRAMES = os.path.join(_HERE, "out", "godot")
OUT = os.path.join(_HERE, "out-night")


def fingerprint(folder: str) -> list[dict]:
    """WHICH export produced these numbers.

    Added 2026-09-05 after a near-miss: an agent re-exported the frames while this
    gate was reading them, and nothing in the result said which bytes it had been
    handed. A measurement that cannot name its own input is not a measurement — so
    every frame's size, mtime and content hash is now recorded beside the numbers.
    """
    out = []
    for f in sorted(os.listdir(folder)):
        if not f.endswith(".tzg"):
            continue
        p = os.path.join(folder, f)
        h = hashlib.sha256()
        with open(p, "rb") as fh:
            for block in iter(lambda: fh.read(1 << 20), b""):
                h.update(block)
        st = os.stat(p)
        out.append({"file": f, "bytes": st.st_size,
                    "mtime": time.strftime("%Y-%m-%dT%H:%M:%S",
                                           time.localtime(st.st_mtime)),
                    "sha256": h.hexdigest()[:16]})
    return out


def one_pair(stage, cam_a, cam_b, n_strokes: int, seed: int, size: float,
             style: str = "painterly") -> dict:
    """Gate 1's four contestants over one engine camera move."""
    truth_b = stage.shade(stage.gbuffer(cam_b))
    flow = stage.flow(cam_a, cam_b)

    world = scatter(stage, cam_a, n=n_strokes, seed=seed, size=size)
    tz_a = canvas.render(stage, cam_a, world, style=style)
    tz_b = canvas.render(stage, cam_b, world, style=style)

    # REVISION 2026-09-06 (TZ-11): FLOOR's frame a is the same scatter, same seed,
    # same camera as TZELEM's -- bit for bit `tz_a`. It was re-rendered at 1920x1080
    # with 30,000 strokes once per pose pair for nothing. FLOOR diverges at frame b.
    fl_a = tz_a
    fl_b = canvas.render(stage, cam_b,
                         scatter(stage, cam_b, n=n_strokes, seed=seed + 1,
                                 size=size), style=style)

    # REVISION 2026-09-06 (TZ-1): ONE warp in all three roles. The pair of identical
    # canvas.warp(tz_a, flow) calls made CEILING coherence 0.00000 by identity, and
    # that zero was printed as "the cheat is caught". It is gone from the dict.
    ce_b, seen = canvas.warp(tz_a, flow)
    w_tz = ce_b
    w_fl = ce_b
    m = flow["valid"] & seen
    m3 = np.repeat(m[..., None], 3, axis=2)

    h, w = truth_b.shape[:2]
    blank = np.tile(truth_b.reshape(-1, 3).mean(axis=0), (h, w, 1))

    return {
        "strokes": int(len(world)),
        "valid_px": int(m.sum()), "total_px": int(m.size),
        "coherence": {
            "FLOOR_repaint_every_frame": _resid(fl_b, w_fl, m3),
            "TZELEM_world_anchored": _resid(tz_b, w_tz, m3),
            # CEILING coherence is 0 BY CONSTRUCTION -- deliberately absent (TZ-1).
        },
        "fidelity_mse": {
            "BLANK_best_flat_colour": _mse(blank, truth_b),
            "FLOOR_repaint_every_frame": _mse(fl_b, truth_b),
            "TZELEM_world_anchored": _mse(tz_b, truth_b),
            "CEILING_warp_only": _mse(ce_b, truth_b),
        },
        "_images": {"truth_b": truth_b, "tz_b": tz_b, "fl_b": fl_b, "ce_b": ce_b},
    }


def verdict(co: dict, fi: dict,
            fidelity_margin: float | None = None) -> tuple[bool, list[str]]:
    """The same questions gate 1 asks, on the SAME bars gate 1 uses.

    REVISION 2026-09-06 (TZ-3): this used to say `hold < boil` while gate 1 said
    `hold < boil * 0.5`, i.e. the bar was twice as loose as the one the docstring
    claimed, and `oneroom/gate.py` imports this function verbatim so the whole
    one-room track ran on the loose bar. The factor now lives in exactly one place,
    `ruler.COHERENCE_MARGIN`, and is imported rather than retyped.
    """
    lines, ok = [], True
    k = ruler.FIDELITY_MARGIN if fidelity_margin is None else float(fidelity_margin)
    boil, hold = co["FLOOR_repaint_every_frame"], co["TZELEM_world_anchored"]
    if hold < boil * ruler.COHERENCE_MARGIN:
        lines.append(f"PASS  coherence: TZELEM {hold:.5f} vs floor {boil:.5f} "
                     f"= x{boil / max(hold, 1e-12):.2f} steadier")
    else:
        ok = False
        lines.append(f"FAIL  coherence: TZELEM {hold:.5f} did not CLEARLY beat the "
                     f"floor {boil:.5f} (bar: at least "
                     f"{1 / ruler.COHERENCE_MARGIN:.0f}x steadier)")
    if fi["TZELEM_world_anchored"] < fi["BLANK_best_flat_colour"]:
        lines.append(f"PASS  fidelity: TZELEM {fi['TZELEM_world_anchored']:.5f} "
                     f"beats BLANK {fi['BLANK_best_flat_colour']:.5f} "
                     f"= x{fi['BLANK_best_flat_colour'] / max(fi['TZELEM_world_anchored'], 1e-12):.2f}")
    else:
        ok = False
        lines.append(f"FAIL  fidelity: TZELEM {fi['TZELEM_world_anchored']:.5f} "
                     f"lost to a flat colour {fi['BLANK_best_flat_colour']:.5f}")
    fce = fi["CEILING_warp_only"]
    if fce > fi["TZELEM_world_anchored"]:
        lines.append(f"PASS  the cheat is caught on FIDELITY: warp-only tears at "
                     f"disocclusion ({fce:.5f} vs TZELEM "
                     f"{fi['TZELEM_world_anchored']:.5f}). Its coherence is 0 by "
                     f"construction and is not measured or quoted.")
    else:
        ok = False
        lines.append(f"FAIL  warp-only did NOT tear ({fce:.5f}); the coherence "
                     f"number can be gamed and means nothing")

    # TZ-2: the bar that was missing everywhere. FLOOR beat TZELEM on fidelity in
    # every stored run of this gate and every one of them said PASS.
    ffl = fi["FLOOR_repaint_every_frame"]
    ftz = fi["TZELEM_world_anchored"]
    ratio = ftz / max(ffl, 1e-12)
    if ftz <= ffl * k:
        lines.append(f"PASS  fidelity vs FLOOR: TZELEM {ftz:.5f} vs floor {ffl:.5f} "
                     f"= x{ratio:.2f} of the floor (bar x{k:.2f})")
    else:
        ok = False
        lines.append(f"FAIL  fidelity vs FLOOR: TZELEM {ftz:.5f} is x{ratio:.2f} the "
                     f"repaint floor {ffl:.5f} (bar x{k:.2f}) — the steadiness is "
                     f"being paid for in fidelity, and that trade was never gated")
    return ok, lines


def main(n_strokes: int = 30_000, size: float = 0.006, seed: int = 5) -> dict:
    t0 = time.time()
    fp = fingerprint(FRAMES)
    stage = gbuffer.LoadedStage.from_dir(FRAMES)
    cams = stage.cameras
    after = fingerprint(FRAMES)
    if fp != after:
        raise SystemExit("the exported frames CHANGED while this gate was reading "
                         "them. Re-run when the exporter has finished; a number "
                         "measured over two different worlds is worth nothing.")
    if len(cams) < 2:
        raise SystemExit(f"{FRAMES}: need at least 2 exported poses, got {len(cams)}")
    print(f"{len(cams)} engine poses at {cams[0].width}x{cams[0].height}", flush=True)

    pairs, keep = [], None
    for i in range(len(cams) - 1):
        a, b = cams[i], cams[i + 1]
        step = float(np.linalg.norm(np.asarray(b.eye) - np.asarray(a.eye)))
        r = one_pair(stage, a, b, n_strokes, seed + i, size)
        keep = keep or r["_images"]
        r["step_m"] = round(step, 3)
        imgs = r.pop("_images")
        pairs.append(r)
        print(f"  pose {i}->{i+1}  step {step:.3f} m  "
              f"floor {r['coherence']['FLOOR_repaint_every_frame']:.5f}  "
              f"TZELEM {r['coherence']['TZELEM_world_anchored']:.5f}  "
              f"valid {100*r['valid_px']/r['total_px']:.1f}%", flush=True)
        del imgs

    def agg(field, key):
        return float(np.mean([p[field][key] for p in pairs]))

    co = {k: agg("coherence", k) for k in pairs[0]["coherence"]}
    fi = {k: agg("fidelity_mse", k) for k in pairs[0]["fidelity_mse"]}
    # TZ-2: derive the fidelity tolerance from THIS run's own FLOOR spread instead of
    # a hand-picked constant. With several pose pairs there is a real spread to use.
    _ffl = np.array([p["fidelity_mse"]["FLOOR_repaint_every_frame"] for p in pairs],
                    dtype=float)
    k_fid = ruler.margin_from_spread(float(_ffl.mean()), float(_ffl.std()))
    ok, lines = verdict(co, fi, fidelity_margin=k_fid)
    for l in lines:
        print(" ", l, flush=True)

    os.makedirs(OUT, exist_ok=True)
    from PIL import Image
    made = {}
    for name, img in keep.items():
        p = os.path.join(OUT, f"GODOT-gate1-{name}.jpg")
        Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8)).save(
            p, quality=93, subsampling=0)
        made[name] = p

    rec = {"when": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "source": "Godot 4.3 export of alma-vr boulevard_cafe, one run",
           "resolution": [cams[0].width, cams[0].height],
           "input_frames": fp,
           # TZ-4: a measurement must name its PAINTER as well as its input. Every
           # stored gate JSON before 2026-09-06 was produced by a canvas.py that had
           # since moved (+511/-240 uncommitted), and nothing said so.
           "painter": canvas.source_hashes(),
           "fidelity_margin": k_fid,
           "poses": len(cams), "strokes": n_strokes, "size": size,
           "pairs": pairs, "coherence": co, "fidelity_mse": fi,
           "pass": ok, "verdict": lines,
           "seconds": round(time.time() - t0, 1), "made": made}
    with open(os.path.join(OUT, "godot-gate1.json"), "w", encoding="utf-8") as f:
        json.dump(rec, f, indent=2, ensure_ascii=False)
    print(f"{'PASS' if ok else 'FAIL'} in {rec['seconds']}s -> "
          f"{os.path.join(OUT, 'godot-gate1.json')}", flush=True)
    return rec


if __name__ == "__main__":
    main()
