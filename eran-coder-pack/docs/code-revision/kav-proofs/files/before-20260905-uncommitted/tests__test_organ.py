"""KAV / קָו — the tests that are allowed to say the model is real.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

KAV was committed with a passing gate and NO tests, which is a window I broke
myself; TZELEM shipped with eight. These are the questions that, left unanswered,
would let a linear regression pass itself off as a model of shape:

  1. does a shape survive being said and heard back?   test_a_shape_survives_being_spoken
  2. is the sentence the SAME sentence every time?     test_one_shape_one_sentence
  3. is the delay line really the context window?      test_the_beat_is_the_position
  4. does the weave agree with the fast body?          test_numpy_is_pinned_to_the_weave
  5. does it beat its floors on unseen shapes?         test_gate1
  6. does heat make it SAY something different?        test_heat_changes_what_it_says
  7. and does what it says still make whole vertices?   test_heat_still_says_whole_vertices
"""
from __future__ import annotations

import os
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
_ORGAN = os.path.abspath(os.path.join(_HERE, ".."))
if _ORGAN not in sys.path:
    sys.path.insert(0, _ORGAN)

import anatomy                                   # noqa: E402
import mesh                                      # noqa: E402
import ruler                                     # noqa: E402
from learn import fit, split                     # noqa: E402


# ------------------------------------------------------------------ the tongue

def test_a_shape_survives_being_spoken():
    """Quantise, canonicalise, speak, hear — and land on the same shape."""
    tris = mesh.box([0, 0, 0], [1, 2, 0.5])
    toks, lo, sc = mesh.speak(tris)
    assert toks[0] == mesh.BOS and toks[-1] == mesh.EOS
    head, tail = mesh.split_sentence(toks)
    assert len(head) % mesh.PER_VERTEX == 0 and len(tail) % mesh.PER_FACE == 0
    back, complaint = mesh.hear(toks, lo, sc)
    assert complaint is None
    ta, fa = mesh.table_and_faces(tris)
    tb, fb = mesh.table_and_faces(back)
    assert np.array_equal(ta, tb) and np.array_equal(fa, fb), "the shape did not survive the round trip"


def test_one_shape_one_sentence():
    """Shuffle the faces and the vertices within them: the sentence must not move.

    Without this the model would spend its life learning that a cube can be
    written 12! ways, and every number in the ruler would be measuring that
    instead of geometry.
    """
    tris = mesh.box([0, 0, 0], [1, 1, 1])
    rng = np.random.default_rng(3)
    shuffled = tris[rng.permutation(len(tris))].copy()
    for i in range(len(shuffled)):          # rotate each face's own corners
        shuffled[i] = np.roll(shuffled[i], rng.integers(0, 3), axis=0)
    assert mesh.speak(tris)[0] == mesh.speak(shuffled)[0]


def test_a_cut_short_face_is_complained_about():
    """A half-spoken face must never be silently dropped."""
    toks, lo, sc = mesh.speak(mesh.box([0, 0, 0], [1, 1, 1]))
    _, complaint = mesh.hear(toks[:-3] + [mesh.EOS], lo, sc)   # two of three indices
    assert complaint is not None and "cut short" in complaint


# ------------------------------------------------------------------ the anatomy

def test_the_beat_is_the_position():
    """The remembered tokens must land on ONE beat, paid for in delay.

    predict_by_weave raises if the fringe speaks more than once, which is exactly
    what happens if the context stops being carried by time.
    """
    p = anatomy.Posture(k=6)
    p.w[0] = np.array([1.0, 0, 0, 0, 0, 0])       # only the OLDEST token counts
    ctx = np.array([9.0, 0, 0, 0, 0, 0])
    assert abs(anatomy.predict_by_weave(ctx, p, 0) - 9.0) < 1e-9

    p2 = anatomy.Posture(k=6)
    p2.w[0] = np.array([0, 0, 0, 0, 0, 1.0])      # only the NEWEST
    assert abs(anatomy.predict_by_weave(ctx, p2, 0) - 0.0) < 1e-9
    ctx2 = np.array([0.0, 0, 0, 0, 0, 7.0])
    assert abs(anatomy.predict_by_weave(ctx2, p2, 0) - 7.0) < 1e-9


def test_numpy_is_pinned_to_the_weave():
    """The fast body must give the loom's answer, or it is a fork."""
    rng = np.random.default_rng(11)
    p = anatomy.Posture(k=8)
    p.w = rng.normal(0, 0.4, size=p.w.shape)
    p.b = rng.normal(0, 1.0, size=p.b.shape)
    for phase in range(anatomy.PHASES):
        ctx = rng.integers(0, mesh.Q, size=8).astype(float)
        a = anatomy.predict_by_weave(ctx, p, phase)
        b = p.predict(ctx, phase)
        assert abs(a - b) < 1e-9, f"phase {phase}: loom {a} vs numpy {b}"


def test_bias_lives_on_the_canvas_knot():
    """With no threads at all the weave must still speak its bias."""
    p = anatomy.Posture(k=3)
    p.b[2] = 4.25
    assert abs(anatomy.predict_by_weave(np.zeros(3), p, 2) - 4.25) < 1e-9


# ------------------------------------------------------------------ the gate

def test_gate1():
    """On shapes it never saw, beat both floors — or it is not a model."""
    r = ruler.measure()
    ok, why = ruler.verdict(r)
    assert ok, "KAV gate 1 failed:\n" + "\n".join(why)


def test_the_sealed_shapes_were_never_fitted():
    """The seal, stated as a test rather than as a promise in a docstring."""
    corpus = mesh.our_corpus()
    train, test = split(corpus, ruler.HELD)
    names = {n for n, _ in train}
    assert not (names & set(ruler.HELD))
    assert {n for n, _ in test} == set(ruler.HELD)


# ------------------------------------------------------------------ the heat

def _small_posture():
    corpus = mesh.our_corpus()
    train, _ = split(corpus, ruler.HELD)
    return fit(train, anatomy.K), corpus


def test_heat_changes_what_it_says():
    """Iddo's stochastic activation, tested where it actually matters.

    An argmax model says the same sentence for ever, which for a generative model
    is the failure mode and not the goal. Heat is the sampler.
    """
    posture, corpus = _small_posture()
    toks, _, _ = mesh.speak(dict(corpus)["drum12"])
    prefix = mesh.split_sentence(toks)[0][:18]        # six vertices to start it

    cold_a = anatomy.continue_shape(prefix, posture, 27, heat=0.0, seed=1)
    cold_b = anatomy.continue_shape(prefix, posture, 27, heat=0.0, seed=2)
    assert cold_a == cold_b, "with no heat the organ must be deterministic"

    hot_a = anatomy.continue_shape(prefix, posture, 27, heat=3.0, seed=1)
    hot_b = anatomy.continue_shape(prefix, posture, 27, heat=3.0, seed=2)
    assert hot_a != hot_b, "heat did not change what it said — the dice never rolled"


def test_heat_still_says_whole_vertices():
    """Sampling may not break the grammar: the vertex half stays whole vertices,
    and hearing it back with the true faces is still a shape, not a complaint."""
    posture, corpus = _small_posture()
    toks, lo, sc = mesh.speak(dict(corpus)["drum12"])
    head, tail = mesh.split_sentence(toks)
    for seed in range(4):
        said = anatomy.continue_shape([mesh.BOS] + head[:18], posture,
                                      len(head) - 18, heat=2.0, seed=seed)
        spoken = mesh.split_sentence(said)[0]
        assert len(spoken) == len(head) and len(spoken) % mesh.PER_VERTEX == 0
        got, complaint = mesh.hear([mesh.BOS] + spoken + [mesh.SEP] + tail + [mesh.EOS], lo, sc)
        assert complaint is None, f"seed {seed}: {complaint}"
        assert len(got) == len(tail) // mesh.PER_FACE


def test_every_token_said_is_a_legal_coordinate():
    """Whatever the heat, the organ may never say a token outside the grid."""
    posture, corpus = _small_posture()
    toks, _, _ = mesh.speak(dict(corpus)["post"])
    head = mesh.split_sentence(toks)[0]
    said = anatomy.continue_shape([mesh.BOS] + head[:9], posture, 90,
                                  heat=40.0, seed=5)       # absurd heat on purpose
    spoken = mesh.split_sentence(said)[0]
    assert all(0 <= t < mesh.Q for t in spoken)
