"""RECORD — every finished painting is itself a weave, and it can be replayed.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

Grafted from the second design because it earned its place: a painting whose
strokes are STRANDS is a painting the language itself can carry. One knot per
band, a `sheet` pool, an `ink` fringe; each committed stroke is one strand:

    weight   = width * opacity       (how much the stroke presses)
    delay    = its stroke index + 1  (distance is time: z-order as beats)
    bearing  = the decoded geometry as one plain phrase of numbers
               (str only — the transcript law; %.17g so floats round-trip)
    tint     = the band it painted in

Run, the record weave pours every stroke's weight through the sheet into the
ink fringe on its own beat — the ink's last recorded value equals the total
stroke weight, asserted HERE at write time, not hoped. `replay()` parses the
bearings back to geometry and re-renders through the atelier: the PNG on disk
and the replayed canvas must match byte for byte, or it screams.

The written file is `alma.godot.weave_scene` of the record weave WITH its run
trace — the canonical §8 JSON extended additively, so `from_dict` reads it
unchanged and the alma-vr bridge can walk it. Plus an additive "atelier" block
with sizes and provenance. Nothing here is torch; on eran4 the same strokes go
through the imported `render_big` for the 4K path (tests pin the equality).
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np

_ALMA = "D:/CLAUDE/alma-language"
if _ALMA not in sys.path:
    sys.path.insert(0, _ALMA)

from alma import Loom, Strand, Weave, from_dict                # noqa: E402
from alma.godot import weave_scene                             # noqa: E402

import atelier as atelier_mod                                  # noqa: E402

F = "%.17g"          # floats survive the trip through text exactly


def _bearing(i: int, xy: np.ndarray, w: float, col: np.ndarray,
             op: float) -> str:
    nums = [F % v for p in xy for v in p] + [F % w] + [F % c for c in col] \
        + [F % op]
    return ("i%03d " % i) + " ".join(nums)


def _parse_bearing(text: str):
    parts = text.split()
    i = int(parts[0][1:])
    vals = [float(v) for v in parts[1:]]
    pts = atelier_mod.POINTS
    xy = np.array(vals[:pts * 2]).reshape(pts, 2)
    w = vals[pts * 2]
    col = np.array(vals[pts * 2 + 1: pts * 2 + 4])
    op = vals[pts * 2 + 4]
    return i, xy, w, col, op


def record_weave(strokes, bands, band_ranges) -> Weave:
    """Build the record weave from [(i, xy, w, col, opacity), ...]."""
    w = Weave("winston-record")
    used = []
    for b in bands:
        lo, hi = band_ranges[b]
        ss = [Strand(weight=float(wd) * float(op), delay=int(i) + 1,
                     tint=b, bearing=_bearing(i, xy, wd, col, op))
              for (i, xy, wd, col, op) in strokes if lo <= i < hi]
        if ss:
            used.append((b, ss))
    w.knot("sheet", verb="pool")
    w.knot("ink", verb="fringe")
    for b, ss in used:
        w.knot(b, verb="pass")
        w.thread(b, "sheet", strands=ss)
        w.seed(b, 1.0, beat=1)
    w.thread("sheet", "ink", strands=[Strand(weight=1.0, delay=1)])
    w.run_hint = max((int(i) for i, *_ in strokes), default=0) + 4
    return w


def paint_record(atelier, json_path: str, png_path: str | None = None,
                 meta: dict | None = None,
                 bands: tuple[int, int, int] | None = None,
                 opacity=None) -> dict:
    """Write one painting's record weave (+run trace +scene) to json_path."""
    geo = atelier.geometry()
    if not geo:
        print("record: nothing alive on the canvas — no record written")
        return {}
    if bands is None:
        bands = (0, 0, atelier.n)
    ofs = np.cumsum((0,) + tuple(bands))
    band_ranges = {b: (int(ofs[k]), int(ofs[k + 1]))
                   for k, b in enumerate(("coarse", "mid", "fine"))}
    op = np.ones(atelier.n) if opacity is None else np.asarray(opacity, float)
    strokes = [(i, xy, wd, col, float(op[i])) for (i, xy, wd, col) in geo]
    w = record_weave(strokes, ("coarse", "mid", "fine"), band_ranges)
    w.validate()
    res = Loom().run(w, w.run_hint)
    total = sum(float(wd) * float(o) for (_, _, wd, _, o) in strokes)
    poured = res.fringe("ink")[-1] if res.fringe("ink") else 0.0
    assert abs(poured - total) < 1e-9 * max(1.0, abs(total)), (poured, total)
    d = weave_scene(w, res)                      # canonical §8 + scene + trace
    d["atelier"] = {"size": atelier.size, "subject": atelier.subject_path,
                    "n_strokes": atelier.n, "png": png_path,
                    "total_weight": total, **(meta or {})}
    os.makedirs(os.path.dirname(os.path.abspath(json_path)), exist_ok=True)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=1, ensure_ascii=False)
    return {"record": json_path, "poured": poured}


def replay(json_path: str, expect_png: str | None = None,
           size: int | None = None) -> np.ndarray:
    """Re-render a record from its bearings alone; assert the pixels match.

    Runs the weave too (a record that no longer validates or runs is a broken
    transcript and must scream). Returns the replayed canvas (H,W,3)."""
    with open(json_path, encoding="utf-8") as f:
        d = json.load(f)
    w = from_dict(d)
    w.validate()
    Loom().run(w, w.run_hint or 32)
    strokes = []
    for t in w.threads:
        for s in t.strands:
            if isinstance(s.bearing, str) and s.bearing.startswith("i"):
                i, xy, wd, col, op = _parse_bearing(s.bearing)
                strokes.append((i, xy, wd, col))
    sz = size or int(d.get("atelier", {}).get("size", atelier_mod.SIZE))
    canvas = atelier_mod.render_geometry(strokes, sz)
    png = expect_png or d.get("atelier", {}).get("png")
    if png and os.path.isfile(png):
        from PIL import Image
        want = np.asarray(Image.open(png).convert("RGB"))
        got = (canvas * 255).astype(np.uint8)
        assert want.shape == got.shape and (want == got).all(), \
            "replay does not match the saved PNG — the record lies"
    return canvas
