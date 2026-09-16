"""TZELEM / צלם — THE RULER: does the organ hold still when the camera moves?

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

THE ANTI-BLIND-RULER CONTROL, run before any learning exists
------------------------------------------------------------
A ruler that cannot separate a known-bad method from a known-good one measures
nothing, and every number taken with it afterwards is theatre. So the ruler is
proven on two methods whose answers we already know:

    FLOOR   — repaint from scratch every frame, the way a 2D painter does.
              The strokes must BOIL. Coherence residual: large.
    CEILING — paint nothing; just carry the previous frame along the exact flow.
              Coherence residual: ZERO by construction — and it is a CHEAT, which
              the second axis is there to catch: it tears open at disocclusion.
    TZELEM  — the same world-anchored strokes, re-seen from the new camera.

TWO AXES, AND THE SECOND ONE IS NOT OPTIONAL. A flat grey image is perfectly
coherent and perfectly useless, so coherence alone would reward the emptiest
possible organ. Fidelity is measured against the shaded truth, with BLANK (the
best flat colour) as its floor — the same guard WINSTON uses.

An organ passes gate 1 only if BOTH hold:
    coherence(TZELEM)  <<  coherence(FLOOR)
    fidelity(TZELEM)   <<  fidelity(BLANK)   and  fidelity(TZELEM) < fidelity(CEILING)
"""
from __future__ import annotations

import os
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import canvas                        # noqa: E402
from anatomy import scatter          # noqa: E402
from stage import Stage, orbit       # noqa: E402


# ---------------------------------------------------------------- THE BARS
# REVISION 2026-09-06. Both bars used to be typed as bare literals inside each
# verdict(), and godot_gate.verdict retyped the coherence one WEAKER (`hold < boil`,
# no 0.5) while its docstring said "the same two questions gate 1 asks" -- so the
# boulevard and the whole one-room track ran on a bar twice as loose as gate 1's
# (TZ-3). A bar that is retyped is a bar that drifts. Both verdicts import these.
COHERENCE_MARGIN = 0.5      # TZELEM must be at least 2x steadier than the boiling floor

# TZ-2: there was NO floor-relative fidelity bar at all -- only BLANK, the single best
# flat colour -- so world-anchoring could be paid for with any amount of fidelity and
# still PASS, and it already was: FLOOR beat TZELEM on fidelity in every stored run
# (boulevard 0.012934 vs 0.019836) and every one said PASS. 1.15 is a STATED default,
# not a measured one; whenever the run reports FLOOR's own spread, pass
# `margin_from_spread(...)` instead so the tolerance is derived from the run itself.
FIDELITY_MARGIN = 1.15


def margin_from_spread(mean: float, std: float, floor: float = 1.0) -> float:
    """FLOOR's own 3-sigma spread expressed as a multiplier -- a measured tolerance.

    A bar hand-picked at 1.15 says nothing about how far the run is from failing.
    This says: "anything inside three sigma of the repaint floor's own scatter is
    not a real fidelity loss." With no spread to speak of it collapses to 1.0, i.e.
    TZELEM must simply not be worse than FLOOR, which is the strict reading.
    """
    if not np.isfinite(mean) or mean <= 0 or not np.isfinite(std):
        return float(floor)
    return max(float(floor), (mean + 3.0 * float(std)) / float(mean))


def _resid(a: np.ndarray, b: np.ndarray, m: np.ndarray) -> float:
    if not m.any():
        return float("nan")
    return float(np.abs(a[m] - b[m]).mean())


def _mse(a: np.ndarray, b: np.ndarray) -> float:
    return float(((a - b) ** 2).mean())


def measure(width: int = 200, height: int = 150, n_strokes: int = 1400,
            sweep_deg: float = 4.0, seed: int = 7, style: str = "painterly",
            start_deg: float = 0.0) -> dict:
    """Run the whole gate on one camera move and hand back every number.

    `style` reaches straight through to canvas.render, so the SAME ruler can score
    the round strokes gate 1 was born with and the painterly ones gate 2 brought —
    which is the only way the question "did painterly cost us coherence?" has an
    answer instead of an opinion.
    """
    stage = Stage()
    cam_a = orbit(start_deg, width, height)
    cam_b = orbit(start_deg + sweep_deg, width, height)

    truth_a = stage.shade(stage.gbuffer(cam_a))
    truth_b = stage.shade(stage.gbuffer(cam_b))
    flow = stage.flow(cam_a, cam_b)

    # --- TZELEM: one set of strokes, planted in the world, seen twice
    world = scatter(stage, cam_a, n=n_strokes, seed=seed)
    tz_a = canvas.render(stage, cam_a, world, style=style)
    tz_b = canvas.render(stage, cam_b, world, style=style)

    # --- FLOOR: a fresh painting for each frame, as a 2D painter must
    # REVISION 2026-09-06 (TZ-11): frame a of FLOOR is a fresh scatter at cam_a with
    # the SAME seed -- i.e. bit for bit the picture `tz_a` already holds (measured:
    # np.array_equal(fl_a, tz_a) True, max|diff| 0.0). Re-deriving it was 18% of every
    # gate 1 run and produced nothing new. FLOOR only diverges from TZELEM at frame b,
    # and THAT is what the contest is about.
    fl_a = tz_a
    fl_b = canvas.render(stage, cam_b, scatter(stage, cam_b, n=n_strokes,
                                               seed=seed + 1), style=style)

    # --- CEILING: paint nothing new, carry frame a along the true flow
    # REVISION 2026-09-06 (TZ-1): ONE warp, used in all three roles. It used to be
    # called twice with identical arguments and the two results scored against EACH
    # OTHER, so `CEILING_warp_only` coherence was 0.00000 by identity -- and that zero
    # was printed as evidence ("the cheat is caught"). A number that cannot vary is not
    # a measurement, so it no longer appears in the coherence dict at all. The LIVE
    # half of that check -- fidelity(CEILING) > fidelity(TZELEM) -- is kept below.
    ce_b, seen = canvas.warp(tz_a, flow)
    w_tz = ce_b                 # the same array, in its second role
    w_fl = ce_b                 # fl_a IS tz_a, so its warp is the same array too
    m = flow["valid"] & seen
    m3 = np.repeat(m[..., None], 3, axis=2)

    blank = np.tile(truth_b.reshape(-1, 3).mean(axis=0), (height, width, 1))

    return {
        "camera": {"width": width, "height": height, "sweep_deg": sweep_deg,
                   "start_deg": start_deg, "style": style,
                   "strokes": int(len(world)),
                   "valid_px": int(m.sum()), "total_px": int(m.size)},
        "coherence": {                       # lower is better
            "FLOOR_repaint_every_frame": _resid(fl_b, w_fl, m3),
            "TZELEM_world_anchored": _resid(tz_b, w_tz, m3),
            # CEILING coherence is 0 BY CONSTRUCTION (see above) -- deliberately absent.
        },
        "fidelity_mse": {                    # lower is better
            "BLANK_best_flat_colour": _mse(blank, truth_b),
            "FLOOR_repaint_every_frame": _mse(fl_b, truth_b),
            "TZELEM_world_anchored": _mse(tz_b, truth_b),
            "CEILING_warp_only": _mse(ce_b, truth_b),
        },
        "_images": {"truth_a": truth_a, "truth_b": truth_b, "tz_a": tz_a,
                    "tz_b": tz_b, "fl_b": fl_b, "ce_b": ce_b},
    }


# ---------------------------------------------------------------- many frames

def sweep(width: int = 1920, height: int = 1080, n_strokes: int = 1800,
          frames: int = 6, sweep_deg: float = 4.0, seed: int = 7,
          style: str = "painterly", verbose: bool = True) -> dict:
    """The gate over a whole camera MOVE, not one pair of frames.

    One pair can be lucky. `frames` consecutive 4-degree steps cannot all be lucky
    in the same direction, so every number the plan quotes is a mean over the move
    with its spread reported next to it.
    """
    per, keys = [], None
    for k in range(frames - 1):
        r = measure(width=width, height=height, n_strokes=n_strokes,
                    sweep_deg=sweep_deg, seed=seed, style=style,
                    start_deg=k * sweep_deg)
        r.pop("_images", None)
        per.append(r)
        keys = keys or list(r["coherence"].keys())
        if verbose:
            print(f"    frame {k + 1}->{k + 2}  "
                  f"floor {r['coherence']['FLOOR_repaint_every_frame']:.5f}  "
                  f"tzelem {r['coherence']['TZELEM_world_anchored']:.5f}")

    def agg(section):
        out = {}
        for k in per[0][section]:
            v = np.array([p[section][k] for p in per], dtype=float)
            out[k] = {"mean": float(v.mean()), "std": float(v.std()),
                      "min": float(v.min()), "max": float(v.max())}
        return out

    co, fi = agg("coherence"), agg("fidelity_mse")
    res = {"camera": {"width": width, "height": height, "frames": frames,
                      "sweep_deg": sweep_deg, "style": style,
                      "strokes": per[0]["camera"]["strokes"]},
           "coherence": co, "fidelity_mse": fi,
           "steadier_than_floor": (co["FLOOR_repaint_every_frame"]["mean"]
                                   / max(co["TZELEM_world_anchored"]["mean"], 1e-12)),
           "per_frame": per}
    if verbose:
        print(f"  {style:>10} @ {width}x{height}, {frames} frames: "
              f"floor {co['FLOOR_repaint_every_frame']['mean']:.5f}  "
              f"tzelem {co['TZELEM_world_anchored']['mean']:.5f}  "
              f"= x{res['steadier_than_floor']:.2f} steadier   |  fidelity "
              f"tzelem {fi['TZELEM_world_anchored']['mean']:.5f} vs blank "
              f"{fi['BLANK_best_flat_colour']['mean']:.5f}")
    return res


def verdict(r: dict, fidelity_margin: float | None = None) -> tuple[bool, list[str]]:
    """The gate, stated as pass/fail with the reason written out.

    `fidelity_margin` is how much worse than the repaint FLOOR TZELEM is allowed to
    be. Pass `margin_from_spread(...)` when the run has measured FLOOR's spread;
    None falls back to the stated `FIDELITY_MARGIN`.
    """
    co, fi = r["coherence"], r["fidelity_mse"]
    lines, ok = [], True
    k = FIDELITY_MARGIN if fidelity_margin is None else float(fidelity_margin)

    boil = co["FLOOR_repaint_every_frame"]
    hold = co["TZELEM_world_anchored"]
    if hold < boil * COHERENCE_MARGIN:
        lines.append(f"PASS  coherence: TZELEM {hold:.5f} vs floor {boil:.5f} "
                     f"({boil / max(hold, 1e-12):.1f}x steadier)")
    else:
        ok = False
        lines.append(f"FAIL  coherence: TZELEM {hold:.5f} did not clearly beat "
                     f"the boiling floor {boil:.5f}")

    if fi["TZELEM_world_anchored"] < fi["BLANK_best_flat_colour"]:
        lines.append(f"PASS  fidelity: TZELEM {fi['TZELEM_world_anchored']:.5f} "
                     f"beats BLANK {fi['BLANK_best_flat_colour']:.5f}")
    else:
        ok = False
        lines.append(f"FAIL  fidelity: TZELEM {fi['TZELEM_world_anchored']:.5f} "
                     f"lost to a flat colour {fi['BLANK_best_flat_colour']:.5f}")

    if fi["TZELEM_world_anchored"] < fi["CEILING_warp_only"]:
        lines.append(f"PASS  the cheat is caught: warp-only scores "
                     f"{fi['CEILING_warp_only']:.5f} on fidelity — it tears at "
                     f"disocclusion, TZELEM does not")
    else:
        ok = False
        lines.append("FAIL  warp-only beat TZELEM on fidelity too — then the organ "
                     "is adding nothing a warp does not already give")

    # TZ-2, the bar that was missing: coherence bought with fidelity is not a win.
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


def _save(images: dict, out: str) -> list[str]:
    from PIL import Image
    os.makedirs(out, exist_ok=True)
    paths = []
    for k, v in images.items():
        p = os.path.join(out, f"TZELEM-gate1-{k}.png")
        Image.fromarray((np.clip(v, 0, 1) * 255).astype(np.uint8)).save(p)
        paths.append(p)
    return paths


if __name__ == "__main__":
    import json

    res = measure()
    passed, why = verdict(res)
    print(json.dumps({k: v for k, v in res.items() if k != "_images"},
                     indent=2, ensure_ascii=False))
    print()
    for line in why:
        print("   ", line)
    print("\nGATE 1:", "PASSED" if passed else "FAILED")
    for p in _save(res["_images"], os.path.join(_HERE, "out")):
        print("   wrote", p)
