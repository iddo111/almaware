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
    """One ridge solution per phase. Nothing iterative, nothing random."""
    rows: list[list[tuple[np.ndarray, int]]] = [[] for _ in range(PHASES)]
    for _, tris in corpus:
        toks, _, _ = mesh.speak(tris)
        for ctx, phase, ans in frames(toks, k):
            rows[phase].append((ctx, ans))

    p = Posture(k=k)
    for ph in range(PHASES):
        if not rows[ph]:
            continue
        X = np.array([c for c, _ in rows[ph]])
        y = np.array([a for _, a in rows[ph]], dtype=np.float64)
        X1 = np.hstack([X, np.ones((len(X), 1))])          # the bias column
        A = X1.T @ X1 + lam * np.eye(X1.shape[1])
        A[-1, -1] -= lam                                   # never penalise the bias
        sol = np.linalg.solve(A, X1.T @ y)
        p.w[ph], p.b[ph] = sol[:-1], sol[-1]
    return p


def split(corpus: list[tuple[str, np.ndarray]], held: tuple[str, ...]):
    """Seal some shapes away. A model is only ever judged on what it never saw."""
    train = [(n, t) for n, t in corpus if n not in held]
    test = [(n, t) for n, t in corpus if n in held]
    if not test:
        raise ValueError(f"the held-out names {held} are not in the corpus")
    return train, test
