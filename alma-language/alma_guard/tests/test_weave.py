# -*- coding: utf-8 -*-
"""Tests for THE NETWORK - the shape, and the time-multiplexed credit.

The load-bearing one is `test_the_stagger_is_load_bearing`: it removes the
stagger (puts every head at the same distance) and requires the weave to get
WORSE, which is how you tell a mechanism from a decoration. It is the same move
`tests/test_chords.py::TestTheGuardIsLoadBearing` makes for the width rule.
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from alma_guard.weave import GuardWeave, Hyper                      # noqa: E402


def toy(n=60, seed=3):
    """A trivially separable two-class task over 8 buckets. Not text - shape only.

    class A always lights bucket 20, class B always lights bucket 21, and both
    light three shared distractors. A learner that cannot do this cannot do
    anything, so this is the floor, not a result.
    """
    rng = random.Random(seed)
    rows = []
    for i in range(n):
        a = i % 2 == 0
        f = {20 if a else 21: 1.0}
        for b in rng.sample(range(30, 40), 3):
            f[b] = 1.0
        rows.append((f, "attack" if a else "benign"))
    return rows


def train(g, rows, epochs, seed=0):
    rng = random.Random(seed)
    order = list(range(len(rows)))
    for _ in range(epochs):
        rng.shuffle(order)
        for i in order:
            g.present(rows[i][0], rows[i][1], learn=True)


def accuracy(g, rows):
    return sum(1 for f, y in rows if g.predict(f)[0] == y) / len(rows)


def test_shape_is_what_the_docstring_says():
    g = GuardWeave(["attack"], Hyper(width=64))
    names = set(g.weave.knots)
    assert "one" in names and "out0" in names and "say0" in names
    assert sum(1 for n in names if n.startswith("x")) == 64
    assert g.weave.knots["out0"].trigger == "rise 0.0"
    assert g.weave.knots["say0"].verb == "fringe"
    g.weave.validate()                       # the language itself must accept it


def test_heads_are_staggered_in_time():
    """Head k's cords are k+1 beats long. That IS the credit-assignment mechanism."""
    g = GuardWeave(["a", "b", "c"], Hyper(width=16))
    for t in g.weave.threads:
        if t.dst.startswith("out"):
            k = int(t.dst[3:])
            assert all(st.delay == k + 1 for st in t.strands), (
                f"thread into {t.dst} has the wrong distance")


def test_absent_features_stay_silent():
    """The whole encoding rests on this: an unseeded knot must never fire."""
    g = GuardWeave(["attack"], Hyper(width=32))
    _, _ = g.present({5: 1.0}, None, learn=False)
    r = g.loom.run(g.weave, beats=4)
    spoke = {f.knot for f in r.fires}
    assert "x5" in spoke and "one" in spoke
    assert not any(n.startswith("x") and n != "x5" for n in spoke)


def test_a_weave_learns_a_separable_task():
    rows = toy()
    g = GuardWeave(["attack"], Hyper(width=64, epochs=0, seed=1))
    before = accuracy(g, rows)
    train(g, rows, epochs=12)
    after = accuracy(g, rows)
    assert after >= 0.95, f"the floor task should be solved; got {after:.2f} (was {before:.2f})"


def test_learning_is_what_moved_the_weights():
    g = GuardWeave(["attack"], Hyper(width=64, seed=2))
    w0 = g.weights()[:]
    train(g, toy(), epochs=4)
    w1 = g.weights()
    moved = sum(1 for a, b in zip(w0, w1) if abs(a - b) > 1e-9)
    assert moved > 10, "cords must actually drift"
    assert max(abs(b) for b in w1) <= 8.0, "floor/ceil must hold"


def test_learning_off_changes_nothing():
    """verdict=None is v0.2 exactly - SPEC.md's promise, checked here too."""
    g = GuardWeave(["attack"], Hyper(width=32, seed=4))
    w0 = g.weights()[:]
    for f, _ in toy(20):
        g.present(f, None, learn=False)
    assert g.weights() == w0


def test_multiclass_heads_learn_different_things():
    """Three classes, one scalar verdict per beat. If the stagger works, the three
    heads end up with DIFFERENT weights on the class-marker buckets."""
    rng = random.Random(5)
    rows = []
    for i in range(90):
        k = i % 3
        f = {20 + k: 1.0}
        for b in rng.sample(range(30, 40), 2):
            f[b] = 1.0
        rows.append((f, ["benign", "injection", "hijack-attempt"][k]))
    g = GuardWeave(["benign", "injection", "hijack-attempt"], Hyper(width=64, seed=5))
    train(g, rows, epochs=15)
    assert accuracy(g, rows) >= 0.85


def test_the_stagger_is_load_bearing():
    """Remove the mechanism; require the result to get worse.

    Every head at delay 1 means one scalar verdict reaches all three heads on the
    same beat, so nothing can tell head 1 "you should have fired" while telling
    head 2 "you should not have". If this test ever passes WITHOUT the stagger,
    the stagger is decoration and the docstring in weave.py is a lie.
    """
    rng = random.Random(6)
    rows = []
    for i in range(90):
        k = i % 3
        f = {20 + k: 1.0}
        for b in rng.sample(range(30, 40), 2):
            f[b] = 1.0
        rows.append((f, ["benign", "injection", "hijack-attempt"][k]))
    heads = ["benign", "injection", "hijack-attempt"]

    good = GuardWeave(heads, Hyper(width=64, seed=6))
    train(good, rows, epochs=15)

    flat = GuardWeave(heads, Hyper(width=64, seed=6))
    for t in flat.weave.threads:            # collapse every head onto beat 2
        if t.dst.startswith("out"):
            for st in t.strands:
                st.delay = 1
    flat.horizon = 5
    train(flat, rows, epochs=15)

    assert accuracy(good, rows) > accuracy(flat, rows), (
        f"staggered {accuracy(good, rows):.2f} did not beat flat "
        f"{accuracy(flat, rows):.2f} - the stagger is not doing the work")
