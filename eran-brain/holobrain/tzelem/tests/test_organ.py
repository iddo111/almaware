"""TZELEM / צלם — the tests that are allowed to say the organ is real.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

Every test here answers one question that, if left unanswered, would let TZELEM be
a pretty lie:

  1. is the ruler's ground truth actually true?      test_the_flow_is_exact
  2. does the LANGUAGE do the occluding?             test_the_beat_is_the_depth
  3. ...or is a hidden sort doing it?                test_flattening_every_delay_breaks_occlusion
  4. is the fast body the same organ?                test_numpy_is_pinned_to_the_weave
  5. does the ruler separate known-bad from good?    test_gate1_ruler_separates
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ORGAN = os.path.abspath(os.path.join(_HERE, ".."))
if _ORGAN not in sys.path:
    sys.path.insert(0, _ORGAN)

import anatomy                                    # noqa: E402
import canvas                                     # noqa: E402
import ruler                                      # noqa: E402
from stage import Box, Camera, Stage, orbit       # noqa: E402


# ---------------------------------------------------------------- 1. the ruler's floor

def test_the_flow_is_exact():
    """Carrying the TRUE image along our flow must land on the true next image.

    This is the foundation the whole organ stands on: if the flow were an estimate,
    every coherence number after it would be measuring the estimator, not the organ.
    """
    st = Stage()
    a, b = orbit(0.0, 120, 90), orbit(4.0, 120, 90)
    truth_a = st.shade(st.gbuffer(a))
    truth_b = st.shade(st.gbuffer(b))
    flow = st.flow(a, b)
    warped, seen = canvas.warp(truth_a, flow)
    m = flow["valid"] & seen
    assert m.sum() > 0.25 * m.size, "the flow discarded most of the image"
    err = np.abs(warped[m] - truth_b[m])
    # The MEDIAN is the honest statistic here, and it is exactly zero: for most of the
    # image the flow lands on the very pixel it should. The mean carries a tail from
    # nearest-neighbour rounding on a checkerboard seen at a grazing angle, where half
    # a pixel is a whole square — that is the resampler, not the flow, and measuring
    # the flow through it would be measuring the wrong thing.
    assert np.median(err) == 0.0, f"flow is not exact: median error {np.median(err):.5f}"
    assert np.percentile(err, 75) < 0.02, (
        f"flow is not exact: 75th percentile {np.percentile(err, 75):.5f}")


# ---------------------------------------------------------------- 2. the facade

def _two_strokes(near_first: bool):
    """Two strokes on ONE line of sight, so only depth can decide which is seen."""
    cam = Camera(eye=[0.0, 0.0, 4.0], target=[0.0, 0.0, 0.0], width=8, height=8)
    near = np.array([0.0, 0.0, 1.0])
    far = np.array([0.0, 0.0, -1.0])
    pts = np.stack([near, far] if near_first else [far, near])
    return anatomy.Strokes(
        point=pts,
        normal=np.tile([0.0, 0.0, 1.0], (2, 1)),
        rgb=np.array([[1.0, 0.0, 0.0], [0.0, 0.0, 1.0]]),
        radius=np.array([0.2, 0.2]),
    ), cam


def test_the_beat_is_the_depth():
    """Move a stroke farther away. Change no code. The picture must occlude differently.

    This is TZELEM's facade test, the counterpart of WINSTON's "the strand IS the
    stroke". Nothing in anatomy.py compares two depths — the near stroke wins only
    because its spark arrives on an earlier beat.
    """
    s, cam = _two_strokes(near_first=True)
    tiles = anatomy.paint_tiles_weave(s, cam, tiles=2)
    winner_near = tiles[tiles != anatomy.EMPTY]
    assert (winner_near == 1).all(), "the near stroke (index 0) should own the canvas"

    # now push stroke 0 BEHIND stroke 1 — the only thing that changes is a distance
    s.point[0] = np.array([0.0, 0.0, -3.0])
    tiles2 = anatomy.paint_tiles_weave(s, cam, tiles=2)
    winner_far = tiles2[tiles2 != anatomy.EMPTY]
    assert (winner_far == 2).all(), (
        "after moving it farther the OTHER stroke must be seen; occlusion did not "
        "follow the depth, so the beat is not carrying it")


def test_flattening_every_delay_breaks_occlusion():
    """If a hidden sort were doing the work, flattening the delays would not matter.

    It does matter: with every strand at delay 1 the sparks all arrive together and
    `fringe` sums them, so the canvas holds a value that belongs to no stroke. The
    occlusion lives in the delays and nowhere else.
    """
    s, cam = _two_strokes(near_first=True)
    w, _ = anatomy.weave_for(s, cam, tiles=2)
    from alma import Loom
    for t in w.threads:
        for st in t.strands:
            st.delay = 1
    res = Loom().run(w)
    got = [rec[0][1] for rec in res.fringes.values() if rec]
    assert got, "nothing reached the canvas at all"
    assert any(v not in (1.0, 2.0) for v in got), (
        "flattening the delays left the picture unchanged — something other than "
        "the beat is deciding what is visible")


# ---------------------------------------------------------------- 3. the pin

def test_numpy_is_pinned_to_the_weave():
    """The fast body must give the DEFINITION's answer, exactly, or it is a fork."""
    st = Stage()
    cam = orbit(0.0, 96, 72)
    s = anatomy.scatter(st, cam, n=140, seed=3)
    a = anatomy.paint_tiles_weave(s, cam, tiles=10)
    b = anatomy.paint_tiles_numpy(s, cam, tiles=10)
    assert np.array_equal(a, b), (
        f"numpy and the loom disagree on {int((a != b).sum())} tiles")


def test_delays_never_invert_depth():
    """Farther may tie, may be pushed later — it may never arrive earlier."""
    st = Stage()
    cam = orbit(0.0, 96, 72)
    s = anatomy.scatter(st, cam, n=200, seed=11)
    px, py, z = cam.project(s.point)
    depth = np.linalg.norm(s.point - cam.eye, axis=-1)
    tile = anatomy._tile_of(px, py, cam, 10)
    beats = anatomy._delays(depth, tile)
    for t in np.unique(tile[tile >= 0]):
        m = tile == t
        d, b = depth[m], beats[m]
        order = np.argsort(d)
        assert np.all(np.diff(b[order]) > 0), (
            "inside one tile the beats must strictly increase with depth")


# ---------------------------------------------------------------- 4. the gate

@pytest.mark.slow
def test_gate1_ruler_separates():
    """A ruler that cannot tell boiling from steady measures nothing."""
    r = ruler.measure(width=120, height=90, n_strokes=600, sweep_deg=4.0)
    ok, why = ruler.verdict(r)
    assert ok, "gate 1 failed:\n" + "\n".join(why)


def test_a_flat_grey_organ_would_fail_the_gate():
    """The second axis exists to catch the emptiest possible organ. Prove it does."""
    r = ruler.measure(width=96, height=72, n_strokes=400, sweep_deg=4.0)
    flat = dict(r)
    flat["coherence"] = dict(r["coherence"], TZELEM_world_anchored=0.0)
    flat["fidelity_mse"] = dict(r["fidelity_mse"],
                                TZELEM_world_anchored=r["fidelity_mse"]
                                ["BLANK_best_flat_colour"] + 0.01)
    ok, _ = ruler.verdict(flat)
    assert not ok, "a perfectly steady, perfectly useless organ passed the gate"


def test_the_scene_is_ours():
    """GATE 0: the stage is geometry in this repo, not data from anywhere."""
    st = Stage()
    assert all(isinstance(b, Box) for b in st.boxes)
    g = st.gbuffer(orbit(0.0, 40, 30))
    assert g["mask"].any() and np.isfinite(g["depth"][g["mask"]]).all()


# --------------------------------------------- 5. the colour travels the weave
#
# Added 2026-09-05, when ALMA v0.4 gave a spark a WIDTH and `anatomy.py` stopped
# having to carry a palette index instead of a colour.
#
# THE QUESTION THESE ANSWER, and it is a facade question, not a feature question:
# is the colour genuinely going THROUGH the weave, or is the weave decoration
# bolted onto a lookup that would have produced the same picture anyway?
#
# The knife is the one SARID and MOREH use — cut a cord and a real number must
# move — sharpened for colour: a LOOKUP TABLE CANNOT BE DIMMED BY A WEIGHT. If
# halving a strand's weight halves the painted colour, the colour was on the cord.

def _one_stroke(rgb=(0.84, 0.36, 0.26)):
    cam = Camera(eye=[0.0, 0.0, 4.0], target=[0.0, 0.0, 0.0], width=8, height=8)
    return anatomy.Strokes(
        point=np.array([[0.0, 0.0, 1.0]]),
        normal=np.array([[0.0, 0.0, 1.0]]),
        rgb=np.array([list(rgb)], dtype=np.float64),
        radius=np.array([0.2]),
    ), cam


def test_the_loom_paints_a_real_colour_not_an_index():
    """The tile holds the stroke's RGB, to full float precision."""
    s, cam = _one_stroke((0.84, 0.36, 0.26))
    img = anatomy.paint_tiles_weave_colour(s, cam, tiles=2)
    painted = img.reshape(-1, 3)
    lit = [c for c in painted if not np.allclose(c, (0.82, 0.87, 0.94))]
    assert lit, "the stroke reached no tile at all"
    for c in lit:
        assert np.allclose(c, (0.84, 0.36, 0.26)), (
            f"the loom painted {c}, not the stroke's colour — a chord lost voices")


def test_the_colour_travels_the_cord():
    """THE FACADE TEST FOR COLOUR: halve the cord, halve the colour.

    A palette lookup is indexed by WHO won, so it is blind to how open the cord
    was. If this picture dims continuously with the weight, the colour is riding
    the strand — which is the whole claim ALMA v0.4 exists to let TZELEM make.
    """
    s, cam = _one_stroke((0.8, 0.4, 0.2))
    BG = (0.82, 0.87, 0.94)

    # The knife goes through the PUBLIC painter, not around it. An earlier version
    # of this test built its own weave and ran the loom itself; a mutation that
    # turned paint_tiles_weave_colour into an index-and-lookup then passed every
    # test in this file. A facade test that does not enter the function it is
    # judging is not a facade test.
    full = anatomy.paint_tiles_weave_colour(s, cam, tiles=2)
    half = anatomy.paint_tiles_weave_colour(s, cam, tiles=2, cut=0.5)

    lit = [(y, x) for y in range(full.shape[0]) for x in range(full.shape[1])
           if not np.allclose(full[y, x], BG)]
    assert lit, "the stroke reached no tile at all"
    for y, x in lit:
        assert np.allclose(half[y, x], full[y, x] * 0.5), (
            f"tile ({y},{x}): halving the cord gave {half[y, x]}, not half of "
            f"{full[y, x]}. The colour is not on the strand — the weave is "
            f"decoration over a lookup.")


def test_cutting_the_cord_puts_the_colour_out():
    """Weight 0 is a shut cord. A shut cord delivers black, not the old colour."""
    s, cam = _one_stroke((0.8, 0.4, 0.2))
    BG = (0.82, 0.87, 0.94)
    full = anatomy.paint_tiles_weave_colour(s, cam, tiles=2)
    dark = anatomy.paint_tiles_weave_colour(s, cam, tiles=2, cut=0.0)
    lit = [(y, x) for y in range(full.shape[0]) for x in range(full.shape[1])
           if not np.allclose(full[y, x], BG)]
    assert lit, "the stroke reached no tile at all"
    for y, x in lit:
        assert np.allclose(dark[y, x], 0.0), (
            f"tile ({y},{x}): a cut cord still delivered {dark[y, x]}; the "
            f"colour did not come down it")


def test_the_beat_is_still_the_depth_when_the_spark_is_a_colour():
    """The v0.4 weave must occlude by the same law as the v0.3 one, unchanged."""
    s, cam = _two_strokes(near_first=True)          # stroke 0 red, stroke 1 blue
    near = anatomy.paint_tiles_weave_colour(s, cam, tiles=2).reshape(-1, 3)
    lit = [c for c in near if not np.allclose(c, (0.82, 0.87, 0.94))]
    assert lit and all(np.allclose(c, (1.0, 0.0, 0.0)) for c in lit), \
        "the near stroke is red and should own the canvas"

    s.point[0] = np.array([0.0, 0.0, -3.0])          # only a distance changes
    far = anatomy.paint_tiles_weave_colour(s, cam, tiles=2).reshape(-1, 3)
    lit = [c for c in far if not np.allclose(c, (0.82, 0.87, 0.94))]
    assert lit and all(np.allclose(c, (0.0, 0.0, 1.0)) for c in lit), (
        "after moving the red stroke behind the blue one the canvas must be BLUE; "
        "occlusion stopped following the depth once the spark became a chord")


def test_numpy_colour_is_pinned_to_the_weave():
    """The fast body must give the DEFINITION's picture, exactly, or it is a fork."""
    st = Stage()
    cam = orbit(0.0, 96, 72)
    s = anatomy.scatter(st, cam, n=140, seed=3)
    a = anatomy.paint_tiles_weave_colour(s, cam, tiles=10)
    b = anatomy.paint_tiles_numpy_colour(s, cam, tiles=10)
    assert np.array_equal(a, b), (
        f"the loom and numpy disagree on {int((a != b).any(axis=-1).sum())} tiles")


def test_the_loom_and_the_palette_agree():
    """The chain between the new definition and the old fast body.

    The tile the INDEX weave says stroke i owns must be the colour the CHORD weave
    paints. If these two ever drift apart, one of them is lying about the picture.
    """
    st = Stage()
    cam = orbit(0.0, 96, 72)
    s = anatomy.scatter(st, cam, n=140, seed=3)
    idx = anatomy.paint_tiles_weave(s, cam, tiles=10)        # v0.3: who owns it
    col = anatomy.paint_tiles_weave_colour(s, cam, tiles=10)  # v0.4: what colour

    from palette import Palette
    pal = Palette.of(s)
    checked = 0
    for y in range(idx.shape[0]):
        for x in range(idx.shape[1]):
            if idx[y, x] == anatomy.EMPTY:
                assert np.allclose(col[y, x], (0.82, 0.87, 0.94)), (
                    f"tile ({y},{x}): nobody owns it but it was painted "
                    f"{col[y, x]}")
                continue
            want = pal.table[int(idx[y, x]) - 1]
            assert np.allclose(col[y, x], want), (
                f"tile ({y},{x}): the index weave says stroke "
                f"{int(idx[y, x]) - 1} ({want}) but the chord weave painted "
                f"{col[y, x]}")
            checked += 1
    assert checked > 20, f"only {checked} tiles were owned; the test proved little"
