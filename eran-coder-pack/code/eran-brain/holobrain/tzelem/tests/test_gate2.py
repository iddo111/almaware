"""TZELEM / צלם — GATE 2: colour, painterly strokes, and resolution-freedom.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

Each test here answers one question that, unanswered, would let "4K TZELEM" be an
upscale with a nice name:

  1. can colour move an edge?              test_palette_lookup_does_not_change_occlusion
  2. is a soft edge a hidden sort?         test_soft_edge_cannot_paint_through_an_occluder
  3. does a stroke keep its shape?         test_a_stroke_is_the_same_size_in_the_world
  4. is 4K the same painting as 480p?      test_ownership_is_resolution_free
  5. does the picture survive the zoom?    test_fidelity_does_not_decay_at_4k
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

import anatomy                                   # noqa: E402
import canvas                                    # noqa: E402
import gate2                                     # noqa: E402
from palette import Palette                      # noqa: E402
from stage import Camera, Stage, orbit           # noqa: E402


# ------------------------------------------------------- 1. colour cannot occlude

def test_palette_lookup_does_not_change_occlusion():
    """Repaint every stroke a random colour. Not one pixel may change owner.

    The weave's spark is an INDEX; the palette is a table read afterwards. If
    colour could reach the ownership decision, this would fail — and TZELEM would
    have quietly grown a second, colour-dependent hidden-surface rule.
    """
    st = Stage()
    cam = orbit(0.0, 240, 180)
    s = anatomy.scatter(st, cam, n=400, seed=5)

    own_a, _, _ = canvas.ownership(cam, s)
    own_b, _, _ = canvas.ownership(cam, s)
    assert np.array_equal(own_a, own_b), "ownership is not even deterministic"

    true_pal = Palette.of(s)
    wrong_pal = Palette.shuffled(s, seed=99)

    img_true = canvas.render(st, cam, s, pal=true_pal)
    img_wrong = canvas.render(st, cam, s, pal=wrong_pal)

    # the palette DID something...
    assert not np.allclose(img_true, img_wrong), (
        "swapping the whole palette changed nothing — colour is not being read")

    # ...but it did nothing to WHO OWNS WHAT.
    own_after, _, _ = canvas.ownership(cam, s)
    assert np.array_equal(own_a, own_after)

    # and the hard-edged picture is EXACTLY the palette indexed by the owner
    hard = canvas.render(st, cam, s, pal=true_pal, soft=False)
    assert np.array_equal(hard, true_pal.lookup(own_a))


def test_soft_edge_cannot_paint_through_an_occluder():
    """A stroke hidden behind a nearer one must contribute NOTHING, alpha or not.

    Soft edges are where renderers smuggle a sort back in. Two strokes on one line
    of sight, the far one bright red: if any red reaches the canvas, the falloff
    has become a blend across depth and the occlusion claim is dead.
    """
    cam = Camera(eye=[0.0, 0.0, 4.0], target=[0.0, 0.0, 0.0], width=64, height=64)
    s = anatomy.Strokes(
        point=np.array([[0.0, 0.0, 1.0], [0.0, 0.0, -1.0]]),
        normal=np.tile([0.0, 0.0, 1.0], (2, 1)),
        rgb=np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]]),   # near black, far RED
        radius=np.array([0.30, 0.30]),
    )
    img = canvas.render(None, cam, s, style="round")
    own, _, _ = canvas.ownership(cam, s, style="round")
    core = own == 0
    assert core.any(), "the near stroke did not land on the canvas at all"
    assert float(img[core][..., 0].max()) < 1e-6, (
        "red bled through the near stroke — the soft edge is blending across depth")


# ------------------------------------------------------- 2. the stroke is a size

def test_a_stroke_is_the_same_size_in_the_world():
    """Double the canvas, double the stroke. That is what resolution-free means."""
    st = Stage()
    s = anatomy.scatter(st, orbit(0.0, 240, 135), n=60, seed=3)
    f1 = canvas.footprint(orbit(0.0, 480, 270), s)
    f2 = canvas.footprint(orbit(0.0, 960, 540), s)
    live = f1["live"] & f2["live"]
    ratio = f2["r"][live] / f1["r"][live]
    assert np.allclose(ratio, 2.0, atol=1e-6), (
        f"pixel radius did not double with the canvas: {ratio.min()}..{ratio.max()}")
    # the jitter is drawn from the stroke, not the canvas: same angle both times
    assert np.allclose(f1["ux"][live], f2["ux"][live], atol=1e-9)


# --------------------------------------------------------- 3. the gate itself

@pytest.mark.slow
def test_ownership_is_resolution_free():
    """480x270 vs 3840x2160: the same stroke must own the same place, >= 95%."""
    r = gate2.resolution_free(n_strokes=1200, factor=8, verbose=False)
    assert r["ownership_agreement"] >= 0.95, (
        f"only {r['ownership_agreement'] * 100:.2f}% of the 4K frame agrees with "
        f"the native 480p frame about which stroke owns which pixel")


@pytest.mark.slow
def test_fidelity_does_not_decay_at_4k():
    """The painting must not get worse when you look at it closer."""
    r = gate2.resolution_free(n_strokes=1200, factor=8, verbose=False)
    assert r["fidelity_big"] <= r["fidelity_small"] * 1.1, (
        f"fidelity decayed: {r['fidelity_small']:.5f} at 480p -> "
        f"{r['fidelity_big']:.5f} at 4K")


def test_ownership_is_resolution_free_cheaply():
    """The same claim at 240x135 vs 960x540, small enough to run every time."""
    st = Stage()
    s = anatomy.scatter(st, orbit(0.0, 240, 135), n=500, seed=7)
    own_s, _, _ = canvas.ownership(orbit(0.0, 240, 135), s)
    own_b, _, _ = canvas.ownership(orbit(0.0, 960, 540), s)
    agree = float((gate2.block_mode(own_b, 4) == own_s).mean())
    assert agree >= 0.95, f"ownership agreement only {agree * 100:.2f}%"


def test_block_mode_is_a_majority_not_an_average():
    """Averaging stroke indices would be nonsense; make sure we never do it."""
    a = np.array([[3, 3, 9, 9], [3, 7, 9, 9], [1, 1, 1, 8], [1, 1, 8, 8]])
    got = gate2.block_mode(a, 2)
    assert np.array_equal(got, np.array([[3, 9], [1, 8]])), got
