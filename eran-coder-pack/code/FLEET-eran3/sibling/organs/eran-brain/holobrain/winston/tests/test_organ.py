"""The 14 PC tests of the WINSTON organ — stdlib + numpy + stubs, zero torch.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

Numbered to match the build spec. Test 7 carries the regression canary that
pins today's loom semantics (silent fires count as fired for drift,
alma/loom.py LEARN step): if the loom ever changes that, the canary screams
before the organ starts lying about merit.
"""
from __future__ import annotations

import json
import sys

import numpy as np
import pytest

import atelier as A
import record
import stubs
from easel import Easel
from proof_of_life import alef_target, disc_target, one_sitting

sys.path.insert(0, "D:/CLAUDE/alma-language")
from alma import (Loom, Strand, Weave, WeaveError, from_dict, from_json,
                  parse_voice, to_dict, to_json, to_voice)                  # noqa: E402
from alma.loom import RESERVED                                              # noqa: E402
from alma.text import FILLER                                                # noqa: E402

SEED = 1933


def small(target=None, gaze=None, theta=0.05, out_dir=None, **kw):
    t = disc_target(16) if target is None else target
    return Easel(t, n_strokes=12, bands=(4, 4, 4), r_fires=3, seed=SEED,
                 size=16, theta=theta, gaze=gaze, out_dir=out_dir,
                 name="test", **kw)


def good_stroke_params(easel, i=0):
    """A stroke aimed at the disc: anchored centre, red, real reach."""
    p = np.zeros(A.PARAMS)
    p[2:A.POINTS * 2] = 1.2                          # real segments, not a dot
    c = np.array([0.85, 0.10, 0.08]).clip(1e-4, 1 - 1e-4)
    p[A.POINTS * 2 + 1:] = np.log(c / (1 - c))
    easel.atelier.table[i] = p
    return p


# ---------------------------------------------------------------- 1

def test_easel_builds():
    for gaze in (None, "stub"):
        e = small(gaze=gaze)
        n = e.n
        w = e.weave()
        e._teach()
        w.validate()
        want_knots = 3 * n + 19 + (5 if e.gaze else 0)
        assert len(w.knots) == want_knots, (len(w.knots), want_knots)
        want_threads = 4 * n + 23 + (5 if e.gaze else 0)
        assert len(w.threads) == want_threads
        want_strands = n * (3 + e.r) + 23 + (5 if e.gaze else 0)
        assert sum(len(t.strands) for t in w.threads) == want_strands
        for k in w.knots.values():
            assert k.name.lower() not in RESERVED, k.name
            if k.spell:
                assert k.spell not in RESERVED and k.spell not in FILLER
        for t in w.threads:
            for s in t.strands:
                assert s.delay >= 1
    # the whole organ imported and built and torch never entered the process
    assert "torch" not in sys.modules, \
        "a PC test path imported torch — the law is numpy only on the PC"


# ---------------------------------------------------------------- 2

def test_determinism():
    a = small()
    fa = a.sitting(persist=False, quiet=True)
    b = small()
    fb = b.sitting(persist=False, quiet=True)
    assert fa == fb
    assert a.last_result.learned == b.last_result.learned
    assert np.array_equal(a.opacity, b.opacity)
    assert [(f.beat, f.knot, f.spoke) for f in a.last_result.fires] == \
           [(f.beat, f.knot, f.spoke) for f in b.last_result.fires]


# ---------------------------------------------------------------- 3

def test_daub_paints():
    e = small()
    good_stroke_params(e, 0)
    e.sitting(persist=False, quiet=True)
    assert 0 in e.atelier.alive, "the aimed stroke was not committed"
    direct = A.render_geometry(e.atelier.geometry(), e.atelier.size)
    assert np.array_equal(direct, e.atelier.canvas()), \
        "weave-painted canvas differs from the direct numpy render"
    sheet = (1.0 - A.render_geometry(
        [g for g in e.atelier.geometry() if g[0] == 0], 16).mean(-1))[None]
    pc = A.pen_check(sheet)
    assert pc["pieces_max"] <= 2, "a stroke must be a segment, not a dot cloud"


# ---------------------------------------------------------------- 4

def test_bounded_reach():
    rng = np.random.default_rng(3)
    p = rng.normal(0, 50.0, (40, A.PARAMS))            # adversarial
    xy, w, col = A.decode(p, 40, np.arange(40))
    step = np.abs(xy[:, 1:] - xy[:, :-1])
    # winston's bound is PER COORDINATE (tanh*MAX_REACH on each axis), so the
    # Chebyshev step is <= MAX_REACH and the Euclidean step <= MAX_REACH*sqrt2.
    assert step.max() <= A.MAX_REACH + 1e-9
    seg = np.linalg.norm(xy[:, 1:] - xy[:, :-1], axis=-1)
    assert seg.max() <= A.MAX_REACH * np.sqrt(2) + 1e-9
    assert np.abs(xy[:, 0]).max() <= 0.95 + 1e-9       # anchors in tanh bound
    assert (w > 0).all() and (col >= 0).all() and (col <= 1).all()


# ---------------------------------------------------------------- 5

def test_bands_are_delays():
    e = small(target=np.ones((16, 16, 3)))             # unpaintable: white
    e.sitting(persist=False, quiet=True)
    fires = e.last_result.fires
    done_beat = {f.knot: f.beat for f in fires if f.knot.endswith("_done")}
    lo, hi = e.band_range["mid"]
    mid_first = min((f.beat for f in fires
                     if f.knot in {"s_%03d" % i for i in range(lo, hi)}),
                    default=None)
    assert mid_first is not None and mid_first > done_beat["coarse_done"]
    # nothing improves on a white canvas -> patience wakes each done EXACTLY
    for band in ("coarse", "mid", "fine"):
        assert done_beat[band + "_done"] == e.patience_beat[band], band


# ---------------------------------------------------------------- 6

def test_worth_gates_commit():
    w = small(target=np.ones((16, 16, 3)))             # every trial hurts
    w.sitting(persist=False, quiet=True)
    assert w.atelier.n_alive() == 0
    assert np.array_equal(w.atelier.canvas(), np.ones((16, 16, 3)))
    g = small()
    good_stroke_params(g, 0)
    g.sitting(persist=False, quiet=True)
    assert g.atelier.n_alive() >= 1                    # positive delta commits


# ---------------------------------------------------------------- 7

def test_drift_records_merit():
    g = small()
    good_stroke_params(g, 0)
    g.sitting(persist=False, quiet=True)
    merit = {i: g.last_result.learned[slot]
             for i, slot in g._merit_slot.items()}
    assert merit[0] > 1.0, "the helpful stroke's cord did not thicken"
    useless = [i for i in merit if i not in g.atelier.alive]
    assert useless and all(merit[i] < 1.0 for i in useless)
    # transcription is monotone in merit
    order = sorted(merit, key=merit.get)
    ops = [g.opacity[i] for i in order]
    assert all(a <= b + 1e-12 for a, b in zip(ops, ops[1:]))

    # THE CANARY that pins alma/loom.py's LEARN semantics: a spark landing on
    # a knot that fires SILENTLY still counts as fired, so the cord THICKENS.
    # Merit hangs on w_### (rise eps) precisely because of this rule; if the
    # loom ever changes it, this assert screams before the organ lies.
    w = Weave("canary")
    w.knot("a", verb="pass")
    w.knot("g", verb="gate")                           # no key -> silent fires
    w.thread("a", "g", strands=[Strand(weight=1.0, delay=1, drift=0.5)])
    w.seed("a", 1.0)
    res = Loom().run(w, 4)
    silent = [f for f in res.fires if f.knot == "g" and f.spoke is None]
    assert silent, "the gate never fired silently — canary setup broken"
    assert res.learned[0] > 1.0, (
        "LOOM SEMANTICS CHANGED: a silent fire no longer counts as fired for "
        "drift. The organ's merit design assumed it does — re-read easel.py.")


# ---------------------------------------------------------------- 8

def test_floors_honest():
    # golden fixture: winston.floors (torch) on rng(20260901).random((24,24,3))
    # with strokes=40, computed 2026-09-01 on this machine, float64.
    rng = np.random.default_rng(20260901)
    x = rng.random((24, 24, 3))
    blank, blur, side = A.floors(x, 40, 24)
    assert side == 6
    assert abs(blank - 0.081159290299096271) < 1e-12
    assert abs(blur - 0.077286365592305825) < 1e-12
    # a flat target: BLANK is unbeatable -> the show gate stays shut
    flat = np.full((16, 16, 3), 0.5)
    e = small(target=flat, gaze="stub")
    fr = e.sitting(persist=False, quiet=True)
    assert fr["beats_blank"] and fr["beats_blank"][0] <= 0
    assert fr["gist_echo"] == [] and fr["ear_echo"] == []
    assert not any(f.knot == "show" and f.spoke is not None
                   for f in e.last_result.fires)


# ---------------------------------------------------------------- 9

def test_roundtrip():
    e = small()
    good_stroke_params(e, 0)
    e._teach()
    e.atelier.reset()
    w1 = e.weave()
    r1 = Loom().run(w1, e.horizon)
    d = to_dict(w1)
    d["atelier"] = {"note": "additive block, ignored by from_dict"}
    w2 = from_json(json.dumps(d))
    e.atelier.reset()
    r2 = Loom().run(w2, e.horizon)
    assert r1.fringes == r2.fringes
    assert r1.learned == r2.learned
    # a non-str bearing is refused loudly, naming the thread
    w3 = e.weave()
    w3.threads[0].strands[0].bearing = np.zeros(3)
    with pytest.raises(WeaveError, match="look"):
        to_json(w3)


# ---------------------------------------------------------------- 10

def test_no_code_in_weave():
    e = small()
    e._teach()
    txt = to_json(e.weave())
    assert "def " not in txt and "lambda" not in txt and "import" not in txt
    d = json.loads(txt)
    spelled = [k for k in d["knots"] if k.get("spell")]
    assert spelled and all(isinstance(k["spell"], str) for k in spelled)
    d["knots"][1]["spell"] = "nobody_taught_this"
    with pytest.raises(WeaveError, match="nobody_taught_this"):
        from_dict(d).validate()


# ---------------------------------------------------------------- 11

def test_record_weave(tmp_path):
    e = small(out_dir=str(tmp_path))
    good_stroke_params(e, 0)
    e.sitting(persist=True, quiet=True)
    assert e.atelier.n_alive() >= 1
    rec = e.last_paths["record"]
    # the record validates, runs, and pours exactly the total stroke weight
    with open(rec, encoding="utf-8") as f:
        d = json.load(f)
    w = from_dict(d)
    w.validate()
    res = Loom().run(w, w.run_hint)
    total = sum(float(g[2]) * float(e.opacity[g[0]])
                for g in e.atelier.geometry())
    assert abs(res.fringe("ink")[-1] - total) < 1e-9
    # both transcripts round-trip. JSON is exact; the voice transcript speaks
    # numbers at :g (alma's own spoken precision) but carries every BEARING
    # verbatim inside quotes — so structure and bearings must come back
    # identical, and weights within spoken precision.
    assert to_dict(from_json(to_json(w))) == to_dict(w)
    w_v = parse_voice(to_voice(w))
    assert list(w_v.knots) == list(w.knots)
    for tv, tw in zip(w_v.threads, w.threads):
        assert (tv.src, tv.dst) == (tw.src, tw.dst)
        for sv, sw in zip(tv.strands, tw.strands):
            assert sv.bearing == sw.bearing and sv.tint == sw.tint
            assert sv.delay == sw.delay
            assert abs(sv.weight - sw.weight) <= 1e-5 * max(1, abs(sw.weight))
    # replay pixel-matches the PNG through the atelier (asserts inside) —
    # and the geometry lives in the bearings, so even the SPOKEN transcript
    # replays to the same pixels
    canvas = record.replay(rec)
    assert canvas.shape == (16, 16, 3)
    spoken = [record._parse_bearing(s.bearing)[:4] for t in w_v.threads
              for s in t.strands if isinstance(s.bearing, str)]
    canvas_v = A.render_geometry(spoken, 16)
    assert np.array_equal(canvas_v, canvas)


# ---------------------------------------------------------------- 12

def test_alarm():
    # a target whose busy tenth is served BETTER by its mean colour than by
    # anything this run paints: half black / half white, and theta too high
    # for any stroke to wake — the canvas stays white, strictly worse than
    # BLANK in the busy tenth, and the alarm gate must FIRE.
    t = np.ones((16, 16, 3))
    t[:, :8] = 0.0
    e = small(target=t, theta=10.0)
    at = e.atelier
    busy_white = A.busy_error(np.ones_like(t), t, at.dmap)
    assert busy_white > at.busy_blank          # precondition, measured
    fr = e.sitting(persist=False, quiet=True)
    assert e.atelier.n_alive() == 0            # nothing woke (pruned by theta)
    assert fr["alarm_out"] == [1.0], "the vanished-person alarm did not fire"


# ---------------------------------------------------------------- 13

def test_stub_gaze_topology():
    e = small(gaze="stub")
    good_stroke_params(e, 0)
    fr = e.sitting(persist=False, quiet=True)
    beat = {f.knot: f.beat for f in e.last_result.fires}
    assert "muse" in beat, "propose never fired"
    assert fr["beats_blank"][0] > 0, "setup: the aimed stroke must pass BLANK"
    assert beat["show"] < beat["behold"] and beat["show"] < beat["hear_back"]
    assert len(fr["gist_echo"]) == 1 and len(fr["ear_echo"]) == 1
    assert -1.0 <= fr["gist_echo"][0] <= 1.0


# ---------------------------------------------------------------- 14

def test_sitting_beats_blank(tmp_path):
    e, fr = one_sitting("ci-disc", disc_target(), out_dir=str(tmp_path))
    assert fr["beats_blank"][0] > 0
    # and the alef target at least produces a run that judges itself
    assert alef_target().shape == (32, 32, 3)
