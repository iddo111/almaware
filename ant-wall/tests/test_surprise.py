"""The curiosity metric must be a distance.

`surprise()` claimed "mean distance to the nearest known unit" and returned
`len(set(units)) / n_centers` — unit diversity, which is not a distance and
grows with clip length. The ant was pressing the longest sound, not the most
alien one. Nothing could catch that: the function was a closure inside
cmd_explore, and the only observable output was which panel got pressed.

These build their own tiny checkpoint, so they need no ant on disk.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import wall  # noqa: E402


def _tone(seconds: float, hz: float = 220.0, amp: float = 0.3) -> np.ndarray:
    t = np.arange(int(seconds * wall.SR)) / wall.SR
    return amp * np.sin(2 * np.pi * hz * t)


def _write_ck(tmp_path, centers: np.ndarray) -> str:
    p = tmp_path / f"ck{centers.shape[0]}-{abs(hash(centers.tobytes())) % 9999}.json"
    p.write_text(json.dumps({
        "centers": np.asarray(centers).tolist(),
        "feature_spec": {"frame_samples": 400, "hop_samples": 160,
                         "spectral_bands": 12},
    }), encoding="utf-8")
    return str(p)


KNOWN = _tone(0.7, hz=220, amp=0.30)      # the sound this ant grew up on


@pytest.fixture
def checkpoint(tmp_path) -> str:
    """A codebook fitted to KNOWN, so "near the codebook" means something.

    A codebook of random vectors cannot test a distance metric: nothing is
    genuinely near it, so any ordering you assert is an accident of the seed.
    """
    return _write_ck(tmp_path, wall.frame_features(KNOWN)[::3])


def test_surprise_is_a_distance_not_a_ratio(tmp_path):
    """Diversity was bounded by 1.0 because it divided by n_centers. A real
    distance in this feature space (log energies) is not."""
    ck = _write_ck(tmp_path, wall.frame_features(_tone(0.3, hz=100))[:2])
    loud = wall.surprise_score(ck, _tone(1.0, hz=4000, amp=0.9))
    assert loud > 1.0, f"got {loud}, which is a ratio, not a distance"


def test_surprise_grows_with_distance_from_the_codebook(checkpoint):
    """The whole point of the metric: a sound the codebook already models must
    score below one it has never heard. The diversity ratio had no such
    guarantee — it did not look at distance at all."""
    near = wall.surprise_score(checkpoint, KNOWN)
    far = wall.surprise_score(checkpoint, _tone(0.7, hz=3500, amp=0.99))
    assert near < 1.0, f"the ant's own training sound scored {near}"
    assert far > near, f"far={far} not greater than near={near}"


def test_surprise_is_not_just_clip_length(tmp_path):
    """The actual bug, in miniature.

    Same sound, three times the duration. A distance is a per-frame average
    and must barely move; a diversity count grows, because a longer clip
    visits more codebook entries. On the real wall this made the two curiosity
    picks the two longest syllables — corr(duration, old score) = +0.51.
    """
    rng = np.random.default_rng(0)
    sweep = np.concatenate([_tone(0.15, hz=f) for f in (120, 400, 900, 2000)])
    ck = _write_ck(tmp_path, wall.frame_features(sweep)[::2])

    def noise(seconds):                      # nothing like the sweep
        return 0.4 * rng.standard_normal(int(seconds * wall.SR))

    short_a, long_a = noise(0.5), noise(1.5)

    short = wall.surprise_score(ck, short_a)
    long = wall.surprise_score(ck, long_a)
    assert short > 1.0 and long > 1.0, "need a genuinely alien sound to compare"
    assert abs(long - short) / short < 0.05, (
        f"score tracks duration: {short:.3f} vs {long:.3f}"
    )


def test_metric_is_decorrelated_from_duration_on_the_real_wall():
    """The measurement that found the bug, kept as a test.

    Across the 22 built panels: corr(duration, old diversity score) = +0.512
    (the tester's figure, reproduced exactly), corr(duration, new distance
    score) = -0.321. Skips where the wall or an ant has not been built.
    """
    ck = Path(r"D:\CLAUDE\voice-ant-farm\state\ant-b\current.json")
    if not ck.exists():
        pytest.skip("no ant-b checkpoint on this machine")
    try:
        w = wall.Wall()
    except wall.WallNotBuilt as exc:
        pytest.skip(str(exc))

    n_centers = len(json.loads(ck.read_text(encoding="utf-8"))["centers"])
    dur, old, new = [], [], []
    for i in range(len(w)):
        a = w.press(i)
        dur.append(a.size / wall.SR)
        old.append(len(set(wall.encode_with_ant(str(ck), a))) / n_centers)
        new.append(wall.surprise_score(str(ck), a))

    r_old = np.corrcoef(dur, old)[0, 1]
    r_new = np.corrcoef(dur, new)[0, 1]
    assert r_old > 0.4, f"expected the old metric to track duration, got {r_old}"
    assert abs(r_new) < abs(r_old), (
        f"new metric still tracks duration: old={r_old:+.3f} new={r_new:+.3f}"
    )


def test_empty_audio_is_not_surprising(checkpoint):
    assert wall.surprise_score(checkpoint, np.zeros(10)) == 0.0


def test_encode_with_ant_stays_backwards_compatible(checkpoint):
    """Callers that want only units must keep getting a plain list."""
    units = wall.encode_with_ant(checkpoint, _tone(0.5))
    assert isinstance(units, list) and all(isinstance(u, int) for u in units)

    units2, dists = wall.encode_with_ant(checkpoint, _tone(0.5),
                                         return_distances=True)
    assert units2 == units
    assert len(dists) == len(units)
    assert all(d >= 0 for d in dists)


def test_warmup_is_capped_so_short_runs_still_explore():
    """`--presses 10` with the default warmup of 8 spent 80% of the run
    pressing at random and exercised curiosity twice."""
    src = (Path(__file__).resolve().parents[1] / "wall.py").read_text(
        encoding="utf-8")
    assert "min(args.warmup, max(1, args.presses // 4))" in src
