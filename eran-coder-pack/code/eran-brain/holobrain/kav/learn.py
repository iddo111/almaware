"""KAV / קָו — LEARNING: the line is fitted, not searched.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

Three of ERAN's organs sat frozen at their birth value tonight because a random
search could not find a step that improved a counting objective. KAV does not open
that door at all: the model is LINEAR in its weights, so the best weights are not
searched for — they are SOLVED, in closed form, by least squares.

That is a deliberate choice and it makes the verdict sharper, not softer. A fitted
linear model is the STRONGEST this architecture can ever be. So if it still cannot
beat the floor, the answer is not "train it longer" or "tune the optimiser" — the
answer is that the architecture is wrong, and we will know that tonight instead of
in a week. An optimiser can hide a bad model. A closed form cannot.

Ridge, with a small lambda, because at phase boundaries the design matrix is
rank-deficient (a column that is zero in every training frame of that phase has no
opinion, and without ridge it would get an arbitrary weight).
"""
from __future__ import annotations

import numpy as np

import mesh
from anatomy import PHASES, Posture, frames


def fit(corpus: list[tuple[str, np.ndarray]], k: int, lam: float = 1e-3) -> Posture:
    """One ridge solution per phase. Nothing iterative, nothing random.

    ONE SHAPE IS ONE VOTE (2026-09-06, KAV-07). The joiner half was fixed on
    2026-09-05 to stop a shape with many rows shouting down a shape with few
    (joiner.fit_line's docstring); this half was left pooling every frame equally,
    which is the same disease. MEASURED on 2026-09-06: of the 2,379 training frames
    the three grid-decimated STL parts supply 1,902 -- 79.9% -- and of the 2,097
    sealed frames pinch-rail alone supplies 1,977 -- 94.3%. So every frame is
    weighted 1/(frames its shape contributed), and the weights are then rescaled
    within each phase to sum to the row count, purely so that `lam` keeps the same
    meaning it had before the weighting.

    MEASURED BEFORE AND AFTER, 2026-09-06, and it is worth reading twice because the
    fix made the printed numbers WORSE:

                        seen (2,379 frames)          sealed (2,097 frames)
                        accuracy   mean abs err      accuracy   mean abs err
        frame-pooled    0.0849     17.88             0.0734     12.55
        one shape one   0.0601     23.56             0.0167     19.31
        vote (this)

    THE OLD NUMBERS WERE FLATTERED BY THE IMBALANCE, not destroyed by the fix. The
    three grid-decimated STL parts supplied 79.9% of the training frames and
    pinch-rail 94.3% of the sealed ones, so the line was mostly fitted to, and mostly
    scored on, the same few printed parts -- and a model that has memorised the
    distribution it is tested on looks good for the wrong reason. Give every shape
    one vote and the coordinate half is plainly weak: 0.0601 against a constant's
    0.2093 on its own training data. It was ALREADY losing to that constant before
    the fix (0.0849 vs 0.2093); nothing was looking (KAV-06).

    Gate 1 therefore FAILS honestly now, and tests/test_organ.py::test_gate1 is
    xfail(strict=True) with the numbers in its reason. It still wins on mean absolute
    error against every floor -- it is a regressor being scored on exact integer
    match -- and that is the honest state of it.
    """
    rows: list[list[tuple[np.ndarray, int, float]]] = [[] for _ in range(PHASES)]
    for _, tris in corpus:
        toks, _, _ = mesh.speak(tris)
        got = list(frames(toks, k))
        if not got:
            raise ValueError(
                "a shape in the corpus produced no vertex frames at all — the "
                "coordinate half has nothing to learn from it")
        share = 1.0 / len(got)                       # one shape, one vote
        for ctx, phase, ans in got:
            rows[phase].append((ctx, ans, share))

    p = Posture(k=k)
    for ph in range(PHASES):
        if not rows[ph]:
            # KAV-12: a phase with no rows used to be skipped in silence, leaving a
            # zero row that predicts 0 for ever. That is the empty-menu shape.
            raise ValueError(
                f"phase {ph} of {PHASES} has no training frames — the coordinate "
                f"model would keep its birth weights and predict 0 for ever")
        X = np.array([c for c, _, _ in rows[ph]])
        y = np.array([a for _, a, _ in rows[ph]], dtype=np.float64)
        wv = np.array([w for _, _, w in rows[ph]], dtype=np.float64)
        wv = wv * (len(wv) / wv.sum())               # same scale as unweighted
        X1 = np.hstack([X, np.ones((len(X), 1))])          # the bias column
        Xw = X1 * wv[:, None]
        A = Xw.T @ X1 + lam * np.eye(X1.shape[1])
        A[-1, -1] -= lam                                   # never penalise the bias
        sol = np.linalg.solve(A, Xw.T @ y)
        p.w[ph], p.b[ph] = sol[:-1], sol[-1]
    return p


def split(corpus: list[tuple[str, np.ndarray]], held: tuple[str, ...]):
    """Seal some shapes away. A model is only ever judged on what it never saw."""
    have = {n for n, _ in corpus}
    missing = [h for h in held if h not in have]
    if missing:
        # KAV-12: only a COMPLETELY empty sealed set used to raise, so a corpus that
        # had quietly lost one held-out shape sealed a smaller set and moved every
        # gate-1 number with no complaint.
        raise ValueError(
            f"held-out shapes not in the corpus: {sorted(missing)} — the sealed set "
            f"would silently shrink and every gate-1 number would move")
    train = [(n, t) for n, t in corpus if n not in held]
    test = [(n, t) for n, t in corpus if n in held]
    if not test:
        raise ValueError(f"the held-out names {held} are not in the corpus")
    return train, test
