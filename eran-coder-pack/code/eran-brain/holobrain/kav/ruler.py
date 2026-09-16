"""KAV / קָו — THE RULER: can it say a shape it was never shown?

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

THREE GATES, and the last one cannot be faked by any number
-----------------------------------------------------------
GATE 1 — PREDICTION of the vertex half of the sentence (the coordinates), on
   shapes never seen, against three floors:
     FLOOR_common   always say the most frequent token in the training corpus.
     FLOOR_repeat   always say the previous token — strong on sorted vertices.
     CEILING        the truth, printed to keep the scale honest.

GATE 1b — JOINING. Given the vertices and the face on one side of an edge, which
   legal vertex is on the other side? The learned scorer against the grammar's
   own floors (mirror / midpoint / most-closing / most-common). Learning is
   credited here and only here.

GATE 2 — SOLID. Hand the organ a quarter of a sealed shape and all its vertices;
   let it speak the rest; ask the geometry whether every edge is shared by exactly
   two faces. Since 2026-09-03 this is asked ONLY of shapes whose truth is a solid
   on the grid: the real printed parts lose most of their faces to Q=128 (the
   PINCH-RAIL 3,796 of 5,150) and are reported as not-solids, not scored against.

A model passes gate 1 only if it beats both floors; gate 1b only if it beats every
floor; gate 2 only if every sealed solid comes back watertight.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import mesh                                            # noqa: E402
import joiner                                          # noqa: E402
from anatomy import K, PHASES, Posture, continue_shape, frames   # noqa: E402
from learn import fit, split                           # noqa: E402

HELD = ("plate", "stack", "drum8", "pinch-rail")   # sealed: never fitted on, ever
SOLID_HELD = ("plate", "stack", "drum8")           # the sealed shapes gate 2 may ask about


def _most_common(corpus) -> int:
    """The most frequent vertex token in `corpus`. (KAV-14: the old `k` argument was
    accepted and never used.)"""
    from collections import Counter
    c = Counter()
    for _, tris in corpus:
        toks, _, _ = mesh.speak(tris)
        c.update(mesh.split_sentence(toks)[0])
    return c.most_common(1)[0][0]


def _constant_floors(corpus, k: int) -> dict:
    """The constants a lazy model would say, computed ON THE SET IT WILL BE JUDGED ON.

    KAV-06, 2026-09-06. Gate 1's floor used to be the most-common token of the TRAIN
    set -- token 0, common because boxes sit at the origin -- applied to a sealed set
    where 0 is rare. MEASURED that morning: KAV 0.0734 sealed against that floor's
    0.0267 was a 2.75x margin; against the sealed set's OWN most-common token (6) the
    floor is 0.0558 and the margin is 1.32x. A floor that is easy because it was
    computed somewhere else is not a floor.
    """
    from collections import Counter
    allc, byph = Counter(), [Counter() for _ in range(PHASES)]
    for _, tris in corpus:
        toks, _, _ = mesh.speak(tris)
        for _ctx, ph, ans in frames(toks, k):
            allc[ans] += 1
            byph[ph][ans] += 1
    common = int(allc.most_common(1)[0][0]) if allc else 0
    per = [int(c.most_common(1)[0][0]) if c else common for c in byph]
    return {"common": common, "per_phase": per}


FLOORS = ("FLOOR_common", "FLOOR_common_train", "FLOOR_repeat", "FLOOR_phase")


def score(posture: Posture, corpus, common_train: int) -> dict:
    """Next-token accuracy and error on the vertex half, for the model and the floors.

    Reported PER SHAPE as well as in total (KAV-06): the sealed set is 2,097 frames
    of which pinch-rail alone is 1,977 -- 94.3% -- so a single grid-broken printed
    part was 94% of gate 1's verdict and nothing printed said so.
    """
    names = ("KAV",) + FLOORS
    own = _constant_floors(corpus, posture.k)
    hits = {k: 0 for k in names}
    errs = {k: [] for k in names}
    by_shape = {}
    n = 0
    for shape_name, tris in corpus:
        toks, _, _ = mesh.speak(tris)
        s_hits, s_n = {k: 0 for k in names}, 0
        for ctx, phase, ans in frames(toks, posture.k):
            n += 1
            s_n += 1
            said = {"KAV": posture.token(ctx, phase),
                    "FLOOR_common": own["common"],
                    "FLOOR_common_train": common_train,
                    "FLOOR_repeat": int(ctx[-1]),
                    "FLOOR_phase": own["per_phase"][phase]}
            for name, v in said.items():
                hits[name] += int(v == ans)
                s_hits[name] += int(v == ans)
                errs[name].append(abs(v - ans))
        by_shape[shape_name] = {"frames": s_n,
                                "accuracy": {k: s_hits[k] / max(s_n, 1) for k in names},
                                "share_of_set": 0.0}
    for row in by_shape.values():
        row["share_of_set"] = row["frames"] / max(n, 1)
    return {"frames": n, "floors_used": own,
            "hits": dict(hits),
            "accuracy": {k: hits[k] / max(n, 1) for k in hits},
            "mean_abs_error": {k: float(np.mean(errs[k])) for k in errs},
            "by_shape": by_shape}


def measure(k: int = K) -> dict:
    """Gate 1: the coordinates."""
    corpus = mesh.our_corpus()
    train, test = split(corpus, HELD)
    common = _most_common(train)
    posture = fit(train, k)
    return {"k": k, "held_out": list(HELD),
            "train_shapes": len(train), "test_shapes": len(test),
            "seen": score(posture, train, common),
            "sealed": score(posture, test, common),
            "_posture": posture}


def not_solids(corpus) -> list[dict]:
    """Which shapes the grid itself breaks — reported, never scored against.

    KAV-04, 2026-09-06: A CHECK THAT HAD NEVER REFUSED. This used to test whether the
    ALREADY-QUANTISED survivor was watertight. The grid-decimated remainder is still
    edge-closed, so it looks like a solid, so this returned [] for all 23 shapes --
    pinch-rail included, which loses 3,796 of its 5,150 faces -- and the "NOT A SOLID
    ON THIS GRID" line in verdict_join, which is the whole reason this function
    exists, had never once printed. The criterion is now the one the module docstring
    always meant: if the Q-grid could not say a face, the thing on this grid is not
    the part, however closed the leftovers happen to be.
    """
    out = []
    for name, tris in corpus:
        dropped = mesh.dropped_by_grid(tris)
        _, lo, scale = mesh.quantise(np.asarray(tris, float))
        table, faces = mesh.table_and_faces(tris)
        g = mesh.geometry(mesh.dequantise(table, lo, scale)[faces])
        if dropped > 0 or len(faces) != len(tris):
            out.append({"name": name, "faces_in": int(len(tris)), "dropped_by_grid": dropped,
                        "faces_left": int(len(faces)), "lone": g["lone"],
                        "remainder_watertight": bool(g["watertight"])})
    return out


def solid_held(corpus) -> tuple:
    """The sealed shapes gate 2 may ask about — DERIVED from not_solids, not listed.

    KAV-04: SOLID_HELD was hand-written, so the real exclusion was a constant and the
    measurement beside it never fired. measure_join() now derives this and REFUSES if
    it disagrees with the recorded constant.
    """
    broken = {ns["name"] for ns in not_solids(corpus)}
    return tuple(n for n in HELD if n not in broken)


def measure_join(seed_fraction: float = joiner.SEED_FRACTION) -> dict:
    """Gates 1b and 2: the joining."""
    corpus = mesh.our_corpus()
    train, _ = split(corpus, HELD)
    derived = solid_held(corpus)
    if derived != SOLID_HELD:
        raise ValueError(
            f"the grid's ruling moved: gate 2's sealed solids are now {derived}, not "
            f"the recorded {SOLID_HELD}. Re-measure before believing any number here.")
    sealed = [(n, t) for n, t in corpus if n in SOLID_HELD]
    scorer = joiner.fit(train)
    common = joiner.most_common_answer(train)
    choosers = {"KAV": scorer,
                "FLOOR_mirror": joiner.MirrorFloor(),
                "FLOOR_mid": joiner.MidFloor(),
                "FLOOR_pmirror": joiner.PointMirrorFloor(),
                "FLOOR_close": joiner.CloseFloor(),
                "FLOOR_common": joiner.CommonFloor(common)}
    return {"held_out": list(SOLID_HELD), "train_shapes": len(train),
            "scorer": scorer.describe(),
            "seen": joiner.score(choosers, train),
            "sealed": joiner.score(choosers, sealed),
            # KAV-03: the same questions asked from the start GATE 2 actually uses,
            # so gate 1b and gate 2 can finally be read as one ladder.
            "sealed_from_gate2_seed": joiner.score(choosers, sealed,
                                                   seed_fraction=seed_fraction),
            "closure_sealed": joiner.closure(scorer, sealed, seed_fraction),
            "closure_by_grammar_alone": joiner.closure(joiner.CloseFloor(), sealed,
                                                       seed_fraction),
            "closure_ceiling": joiner.closure(None, sealed, seed_fraction, oracle=True),
            "not_solids": not_solids(corpus),
            "_scorer": scorer}


# ------------------------------------------------------- THE WIDE DENOMINATOR

FOLD_COLUMNS = (14, 15, 16, 17)
"""THE FOLD: the four descriptions added 2026-09-05 that say at what ANGLE the new
face would fold away from the known one (see joiner.step_of's docstring, columns
14-17: across/radius, out/radius, the radius itself, and how far that radius is
from the known corner's own). Dropping these four columns is the ABLATION that
answers "does the fold stay?".

THE OLD FOURTEEN are columns 0-13: the descriptions as they stood on the morning of
2026-09-05, before the fold and the other 28 were added. Blinding 14-45 reproduces
that learner exactly, and it is kept as a column so the widened table can be checked
against the number the change was first reported against (0.6162)."""

OLD_FOURTEEN_DROP = tuple(range(14, 46))


def fit_line_without(corpus, drop=FOLD_COLUMNS, lam: float = 1e-2):
    """joiner.fit_line with some description columns blinded.

    The columns are zeroed in the design matrix, so the ridge gives them weight
    exactly 0 (a zero column decouples: lam*w_j = 0). Nothing else about the fit
    changes -- same rows, same one-question-one-vote weighting, same phase gating.
    """
    corpus = joiner.intact_only(corpus)
    X, P, R, _, _ = joiner.training_pairs(corpus)
    X = np.array(X, dtype=np.float64, copy=True)
    if drop:
        X[:, list(drop)] = 0.0
    w = joiner._ridge_rank(X, lam, R)
    W = {}
    for ph in range(joiner.BINS):
        m = P == ph
        # KAV-11: the same one-question-one-vote gate as joiner.fit_line, or the
        # ablation would be fitted under a different rule than the thing it ablates.
        if float(R[m].sum()) >= joiner.MIN_QUESTIONS:
            W[ph] = joiner._ridge_rank(X[m], lam, R[m])
    return joiner.Scorer(w, W)


class _BlindGroveScorer(joiner.GroveScorer):
    """joiner.GroveScorer with some description columns blinded at both fit and ask."""

    def __init__(self, grove, drop) -> None:
        super().__init__(grove)
        self.drop = list(drop)

    def choose(self, st) -> int:
        F = joiner.design(st, self.context)      # design() returns a fresh array
        F[:, self.drop] = 0.0
        return int(st.cands[int(np.argmax(self.grove.predict(F)))])

    def describe(self) -> dict:
        d = super().describe()
        d["blinded"] = self.drop
        return d


def fit_grove_without(corpus, drop=FOLD_COLUMNS, n_trees: int = joiner.N_TREES,
                      depth: int = joiner.DEPTH, lr: float = joiner.LR):
    """joiner.fit with some description columns blinded — the SHIPPED learner's ablation.

    A constant-zero column can never be split on (both sides of every candidate split
    have zero weight, so its gain is -inf), so blinding is exact, not approximate.
    """
    X, y, W = joiner.training_candidates(joiner.intact_only(corpus))
    X = np.array(X, dtype=np.float64, copy=True)
    if drop:
        X[:, list(drop)] = 0.0
    g = joiner.Grove(n_trees=n_trees, depth=depth, lr=lr).fit(X, y, W)
    return _BlindGroveScorer(g, drop)


def clean_solids(corpus=None) -> list:
    """The 19 solids the Q=128 grid does not break -- the honest denominator.

    measure_join() asks gate 1b and gate 2 of THREE shapes (SOLID_HELD), which is
    49 questions. That is too few to resolve a change worth 22 accuracy points:
    on 2026-09-05 the new learner moved the wide number 0.6162 -> 0.8339 while the
    three-shape number moved 0.6327 -> 0.6122, which is ONE question. This is the
    denominator to believe.
    """
    return joiner.intact_only(corpus if corpus is not None else mesh.our_corpus())


def _wide_choosers(train, names) -> dict:
    """Only the choosers that were asked for — fitting six when two are wanted is why
    the wide gate was too slow to be the always-on one (KAV-01)."""
    make = {
        "OLD14": lambda: fit_line_without(train, OLD_FOURTEEN_DROP),
        "NOFOLD": lambda: fit_line_without(train),
        "FOLD_LINEAR": lambda: joiner.fit_line(train),
        "GROVE_NOFOLD": lambda: fit_grove_without(train),
        "FOLD_GROVE": lambda: joiner.fit(train),
        "FLOOR_mirror": lambda: joiner.MirrorFloor(),
    }
    return {n: make[n]() for n in names}


def measure_join_wide(seed_fraction: float = joiner.SEED_FRACTION,
                      progress=None, columns=None) -> dict:
    """GATE 2, WIDENED: the SAME questions measure_join() asks, over 19 solids.

    Leave-one-SHAPE-out. For each of the 19 clean solids: fit on the other 18,
    then ask that solid the two gate questions with joiner.score (gate 1b, the
    per-step joining) and joiner.closure (gate 2, does a quarter of it grow back
    into the RIGHT solid). Nothing about the metric is new -- only the shape set
    the same metric is computed over. measure_join() is untouched and its
    three-shape number stays computable beside this one.

    Five choosers, so the fold can be credited or refused on its own:
        OLD14         the linear scorer on the fourteen descriptions that existed
                      before the fold -- the learner the change was reported against
        NOFOLD        the linear scorer on all the descriptions EXCEPT the fold's
                      four; the honest, strongest no-fold control
        FOLD_LINEAR   the same linear scorer, fold included
        GROVE_NOFOLD  the shipped learner with the fold's four columns blinded --
                      the ablation the ruling on the fold actually rests on
        FOLD_GROVE    the shipped learner: the grove over all the descriptions
        FLOOR_mirror  the flat guess, which learns nothing
    """
    names = tuple(columns) if columns else COLUMNS
    clean = clean_solids()
    rows, hits, asked = [], {n: 0 for n in names}, 0
    right = {n: 0 for n in names}
    beyond_total = 0
    for i, (name, tris) in enumerate(clean):
        train = clean[:i] + clean[i + 1:]
        one = [(name, tris)]
        choosers = _wide_choosers(train, names)
        sc = joiner.score(choosers, one)
        row = {"name": name, "questions": sc["frames"],
               "beyond_reach": sc["beyond_reach"],
               "true_faces": int(len(mesh.table_and_faces(tris)[1])),
               "accuracy": {n: sc["accuracy"][n] for n in names},
               "right": {}, "said_faces": {}, "volume_ratio": {}, "watertight": {},
               "status": {}}
        seeded_here = 0
        for n in names:
            c = joiner.closure(choosers[n], one, seed_fraction)
            s = c["shapes"][0]
            seeded_here = int(s["seeded"])
            row["right"][n] = bool(s["solid"])
            row["said_faces"][n] = int(s["said_faces"])
            row["volume_ratio"][n] = float(s["volume_ratio"])
            row["watertight"][n] = bool(s["watertight"])
            row["status"][n] = s["status"]
            right[n] += int(s["solid"])
            # KAV-13: joiner.score already had the integer; reconstructing it out of
            # a float and comparing the result to four decimal places was needless
            # fragility in the number the whole 2026-09-05 ruling rests on.
            hits[n] += int(sc["hits"][n])
        row["seeded"] = int(seeded_here)          # a property of the SHAPE, not the chooser
        asked += sc["frames"]
        beyond_total += sc["beyond_reach"]
        rows.append(row)
        if progress:
            progress(i + 1, len(clean), row)
    return {"how": "leave-one-SHAPE-out over the 19 clean solids; the questions and "
                   "the solid test are joiner.score and joiner.closure unchanged",
            "solids": len(clean), "questions": asked, "beyond_reach": beyond_total,
            "seed_fraction": seed_fraction,
            "accuracy": {n: hits[n] / max(asked, 1) for n in names},
            "right_solids": {n: right[n] for n in names},
            "shapes": rows}


COLUMNS = ("OLD14", "NOFOLD", "FOLD_LINEAR", "GROVE_NOFOLD", "FOLD_GROVE",
           "FLOOR_mirror")


def measure_join_narrow(seed_fraction: float = joiner.SEED_FRACTION,
                        columns=None) -> dict:
    """THE OLD THREE-SHAPE GATE, asked of the same six choosers.

    This is measure_join()'s own protocol -- fit on the corpus minus HELD, score the
    three SOLID_HELD shapes -- so the 49-question number stays computable beside the
    271-question one, in the same vocabulary. It is kept precisely so that neither
    denominator can be quietly dropped: the ruling of 2026-09-05 is that the widened
    one is the one to believe, and that ruling is only checkable if both are here.
    """
    corpus = mesh.our_corpus()
    train, _ = split(corpus, HELD)
    sealed = [(n, t) for n, t in corpus if n in SOLID_HELD]
    names = tuple(columns) if columns else COLUMNS
    choosers = _wide_choosers(train, names)
    sc = joiner.score(choosers, sealed)
    right, shapes = {}, {}
    for n, ch in choosers.items():
        c = joiner.closure(ch, sealed, seed_fraction)
        right[n] = int(c["solid"])
        shapes[n] = [{"name": x["name"], "right": bool(x["solid"]),
                      "said_faces": int(x["said_faces"]),
                      "true_faces": int(x["true_faces"]),
                      "volume_ratio": float(x["volume_ratio"])} for x in c["shapes"]]
    return {"how": "measure_join()'s own protocol: fit on the corpus minus HELD, "
                   "score the three SOLID_HELD shapes",
            "solids": len(sealed), "held_out": list(SOLID_HELD),
            "questions": sc["frames"], "beyond_reach": sc["beyond_reach"],
            "accuracy": {n: sc["accuracy"][n] for n in names},
            "right_solids": {n: right[n] for n in names},
            "shapes": shapes}


def verdict_join_wide(r: dict) -> list[str]:
    """The widened gate, printed as a table. No pass/fail: this is the ruler telling
    the truth about a denominator, and the ruling on it lives in tests/test_joiner.py."""
    names = ("OLD14", "NOFOLD", "FOLD_LINEAR", "GROVE_NOFOLD", "FOLD_GROVE",
             "FLOOR_mirror")
    lines = [f"GATE 2, WIDENED: {r['solids']} clean solids, {r['questions']} questions, "
             f"leave-one-shape-out, seed fraction {r['seed_fraction']:.2f}",
             f"{'solid':11s} {'Q':>3s}  " + "  ".join(f"{n:>12s}" for n in names)]
    for s in r["shapes"]:
        cells = "  ".join(f"{s['accuracy'][n]:.4f}{'*' if s['right'][n] else ' '}"
                          f"{'':5s}" for n in names)
        lines.append(f"{s['name']:11s} {s['questions']:3d}  {cells}")
    lines.append(f"{'ALL':11s} {r['questions']:3d}  " +
                 "  ".join(f"{r['accuracy'][n]:.4f}{'':6s}" for n in names))
    lines.append(f"{'right solids':11s} {'':3s}  " +
                 "  ".join(f"{r['right_solids'][n]:>2d}/{r['solids']:<2d}{'':6s}" for n in names))
    lines.append("(* = that solid came back RIGHT: watertight, the truth's face count, "
                 "the truth's volume)")
    return lines


# ------------------------------------------- GATE 3: THE TWO HALVES, COMPOSED
#
# KAV-02, 2026-09-06. The organ has TWO halves and they had never once been asked to
# speak together. joiner.closure() -- gate 2 -- builds every shape from
# `table, faces = mesh.table_and_faces(tris)`: the TRUTH's vertex table. And
# anatomy.continue_shape, the only code in the organ that GENERATES coordinates, was
# called nowhere outside tests/test_organ.py, and those tests assert only that the
# tokens are whole vertices inside the grid -- never that what was generated is a
# shape. So "13/19 right solids" is entirely the joiner's achievement ON THE TRUTH'S
# VERTICES, and the coordinate model (gate 1) contributes nothing to it.
#
# Gate 3 composes them: fit the Posture, let it say the vertex half of a sealed shape
# at heat 0, sort those coordinates into a table the same canonical way mesh does,
# and then run the joiner's grammar over KAV'S OWN VERTICES, scored watertight /
# face-count / volume exactly as gate 2 scores. It is reported SEPARATELY and is
# never folded into gate 2. It is expected to fail; that is the point of asking.

def corpus_fingerprint(corpus) -> str:
    """A short hash of what the organ ate — so an artifact can name its own corpus."""
    h = hashlib.sha256()
    for name, tris in corpus:
        toks, _, _ = mesh.speak(tris)
        h.update(name.encode("utf-8"))
        h.update(np.asarray(toks, dtype=np.int64).tobytes())
    return h.hexdigest()[:16]


def _canonical_table(rows: np.ndarray) -> np.ndarray:
    """Unique vertices, ordered by z then y then x — mesh._tongue's own ordering, so
    KAV's spoken table is indexed the way the grammar expects a table to be."""
    uniq = np.unique(np.asarray(rows, dtype=np.int64), axis=0)
    order = np.lexsort((uniq[:, 0], uniq[:, 1], uniq[:, 2]))
    return uniq[order]


def say_vertices(tris, posture: Posture, seed_fraction: float = joiner.SEED_FRACTION,
                 heat: float = 0.0, seed: int = 0) -> dict:
    """Hand the coordinate model the same quarter of the shape gate 2 hands the joiner
    — but of the VERTEX sentence — and let it say the rest itself."""
    toks, lo, scale = mesh.speak(tris)
    head, _ = mesh.split_sentence(toks)
    n = len(head)
    keep = max(mesh.PER_VERTEX,
               (int(n * seed_fraction) // mesh.PER_VERTEX) * mesh.PER_VERTEX)
    prefix = [mesh.BOS] + list(head[:keep])
    said = continue_shape(prefix, posture, n - keep, heat=heat, seed=seed)
    body = mesh.split_sentence(said)[0]
    rows = np.array(body, dtype=np.int64).reshape(-1, mesh.PER_VERTEX)
    table = _canonical_table(rows)
    true_table = _canonical_table(np.array(head, dtype=np.int64).reshape(-1, mesh.PER_VERTEX))
    said_set = {tuple(int(x) for x in r) for r in table}
    true_set = {tuple(int(x) for x in r) for r in true_table}
    return {"table": table, "lo": lo, "scale": scale,
            "seeded_vertices": keep // mesh.PER_VERTEX,
            "true_vertices": int(len(true_table)),
            "said_vertices": int(len(table)),
            "vertices_right": int(len(said_set & true_set)),
            "tokens_asked": n - keep}


def say_shape(name: str, tris, posture: Posture, scorer, whole: bool = True,
              seed_fraction: float = joiner.SEED_FRACTION,
              heat: float = 0.0, seed: int = 0) -> dict:
    """The organ speaks one shape, end to end, and the geometry judges what came out.

    whole=False is gate 2's chain: the TRUTH's vertex table, a quarter of its faces,
                and the learner joining the rest. This is what "13/19" measures.
    whole=True  is gate 3's chain: KAV says the vertices TOO, and the grammar starts
                from its own restart-seed over them. Nothing of the truth is used
                except how many vertices to say and how many faces to allow.
    """
    table_true, faces_true = mesh.table_and_faces(tris)
    _, lo, scale = mesh.quantise(np.asarray(tris, float))
    v = None
    if whole:
        v = say_vertices(tris, posture, seed_fraction, heat, seed)
        table = v["table"]
        seeds = np.zeros((0, 3), dtype=np.int64)      # grow() makes its own first face
        budget = int(len(faces_true))
    else:
        table = table_true
        seeds = joiner.seed_faces(faces_true, seed_fraction)
        budget = int(len(faces_true) - len(seeds))
    faces = joiner.grow(table.astype(float), seeds, scorer, budget)
    got = mesh.dequantise(table, lo, scale)[faces] if len(faces) else np.zeros((0, 3, 3))
    g = mesh.geometry(got) if len(faces) else {"watertight": False, "volume": 0.0,
                                               "shared_2": 0, "lone": 0, "faces": 0}
    truth_g = mesh.geometry(mesh.dequantise(table_true, lo, scale)[faces_true])
    ratio = (g["volume"] / truth_g["volume"]) if truth_g["volume"] else 0.0
    right = (bool(g["watertight"]) and len(faces) == len(faces_true)
             and abs(ratio - 1.0) <= joiner.VOLUME_TOLERANCE)
    return {"name": name, "chain": "gate3 (KAV's own vertices)" if whole
                                    else "gate2 (the truth's vertices)",
            "tris": got, "faces": faces,
            "true_faces": int(len(faces_true)), "said_faces": int(len(faces)),
            "true_vertices": int(len(table_true)), "said_vertices": int(len(table)),
            "watertight": bool(g["watertight"]), "volume_ratio": float(ratio),
            "right": bool(right), "vertices": v}


def measure_gate3(k: int = K, heat: float = 0.0, seed: int = 0) -> dict:
    """Gate 3 over the same sealed solids gate 2 is asked of. Reported, never folded in."""
    corpus = mesh.our_corpus()
    train, _ = split(corpus, HELD)
    posture = fit(train, k)
    scorer = joiner.fit(train)
    rows = []
    for name, tris in corpus:
        if name not in SOLID_HELD:
            continue
        r = say_shape(name, tris, posture, scorer, whole=True, heat=heat, seed=seed)
        r.pop("tris"), r.pop("faces")
        rows.append(r)
    return {"how": "the coordinate half SAYS the vertices, then the joiner joins them; "
                   "scored watertight / the truth's face count / the truth's volume, "
                   "exactly as gate 2 scores",
            "tried": len(rows), "right": sum(int(r["right"]) for r in rows),
            "corpus": corpus_fingerprint(corpus), "shapes": rows}


def verdict_gate3(r: dict) -> tuple[bool, list[str]]:
    lines = []
    for s in r["shapes"]:
        v = s["vertices"] or {}
        lines.append(f"      {s['name']:8s} said {s['said_vertices']:3d} vertices of "
                     f"{s['true_vertices']:3d} ({v.get('vertices_right', 0)} of them exactly "
                     f"right, {v.get('seeded_vertices', 0)} were given) -> "
                     f"{s['said_faces']:3d}/{s['true_faces']:3d} faces, "
                     f"{'watertight' if s['watertight'] else 'open'}, "
                     f"volume x{s['volume_ratio']:.3f}, "
                     f"{'RIGHT SOLID' if s['right'] else 'not the shape'}")
    ok = r["right"] == r["tried"] and r["tried"] > 0
    lines.append(("PASS" if ok else "FAIL") +
                 f"  GATE 3 (the halves composed): {r['right']}/{r['tried']} sealed shapes "
                 f"came back as the RIGHT solid from vertices KAV said itself")
    return ok, lines


# ------------------------------------------------- KAV-15: the artifact writer
#
# The only thing KAV hands the render track is kav/KAV-first-shape.stl, read by
# tzelem/night.py, tzelem/hero8k.py and einayim/truthviews.py as "the cube ERAN's own
# modeller emitted". It was 684 bytes dated 2026-09-02 05:35 -- it PREDATED the
# 2026-09-03 vertex-index rebuild -- and NO code in the repository could write it:
# mesh.write_stl had zero callers anywhere in holobrain. The run leg produced stdout
# and nothing else, and a downstream consumer was pinned to a model version that no
# longer existed. `python ruler.py --say <shape> --out <path>` runs the real chain and
# writes the STL plus a sidecar JSON naming the chain, the gates, the corpus and the
# hour that produced it.

def say_to_file(name: str, out_path: str, whole: bool = False, k: int = K,
                heat: float = 0.0, seed: int = 0) -> dict:
    corpus = mesh.our_corpus()
    train, _ = split(corpus, HELD)
    tris = None
    for n, t in corpus:
        if n == name:
            tris = t
    if tris is None:
        raise ValueError(f"{name!r} is not in the corpus: {[n for n, _ in corpus]}")
    posture = fit(train, k)
    scorer = joiner.fit(train)
    r = say_shape(name, tris, posture, scorer, whole=whole, heat=heat, seed=seed)
    mesh.write_stl(out_path, r["tris"], header=b"KAV")
    side = {"wrote": os.path.basename(out_path),
            "shape": name, "chain": r["chain"],
            "said_faces": r["said_faces"], "true_faces": r["true_faces"],
            "said_vertices": r["said_vertices"], "true_vertices": r["true_vertices"],
            "watertight": r["watertight"], "volume_ratio": round(r["volume_ratio"], 6),
            "right_solid": r["right"],
            "was_sealed_from_the_fit": name in HELD,
            "corpus": corpus_fingerprint(corpus),
            "corpus_shapes": [n for n, _ in corpus],
            "constants": {"Q": mesh.Q, "K": k, "NEAR": joiner.NEAR,
                          "N_TREES": joiner.N_TREES, "DEPTH": joiner.DEPTH,
                          "LR": joiner.LR, "SEED_FRACTION": joiner.SEED_FRACTION,
                          "VOLUME_TOLERANCE": joiner.VOLUME_TOLERANCE},
            "written_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    with open(os.path.splitext(out_path)[0] + ".json", "w", encoding="utf-8") as f:
        json.dump(side, f, indent=2, ensure_ascii=False)
    return side


def verdict(r: dict) -> tuple[bool, list[str]]:
    """Gate 1, on BOTH the seen and the sealed set.

    KAV-06, 2026-09-06: this used to read r["sealed"] only and never r["seen"], which
    measure() has always returned. MEASURED that morning: on its own TRAINING data the
    fitted line scored 0.0849 against a constant's 0.2093 -- 2.5x WORSE than saying one
    number for ever -- and gate 1 printed PASSED, because nothing looked. A model that
    loses to a constant on the data it was fitted on must not be able to pass.
    """
    lines, ok = [], True
    for which in ("seen", "sealed"):
        a = r[which]["accuracy"]
        e = r[which]["mean_abs_error"]
        for floor in FLOORS:
            good = a["KAV"] > a[floor]
            ok = ok and good
            lines.append(f"{'PASS' if good else 'FAIL'}  gate 1 accuracy on {which:6s}: "
                         f"KAV {a['KAV']:.4f} vs {floor} {a[floor]:.4f}")
        worst = min(e[f] for f in FLOORS)
        good = e["KAV"] < worst
        ok = ok and good
        lines.append(f"{'PASS' if good else 'FAIL'}  gate 1 error    on {which:6s}: "
                     f"KAV off by {e['KAV']:.2f} of 127, best floor {worst:.2f}")
        lines.append(f"      floors on this set: most-common token "
                     f"{r[which]['floors_used']['common']}, per phase "
                     f"{r[which]['floors_used']['per_phase']}")
        # KAV-06: one 659-vertex printed part was 94.3% of the sealed verdict and the
        # printed lines never said so. Per shape, largest share first.
        for name, row in sorted(r[which]["by_shape"].items(),
                                key=lambda kv: -kv[1]["frames"]):
            lines.append(f"      {name:12s} {row['frames']:5d} frames "
                         f"({row['share_of_set']:5.1%} of {which}): KAV "
                         f"{row['accuracy']['KAV']:.4f} vs common "
                         f"{row['accuracy']['FLOOR_common']:.4f}")
    return ok, lines


def verdict_join(r: dict) -> tuple[bool, bool, list[str]]:
    """(gate 1b passed, gate 2 passed, lines)."""
    a = r["sealed"]["accuracy"]
    lines, learned = [], True
    for floor in ("FLOOR_mirror", "FLOOR_mid", "FLOOR_pmirror", "FLOOR_close", "FLOOR_common"):
        good = a["KAV"] > a[floor]
        learned = learned and good
        lines.append(f"{'PASS' if good else 'FAIL'}  gate 1b joining: KAV {a['KAV']:.4f} "
                     f"vs {floor} {a[floor]:.4f}")
    lines.append(f"      ({r['sealed']['frames']} questions on sealed solids, started from "
                 f"{r['sealed']['started_from']}; {r['sealed']['beyond_reach']} true corners "
                 f"beyond the {joiner.NEAR}-nearest reach)")
    # KAV-03: gate 1b above starts from ONE face; gate 2 below starts from a quarter of
    # every piece. Until 2026-09-06 only the first was printed and the two were read as
    # one ladder anyway. Both are printed now, and this is the one gate 2 climbs.
    g2 = r.get("sealed_from_gate2_seed")
    if g2:
        a2 = g2["accuracy"]
        lines.append(f"      SAME QUESTIONS FROM GATE 2's OWN START ({g2['started_from']}): "
                     f"{g2['frames']} questions, KAV {a2['KAV']:.4f}, "
                     + ", ".join(f"{f.replace('FLOOR_', '')} {a2[f]:.4f}"
                                 for f in ("FLOOR_mirror", "FLOOR_mid", "FLOOR_pmirror",
                                           "FLOOR_close", "FLOOR_common")))
        beat2 = [f for f in ("FLOOR_mirror", "FLOOR_mid", "FLOOR_pmirror",
                             "FLOOR_close", "FLOOR_common") if a2["KAV"] <= a2[f]]
        lines.append(("PASS" if not beat2 else "FAIL") +
                     "  gate 1b FROM THE START GATE 2 CLIMBS: " +
                     ("KAV is above every floor there too"
                      if not beat2 else
                      f"KAV {a2['KAV']:.4f} does NOT beat {', '.join(beat2)} "
                      f"({', '.join(f'{a2[f]:.4f}' for f in beat2)}). The gate-1b PASS "
                      f"above is measured from ONE face; gate 2 starts from a quarter "
                      f"of every piece, and there the learner is not ahead. Reported, "
                      f"not folded into the pass/fail, so the 0.6122 on record stays "
                      f"comparable -- but this is why 1b passes and 2 fails."))
    c = r["closure_sealed"]
    for s in c["shapes"]:
        lines.append(f"      {s['name']:8s} seeded {s['seeded']:3d}/{s['true_faces']:3d} faces -> "
                     f"said {s['said_faces']:3d}, {'SOLID' if s['solid'] else ('watertight but WRONG' if s['watertight'] else 'open')}"
                     f" ({s['shared']} shared / {s['lone']} lone), volume x{s['volume_ratio']:.3f}, "
                     f"restarts {s['restarts']}, dead edges {s['dead_edges']}")
        # KAV-08: "open" was printed for two states the ruler had not distinguished --
        # a learner that left holes, and a run the budget cut off with its front open.
        lines.append(f"               {s['status']}")
    solid = c["solid"] == c["tried"] and c["tried"] > 0
    lines.append(("PASS" if solid else "FAIL") +
                 f"  GATE 2 (solid): {c['solid']}/{c['tried']} sealed shapes came back as the RIGHT solid "
                 f"(watertight, the truth's face count, volume within {joiner.VOLUME_TOLERANCE:.0%}); "
                 f"{c['watertight']}/{c['tried']} merely watertight, connectivity {c['connectivity']:.3f}")
    g = r["closure_by_grammar_alone"]
    lines.append(f"      the grammar alone (FLOOR_close as chooser): {g['solid']}/{g['tried']} right solids, "
                 f"{g['watertight']}/{g['tried']} watertight -- CREDIT: the grammar")
    o = r["closure_ceiling"]
    lines.append(f"      CEILING (the truth as chooser): {o['solid']}/{o['tried']} right solids -- "
                 f"what the grammar can rebuild from a quarter of the shape when every answer is right")
    for ns in r["not_solids"]:
        lines.append(f"      NOT A SOLID ON THIS GRID: {ns['name']} -- the Q={mesh.Q} grid dropped "
                     f"{ns['dropped_by_grid']} of {ns['faces_in']} faces and left {ns['lone']} lone "
                     f"edges in the TRUTH. Gate 2 is not askable of it; that is the grid's limit.")
    return learned, solid, lines


if __name__ == "__main__":
    if "--say" in sys.argv:
        i = sys.argv.index("--say")
        shape = sys.argv[i + 1]
        out = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv \
            else f"KAV-{shape}.stl"
        info = say_to_file(shape, out, whole="--whole" in sys.argv)
        print(json.dumps(info, indent=2, ensure_ascii=False))
        sys.exit(0)

    r1 = measure()
    ok1, why1 = verdict(r1)
    r2 = measure_join()
    ok1b, ok2, why2 = verdict_join(r2)
    print(json.dumps({k: v for k, v in r1.items() if not k.startswith("_")},
                     indent=2, ensure_ascii=False))
    print(json.dumps({k: v for k, v in r2.items() if not k.startswith("_")},
                     indent=2, ensure_ascii=False, default=str))
    print()
    for line in why1 + why2:
        print("   ", line)
    r3 = measure_gate3()
    ok3, why3 = verdict_gate3(r3)
    for line in why3:
        print("   ", line)
    print("\nKAV GATE 1 (coordinates):", "PASSED" if ok1 else "FAILED")
    print("KAV GATE 1b (joining):    ", "PASSED" if ok1b else "FAILED")
    print("KAV GATE 2 (solid):       ", "PASSED" if ok2 else "FAILED")
    print("KAV GATE 3 (composed):    ", "PASSED" if ok3 else "FAILED")

    if "--wide" in sys.argv:
        rn = measure_join_narrow()
        rw = measure_join_wide()
        print()
        print(f"    THE OLD GATE, {rn['questions']} questions on {rn['solids']} shapes "
              f"{tuple(rn['held_out'])}:")
        for n in COLUMNS:
            print(f"      {n:13s} {rn['accuracy'][n]:.4f}   right solids "
                  f"{rn['right_solids'][n]}/{rn['solids']}")
        print()
        for line in verdict_join_wide(rw):
            print("   ", line)
