"""GADAL — the tests that would catch a lie.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

The one that matters: a growth step must not change what the model says. If widening
moves the outputs even slightly, every comparison after it is measuring a different
model and the whole mechanism is unfalsifiable.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from grow import Gardener, noise_floor          # noqa: E402
from net import Net                             # noqa: E402


def _net(seed=0, widths=(4,), act="relu"):
    return Net(6, 3, widths=widths, seed=seed, act=act)


def _X(n=32, d=6, seed=7):
    return np.random.default_rng(seed).normal(size=(n, d))


# ---------------------------------------------------------------- function preservation
def _ulp(a):
    """The tolerance a matmul is allowed: a few ULP of the largest output seen."""
    return 8.0 * np.spacing(max(float(np.abs(a).max()), 1.0))


@pytest.mark.parametrize("mode", ["zero", "split"])
@pytest.mark.parametrize("act", ["relu", "tanh"])
@pytest.mark.parametrize("k", [1, 3, 7])
def test_widen_is_function_preserving_to_float_error(mode, act, k):
    n, X = _net(act=act), _X()
    before = n.forward(X)
    n.widen(k, mode=mode)
    after = n.forward(X)
    assert n.widths == (4 + k,)
    assert np.max(np.abs(after - before)) <= _ulp(before), "widening moved the output"


def test_split_widen_splits_the_outgoing_weights_bit_exactly():
    """The invariant under the tolerance above: the two halves must re-sum EXACTLY.
    A tolerance on the output could hide a real drift; this equality cannot."""
    n = _net(widths=(4,))
    row = n.W[1][2, :].copy()
    n.widen(1, pick=lambda net, li: 2, mode="split")
    assert np.array_equal(n.W[1][2, :] + n.W[1][-1, :], row)
    assert np.array_equal(n.W[0][:, 2], n.W[0][:, -1])
    assert n.b[0][2] == n.b[0][-1]


def test_zero_widen_adds_a_new_direction_with_no_fan_out():
    """The whole point of "zero": preserved because the fan-out is 0, and NOT a duplicate
    of any unit already there, so there is no symmetry to wait out."""
    n = _net(widths=(4,))
    n.widen(1, mode="zero")
    assert np.array_equal(n.W[1][-1, :], np.zeros(3))
    assert n.b[0][-1] == 0.0
    for j in range(4):
        assert not np.allclose(n.W[0][:, j], n.W[0][:, -1]), "the new unit duplicates unit %d" % j


def test_zero_widen_new_unit_starts_learning_immediately():
    """A zero fan-out is only useful if it does not also mean a zero gradient."""
    n, X = _net(widths=(4,)), _X()
    Y = np.random.default_rng(2).normal(size=(len(X), 3))
    n.widen(1, mode="zero")
    _, gW, _ = n.grads(X, Y)
    assert np.abs(gW[1][-1, :]).max() > 1e-9, "the new unit's fan-out has no gradient"


def test_widen_preserved_through_several_layers():
    for mode in ("zero", "split"):
        n, X = _net(widths=(5, 4, 3)), _X()
        before = n.forward(X)
        for layer in (0, 1, 2):
            n.widen(2, layer=layer, mode=mode)
            assert np.max(np.abs(n.forward(X) - before)) <= _ulp(before), \
                f"{mode} layer {layer} moved it"


def test_deepen_is_exactly_function_preserving():
    n, X = _net(widths=(5,)), _X()
    before = n.forward(X)
    n.deepen()
    assert n.widths == (5, 5)
    assert np.max(np.abs(n.forward(X) - before)) == 0.0     # identity matmul: bit exact


def test_widen_breaks_symmetry_so_the_new_unit_is_not_dead():
    """Exactly-preserving is worthless if the copies can never separate again."""
    n, X = _net(), _X()
    Y = np.random.default_rng(1).normal(size=(len(X), 3))
    n.widen(1, mode="split")
    j, new = int(np.argmax(np.linalg.norm(n.W[1][:-1], axis=1))), n.W[0].shape[1] - 1
    _, gW, _ = n.grads(X, Y)
    assert not np.allclose(gW[0][:, j], gW[0][:, new]), "the copied unit gets an identical gradient"
    for _ in range(20):
        n.step(X, Y, lr=0.05)
    assert not np.allclose(n.W[0][:, j], n.W[0][:, new]), "the copies never separated"


def test_widen_refuses_a_linear_model():
    with pytest.raises(ValueError):
        Net(4, 2, widths=()).widen(1)


# ---------------------------------------------------------------- pruning
def test_prune_of_a_dead_unit_does_not_change_the_output():
    n, X = _net(), _X()
    n.W[1][2, :] = 0.0                                   # unit 2 now reaches nothing
    before = n.forward(X)
    u = n.utility(X)
    assert u[2] == 0.0
    keep = u > 0
    n.fold_constant(X, keep)
    assert n.prune(keep) == 1
    assert np.max(np.abs(n.forward(X) - before)) < 1e-12


def test_prune_folds_a_constant_unit_into_the_bias():
    """A unit that never varies carries a constant, not information. Removing it after
    folding must move the output by nothing."""
    n, X = _net(), _X()
    n.W[0][:, 1] = 0.0
    n.b[0][1] = 0.7                                       # always relu(0.7) = 0.7
    before = n.forward(X)
    u = n.utility(X)
    assert u[1] == pytest.approx(0.0, abs=1e-12)
    keep = np.ones(4, bool)
    keep[1] = False
    n.fold_constant(X, keep)
    n.prune(keep)
    assert np.max(np.abs(n.forward(X) - before)) < 1e-12


def test_prune_refuses_to_empty_a_layer():
    n = _net()
    with pytest.raises(ValueError):
        n.prune(np.zeros(4, bool))


# ---------------------------------------------------------------- the instrument
def test_noise_floor_is_the_within_group_spread():
    Y = np.array([[0.0], [2.0], [10.0], [10.0]])
    M = np.ones_like(Y)
    g = np.array([0, 0, 1, 1])
    f = noise_floor(Y, M, g)
    assert f["floor"] == pytest.approx((1.0 + 1.0 + 0.0 + 0.0) / 4)
    assert f["usable"] and f["n_groups"] == 2 and f["n_groups_repeated"] == 2


def test_noise_floor_says_so_when_no_input_repeats():
    Y = np.arange(4.0).reshape(4, 1)
    f = noise_floor(Y, np.ones_like(Y), np.arange(4))
    assert f["floor"] == 0.0 and f["usable"] is False


def test_noise_floor_ignores_masked_entries():
    Y = np.array([[0.0, 99.0], [2.0, -99.0]])
    M = np.array([[1.0, 0.0], [1.0, 0.0]])
    f = noise_floor(Y, M, np.array([0, 0]))
    assert f["floor"] == pytest.approx(2.0 / 2)          # only column 0 counted


# ---------------------------------------------------------------- the policy
def test_gardener_never_grows_without_a_train_plateau():
    """Condition A: while train is still descending, no growth step may be logged."""
    rng = np.random.default_rng(0)
    X = rng.normal(size=(80, 6))
    Y = np.tanh(X @ rng.normal(size=(6, 3)))
    g = Gardener(6, 3, seed=0, max_epochs=25, check_every=25, patience=4)
    g.fit(X, Y, np.ones_like(Y), X, Y, np.ones_like(Y), groups_tr=np.arange(80))
    assert not [r for r in g.log if r["kind"] == "grow"]


def test_gardener_refuses_to_grow_when_the_gap_is_wide():
    """Condition C: a model already memorising must not be given more room."""
    rng = np.random.default_rng(3)
    X = rng.normal(size=(12, 6))
    Y = rng.normal(size=(12, 3))                          # unlearnable: pure memorisation
    Xv, Yv = rng.normal(size=(40, 6)), rng.normal(size=(40, 3))
    g = Gardener(6, 3, seed=0, gap_max=0.0, max_epochs=2000)
    g.fit(X, Y, np.ones_like(Y), Xv, Yv, np.ones_like(Yv), groups_tr=np.arange(12))
    halts = [r for r in g.log if r["kind"] == "halt_growth"]
    assert halts and "C_not_memorising" in halts[0]["reason"]


def test_condition_B_halts_growth_once_train_reaches_the_measured_floor():
    """B is the leg that makes "underfit" a number. Give a model a task it can fit down to
    the irreducible spread of its repeated inputs, and B must be the reason growth stops --
    not a plateau, not the gap. Without this the floor is decoration."""
    rng = np.random.default_rng(17)
    base = rng.normal(size=(6, 6))
    X = np.repeat(base, 10, axis=0)                       # 6 inputs, 10 noisy answers each
    clean = np.repeat(base @ rng.normal(size=(6, 3)), 10, axis=0)
    Y = clean + 0.30 * rng.normal(size=clean.shape)       # the noise IS the floor
    M = np.ones_like(Y)
    g = np.repeat(np.arange(6), 10)
    fl = noise_floor(Y, M, g)
    assert fl["usable"] and fl["floor"] > 0.05
    gd = Gardener(6, 3, seed=0, max_epochs=8000, gap_max=1e9, grow_patience=99)
    gd.fit(X, Y, M, X, Y, M, groups_tr=g)
    halt = next(r for r in gd.log if r["kind"] == "halt_growth")
    assert halt["conditions"]["B_underfit"] is False, "B never became the binding constraint"
    assert "B_underfit" in halt["reason"]
    assert halt["train_mse"] <= fl["floor"] * 1.10 + 1e-9, "halted above the floor it claimed"


def test_every_growth_step_logs_the_numbers_that_justified_it():
    rng = np.random.default_rng(5)
    X = np.repeat(rng.normal(size=(20, 6)), 3, axis=0)
    Y = np.tanh(X @ rng.normal(size=(6, 3)) * 3) + 0.05 * rng.normal(size=(60, 3))
    g = Gardener(6, 3, seed=0, max_epochs=4000)
    g.fit(X, Y, np.ones_like(Y), X, Y, np.ones_like(Y), groups_tr=np.repeat(np.arange(20), 3))
    grows = [r for r in g.log if r["kind"] == "grow"]
    assert grows, "nothing grew on a clearly underfit task"
    for r in grows:
        for key in ("width_before", "width_after", "train_mse", "val_mse", "gap", "floor",
                    "conditions", "preserve_max_abs_delta", "params_before", "params_after"):
            assert key in r, f"growth step {r['i']} did not log {key}"
        assert r["preserve_max_abs_delta"] < 1e-12, "a growth step moved the model"
        assert r["conditions"]["A_train_plateau"] is True
        assert r["conditions"]["B_underfit"] is True


def test_gardener_keeps_the_best_val_size_not_the_last_size():
    rng = np.random.default_rng(11)
    X = np.repeat(rng.normal(size=(15, 6)), 3, axis=0)
    Y = np.tanh(X @ rng.normal(size=(6, 3))) + 0.1 * rng.normal(size=(45, 3))
    Xv = rng.normal(size=(60, 6))
    Yv = np.tanh(Xv @ np.zeros((6, 3)))
    g = Gardener(6, 3, seed=0, max_epochs=3000)
    net, best = g.fit(X, Y, np.ones_like(Y), Xv, Yv, np.ones_like(Yv),
                      groups_tr=np.repeat(np.arange(15), 3))
    assert net.widths == best["widths"], "the returned net is not the best-val snapshot"
    assert g.log[-1]["kind"] == "done"
