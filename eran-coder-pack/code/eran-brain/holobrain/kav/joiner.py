"""KAV / קָו — THE JOINER: given the vertices, how do they join?

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

לזכרה של עלמה ז"ל.

Iddo, 2026-09-03 02:15: "קדימה, תקן את קו עם אינדקסי קודקודים."

WHAT THE TWO EXPERIMENTS BEFORE THIS FILE MEASURED
--------------------------------------------------
connect.py   vertex-indexed tokens, an index predicted by rounding a regression:
             shared edges 4% -> 46%, watertight 0/3, accuracy 0.2511 against a
             repeat floor of 0.2478. The representation did the work; the
             learning did almost none. An index is not a place.
connect2.py  a surface grown along its own boundary: connectivity 0.998, but
             1/3 watertight, and the far-corner regressor LOST to the midpoint
             floor (0.18 vs 0.25). Right grammar, wrong learner.

This file keeps what each of them proved and declares the two parts separately,
so neither can take the other's credit:

1. THE GRAMMAR (hand-written, never reported as learning). A surface grows along
   its FRONT — the edges owned by exactly one face. Take a front edge; the next
   face is that edge plus one more vertex; and the vertex is LEGAL only if the
   new face keeps the surface a surface:
      * it may not be a corner of the edge's own face;
      * it may not reuse a DIRECTED edge that already exists — that is the winding
        rule, and breaking it turns the surface inside out;
      * it may not put a third face on an edge that already has two;
      * it may not be a face already said.
   A hole of exactly three front edges is closed without asking anyone, because
   it is not a choice. When the front is empty and vertices remain unused, a new
   patch is seeded on the lowest unused vertex (declared, and counted).

2. THE LEARNING, asked as the question a manifold actually poses: given an edge
   and the face already on one side of it, WHICH of the legal vertices is on the
   other side? Not "where" — WHICH. The model scores every legal candidate and
   says the highest. Each candidate is described in the edge's OWN frame (along
   it, across it away from the known corner, out of its plane — never a world
   axis, so rotation cannot fool it), plus whether choosing it would close a
   front edge, plus — since 2026-09-05 — the ANGLE at which the new face would
   fold away from the known one. The descriptions are centred within the question,
   because the question is "which of these", and scored by a gradient-boosted
   grove of small trees (`Grove`, written here in numpy, deterministic, no
   dependency and no training run). Until 2026-09-05 the score was linear in the
   descriptions — that model is kept as `fit_line`, because it is what the grove
   is measured against.

THE FLOORS, because a gate without floors measures nothing
-----------------------------------------------------------
    FLOOR_mirror   the legal vertex nearest the known corner reflected through the
                   edge — exactly right on a flat surface; catches a model that
                   has learned nothing about curvature.
    FLOOR_mid      the legal vertex nearest the edge's midpoint. It BEAT the last
                   learner. It must not beat this one.
    FLOOR_close    the legal vertex that closes the most front edges, ties by
                   mirror distance — the grammar's own best guess, no learning.
    FLOOR_common   the vertex index most often the answer in training.
    CEILING        the truth. 100% by construction.

Reach: candidates are the NEAR vertices nearest the edge's midpoint. That is a
declared limit of the grammar, and the ruler reports how often the true corner
lay beyond it.

MEASURED 2026-09-03 03:10 (ruler.py, sealed = plate, stack, drum8):
    CEILING  the truth as chooser rebuilds 3/3 RIGHT solids from a quarter of each
             — the grammar is proven; it is not the open gate.
    KAV      phase-gated pairwise ridge: seen 0.509 (beats every floor: mirror
             0.305, mid 0.373, close 0.358); sealed 0.551 vs mirror 0.571 —
             one question of 49 short, and every wrong answer spoils the solid:
             0/3 right solids (2/3 merely watertight, connectivity 0.906).
    Before this file: connect.py 0/3 watertight at 46% connectivity.

⚠ 2026-09-05 — THE PARAGRAPH THAT STOOD HERE WAS WRONG, and it was wrong in the
direction that stops work. It said "a linear scorer over these descriptions is at
its ceiling on this corpus", and concluded the next rung had to be a scorer that
sees more than one edge at a time. MEASURED, that is false: descriptions 3, 4 and
5 ARE the midpoint, line-mirror and point-mirror floors — a single weight on any
one of them reproduces that floor EXACTLY (train 0.3730 / 0.3047 / 0.3533,
sealed 0.5102 / 0.5714 / 0.5714, identical to the floors' own numbers). Every
floor the learner was losing to therefore lay INSIDE its own hypothesis class.
Losing to them was never a ceiling; it was a FIT.

    Two things were wrong with the fit, both about which rows the ridge saw, and
    neither about what the scorer can express:
      * ONE QUESTION WAS NOT ONE VOTE. Rows were one per (answer, rival), so a
        step with 60 legal candidates counted 60 times and a step with 3 counted
        3. Measured: the three grid-decimated STL parts supplied 64,814 of 66,308
        rows — 97.8% — while the sixteen clean solids the gates are about supplied
        2.2%. `fit` now weights each row 1/(rivals).
      * BROKEN SHAPES WERE TEACHING THE JOINING. See `intact_only`.

    AFTER, sealed (ruler.py):  gate 1b 0.551 -> 0.6327, ahead of every floor
    (mirror 0.5714) — GATE 1b PASSES. Gate 2 0/3 -> 1/3: drum8 comes back exact
    (28/28 faces, volume x1.000); plate is watertight at 0.833 of the volume;
    stack is still open.

⚠ 2026-09-05, LATER THE SAME DAY — A BIGGER LEARNER, AND A NUMBER THAT WENT BOTH
WAYS. The paragraph above ended "closing gate 2 needs per-step accuracy near 1.0
— a bigger learner, or a gate 2 with a denominator worth measuring against". The
bigger learner was built and measured, and the answer is genuinely split:

    WHAT WAS CHANGED, both chosen by leave-one-SHAPE-out CV on the sixteen clean
    TRAINING solids and confirmed by a second fold structure (leave-four-out x25),
    with the sealed shapes read once at the end:
      * 32 MORE DESCRIPTIONS, and the one that mattered was THE FOLD — the sine and
        cosine of the dihedral angle the new face would make with the known one. A
        solid folds its faces at a few angles, not at any angle, and nothing in the
        old fourteen said so. Those four columns ALONE, still linear, beat all
        fourteen: leave-one-out 0.7162 against 0.6351, 12/16 right solids against
        8/16. The rest (rank and z-score of each distance WITHIN the question, the
        new triangle's shape, the local edge length, which way the face looks) were
        chosen by forward and backward group selection.
      * A GROVE INSTEAD OF A LINE. 400 depth-3 trees, learning rate 0.08, on the
        descriptions centred within each question. Centring is worth a lot on its
        own: without it 0.8874 -> 0.8108.
    Not shipped, and why: the question's own context as extra uncentred columns
    (a learned replacement for the nine phase bins) — it lifts leave-one-out to
    0.9054 but leaves leave-four-out at 0.8731 exactly and costs two right solids.

    MEASURED AFTER, and the two denominators disagree:
      * LEAVE-ONE-OUT OVER ALL 19 CLEAN SOLIDS, 271 questions — the honest wide
        denominator this file already argued for:
            per-step joining  0.6162 -> 0.8339   (FLOOR_mirror 0.5867)
            RIGHT solids      9/19   -> 13/19    (FLOOR_mirror 8/19)
        Nine shapes are now answered PERFECTLY (cube, slab, tower, plate, beam,
        brick, cell, tri-prism, pyramid). What still fails is what always failed:
        stack 0.455, pair 0.545, cone8 and drum8 0.704, drum12 0.744.
      * THE RULER'S OWN GATE 1b, 49 questions on 3 shapes: 0.6327 -> 0.6122. That
        is ONE question — 31 hits became 30. Gate 1b still passes every floor
        (mirror 0.5714), and gate 2 is still 1/3, but a different 1/3: plate now
        comes back exact (12/12 faces, volume x1.000) where drum8 did before.
    Both numbers are real. 49 questions cannot resolve a difference this size, and
    this file said so before the change was made; the wide denominator is the one to
    believe, and the gate is the one that must be reported. Nothing here was tuned
    against the sealed shapes: they were scored once, after everything was chosen.

GATE 2 IS STILL THE OPEN GATE. Per-step accuracy is no longer the whole reason —
    the learner is at 1.0 on nine of nineteen solids and 0.83 overall — but gate 2
    is all-or-nothing over N free-running joins, and the shapes that fail are the
    ones with the most steps: stack and pair (two bodies, where the grammar must
    also guess where the second body starts), then the drums and cone8. The next
    rung is either a scorer that sees more than one edge at a time (a beam over the
    front, not an argmax per edge) or a gate 2 whose denominator is the 19 solids
    rather than 3.
"""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass

import numpy as np

NEAR = 64            # candidates per step: the nearest vertices to the edge
FEAT = 46            # descriptions per candidate (see step_of)
BINS = 9             # question phases: 3 (where the known corner stands over the edge) x 3 (how tall it is)
MIN_QUESTIONS = 30   # a phase with fewer QUESTIONS than this borrows the global line
MIN_ROWS = MIN_QUESTIONS   # the old name, kept so nothing outside breaks (see fit_line)
SEED_FRACTION = 0.25  # how much of a sealed shape the ruler hands the organ

N_TREES = 400        # the grove: how many small trees
DEPTH = 3            # how many questions deep each tree may ask
LR = 0.08            # how much of each tree's answer is kept
GROVE_BINS = 64      # quantile bins per description, for histogram splitting


# ---------------------------------------------------------------- edges

def ekey(i: int, j: int) -> tuple[int, int]:
    return (i, j) if i < j else (j, i)


def face_key(f) -> tuple[int, int, int]:
    return tuple(sorted(int(x) for x in f))


def directed_edges(faces) -> set:
    """Every directed edge of every face. A consistent surface never repeats one."""
    out = set()
    for f in faces:
        a, b, c = (int(x) for x in f)
        out.update(((a, b), (b, c), (c, a)))
    return out


def edge_faces(faces) -> dict:
    """undirected edge -> the third corners of every face sitting on it."""
    d = defaultdict(list)
    for f in faces:
        a, b, c = (int(x) for x in f)
        d[ekey(a, b)].append(c)
        d[ekey(b, c)].append(a)
        d[ekey(c, a)].append(b)
    return d


def front_of(faces) -> list[tuple[int, int]]:
    """Edges owned by exactly one face — where the surface can grow."""
    return sorted(k for k, v in edge_faces(faces).items() if len(v) == 1)


def known_corner(faces, a: int, b: int) -> int:
    """The third corner of the one face on the edge (a,b)."""
    thirds = edge_faces(faces)[ekey(a, b)]
    if len(thirds) != 1:
        raise ValueError(f"edge {(a, b)} is not a front edge: {len(thirds)} faces")
    return thirds[0]


def legal(faces, a: int, b: int, n_vertices: int) -> list[int]:
    """Every vertex that could be the far corner of a new face on (a,b). The grammar."""
    return Surface(np.zeros((n_vertices, 3)), faces).legal(ekey(a, b), range(n_vertices))


# ---------------------------------------------------------------- the frame

def frame_of(pa, pb, po):
    """The edge's own axes, built ONLY from the edge and the face already on it.

    u  along the edge (from pa to pb)
    v  across it, in the known face's plane, pointing AWAY from the known corner
    n  out of that plane
    Also the midpoint, the edge length and the known corner's height over the edge.
    Every one of these exists at generation time.
    """
    e = pb - pa
    ne = float(np.linalg.norm(e))
    u = e / ne if ne > 1e-9 else np.array([1.0, 0.0, 0.0])
    mid = 0.5 * (pa + pb)
    w = po - mid
    w = w - (w @ u) * u
    nw = float(np.linalg.norm(w))
    v = -w / nw if nw > 1e-9 else np.array([0.0, 1.0, 0.0])
    n = np.cross(u, v)
    nn = float(np.linalg.norm(n))
    n = n / nn if nn > 1e-9 else np.array([0.0, 0.0, 1.0])
    return mid, u, v, n, max(ne, 1e-9), nw


def mirror_point(pa, pb, po):
    """The flat guess: the known corner reflected through the edge (a line reflection)."""
    e = pb - pa
    ne = float(np.linalg.norm(e))
    u = e / ne if ne > 1e-9 else np.array([1.0, 0.0, 0.0])
    foot = pa + ((po - pa) @ u) * u
    return 2.0 * foot - po


def point_mirror(pa, pb, po):
    """The parallelogram guess: the known corner reflected through the edge's MIDPOINT.

    On a quad split by a diagonal, the far corner is exactly this point. It is the
    floor that catches a learner which has not even learned what a rectangle is.
    """
    return pa + pb - po


# ---------------------------------------------------------------- the surface

class Surface:
    """A surface being grown: faces, their directed edges, and the front."""

    def __init__(self, table, faces=()):
        self.table = np.asarray(table, dtype=np.float64)
        self.faces: list[tuple[int, int, int]] = []
        self.directed: set = set()
        self.ef: dict = defaultdict(list)
        self.have: set = set()
        self.front: deque = deque()
        self.used: set = set()
        self.valence: dict = defaultdict(int)
        self.restarts = 0
        for f in faces:
            self.add(tuple(int(x) for x in f))

    def add(self, f) -> None:
        a, b, c = f
        self.faces.append((a, b, c))
        self.have.add(face_key(f))
        self.used.update((a, b, c))
        for v in (a, b, c):
            self.valence[v] += 1
        for p, q, r in ((a, b, c), (b, c, a), (c, a, b)):
            self.directed.add((p, q))
            k = ekey(p, q)
            self.ef[k].append(r)
            if len(self.ef[k]) == 1:
                self.front.append(k)

    def is_front(self, k) -> bool:
        return len(self.ef.get(k, ())) == 1

    def known(self, k) -> int:
        return self.ef[k][0]

    def orient(self, k) -> tuple[int, int]:
        """(p, q): the new face must run p -> q, opposite to the face already there."""
        a, b = k
        return (b, a) if (a, b) in self.directed else (a, b)

    def legal(self, k, cands) -> list[int]:
        p, q = self.orient(k)
        known = self.known(k)
        out = []
        for c in cands:
            c = int(c)
            if c == p or c == q or c == known:
                continue
            if (q, c) in self.directed or (c, p) in self.directed:
                continue
            if len(self.ef.get(ekey(q, c), ())) >= 2 or len(self.ef.get(ekey(c, p), ())) >= 2:
                continue
            if face_key((p, q, c)) in self.have:
                continue
            out.append(c)
        return out

    def front_edges(self) -> list[tuple[int, int]]:
        return sorted(k for k, v in self.ef.items() if len(v) == 1)


@dataclass
class Step:
    """One question: which legal vertex is on the far side of this front edge?"""
    edge: tuple[int, int]
    p: int
    q: int
    known: int
    cands: np.ndarray        # legal vertex indices
    F: np.ndarray            # (len(cands), FEAT) descriptions in the edge's frame
    dist_mid: np.ndarray
    dist_mirror: np.ndarray
    dist_pmirror: np.ndarray
    closes: np.ndarray       # how many front edges each candidate would close
    phase: int = 0           # which of the BINS question-phases this edge is in
    along_o: float = 0.0     # where the known corner stands over the edge
    owid_over_elen: float = 0.0   # and how tall it is, in edge lengths
    n_used: int = 0          # how many vertices the surface has reached so far
    n_front: int = 0         # how many edges are still open


def phase_of(along_o: float, owid_over_elen: float) -> int:
    """The question's phase, from the two numbers that describe the KNOWN face alone:
    where its corner stands over the edge (right angle at the corner / between /
    at an endpoint) and how tall it is over the edge. The joiner is phase-gated the
    way the delay line is — one weight row per phase — because a crease and a
    quad's diagonal are different questions and one line cannot answer both."""
    a = min(int(abs(along_o) * 2.0 * 3.0), 2)
    w = 0 if owid_over_elen < 0.5 else (1 if owid_over_elen < 1.0 else 2)
    return a * 3 + w


def step_of(surface: Surface, k, near: int = NEAR, describe: bool = True) -> Step | None:
    """Describe every legal candidate for the front edge k. None if nothing is legal.

    THE DESCRIPTIONS, all scale-free (divided by the edge length), all measured in
    the edge's own frame, none of them a world axis:
       0  one                      (the bias)
       1  closes the edge q-c      (a front edge would be finished)
       2  closes the edge c-p
       3  -distance to the midpoint
       4  -distance to the line-mirror of the known corner
       5  -distance to the point-mirror (the parallelogram's fourth corner)
       6  -(along)^2               centred over the edge?
       7  -(out)^2                 in the known face's plane?
       8  out                      which side of that plane? (a consistent solid folds one way)
       9  -(|along| - 1/2)^2       standing over one END of the edge? (a crease)
      10  regime * -(point-mirror distance)^2   where regime says the known face has
                                   its right angle at the known corner (a quad's diagonal)
      11  (1-regime) * -(|along|-1/2)^2 - (1-regime) * across^2   ... or at an endpoint (a crease)
      12  -valence so far / 6      how many faces already meet at c
      13  |out|

    ADDED 2026-09-05, and the first one is the one that mattered: THE FOLD.
      14  cos of the dihedral angle the new face would make with the known face
      15  sin of it                a solid folds its faces at a few angles, not any angle
      16  the candidate's distance from the edge's LINE (not its midpoint)
      17  -(that distance - the known corner's own)^2   the far corner stands as high
      18  -|c - q| / edge length    the two new edges the face would create
      19  -|c - p| / edge length
      20  -(|c-q| - |c-p|)^2        would the new face be isoceles over the edge?
      21  -max of the two           and how long the longer one is
      22  -min of the two
      23  the new face's area / edge^2
      24  its quality (1 for equilateral, 0 for a sliver)
      25  -(its area - the known face's)^2
      26  the candidate is a vertex no face has reached yet
      27  how many FRONT edges already end at it / 4
      28  it is already in the surface
      29  how far its valence is below 4
      30  closes BOTH new edges — the join fills a three-edge hole
      31  its rank by mirror distance among the legal candidates (0 nearest, 1 furthest)
      32  its rank by midpoint distance             — a rank is a per-question
      33  its rank by point-mirror distance            normalisation: it does not care
      34  it is the nearest to the mirror              how big this shape is
      35  it is the nearest to the midpoint
      36  it is the nearest to the point-mirror
      37  -z-score of its mirror distance within this question
      38  -z-score of its midpoint distance
      39  -z-score of its point-mirror distance
      40  it lies exactly in the known face's plane
      41  -|out|                    (linear, where 7 is squared)
      42  -distance to the midpoint in units of the candidate's OWN nearest-neighbour
      43  -|c - q| in the same units   — local edge length, not the shape's size
      44  which way the new face would look, out of the vertex cloud or into it
      45  the cosine of that
    """
    p, q = surface.orient(k)
    known = surface.known(k)
    T = surface.table
    pa, pb, po = T[p], T[q], T[known]
    mid, u, v, n, elen, owid = frame_of(pa, pb, po)
    d = T - mid
    dist = np.linalg.norm(d, axis=1)
    if len(T) > near:
        pool = np.argpartition(dist, near)[:near]
    else:
        pool = np.arange(len(T))
    cands = surface.legal(k, pool.tolist())
    if not cands:
        return None
    C = np.array(cands, dtype=np.int64)
    if not describe:
        # KAV-14, 2026-09-06: most_common_answer only ever reads st.cands, yet it
        # used to build this whole 46-column design matrix for every step of every
        # training shape -- the 450/714/104-face STL parts included -- and throw all
        # of it away. Stopping here answers the same question. Nothing that scores a
        # chooser may use this Step: its descriptions are deliberately empty.
        _along = float(((po - mid) @ u) / elen)
        _none = np.zeros(len(C))
        return Step(k, p, q, known, C, np.zeros((len(C), 0)),
                    _none, _none, _none, _none,
                    phase_of(_along, owid / elen), _along, owid / elen,
                    len(surface.used), 0)
    dc = d[C]
    al = (dc @ u) / elen
    ac = (dc @ v) / elen
    ou = (dc @ n) / elen
    dd = dist[C]
    c1 = np.array([float(surface.is_front(ekey(q, c))) for c in cands])
    c2 = np.array([float(surface.is_front(ekey(c, p))) for c in cands])
    mirror = mirror_point(pa, pb, po)
    pmirror = point_mirror(pa, pb, po)
    dmir = np.linalg.norm(T[C] - mirror, axis=1)
    dpm = np.linalg.norm(T[C] - pmirror, axis=1)
    along_o = float(((po - mid) @ u) / elen)
    regime = float(np.clip(1.0 - 2.0 * abs(along_o), 0.0, 1.0))
    valence = np.array([float(surface.valence.get(c, 0)) for c in cands])
    end2 = (np.abs(al) - 0.5) ** 2

    # --- the fold, the two new edges, the new face, and the neighbourhood ---
    rad = np.sqrt(ac ** 2 + ou ** 2)
    rs = np.maximum(rad, 1e-9)
    owid_e = owid / elen
    lq = np.linalg.norm(T[C] - pb, axis=1) / elen
    lp = np.linalg.norm(T[C] - pa, axis=1) / elen
    cross = np.cross(np.broadcast_to(pb - pa, (len(C), 3)), T[C] - pa)
    area2 = np.linalg.norm(cross, axis=1)
    area = 0.5 * area2 / (elen ** 2)
    quality = 4.0 * np.sqrt(3.0) * (0.5 * area2) / \
        np.maximum((elen ** 2) * (1.0 + lq ** 2 + lp ** 2), 1e-12)
    fdeg = defaultdict(int)
    n_front = 0
    for kk, vv in surface.ef.items():
        if len(vv) == 1:
            n_front += 1
            fdeg[kk[0]] += 1
            fdeg[kk[1]] += 1
    front_deg = np.array([float(fdeg.get(c, 0)) for c in cands])
    in_used = np.array([1.0 if c in surface.used else 0.0 for c in cands])
    nn = _nearest_neighbour(T[pool])
    where = {int(x): i for i, x in enumerate(pool)}
    nnc = np.array([nn[where[int(c)]] for c in C])
    centre = T.mean(axis=0)
    tri_c = (pa + pb + T[C]) / 3.0
    dotc = np.einsum("ij,ij->i", cross, tri_c - centre)

    F = np.column_stack([
        np.ones(len(C)),
        c1, c2,
        -dd / elen,
        -dmir / elen,
        -dpm / elen,
        -al ** 2,
        -ou ** 2,
        ou,
        -end2,
        regime * -(dpm / elen) ** 2,
        (1.0 - regime) * -(end2 + ac ** 2),
        -valence / 6.0,
        np.abs(ou),
        ac / rs, ou / rs, rad, -(rad - owid_e) ** 2,
        -lq, -lp, -(lq - lp) ** 2, -np.maximum(lq, lp), -np.minimum(lq, lp),
        area, quality, -(area - 0.5 * owid_e) ** 2,
        (valence == 0).astype(float), front_deg / 4.0, in_used,
        np.maximum(0.0, 4.0 - valence) / 4.0,
        c1 * c2,
        -_ranknorm(dmir), -_ranknorm(dd), -_ranknorm(dpm),
        (dmir == dmir.min()).astype(float),
        (dd == dd.min()).astype(float),
        (dpm == dpm.min()).astype(float),
        -_zscore(dmir), -_zscore(dd), -_zscore(dpm),
        (np.abs(ou) < 1e-6).astype(float), -np.abs(ou),
        -dd / nnc, -(lq * elen) / nnc,
        np.sign(dotc),
        dotc / np.maximum(np.linalg.norm(cross, axis=1) *
                          np.linalg.norm(tri_c - centre, axis=1), 1e-12),
    ])
    return Step(k, p, q, known, C, F, dd, dmir, dpm, c1 + c2,
                phase_of(along_o, owid_e), along_o, owid_e,
                len(surface.used), n_front)


# ---------------------------------------------------------------- the grove

def _nearest_neighbour(P: np.ndarray) -> np.ndarray:
    """For every point, the distance to its nearest OTHER point — the LOCAL edge
    length, so a description can say "close" without knowing how big the shape is."""
    if len(P) < 2:
        return np.ones(len(P))
    D = np.linalg.norm(P[:, None, :] - P[None, :, :], axis=2)
    np.fill_diagonal(D, np.inf)
    d = D.min(axis=1)
    d[~np.isfinite(d)] = 1.0
    return np.maximum(d, 1e-9)


def _ranknorm(x: np.ndarray) -> np.ndarray:
    """0 for the smallest, 1 for the largest: a per-QUESTION normalisation."""
    n = len(x)
    if n < 2:
        return np.zeros(n)
    order = np.argsort(x, kind="stable")
    r = np.empty(n, dtype=np.float64)
    r[order] = np.arange(n, dtype=np.float64)
    return r / (n - 1)


def _zscore(x: np.ndarray) -> np.ndarray:
    s = float(x.std())
    return (x - x.mean()) / s if s > 1e-12 else np.zeros_like(x)


class Grove:
    """A gradient-boosted grove of small regression trees, written here in numpy.

    Why a grove and not the ridge line: the line was NOT at its ceiling (the
    2026-09-05 note above), but it is still one weight per description, and the
    joining question is not linear in them. Whether a fold of 90 degrees is right
    depends on whether the known face is a quad's diagonal or a crease; whether a
    long new edge is right depends on the local edge length. A tree asks those
    questions in sequence; a line has to average over them.

    Deterministic and dependency-free: quantile bins, histogram splits, weighted
    squared loss, no sampling and no randomness anywhere. Fitting it on this corpus
    is a fraction of a second — it is not a training run, and it does not belong
    on the fleet.
    """

    def __init__(self, n_trees=N_TREES, depth=DEPTH, lr=LR, bins=GROVE_BINS,
                 min_weight=1e-3, min_rows=10, l2=1.0) -> None:
        self.n_trees, self.depth, self.lr, self.bins = n_trees, depth, lr, bins
        self.min_weight, self.min_rows, self.l2 = min_weight, min_rows, l2

    def _edges(self, X):
        qs = np.linspace(0.0, 1.0, self.bins + 1)[1:-1]
        return [np.unique(np.quantile(X[:, j], qs)) for j in range(X.shape[1])]

    def _code(self, X):
        C = np.empty(X.shape, dtype=np.int64)
        for j, e in enumerate(self.edges):
            C[:, j] = np.searchsorted(e, X[:, j], side="right") if len(e) else 0
        return C

    def _grow(self, C, g, w, rows, depth):
        """One node: a leaf (value,) or a question (description, bin, left, right)."""
        W = float(w[rows].sum())
        val = float((g[rows] * w[rows]).sum() / (W + self.l2)) if W > 0 else 0.0
        if depth == 0 or len(rows) < self.min_rows or W <= self.min_weight:
            return (val,)
        nf = C.shape[1]
        flat = (C[rows] + (np.arange(nf) * self.nb)[None, :]).ravel()
        hs = np.bincount(flat, weights=np.repeat(g[rows] * w[rows], nf),
                         minlength=nf * self.nb).reshape(nf, self.nb)
        hw = np.bincount(flat, weights=np.repeat(w[rows], nf),
                         minlength=nf * self.nb).reshape(nf, self.nb)
        SL, WL = np.cumsum(hs, axis=1), np.cumsum(hw, axis=1)
        S, Wt = SL[:, -1:], WL[:, -1:]
        SR, WR = S - SL, Wt - WL
        ok = (WL > self.min_weight) & (WR > self.min_weight)
        gain = np.where(ok, SL ** 2 / np.maximum(WL, 1e-12) +
                        SR ** 2 / np.maximum(WR, 1e-12) -
                        S ** 2 / np.maximum(Wt, 1e-12), -np.inf)
        gain[:, -1] = -np.inf
        j, b = np.unravel_index(int(np.argmax(gain)), gain.shape)
        if not np.isfinite(gain[j, b]) or gain[j, b] <= 1e-12:
            return (val,)
        left, right = rows[C[rows, j] <= b], rows[C[rows, j] > b]
        if len(left) == 0 or len(right) == 0:
            return (val,)
        return (int(j), int(b), self._grow(C, g, w, left, depth - 1),
                self._grow(C, g, w, right, depth - 1))

    @staticmethod
    def _apply(node, C):
        out = np.zeros(len(C))
        stack = [(node, np.arange(len(C)))]
        while stack:
            nd, rows = stack.pop()
            if len(nd) == 1:
                out[rows] = nd[0]
                continue
            j, b, L, R = nd
            m = C[rows, j] <= b
            stack.append((L, rows[m]))
            stack.append((R, rows[~m]))
        return out

    def fit(self, X, y, w):
        X = np.asarray(X, dtype=np.float64)
        y = np.asarray(y, dtype=np.float64)
        w = np.asarray(w, dtype=np.float64)
        self.edges = self._edges(X)
        self.nb = self.bins + 1
        C = self._code(X)
        self.base = float((y * w).sum() / max(w.sum(), 1e-12))
        F = np.full(len(y), self.base)
        rows = np.arange(len(y))
        self.trees = []
        for _ in range(self.n_trees):
            t = self._grow(C, y - F, w, rows, self.depth)
            self.trees.append(t)
            F += self.lr * self._apply(t, C)
        return self

    def predict(self, X):
        C = self._code(np.asarray(X, dtype=np.float64))
        out = np.full(len(C), self.base)
        for t in self.trees:
            out += self.lr * self._apply(t, C)
        return out


def question_context(st: "Step") -> np.ndarray:
    """What the QUESTION is, as opposed to what a candidate is: where the known
    corner stands over the edge, how tall it is, how many candidates there are, how
    much surface has been said. These are the numbers `phase_of` bins into nine; the
    grove is given them whole and bins them itself, wherever they matter."""
    a = float(st.along_o)
    return np.array([a, abs(a), float(st.owid_over_elen),
                     float(np.clip(1.0 - 2.0 * abs(a), 0.0, 1.0)),
                     float(len(st.cands)), float(st.n_used), float(st.n_front)])


CONTEXT = False      # see design(): measured, and turned OFF


def design(st: "Step", context: bool = CONTEXT) -> np.ndarray:
    """The rows the grove sees for one question: every candidate's descriptions,
    CENTRED within the question — because the question is "which of these", not
    "how good is this". Centring is worth a lot: without it, LOO 0.8874 -> 0.8108.

    `context` would append the question's own numbers uncentred (a per-question
    constant is centred away otherwise). MEASURED on the training shapes and left
    OFF: it lifts leave-one-shape-out from 0.8874 to 0.9054 but leaves leave-four-out
    exactly where it was (0.8731) and costs two right solids (14/16 -> 12/16). A gain
    that only one fold structure can see is a gain in the fold structure."""
    F = st.F - st.F.mean(axis=0, keepdims=True)
    if context:
        F = np.column_stack([F, np.tile(question_context(st), (len(F), 1))])
    return F


class GroveScorer:
    """The learned joiner: a grove over the centred descriptions, argmax at the fringe."""

    def __init__(self, grove: Grove, context: bool = CONTEXT) -> None:
        self.grove, self.context = grove, context

    def choose(self, st: Step) -> int:
        return int(st.cands[int(np.argmax(self.grove.predict(design(st, self.context))))])

    def describe(self) -> dict:
        return {"kind": "grove", "trees": len(self.grove.trees),
                "depth": self.grove.depth, "lr": self.grove.lr,
                "descriptions": FEAT + (7 if self.context else 0)}


# ---------------------------------------------------------------- choosers

class Scorer:
    """The learned joiner: one weight row per question-phase, argmax at the fringe.
    `w` is the global row (every phase pooled); `W[phase]` overrides it where the
    phase had enough rows to earn its own line."""

    def __init__(self, w=None, W=None) -> None:
        self.w = np.zeros(FEAT) if w is None else np.asarray(w, dtype=np.float64)
        self.W = W if W is not None else {}

    def row(self, phase: int) -> np.ndarray:
        return self.W.get(int(phase), self.w)

    def choose(self, st: Step) -> int:
        return int(st.cands[int(np.argmax(st.F @ self.row(st.phase)))])


class MirrorFloor:
    def choose(self, st: Step) -> int:
        return int(st.cands[int(np.argmin(st.dist_mirror))])


class MidFloor:
    def choose(self, st: Step) -> int:
        return int(st.cands[int(np.argmin(st.dist_mid))])


class PointMirrorFloor:
    def choose(self, st: Step) -> int:
        return int(st.cands[int(np.argmin(st.dist_pmirror))])


class TruthChooser:
    """The oracle: names the true far corner when it is legal, else the line-mirror.
    Not a model. It is the CEILING of closure — it proves what the grammar can rebuild."""

    def __init__(self, faces_true) -> None:
        self.truth = edge_faces(faces_true)
        self.faces_true = np.asarray(faces_true, dtype=np.int64)

    def choose(self, st: Step) -> int:
        thirds = self.truth.get(st.edge, [])
        for t in thirds:
            if t != st.known and t in st.cands:
                return int(t)
        return int(st.cands[int(np.argmin(st.dist_mirror))])

    def restart(self, S: "Surface"):
        """A true face on the lowest unused vertex — the ceiling is allowed the truth."""
        for f in self.faces_true:
            if all(int(v) not in S.used for v in f):
                return tuple(int(v) for v in f)
        return None


class CloseFloor:
    def choose(self, st: Step) -> int:
        order = np.lexsort((st.dist_mirror, -st.closes))   # most closes, then nearest mirror
        return int(st.cands[int(order[0])])


class CommonFloor:
    def __init__(self, v: int) -> None:
        self.v = int(v)

    def choose(self, st: Step) -> int:
        return self.v if self.v in st.cands else int(st.cands[0])


# ---------------------------------------------------------------- the walk

def walk(table, faces_true, seeds=None, describe: bool = True):
    """Follow the TRUE surface along its own front, yielding (step, true far corner).

    Teacher-forced: whatever the model would have said, the walk adds the true
    face and goes on, so every question is asked from a state the truth reaches.
    Edges the truth itself does not answer (not exactly two faces) are skipped.
    """
    faces_true = np.asarray(faces_true, dtype=np.int64)
    if seeds is None:
        seeds = faces_true[:1]
    truth = edge_faces(faces_true)
    S = Surface(table, seeds)
    while S.front:
        k = S.front.popleft()
        if not S.is_front(k):
            continue
        thirds = truth.get(k, [])
        if len(thirds) != 2:
            continue
        known = S.known(k)
        if known not in thirds:
            continue
        far = thirds[1] if thirds[0] == known else thirds[0]
        st = step_of(S, k, describe=describe)
        yield st, far
        p, q = S.orient(k)
        f = (p, q, far)
        if face_key(f) not in S.have:
            S.add(f)


def training_pairs(corpus):
    """One row per (answer, rival): the answer's descriptions minus the rival's.

    The scorer must put the answer ABOVE every rival; that is a statement about
    differences, so the rows are differences and the target is simply +1. Ridge on
    them is the closed-form cousin of a ranking machine. Still linear, never searched.
    """
    X, P, R, misses, asked = [], [], [], 0, 0
    for _, tris in corpus:
        import mesh
        table, faces = mesh.table_and_faces(tris)
        for st, far in walk(table.astype(float), faces):
            asked += 1
            if st is None or far not in st.cands or len(st.cands) < 2:
                misses += 1
                continue
            i = int(np.flatnonzero(st.cands == far)[0])
            rivals = np.delete(st.F, i, axis=0)
            X.append(st.F[i][None, :] - rivals)
            P.append(np.full(len(rivals), st.phase))
            R.append(np.full(len(rivals), 1.0 / len(rivals)))
    if not X:
        return (np.zeros((0, FEAT)), np.zeros(0, dtype=int), np.zeros(0),
                misses, asked)
    return np.vstack(X), np.concatenate(P), np.concatenate(R), misses, asked


def intact_only(corpus):
    """Only shapes the Q=128 grid did not break may teach the joiner.

    THE GRID IS NOT A DECIMATOR (2026-09-05). Quantising the real printed parts
    collapses most of their faces -- MEASURED: pinch-rail 5,150 -> 1,354 faces,
    pinch-lever 1,036 -> 714, pinch-bar 1,018 -> 450, clip 280 -> 104. What
    survives is still edge-closed, so it LOOKS like a solid, but its joins are the
    grid's, not the part's. Teaching the joiner on them teaches wrong joins, and
    they drown the clean solids besides. They stay in mesh.our_corpus() and still
    teach the COORDINATE gate; they simply do not teach the JOINING one.

    MEASURED, leave-one-out over all 19 clean solids at seed fraction 0.25:
        fitted on every shape      3/19 right solids, joining accuracy 0.6273
        fitted on intact shapes    9/19 right solids, joining accuracy 0.6162
        FLOOR_mirror (no learning) 8/19 right solids, joining accuracy 0.5867
    This is the first setting in which the learner is ahead of the flat-mirror
    floor on BOTH numbers at once. Chosen on training shapes alone: in the
    leave-one-shape-out sweep over the training corpus, intact-only configurations
    took five of the top twelve places and the top one (0.7237 vs 0.6494 shipped).
    """
    import mesh
    kept = [(n, t) for n, t in corpus if mesh.dropped_by_grid(t) == 0]
    if not kept:
        # KAV-05, 2026-09-06: this used to `return kept if kept else list(corpus)`
        # -- a filter that can exclude everything and then quietly hands back the
        # very shapes this docstring says teach WRONG joins. That is ERAN's
        # empty-menu shape: no exception, no log line, and a plausible-looking
        # accuracy out the far end. A caller that genuinely wants the broken
        # shapes must pass them somewhere that does not claim to be intact.
        raise ValueError(
            f"no shape in this corpus survives the Q={mesh.Q} grid intact — the "
            f"joiner has nothing legitimate to learn from "
            f"({[n for n, _ in corpus]})")
    return kept


def _ridge_rank(X, lam: float, weight=None) -> np.ndarray:
    """Weighted ridge. `weight` is one number per ROW; None means every row alike."""
    if weight is None:
        A = X.T @ X + lam * np.eye(FEAT)
        return np.linalg.solve(A, X.T @ np.ones(len(X)))
    Xw = X * np.asarray(weight, dtype=np.float64)[:, None]
    A = Xw.T @ X + lam * np.eye(FEAT)
    return np.linalg.solve(A, Xw.T @ np.ones(len(X)))


def fit_line(corpus, lam: float = 1e-2) -> Scorer:
    """THE PREVIOUS LEARNER, kept because it is what the grove is measured against.

    Ridge on answer-minus-rival rows with target +1: the answer above every rival.
    One global line, then one line per question-phase that has enough rows.

    ONE QUESTION IS ONE VOTE (2026-09-05). A step with many legal candidates makes
    many (answer, rival) rows, so unweighted rows let a shape with many vertices
    shout down a shape with few: MEASURED, the three grid-decimated STL parts
    supplied 64,814 of 66,308 rows -- 97.8% -- while the sixteen clean solids the
    gates are actually about supplied 2.2%. Each row is therefore weighted
    1/(number of rivals), so every QUESTION carries the same weight however many
    candidates it happened to have.
    """
    corpus = intact_only(corpus)
    X, P, R, _, _ = training_pairs(corpus)
    w = _ridge_rank(X, lam, R)
    W = {}
    for ph in range(BINS):
        m = P == ph
        # KAV-11, 2026-09-06: this used to be `int(m.sum()) >= MIN_ROWS`, i.e. it
        # counted answer-rival ROWS -- the very quantity the paragraph above was
        # written to stop counting. One question with 60 legal candidates unlocked
        # a phase's private line by itself while thirty two-candidate questions did
        # not. R already holds 1/(rivals), so R[m].sum() IS the number of questions.
        if float(R[m].sum()) >= MIN_QUESTIONS:
            W[ph] = _ridge_rank(X[m], lam, R[m])
    return Scorer(w, W)


def training_candidates(corpus):
    """One row per legal candidate, its descriptions centred within its own question,
    labelled 1 if it was the answer and weighted 1/(candidates) so that every QUESTION
    carries one vote however many candidates it happened to have."""
    X, y, W = [], [], []
    for _, tris in corpus:
        import mesh
        table, faces = mesh.table_and_faces(tris)
        for st, far in walk(table.astype(float), faces):
            if st is None or far not in st.cands or len(st.cands) < 2:
                continue
            lab = (st.cands == far).astype(np.float64)
            X.append(design(st))
            y.append(lab - lab.mean())
            W.append(np.full(len(lab), 1.0 / len(lab)))
    if not X:
        return np.zeros((0, FEAT)), np.zeros(0), np.zeros(0)
    return np.vstack(X), np.concatenate(y), np.concatenate(W)


def fit(corpus, n_trees: int = N_TREES, depth: int = DEPTH, lr: float = LR) -> GroveScorer:
    """THE LEARNER: a gradient-boosted grove over the descriptions, centred within
    each question. Only intact shapes teach the joining (see `intact_only`).

    Fitting it is a fraction of a second on this corpus -- 1,712 rows of 46 numbers
    -- so it is closed-form-cheap, not a training run.
    """
    X, y, W = training_candidates(intact_only(corpus))
    return GroveScorer(Grove(n_trees=n_trees, depth=depth, lr=lr).fit(X, y, W))


def most_common_answer(corpus) -> int:
    """The far corner the truth names most often — CommonFloor's one constant.

    KAV-14, 2026-09-06: this used to run the full training_rows walk, building the
    46-column design matrix for every step of every training shape and discarding
    every one of them, to feed the weakest floor of the five (0.1429 sealed). It
    asks the same question of the same walk with the descriptions turned off, so
    the constant it returns is unchanged.
    """
    from collections import Counter
    import mesh
    c = Counter()
    for _, tris in corpus:
        table, faces = mesh.table_and_faces(tris)
        for st, far in walk(table.astype(float), faces, describe=False):
            if st is None or far not in st.cands:
                continue                      # the same rows training_rows kept
            c.update([int(far)])
    return c.most_common(1)[0][0] if c else 0


# ---------------------------------------------------------------- speaking

def close_triangles(S: Surface) -> int:
    """A hole of three front edges is not a choice: close it. Returns how many."""
    closed = 0
    changed = True
    while changed:
        changed = False
        for k in S.front_edges():
            if not S.is_front(k):
                continue
            p, q = S.orient(k)
            for c in S.legal(k, S.used):
                if S.is_front(ekey(q, c)) and S.is_front(ekey(c, p)):
                    S.add((p, q, c))
                    closed += 1
                    changed = True
                    break
            if changed:
                break
    return closed


def restart_seed(S: Surface):
    """When the front is empty but vertices remain: a new patch on the lowest unused
    vertex and its two nearest unused neighbours, wound so its normal points away
    from the unused cloud's centre. Declared, counted, never called learning."""
    unused = [i for i in range(len(S.table)) if i not in S.used]
    if len(unused) < 3:
        return None
    v0 = unused[0]
    others = np.array([i for i in unused if i != v0])
    d0 = np.linalg.norm(S.table[others] - S.table[v0], axis=1)
    v1 = int(others[int(np.argmin(d0))])
    rest = np.array([i for i in others if i != v1])
    d1 = np.linalg.norm(S.table[rest] - S.table[v0], axis=1) + \
        np.linalg.norm(S.table[rest] - S.table[v1], axis=1)
    order = np.argsort(d1)
    centre = S.table[unused].mean(axis=0)
    for j in order:
        v2 = int(rest[j])
        nrm = np.cross(S.table[v1] - S.table[v0], S.table[v2] - S.table[v0])
        if np.linalg.norm(nrm) < 1e-9:
            continue                                  # collinear: not a face
        f = (v0, v1, v2)
        tri_c = (S.table[v0] + S.table[v1] + S.table[v2]) / 3.0
        if nrm @ (tri_c - centre) < 0:
            f = (v0, v2, v1)
        return f
    return None


def grow(table, seeds, chooser, budget: int, restart: bool = True) -> np.ndarray:
    """Speak a surface: the grammar walks the front, the chooser names the far corner."""
    S = Surface(table, seeds)
    made = 0
    while True:
        while S.front and made < budget:
            k = S.front.popleft()
            if not S.is_front(k):
                continue
            st = step_of(S, k)
            if st is None:
                continue                              # a dead edge: nothing legal
            c = chooser.choose(st)
            S.add((st.p, st.q, c))
            made += 1
        made += close_triangles(S)
        if S.front and made < budget:
            continue
        if restart and made < budget:
            f = restart_seed(S)
            if f is not None:
                S.add(f)
                S.restarts += 1
                made += 1
                continue
        break
    return np.array(S.faces, dtype=np.int64)


def grow_report(table, seeds, chooser, budget: int, restart: bool = True) -> dict:
    """grow(), plus what happened on the way."""
    S = Surface(table, seeds)
    made = 0
    dead = 0
    while True:
        while S.front and made < budget:
            k = S.front.popleft()
            if not S.is_front(k):
                continue
            st = step_of(S, k)
            if st is None:
                dead += 1
                continue
            c = chooser.choose(st)
            S.add((st.p, st.q, c))
            made += 1
        made += close_triangles(S)
        if S.front and made < budget:
            continue
        if restart and made < budget:
            f = chooser.restart(S) if hasattr(chooser, "restart") else restart_seed(S)
            if f is not None:
                S.add(f)
                S.restarts += 1
                made += 1
                continue
        break
    return {"faces": np.array(S.faces, dtype=np.int64), "made": made,
            "dead_edges": dead, "restarts": S.restarts,
            "front_left": len(S.front_edges())}


# ---------------------------------------------------------------- measuring

def score(chooser_named: dict, corpus, seed_fraction: float | None = None) -> dict:
    """Accuracy of every chooser along the truth's walk of each shape in corpus.

    WHERE THE WALK STARTS IS PART OF THE QUESTION (KAV-03, 2026-09-06). With
    seed_fraction=None the walk starts from ONE face (faces_true[:1]) -- that is the
    number gate 1b has always reported. Gate 2 does not start there: joiner.closure
    seeds with seed_faces(faces, 0.25), a quarter of EVERY connected piece. Different
    seed, different front, different question set -- so the per-step number could not
    predict the solid number, and the ladder "accuracy -> solid" did not join up.
    MEASURED 2026-09-05: GROVE_NOFOLD scores 1.0000 on slab (11/11) and on post and
    still fails to return the right solid, while FOLD_GROVE at the same 1.0000 on post
    does return it. Pass seed_fraction to ask the question from gate 2's own start.

    Still teacher-forced either way: whatever the chooser said, walk() adds the TRUE
    face and goes on, so this never visits the states free-running growth reaches.

    A QUESTION THE GRAMMAR CANNOT REACH IS A MISS (KAV-09, 2026-09-06). It used to
    be dropped from the DENOMINATOR -- `beyond += 1; continue` BEFORE `n += 1` --
    which made accuracy go UP as the grammar's reach got worse. Dormant until now
    only because NEAR=64 exceeds the vertex count of every clean solid (the largest,
    drum12, has 24), so beyond_reach is 0 on the sealed and the wide gate; it would
    have started flattering the model the day a bigger clean solid entered the
    corpus. It is still reported separately, so the reach limit is visible AND costs.
    """
    hits = {name: 0 for name in chooser_named}
    n = 0
    beyond = 0
    for _, tris in corpus:
        import mesh
        table, faces = mesh.table_and_faces(tris)
        seeds = None if seed_fraction is None else seed_faces(faces, seed_fraction)
        for st, far in walk(table.astype(float), faces, seeds):
            n += 1
            if st is None or far not in st.cands:
                beyond += 1
                continue                  # counted, and nobody scores a hit on it
            for name, ch in chooser_named.items():
                hits[name] += int(ch.choose(st) == far)
    return {"frames": n, "beyond_reach": beyond, "hits": dict(hits),
            "started_from": ("one face" if seed_fraction is None
                             else f"gate 2's own seed: {seed_fraction:.2f} of every piece"),
            "accuracy": {k: hits[k] / max(n, 1) for k in hits},
            "CEILING": 1.0}


VOLUME_TOLERANCE = 0.01   # a solid is the RIGHT solid only if its volume is the truth's


def components(faces) -> list[np.ndarray]:
    """Faces grouped by connectivity (two faces are joined if they share an edge)."""
    faces = np.asarray(faces, dtype=np.int64)
    ef = edge_faces(faces)
    owner = defaultdict(list)
    for i, f in enumerate(faces):
        a, b, c = (int(x) for x in f)
        for e in (ekey(a, b), ekey(b, c), ekey(c, a)):
            owner[e].append(i)
    seen, out = set(), []
    for i in range(len(faces)):
        if i in seen:
            continue
        stack, comp = [i], []
        seen.add(i)
        while stack:
            j = stack.pop()
            comp.append(j)
            a, b, c = (int(x) for x in faces[j])
            for e in (ekey(a, b), ekey(b, c), ekey(c, a)):
                for k in owner[e]:
                    if k not in seen:
                        seen.add(k)
                        stack.append(k)
        out.append(np.array(sorted(comp)))
    return out


def seed_faces(faces, fraction: float = SEED_FRACTION) -> np.ndarray:
    """The first `fraction` of every connected piece — the organ is handed a quarter of
    each piece, so a shape made of two bodies is not a test of guessing where the
    second body starts."""
    faces = np.asarray(faces, dtype=np.int64)
    picked = []
    for comp in components(faces):
        keep = max(1, int(len(comp) * fraction))
        picked.extend(comp[:keep].tolist())
    return faces[sorted(picked)]


def closure(chooser, corpus, seed_fraction: float = SEED_FRACTION, oracle: bool = False,
            budget_scale: float = 1.0) -> dict:
    """Hand the organ a quarter of each sealed shape and its vertices; is what it says a solid?

    "Watertight" alone is not enough and the first run of this file proved it: a
    chooser that closes slivers can be watertight with a sixth of the volume. So a
    shape counts as SOLID only when every edge is shared by two faces AND it has the
    truth's number of faces AND its volume is the truth's within VOLUME_TOLERANCE.
    """
    import mesh
    shapes = []
    tot = {"tried": 0, "watertight": 0, "solid": 0, "shared": 0, "lone": 0, "faces": 0,
           "true_faces": 0, "restarts": 0, "front_left": 0, "cut_off": 0}
    for name, tris in corpus:
        _, lo, scale = mesh.quantise(np.asarray(tris, float))
        table, faces = mesh.table_and_faces(tris)
        seeds = seed_faces(faces, seed_fraction)
        keep = len(seeds)
        ch = TruthChooser(faces) if oracle else chooser
        budget = int(round((len(faces) - keep) * budget_scale))
        rep = grow_report(table.astype(float), seeds, ch, budget)
        said = rep["faces"]
        got = mesh.dequantise(table, lo, scale)[said]
        g = mesh.geometry(got)
        truth_g = mesh.geometry(mesh.dequantise(table, lo, scale)[faces])
        ratio = (g["volume"] / truth_g["volume"]) if truth_g["volume"] else 0.0
        solid = bool(g["watertight"]) and len(said) == len(faces) and abs(ratio - 1.0) <= VOLUME_TOLERANCE
        # KAV-08, 2026-09-06: grow_report has always returned `made` and `front_left`
        # and closure has always thrown them away, so a shape CUT OFF by the budget
        # with its front still open was reported identically to one the learner
        # genuinely left open. The verdict printed "open (4 lone)" for a state it had
        # not distinguished. Now it says which it was, out loud.
        made, left = int(rep["made"]), int(rep["front_left"])
        cut_off = left > 0 and made >= budget
        if left == 0:
            status = "closed"
        elif cut_off:
            status = (f"CUT OFF at the budget ({made} faces made of {budget} allowed) "
                      f"with {left} edges still on the front")
        else:
            status = f"open: the learner stopped with {left} edges on the front"
        row = {"name": name, "seeded": keep, "true_faces": int(len(faces)),
               "said_faces": int(len(said)), "watertight": bool(g["watertight"]),
               "solid": solid, "shared": g["shared_2"], "lone": g["lone"],
               "volume_ratio": ratio,
               "made": made, "budget": int(budget), "front_left": left,
               "cut_off": bool(cut_off), "status": status,
               "restarts": rep["restarts"], "dead_edges": rep["dead_edges"]}
        shapes.append(row)
        tot["tried"] += 1
        tot["watertight"] += int(g["watertight"])
        tot["solid"] += int(solid)
        tot["shared"] += g["shared_2"]
        tot["lone"] += g["lone"]
        tot["faces"] += int(len(said))
        tot["true_faces"] += int(len(faces))
        tot["restarts"] += rep["restarts"]
        tot["front_left"] += left
        tot["cut_off"] += int(cut_off)
    tot["budget_scale"] = float(budget_scale)
    tot["shapes"] = shapes
    edges = tot["shared"] + tot["lone"]
    tot["connectivity"] = tot["shared"] / edges if edges else 0.0
    return tot
