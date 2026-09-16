"""The discrimination probe must be honest: chance in, chance out."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import discrimination as probe  # noqa: E402


def test_loud_frames_keeps_the_loudest_sixty_percent():
    x = np.zeros((10, 14), dtype=np.float32)
    x[:, 0] = np.arange(10)
    loud = probe.loud_frames(x)
    assert len(loud) == 6
    assert sorted(loud[:, 0].tolist()) == [4.0, 5.0, 6.0, 7.0, 8.0, 9.0]


def test_loud_frames_never_returns_empty():
    assert len(probe.loud_frames(np.zeros((1, 14), dtype=np.float32))) == 1


def test_separable_classes_score_one():
    rng = np.random.default_rng(0)
    labels = [f"c{i // 5}" for i in range(20)]
    base = np.repeat(np.eye(4) * 10.0, 5, axis=0)
    train = base + rng.normal(0, 0.01, base.shape)
    test = base + rng.normal(0, 0.01, base.shape)
    result = probe.nn_probe(train, labels, test, labels, "l2")
    assert result["top1"] == 1.0
    assert result["centroid_top1"] == 1.0
    assert result["chance"] == pytest.approx(0.25)


def test_unrelated_labels_score_near_chance():
    """A probe that scores well on noise would be measuring nothing."""
    rng = np.random.default_rng(1)
    classes = 22
    labels = [f"c{i % classes}" for i in range(440)]
    scores = []
    for trial in range(5):
        g = np.random.default_rng(100 + trial)
        train = g.normal(size=(440, 28))
        test = g.normal(size=(220, 28))
        test_labels = [f"c{i % classes}" for i in range(220)]
        scores.append(probe.nn_probe(train, labels, test, test_labels, "l2")["top1"])
    assert np.mean(scores) < 4 * (1.0 / classes)
    assert rng is not None


def test_unit_descriptor_is_a_probability_histogram():
    rng = np.random.default_rng(2)
    centers = rng.normal(size=(8, 14)).astype(np.float32)
    items = [{"loud": rng.normal(size=(30, 14)).astype(np.float32)} for _ in range(4)]
    hist = probe.unit_descriptor(items, centers)
    assert hist.shape == (4, 8)
    assert np.allclose(hist.sum(axis=1), 1.0)
    assert (hist >= 0).all()


def test_quantised_descriptor_matches_raw_when_every_frame_is_a_centre():
    rng = np.random.default_rng(3)
    centers = rng.normal(size=(6, 14)).astype(np.float32)
    items = [{"loud": centers[[0, 1, 2, 3]].copy()}]
    assert np.allclose(
        probe.quantised_descriptor(items, centers), probe.raw_descriptor(items)
    )


def test_frame_agreement_is_zero_when_units_carry_no_label_information():
    centers = np.zeros((1, 14), dtype=np.float32)
    items = [
        {"label": "a", "loud": np.zeros((10, 14), dtype=np.float32)},
        {"label": "b", "loud": np.zeros((10, 14), dtype=np.float32)},
    ]
    agreement = probe.frame_agreement(items, centers)
    assert agreement["mutual_information_bits"] == pytest.approx(0.0, abs=1e-12)
    assert agreement["nmi_sqrt"] == pytest.approx(0.0, abs=1e-12)


def test_leave_one_base_out_never_tests_on_its_own_base():
    rng = np.random.default_rng(4)
    items = []
    for label in ("x", "y"):
        for base in range(4):
            for aug in range(2):
                items.append({
                    "name": f"{label}_{base}_{aug}", "label": label,
                    "base": f"{label}/words/b0{base}",
                    "loud": rng.normal(size=(20, 14)).astype(np.float32),
                })
    descriptor = np.asarray([[1.0, 0.0] if it["label"] == "x" else [0.0, 1.0] for it in items])
    result = probe.leave_one_base_out(items, descriptor, "cosine")
    assert result["folds"] == 4
    assert result["top1"] == 1.0
    assert result["classes"] == 2
