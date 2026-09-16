"""PROOF OF LIFE — the organ paints on the PC, zero torch, in seconds.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

Two sittings, seed 1933, 64 strokes in bands 8/16/40, R=3 wiggle voices:

  1. a red disc on white, 32x32 — the target the floors are sharp on: the
     empty white canvas does NOT beat BLANK here (BLANK is the OPTIMAL flat
     colour), so `beats_blank > 0` means the weave genuinely painted.
     This one is ASSERTED. If it fails, the organ is dead and says so.
  2. the alef from the hand's own 22x36 table (state/alef-row.npz, extracted
     from eran-brain/hand/state/hand.pt — ERAN's hand, not a font), rendered
     to a target by the same segment ink the hand draws with. Reported
     honestly, PASSES or FAILS, whichever way it goes.

Each sitting prints the winston.py-style verdict block (BLANK margin, BLUR,
the busy tenth and the vanished-person line, strokes alive), writes the weave
JSON + PNG + the record weave (with godot scene + trace) to weaves/, replays
the record and asserts the pixels match, and puts the run in front of MURPHY.

    PYTHONIOENCODING=utf-8 python proof_of_life.py
"""
from __future__ import annotations

import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import record                                                  # noqa: E402
from atelier import mse                                        # noqa: E402
from easel import Easel                                        # noqa: E402

SEED = 1933
N, BANDS, R = 64, (8, 16, 40), 3
SIZE = 32


def disc_target(size: int = SIZE) -> np.ndarray:
    """A red disc on white — flat regions, one clear subject, honest floors."""
    g = np.linspace(-1, 1, size)
    yy, xx = np.meshgrid(g, g, indexing="ij")
    m = (xx ** 2 + yy ** 2) <= 0.55 ** 2
    x = np.ones((size, size, 3))
    x[m] = (0.85, 0.10, 0.08)
    return x


def alef_target(size: int = SIZE) -> np.ndarray:
    """The alef ERAN's own hand knows: 36 numbers -> tanh*0.85 control points
    -> distance-to-segment ink at W_FIXED=0.045 (hand_eye.pen/ink, in numpy)."""
    z = np.load(os.path.join(HERE, "state", "alef-row.npz"))
    raw, strokes, points = z["raw"], int(z["strokes"]), int(z["points"])
    xy = np.tanh(raw.reshape(strokes, points, 2)) * 0.85
    g = np.linspace(-1, 1, size)
    gy, gx = np.meshgrid(g, g, indexing="ij")
    px = np.stack([gx, gy], -1).reshape(-1, 2)
    ink = np.zeros(px.shape[0])
    for s in range(strokes):
        a0, a1 = xy[s, :-1], xy[s, 1:]
        d = a1 - a0
        dd = (d * d).sum(-1).clip(min=1e-6)
        v = px[None] - a0[:, None]
        t = ((v * d[:, None]).sum(-1) / dd[:, None]).clip(0, 1)
        near = a0[:, None] + t[..., None] * d[:, None]
        d2 = ((px[None] - near) ** 2).sum(-1).min(0)
        ink = np.maximum(ink, np.exp(-d2 / (2 * 0.045 ** 2)))
    return (1.0 - 0.92 * ink.reshape(size, size))[..., None].repeat(3, -1)


def one_sitting(name: str, target: np.ndarray,
                out_dir: str | None = None) -> tuple[Easel, dict]:
    e = Easel(target, n_strokes=N, bands=BANDS, r_fires=R, seed=SEED,
              name="winston-pol-" + name, size=SIZE, out_dir=out_dir)
    fr = e.sitting(persist=True)
    # replay the newest record and let it assert the pixels match
    recs = sorted(f for f in os.listdir(e.out_dir)
                  if f.startswith("record-") and f.endswith(".json"))
    if e.atelier.n_alive() and recs:
        record.replay(os.path.join(e.out_dir, recs[-1]))
        print(" record replayed: pixels match the PNG byte for byte")
    return e, fr


def murphy_watch(e: Easel, name: str) -> None:
    """One murphy.watch() per claim — the claim is `beats_blank > 0`."""
    try:
        sys.path.insert(0, "D:/CLAUDE/murphy")
        from murphy import watch
    except ImportError:
        print("murphy not reachable from this machine — verdict NOT ruled "
              "(said plainly, not skipped in silence)")
        return
    a = e.atelier
    steps = [{"step": k + 1, "metric": float(a.err_white - err)}
             for k, (_, err) in enumerate(a.history)] or \
            [{"step": 1, "metric": 0.0}]
    v = a.verdicts()
    watch({"steps": steps, "chance": 0.0, "baseline": 0.0,
           "held_out": "one subject, one painting — no holdout exists; the "
                       "floors are BLANK/BLUR computed on the same subject",
           "judge_in_loop": False, "independent": "mse against the subject is "
                                                  "arithmetic, not a model",
           "artifact": getattr(e, "last_paths", {}).get("png", "(not written)"),
           "looked_at": False,
           "final": {"beats_blank": v["beats_blank"],
                     "busy_gap": v["busy_gap"]}},
          name="winston-organ proof-of-life: " + name)


def main() -> int:
    print("WINSTON as a HOLOBRAIN organ — proof of life (PC, numpy, no torch)")
    print("=" * 72)

    e1, fr1 = one_sitting("disc", disc_target())
    murphy_watch(e1, "red disc")
    bb = fr1["beats_blank"][0] if fr1["beats_blank"] else float("-inf")
    assert bb > 0, ("PROOF OF LIFE FAILED: beats_blank = %r — the weave did "
                    "not out-paint a flat colour" % bb)

    e2, fr2 = one_sitting("alef", alef_target())
    murphy_watch(e2, "alef from the hand's table")

    print("\nproof of life: the disc sitting PASSES its BLANK floor "
          "(margin %.5f); alef reported above, whichever way it went."
          % bb)
    print("הוכחת חיים: האריג צייר — עבר את רצפת הצבע האחיד. הקבצים ב-weaves/.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
