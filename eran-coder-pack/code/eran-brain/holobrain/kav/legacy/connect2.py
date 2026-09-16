"""KAV / קָו — GROWING ALONG THE EDGE: the second attack on gate 2.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

WHAT connect.py MEASURED, AND WHY IT WAS NOT ENOUGH
---------------------------------------------------
Vertex-indexed tokens took connectivity from 4% to 46%, which looked like the
answer. It was not, and its own numbers say so:

    accuracy  0.2511   FLOOR_repeat  0.2478    <- a margin of 0.0033
    watertight 0 / 3

The 46% came from the REPRESENTATION — a shared vertex table makes edges
shareable at all — and almost none of it came from learning. That model predicted
an INDEX by rounding a regression, and an index is not a place: being one off in
index space can be the far side of the shape.

TWO THINGS, DECLARED SEPARATELY SO NEITHER GETS THE OTHER'S CREDIT
------------------------------------------------------------------
1. A GRAMMAR. HAND-WRITTEN. NOT LEARNED. It must never be reported as learning:
   a surface grows along its own boundary. Hold the front of edges owned by only
   one face; take one; the next face is that edge plus one more vertex. Every face
   therefore shares at least one edge BY CONSTRUCTION.

   The first run of this file proved how much that alone is worth: connectivity
   0.458 -> 0.994 with a model that was WORSE than guessing. If the two had been
   reported together it would have read as a triumph. It was a grammar.

   This is the same move as ERAN's mouth: anatomy carries what anatomy should
   carry, and learning is left only the part that must be learned.

2. THE LEARNING, and the first version got the question wrong. Asking "where is
   the third corner of this face" while BUILDING the frame from that corner is
   circular — at generation time the corner does not exist yet. The honest task,
   and the one a manifold actually poses:

       given an edge, and the face already on ONE side of it,
       where is the vertex on the OTHER side?

   Every closed surface answers that question for every interior edge, and the
   answer is never visible in the question. That is the task here.

WHY A LOCAL FRAME. The first version predicted world coordinates and lost to the
midpoint. Where the far vertex sits depends on which way the edge points and which
way the known face folds — that is rotation, and a linear model in world axes
cannot see it. So every number the model reads or writes is measured ALONG the
edge, ACROSS it in the known face's plane, or OUT of that plane.

THE FLOORS, because a gate without floors measures nothing
-----------------------------------------------------------
    FLOOR_mirror   reflect the known vertex through the edge — the flat guess,
                   exactly right on a flat surface, and the floor that catches a
                   model which has learned nothing about curvature.
    FLOOR_mid      snap the edge midpoint to its nearest vertex.
    FLOOR_repeat   say the previous answer again.
    FLOOR_common   say the most frequent vertex in training.
    CEILING        the truth, printed to keep the scale honest.

A pass needs the model to beat EVERY floor on the sealed shapes. Connectivity and
watertightness are reported whatever happens, and are credited to the grammar.
"""
from __future__ import annotations

import os
import sys
from collections import Counter, defaultdict

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import mesh                                    # noqa: E402
from connect import table_and_faces            # noqa: E402

HELD = ("plate", "stack", "pinch-rail")        # sealed: never fitted on
AXES = 3                                       # along the edge, across it, out of plane
FEAT = 6


# ---------------------------------------------------------------- the grammar

def edge_key(i: int, j: int) -> tuple[int, int]:
    return (i, j) if i < j else (j, i)


def edge_faces(faces) -> dict:
    """edge -> the third vertices of every face sitting on it."""
    d = defaultdict(list)
    for f in faces:
        for a, b, c in ((0, 1, 2), (1, 2, 0), (2, 0, 1)):
            d[edge_key(int(f[a]), int(f[b]))].append(int(f[c]))
    return d


def front_of(faces) -> list[tuple[int, int]]:
    """Edges owned by exactly one face — the boundary the surface can grow from."""
    d = edge_faces(faces)
    return sorted(k for k, v in d.items() if len(v) == 1)


# ---------------------------------------------------------------- the frame

def frame_of(pa, pb, po):
    """The edge's own axes, built ONLY from the edge and the face already on it.

    u  along the edge
    v  across it, inside the known face's plane, pointing AWAY from the known corner
    n  out of that plane
    Returns the midpoint, the three axes, the edge length, and how far the known
    corner stands from the edge. All of it is available at generation time.
    """
    e = pb - pa
    ne = float(np.linalg.norm(e))
    u = e / ne if ne > 1e-9 else np.array([1.0, 0.0, 0.0])
    mid = 0.5 * (pa + pb)
    w = po - mid
    w = w - (w @ u) * u
    nw = float(np.linalg.norm(w))
    v = -w / nw if nw > 1e-9 else np.array([0.0, 1.0, 0.0])   # away from the known one
    n = np.cross(u, v)
    nn = float(np.linalg.norm(n))
    n = n / nn if nn > 1e-9 else np.array([0.0, 0.0, 1.0])
    return mid, u, v, n, ne, nw


def context(table, a: int, b: int, opp: int, prev: int | None) -> np.ndarray:
    """What the model may see. Not one world axis among them."""
    pa, pb = table[a].astype(float), table[b].astype(float)
    po = table[opp].astype(float)
    mid, u, v, n, elen, owid = frame_of(pa, pb, po)
    if prev is None:
        d = np.zeros(3)
    else:
        d = table[prev].astype(float) - mid
    return np.array([elen, owid, d @ u, d @ v, d @ n, 1.0])


def mirror_point(table, a: int, b: int, opp: int) -> np.ndarray:
    """The flat guess: the known corner reflected through the edge."""
    pa, pb = table[a].astype(float), table[b].astype(float)
    po = table[opp].astype(float)
    e = pb - pa
    ne = float(np.linalg.norm(e))
    u = e / ne if ne > 1e-9 else np.array([1.0, 0.0, 0.0])
    foot = pa + ((po - pa) @ u) * u
    return 2.0 * foot - po


# ---------------------------------------------------------------- the model

class Posture:
    """Three ridge lines. The beat is which of the edge's own axes is spoken."""

    def __init__(self) -> None:
        self.w = np.zeros((AXES, FEAT))

    def offset(self, ctx: np.ndarray) -> np.ndarray:
        return self.w @ ctx


def pairs_of(table, faces):
    """(edge, known corner) -> the corner on the OTHER side. No leakage possible.

    Only interior edges qualify: an edge with one face has no far side to name.
    """
    for (a, b), thirds in edge_faces(faces).items():
        if len(thirds) != 2:
            continue
        o1, o2 = thirds
        yield a, b, o1, o2
        yield a, b, o2, o1


def training_rows(corpus):
    X, Y = [], []
    for _, tris in corpus:
        table, faces = table_and_faces(tris)
        prev = None
        for a, b, known, answer in pairs_of(table, faces):
            X.append(context(table, a, b, known, prev))
            mid, u, v, n, _, _ = frame_of(table[a].astype(float),
                                          table[b].astype(float),
                                          table[known].astype(float))
            t = table[answer].astype(float) - mid
            Y.append(np.array([t @ u, t @ v, t @ n]))
            prev = answer
    return np.array(X), np.array(Y)


def fit(corpus, lam: float = 1e-3) -> Posture:
    X, Y = training_rows(corpus)
    p = Posture()
    A = X.T @ X + lam * np.eye(FEAT)
    for ax in range(AXES):
        p.w[ax] = np.linalg.solve(A, X.T @ Y[:, ax])
    return p


def to_world(table, a, b, known, off) -> np.ndarray:
    mid, u, v, n, _, _ = frame_of(table[a].astype(float), table[b].astype(float),
                                 table[known].astype(float))
    return mid + off[0] * u + off[1] * v + off[2] * n


def snap(table, point, forbid=()) -> int:
    """The nearest vertex the shape actually owns. Declared decoding, not magic."""
    d = np.linalg.norm(table.astype(float) - point[None, :], axis=1)
    for i in forbid:
        d[i] = np.inf
    return int(np.argmin(d))


# ---------------------------------------------------------------- the measuring

def score(post: Posture, corpus, common: int) -> dict:
    hits = {"KAV3": 0, "FLOOR_mirror": 0, "FLOOR_mid": 0,
            "FLOOR_repeat": 0, "FLOOR_common": 0}
    dist = {"KAV3": [], "FLOOR_mirror": [], "FLOOR_mid": []}
    n = 0
    for _, tris in corpus:
        table, faces = table_and_faces(tris)
        prev = None
        for a, b, known, answer in pairs_of(table, faces):
            ctx = context(table, a, b, known, prev)
            here = to_world(table, a, b, known, post.offset(ctx))
            mirror = mirror_point(table, a, b, known)
            mid = 0.5 * (table[a].astype(float) + table[b].astype(float))
            said = {"KAV3": snap(table, here, forbid=(a, b, known)),
                    "FLOOR_mirror": snap(table, mirror, forbid=(a, b, known)),
                    "FLOOR_mid": snap(table, mid, forbid=(a, b, known)),
                    "FLOOR_repeat": prev if prev is not None else known,
                    "FLOOR_common": common}
            for name, val in said.items():
                hits[name] += int(val == answer)
            truth = table[answer].astype(float)
            dist["KAV3"].append(float(np.linalg.norm(here - truth)))
            dist["FLOOR_mirror"].append(float(np.linalg.norm(mirror - truth)))
            dist["FLOOR_mid"].append(float(np.linalg.norm(mid - truth)))
            n += 1
            prev = answer
    return {"frames": n,
            "accuracy": {k: hits[k] / max(n, 1) for k in hits},
            "mean_distance": {k: float(np.mean(v)) for k, v in dist.items()},
            "CEILING": 1.0}


def grow(table, seed_faces, post: Posture, n_faces: int) -> np.ndarray:
    """Speak a surface by walking its own boundary. The grammar keeps it joined."""
    faces = [tuple(int(x) for x in f) for f in seed_faces]
    have = {tuple(sorted(f)) for f in faces}
    prev = None
    for _ in range(n_faces):
        d = edge_faces(faces)
        front = sorted(k for k, v in d.items() if len(v) == 1)
        if not front:
            break
        placed = False
        for a, b in front:
            known = d[(a, b)][0]
            c = snap(table, to_world(table, a, b, known, post.offset(
                context(table, a, b, known, prev))), forbid=(a, b, known))
            key = tuple(sorted((a, b, c)))
            if key not in have:
                faces.append((a, b, c))
                have.add(key)
                prev = c
                placed = True
                break
        if not placed:
            break
    return np.array(faces)


def closure(post: Posture, corpus) -> dict:
    out = {"tried": 0, "watertight": 0, "shared": 0, "lone": 0, "faces": 0}
    for _, tris in corpus:
        _, lo, scale = mesh.quantise(np.asarray(tris, float))
        table, faces = table_and_faces(tris)
        keep = max(2, len(faces) // 4)
        said = grow(table, faces[:keep], post, len(faces) - keep)
        got = mesh.dequantise(table, lo, scale)[np.clip(said, 0, len(table) - 1)]
        g = mesh.geometry(got)
        out["tried"] += 1
        out["watertight"] += int(g["watertight"])
        out["shared"] += g["shared_2"]
        out["lone"] += g["lone"]
        out["faces"] += g["faces"]
    tot = out["shared"] + out["lone"]
    out["connectivity"] = out["shared"] / tot if tot else 0.0
    return out


def measure() -> dict:
    corpus = mesh.our_corpus()
    train = [(n, t) for n, t in corpus if n not in HELD]
    test = [(n, t) for n, t in corpus if n in HELD]
    post = fit(train)
    c = Counter()
    for _, tris in train:
        _, faces = table_and_faces(tris)
        c.update(faces.reshape(-1).tolist())
    common = c.most_common(1)[0][0] if c else 0
    return {"train_shapes": len(train), "held_out": list(HELD),
            "sealed": score(post, test, common),
            "closure_sealed": closure(post, test)}


def verdict(r: dict) -> tuple[bool, list[str]]:
    a = r["sealed"]["accuracy"]
    lines, ok = [], True
    for floor in ("FLOOR_mirror", "FLOOR_mid", "FLOOR_repeat", "FLOOR_common"):
        good = a["KAV3"] > a[floor]
        ok = ok and good
        lines.append(f"{'PASS' if good else 'FAIL'}  accuracy: KAV3 {a['KAV3']:.4f} "
                     f"vs {floor} {a[floor]:.4f}")
    d = r["sealed"]["mean_distance"]
    lines.append("      distance to the true corner (of 127): KAV3 %.2f | mirror "
                 "%.2f | midpoint %.2f" % (d["KAV3"], d["FLOOR_mirror"],
                                           d["FLOOR_mid"]))
    c = r["closure_sealed"]
    lines.append("      connectivity %.3f  (%d shared / %d lone, %d faces) "
                 "-- CREDIT: the grammar, not the model"
                 % (c["connectivity"], c["shared"], c["lone"], c["faces"]))
    solid = c["watertight"] == c["tried"] and c["tried"] > 0
    lines.append(("PASS" if solid else "FAIL") +
                 f"  GATE 2 (solid): {c['watertight']}/{c['tried']} watertight")
    return ok, lines


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
