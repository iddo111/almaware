"""KAV / קָו — CONNECTIVITY: the experiment that attacks gate 2.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

GATE 2 said KAV makes sentences and not surfaces: twelve faces, thirty-six edges,
ZERO of them shared. The cause was the tokenisation — nine independent numbers per
face means two faces can share an edge only by emitting the identical coordinate
triple twice, and a regressor never does that.

This file tests the known answer WITHOUT replacing anything, so the choice is made
on numbers rather than on my say-so.

    the old question   given the numbers so far, what is the next COORDINATE?
    the new question   given the vertices of this shape, which three of them
                       is the next FACE?

Connectivity is the whole of watertightness — a shared edge is two faces sharing
two indices — so this is not a smaller problem, it is the RIGHT one. The vertex
table comes from the shape (and one day from ERAN's eye, which is TZELEM run
backwards); the model's job is to say how they join.

HONEST ABOUT THE DECODER: a predicted index is rounded and clamped into the table,
which is ordinary decoding in a discrete domain and is declared here rather than
buried. It cannot invent a vertex that does not exist — which is itself a grammar
the coordinate model never had.
"""
from __future__ import annotations

import os
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import mesh                                    # noqa: E402

K = 12                 # how many indices back the line reaches: four faces
PHASES = 3             # where we stand inside a face: which corner


def table_and_faces(tris) -> tuple[np.ndarray, np.ndarray]:
    """A shape becomes (vertex table, faces as index triples), canonically.

    Vertices are quantised first, so two corners that the grid cannot tell apart
    become ONE vertex — which is exactly what makes a shared edge possible at all.
    """
    ints, lo, scale = mesh.quantise(np.asarray(tris, float))
    flat = ints.reshape(-1, 3)
    uniq, inv = np.unique(flat, axis=0, return_inverse=True)
    order = np.lexsort((uniq[:, 0], uniq[:, 1], uniq[:, 2]))   # by z, then y, then x
    rank = np.empty(len(uniq), dtype=np.int64)
    rank[order] = np.arange(len(uniq))
    table = uniq[order]
    faces = rank[inv].reshape(-1, 3)
    faces = np.array([np.roll(f, -int(np.argmin(f))) for f in faces])   # rotate, never sort
    faces = faces[np.lexsort((faces[:, 2], faces[:, 1], faces[:, 0]))]
    return table, faces


def rebuild(table: np.ndarray, faces: np.ndarray, lo, scale) -> np.ndarray:
    v = mesh.dequantise(table, lo, scale)
    return v[np.clip(faces, 0, len(table) - 1)]


def frames(faces: np.ndarray, k: int):
    """Every (context, corner, answer) in one shape's face list."""
    flat = faces.reshape(-1)
    for j in range(len(flat)):
        tail = flat[max(0, j - k):j]
        ctx = np.array([0] * (k - len(tail)) + list(tail), dtype=np.float64)
        yield ctx, j % PHASES, int(flat[j])


class Posture:
    def __init__(self, k: int = K) -> None:
        self.k = k
        self.w = np.zeros((PHASES, k))
        self.b = np.zeros(PHASES)

    def index(self, ctx, phase: int, n_vertices: int, heat: float = 0.0,
              rng=None) -> int:
        v = float(self.w[phase] @ ctx + self.b[phase])
        if heat > 0:
            v += (rng or np.random.default_rng()).normal(0.0, heat)
        return int(np.clip(round(v), 0, n_vertices - 1))


def fit(corpus, k: int = K, lam: float = 1e-3) -> Posture:
    rows = [[] for _ in range(PHASES)]
    for _, tris in corpus:
        _, faces = table_and_faces(tris)
        for ctx, ph, ans in frames(faces, k):
            rows[ph].append((ctx, ans))
    p = Posture(k)
    for ph in range(PHASES):
        if not rows[ph]:
            continue
        X = np.array([c for c, _ in rows[ph]])
        y = np.array([a for _, a in rows[ph]], dtype=np.float64)
        X1 = np.hstack([X, np.ones((len(X), 1))])
        A = X1.T @ X1 + lam * np.eye(X1.shape[1])
        A[-1, -1] -= lam
        sol = np.linalg.solve(A, X1.T @ y)
        p.w[ph], p.b[ph] = sol[:-1], sol[-1]
    return p


def say_faces(table, prefix_faces, posture, n_faces: int, heat: float = 0.0,
              seed: int = 0) -> np.ndarray:
    """Continue the face list. The vertices are given; only the joining is said."""
    rng = np.random.default_rng(seed)
    flat = list(np.asarray(prefix_faces).reshape(-1))
    for j in range(n_faces * PHASES):
        tail = flat[-posture.k:]
        ctx = np.array([0] * (posture.k - len(tail)) + list(tail), dtype=np.float64)
        flat.append(posture.index(ctx, len(flat) % PHASES, len(table),
                                  heat=heat, rng=rng))
    return np.array(flat).reshape(-1, 3)


def measure(k: int = K, heat: float = 0.0, held=("plate", "stack", "pinch-rail")):
    """The same two gates, asked of connectivity instead of coordinates."""
    corpus = mesh.our_corpus()
    train = [(n, t) for n, t in corpus if n not in held]
    test = [(n, t) for n, t in corpus if n in held]
    post = fit(train, k)

    from collections import Counter
    c = Counter()
    for _, tris in train:
        _, f = table_and_faces(tris)
        c.update(f.reshape(-1).tolist())
    common = c.most_common(1)[0][0]

    hits = {"KAV2": 0, "FLOOR_common": 0, "FLOOR_repeat": 0}
    n = 0
    for _, tris in test:
        _, faces = table_and_faces(tris)
        nv = len(table_and_faces(tris)[0])
        for ctx, ph, ans in frames(faces, k):
            n += 1
            hits["KAV2"] += int(post.index(ctx, ph, nv) == ans)
            hits["FLOOR_common"] += int(common == ans)
            hits["FLOOR_repeat"] += int(int(ctx[-1]) == ans)

    solid = {"tried": 0, "watertight": 0, "shared": 0, "lone": 0, "faces": 0}
    for _, tris in test:
        ints, lo, scale = mesh.quantise(np.asarray(tris, float))
        table, faces = table_and_faces(tris)
        keep = max(2, len(faces) // 4)
        said = say_faces(table, faces[:keep], post, len(faces) - keep,
                         heat=heat, seed=1)
        got = rebuild(table, said, lo, scale)
        g = mesh.geometry(got)
        solid["tried"] += 1
        solid["watertight"] += int(g["watertight"])
        solid["shared"] += g["shared_2"]
        solid["lone"] += g["lone"]
        solid["faces"] += g["faces"]
    return {"k": k, "frames": n,
            "accuracy": {a: hits[a] / max(n, 1) for a in hits},
            "solid": solid}


if __name__ == "__main__":
    # KAV-10, 2026-09-06: NEUTERED. This file is a RETIRED ruler. Its __main__ used to
    # print a PASSING gate by a standard this project has explicitly refuted -- for
    # connect2.py, `solid = c["watertight"] == c["tried"]`: watertight only, no face
    # count, no volume. MEASURED with the LIVE ruler on 2026-09-06: the flat
    # close-the-hole floor is 3/3 watertight at volume ratios 0.167 / 0.300 / 0.249 and
    # 0/3 RIGHT solids, so this __main__ would have printed a green gate 2 for a sixth
    # of a box. joiner.py's own docstring says so: "a chooser that closes slivers can be
    # watertight with a sixth of the volume." Nothing imports this file. The live ruler
    # is ../ruler.py; the numbers this one measured are preserved in joiner.py's
    # docstring and in tests/test_joiner.py's GATE2_DECISION_20260905.
    raise SystemExit(
        __file__ + " is a RETIRED ruler kept for its record only. Its gate was "
        "refuted (watertight alone, no face count, no volume). Run ../ruler.py.")
