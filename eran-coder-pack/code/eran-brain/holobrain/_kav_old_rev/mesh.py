"""KAV / קָו — THE TONGUE: a shape, said as a sentence.

The name is Iddo's, 2026-09-01 21:00, and it is exact twice over.
  * Lurianic Kabbalah: after the contraction, ONE line - the קו - enters the empty
    space, and קו המידה, the line of measure, is what gives the light its shape.
    The line is the thing that forms worlds.
  * Isaiah 44:13 is a modelling pipeline written in a single verse: the craftsman
    STRETCHES A LINE, marks with a stylus, shapes with planes, marks with a
    compass, and makes it in the PATTERN of a man. (Ezekiel 40:3 holds the rod he
    also reached for: the measuring reed that surveys a building.)
  * And plainly: this model emits a LINE of tokens that becomes a shape.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

לזכרה של עלמה ז"ל.

Iddo, 2026-09-01 20:57: "תתחיל לכתוב את המודלר שלנו כמו NLP בשפת עלמה."
Iddo, 2026-09-03 02:15: "קדימה, תקן את קו עם אינדקסי קודקודים."

WHY A MESH AND NOT A PICTURE, in one paragraph, because the choice is the whole
project: a spark in ALMA v0.3 is a SCALAR. An image is a tensor and every organ
that paints one (WINSTON, TZELEM) has to reach for a spell to carry it. A mesh
written as a token stream is ALREADY a stream of numbers. So of every family in
generative AI, the autoregressive-mesh family (PolyGen -> MeshGPT -> EdgeRunner ->
MeshRipple) is the ONE that ALMA can speak today, in the language exactly as it
stands, with nothing smuggled in.

THE GRAMMAR — VERTEX-INDEXED, since 2026-09-03
----------------------------------------------
The first grammar was triangle soup: nine coordinates per face. It passed gate 1
and failed gate 2 by construction — two faces could share an edge only by saying
the identical coordinate triple twice, which a regressor never does — and the
picture showed twelve loose triangles. So the sentence is now in two parts, the
way PolyGen and MeshGPT say a shape, and the way Isaiah says it (first the line
is stretched, THEN the shape is marked out):

    BOS  x y z  x y z ... (every vertex, once, sorted by z then y then x)
    SEP
         i j k  i j k ... (every face as three INDICES into that table)
    EOS

  * Coordinates are quantised to Q levels in the unit cube; the transform is kept.
  * Corners the grid cannot tell apart become ONE vertex — that merge is what makes
    a shared edge sayable at all.
  * A face is rotated so its smallest index leads (a ROTATION, never a sort: sorting
    would flip the winding and turn the surface inside out); faces are then sorted.
    One shape, one sentence.
  * Faces the grid cannot say — a corner repeated, or the same face twice — are
    dropped when the shape is quantised, and `dropped_by_grid` reports how many.
    THIS IS WHERE THE REAL PARTS BREAK: at Q=128 the PINCH-RAIL loses 3,796 of its
    5,150 faces to the grid. That is the grid's limit, not the model's, and the
    ruler says so instead of scoring a model against a target that is not a solid.

GATE 0 — PROVENANCE. The meshes are ours: boxes and prisms we wrote, and STLs
already in this repository (the Pongo clip, the larynx mould). Nothing scraped.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass

import numpy as np

Q = 128                    # quantisation levels per axis
BOS = Q                    # 128
EOS = Q + 1                # 129
SEP = Q + 2                # 130 — the line between the vertices and the faces
VOCAB = Q + 3              # 131
PER_VERTEX = 3             # x y z
PER_FACE = 3               # i j k — three indices, no longer nine coordinates


@dataclass
class Shape:
    """A triangle soup, plus the transform that put it in the unit cube."""
    tris: np.ndarray           # (F, 3, 3) float
    lo: np.ndarray = None      # unit-cube transform, so a sentence can be spoken back
    scale: float = 1.0

    def __len__(self) -> int:
        return int(self.tris.shape[0])


# ------------------------------------------------------------------ shapes in

def box(lo, hi) -> np.ndarray:
    """The 12 triangles of an axis-aligned box, outward facing."""
    lo, hi = np.asarray(lo, float), np.asarray(hi, float)
    x0, y0, z0 = lo
    x1, y1, z1 = hi
    v = np.array([[x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0],
                  [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]])
    faces = [(0, 2, 1), (0, 3, 2),      # bottom
             (4, 5, 6), (4, 6, 7),      # top
             (0, 1, 5), (0, 5, 4),      # -y
             (2, 3, 7), (2, 7, 6),      # +y
             (1, 2, 6), (1, 6, 5),      # +x
             (0, 4, 7), (0, 7, 3)]      # -x
    return np.array([[v[a], v[b], v[c]] for a, b, c in faces])


def regular(n: int, r: float, phase: float = 0.0) -> np.ndarray:
    """A regular n-gon in the plane, counter-clockwise, radius r."""
    t = phase + 2 * np.pi * np.arange(n) / n
    return np.stack([r * np.cos(t), r * np.sin(t)], axis=1)


def prism(bottom: np.ndarray, top: np.ndarray, z0: float, z1: float) -> np.ndarray:
    """A closed prism (or frustum) between two CONVEX rings of the same length.

    Rings are counter-clockwise seen from +z. Caps are fans from ring vertex 0,
    sides are two triangles per edge; every winding is outward. Written here so
    that the corpus can hold solids that are not boxes without downloading a thing.
    """
    n = len(bottom)
    assert len(top) == n and n >= 3
    B = np.column_stack([bottom, np.full(n, float(z0))])
    T = np.column_stack([top, np.full(n, float(z1))])
    tris = []
    for i in range(1, n - 1):
        tris.append([B[0], B[i + 1], B[i]])         # bottom cap, seen from below
        tris.append([T[0], T[i], T[i + 1]])         # top cap
    for i in range(n):
        j = (i + 1) % n
        tris.append([B[i], B[j], T[j]])
        tris.append([B[i], T[j], T[i]])
    return np.array(tris)


def pyramid(half: float, h: float) -> np.ndarray:
    """A square pyramid: five vertices, six faces, outward."""
    b = np.array([[-half, -half, 0], [half, -half, 0], [half, half, 0], [-half, half, 0]], float)
    apex = np.array([0.0, 0.0, h])
    tris = [[b[0], b[2], b[1]], [b[0], b[3], b[2]]]
    for i in range(4):
        tris.append([b[i], b[(i + 1) % 4], apex])
    return np.array(tris)


def read_stl(path: str) -> np.ndarray:
    """Binary STL -> (F,3,3). The same three lines that shipped the Pongo clip."""
    with open(path, "rb") as f:
        f.read(80)
        n = struct.unpack("<I", f.read(4))[0]
        out = np.empty((n, 3, 3))
        for i in range(n):
            d = struct.unpack("<12fH", f.read(50))
            out[i] = np.array(d[3:12]).reshape(3, 3)
    return out


def write_stl(path: str, tris: np.ndarray, header: bytes = b"YOTZER") -> None:
    with open(path, "wb") as f:
        f.write(header.ljust(80, b" "))
        f.write(struct.pack("<I", len(tris)))
        for t in tris:
            n = np.cross(t[1] - t[0], t[2] - t[0])
            ln = np.linalg.norm(n)
            n = n / ln if ln > 1e-12 else np.zeros(3)
            f.write(struct.pack("<12fH", *n, *t.reshape(-1), 0))


# ------------------------------------------------------------------ the tongue

def quantise(tris: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
    """Into the unit cube, then onto the Q-grid. Returns (ints, lo, scale)."""
    pts = tris.reshape(-1, 3)
    lo = pts.min(axis=0)
    scale = float(max((pts.max(axis=0) - lo).max(), 1e-9))
    u = (tris - lo) / scale                       # 0..1 on the longest axis
    return np.clip(np.rint(u * (Q - 1)), 0, Q - 1).astype(np.int64), lo, scale


def dequantise(ints: np.ndarray, lo, scale: float) -> np.ndarray:
    return ints.astype(np.float64) / (Q - 1) * scale + np.asarray(lo, float)


def canonical_faces(faces: np.ndarray) -> np.ndarray:
    """Rotate each face so its smallest index leads, drop what the grid cannot say
    (a repeated corner, or a face said twice), then sort. One shape, one sentence."""
    seen, out = set(), []
    for f in np.asarray(faces, dtype=np.int64).reshape(-1, 3):
        if len({int(f[0]), int(f[1]), int(f[2])}) < 3:
            continue                                   # degenerate on this grid
        r = tuple(int(x) for x in np.roll(f, -int(np.argmin(f))))
        if r in seen:
            continue
        seen.add(r)
        out.append(r)
    if not out:
        return np.zeros((0, 3), dtype=np.int64)
    return np.array(sorted(out), dtype=np.int64)


def _tongue(tris) -> tuple[np.ndarray, np.ndarray, np.ndarray, float, int]:
    """(table, faces, lo, scale, dropped) — the shape as the grid can say it."""
    ints, lo, scale = quantise(np.asarray(tris, float))
    flat = ints.reshape(-1, 3)
    uniq, inv = np.unique(flat, axis=0, return_inverse=True)
    inv = np.asarray(inv).reshape(-1)
    order = np.lexsort((uniq[:, 0], uniq[:, 1], uniq[:, 2]))   # by z, then y, then x
    rank = np.empty(len(uniq), dtype=np.int64)
    rank[order] = np.arange(len(uniq))
    table = uniq[order]
    raw = rank[inv].reshape(-1, 3)
    faces = canonical_faces(raw)
    return table, faces, lo, scale, int(len(raw) - len(faces))


def table_and_faces(tris) -> tuple[np.ndarray, np.ndarray]:
    """A shape becomes (vertex table, faces as index triples), canonically."""
    table, faces, _, _, _ = _tongue(tris)
    return table, faces


def dropped_by_grid(tris) -> int:
    """How many faces the Q-grid could not say. Zero for every box; thousands for a
    finely tessellated STL — the number that tells you whether gate 2 is even askable."""
    return _tongue(tris)[4]


def speak(tris: np.ndarray) -> tuple[list[int], np.ndarray, float]:
    """A shape becomes a sentence: BOS vertices SEP faces EOS. Returns (tokens, lo, scale)."""
    table, faces, lo, scale, _ = _tongue(tris)
    toks = [BOS]
    toks.extend(int(c) for c in table.reshape(-1))
    toks.append(SEP)
    toks.extend(int(i) for i in faces.reshape(-1))
    toks.append(EOS)
    return toks, lo, scale


def split_sentence(tokens: list[int]) -> tuple[list[int], list[int]]:
    """(vertex tokens, face tokens) — the two halves of the line, markers removed."""
    body = [t for t in tokens if t not in (BOS, EOS)]
    if SEP in body:
        s = body.index(SEP)
        return body[:s], [t for t in body[s + 1:] if t != SEP]
    return body, []


def hear(tokens: list[int], lo=(0.0, 0.0, 0.0), scale: float = 1.0):
    """A sentence becomes a shape again.

    Returns (tris, complaint). `complaint` is None when the sentence was whole —
    and is a STRING when it was not, because a modeller that silently discards a
    half-spoken face, or clips an index onto a vertex that was never said, is a
    modeller whose failures never reach a number.
    """
    empty = np.zeros((0, 3, 3))
    if SEP not in tokens:
        return empty, "no line was drawn between the vertices and the faces"
    head, tail = split_sentence(tokens)
    if any(t < 0 or t >= Q for t in head):
        return empty, "a token outside the coordinate range was said"
    if len(head) % PER_VERTEX:
        return empty, f"the last vertex was cut short: {len(head) % PER_VERTEX} of 3 tokens"
    nv = len(head) // PER_VERTEX
    if nv == 0:
        return empty, "no vertices were said"
    table = np.array(head, dtype=np.int64).reshape(nv, 3)
    leftover = len(tail) % PER_FACE
    nf = len(tail) // PER_FACE
    faces = np.array(tail[:nf * PER_FACE], dtype=np.int64).reshape(nf, 3) \
        if nf else np.zeros((0, 3), dtype=np.int64)
    bad = [int(i) for i in faces.reshape(-1) if i < 0 or i >= nv]
    whole = np.array([bool(np.all((f >= 0) & (f < nv))) for f in faces], dtype=bool) \
        if nf else np.zeros(0, dtype=bool)
    good = faces[whole] if nf else faces
    tris = dequantise(table, lo, scale)[good] if len(good) else empty
    if bad:
        return tris, (f"a face pointed at vertex {bad[0]} but only {nv} vertices were said"
                      f" ({len(bad)} such corners)")
    if leftover:
        return tris, f"the last face was cut short: {leftover} of 3 tokens"
    if nf == 0:
        return tris, "no faces were said"
    return tris, None


# ------------------------------------------------------------------ the corpus

def our_corpus() -> list[tuple[str, np.ndarray]]:
    """Shapes ERAN is allowed to learn from: ones this lab made.

    Boxes, then solids that are not boxes — prisms, drums, a pyramid, a frustum —
    all written above, all closed by construction, all sayable on the grid. Then the
    real printed parts, which the grid breaks (see the docstring): they stay in the
    corpus for the coordinate gate and are named in the ruler as not-solids.
    """
    out = [
        ("cube", box([0, 0, 0], [1, 1, 1])),
        ("slab", box([0, 0, 0], [2, 0.3, 1])),
        ("post", box([0, 0, 0], [0.4, 2.2, 0.4])),
        ("tower", box([0, 0, 0], [0.6, 3.0, 0.6])),
        ("plate", box([0, 0, 0], [3.0, 0.15, 2.0])),
        ("beam", box([0, 0, 0], [4.0, 0.5, 0.5])),
        ("brick", box([0, 0, 0], [1.6, 0.8, 0.8])),
        ("cell", box([0, 0, 0], [0.9, 0.9, 1.8])),
        ("tri-prism", prism(regular(3, 0.7), regular(3, 0.7), 0, 1.0)),
        ("wedge", prism(np.array([[0, 0], [1, 0], [0, 0.6]], float),
                        np.array([[0, 0], [1, 0], [0, 0.6]], float), 0, 0.8)),
        ("pent-prism", prism(regular(5, 0.6), regular(5, 0.6), 0, 1.4)),
        ("drum6", prism(regular(6, 0.5), regular(6, 0.5), 0, 1.2)),
        ("drum8", prism(regular(8, 0.8), regular(8, 0.8), 0, 0.5)),
        ("drum12", prism(regular(12, 0.6), regular(12, 0.6), 0, 2.0)),
        ("frustum", prism(regular(4, 1.0, np.pi / 4), regular(4, 0.5, np.pi / 4), 0, 0.9)),
        ("cone8", prism(regular(8, 0.9), regular(8, 0.3), 0, 1.5)),
        ("pyramid", pyramid(0.8, 1.1)),
    ]
    import os as _os
    _ROOT = _os.path.abspath(_os.path.join(_os.path.dirname(__file__),
                                           "..", "..", ".."))
    for name, rel in (("clip", "pongo-dave/dave-uclip-v1.stl"),
                      ("pinch-bar", "alma-larynx/FULL-THROAT/PINCH-BAR.stl"),
                      ("pinch-lever", "alma-larynx/FULL-THROAT/PINCH-LEVER.stl"),
                      ("pinch-rail", "alma-larynx/FULL-THROAT/PINCH-RAIL.stl")):
        path = _os.path.join(_ROOT, rel)
        if _os.path.exists(path):
            out.append((name, read_stl(path)))

    # two boxes at once — the first sentence with more than one object in it
    out.append(("pair", np.concatenate([box([0, 0, 0], [1, 1, 1]),
                                        box([1.4, 0, 0], [2.2, 1.6, 1])])))
    out.append(("stack", np.concatenate([box([0, 0, 0], [1, 0.6, 1]),
                                         box([0.1, 0.6, 0.1], [0.9, 1.4, 0.9])])))
    return out


# ------------------------------------------------------------------ the solid

def geometry(tris) -> dict:
    """Is this a SURFACE, or a pile of triangles that happen to be near each other?

    Added 2026-09-01 22:05, the moment a rendered picture said what the numbers had
    not. A closed surface has every edge shared by exactly two faces. That single
    count is the difference between a mesh and a soup, and it is not something a
    model can be given credit for by accident.
    """
    from collections import Counter
    t = np.asarray(tris, dtype=np.float64)
    if len(t) == 0:
        return {"faces": 0, "edges": 0, "shared_2": 0, "lone": 0,
                "watertight": False, "volume": 0.0}
    q = np.rint(t * 1e6).astype(np.int64)          # quantised so equality is exact
    edges = Counter()
    for f in q:
        for a, b in ((0, 1), (1, 2), (2, 0)):
            edges[tuple(sorted((tuple(f[a]), tuple(f[b]))))] += 1
    counts = Counter(edges.values())
    vol = abs(float(np.einsum("fk,fk->f", t[:, 0, :],
                              np.cross(t[:, 1, :] - t[:, 0, :],
                                       t[:, 2, :] - t[:, 0, :])).sum() / 6.0))
    return {"faces": int(len(t)), "edges": len(edges),
            "shared_2": counts.get(2, 0), "lone": counts.get(1, 0),
            "watertight": counts.get(1, 0) == 0 and counts.get(2, 0) == len(edges),
            "volume": vol}
