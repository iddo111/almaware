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

import os
import sys

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


def _most_common(corpus, k: int) -> int:
    from collections import Counter
    c = Counter()
    for _, tris in corpus:
        toks, _, _ = mesh.speak(tris)
        c.update(mesh.split_sentence(toks)[0])
    return c.most_common(1)[0][0]


def score(posture: Posture, corpus, common: int) -> dict:
    """Next-token accuracy and error on the vertex half, for the model and both floors."""
    hits = {"KAV": 0, "FLOOR_common": 0, "FLOOR_repeat": 0}
    errs = {"KAV": [], "FLOOR_common": [], "FLOOR_repeat": []}
    n = 0
    for _, tris in corpus:
        toks, _, _ = mesh.speak(tris)
        for ctx, phase, ans in frames(toks, posture.k):
            n += 1
            said = {"KAV": posture.token(ctx, phase),
                    "FLOOR_common": common,
                    "FLOOR_repeat": int(ctx[-1])}
            for name, v in said.items():
                hits[name] += int(v == ans)
                errs[name].append(abs(v - ans))
    return {"frames": n,
            "accuracy": {k: hits[k] / max(n, 1) for k in hits},
            "mean_abs_error": {k: float(np.mean(errs[k])) for k in errs}}


def measure(k: int = K) -> dict:
    """Gate 1: the coordinates."""
    corpus = mesh.our_corpus()
    train, test = split(corpus, HELD)
    common = _most_common(train, k)
    posture = fit(train, k)
    return {"k": k, "held_out": list(HELD),
            "train_shapes": len(train), "test_shapes": len(test),
            "seen": score(posture, train, common),
            "sealed": score(posture, test, common),
            "_posture": posture}


def not_solids(corpus) -> list[dict]:
    """Which shapes the grid itself breaks — reported, never scored against."""
    out = []
    for name, tris in corpus:
        dropped = mesh.dropped_by_grid(tris)
        _, lo, scale = mesh.quantise(np.asarray(tris, float))
        table, faces = mesh.table_and_faces(tris)
        g = mesh.geometry(mesh.dequantise(table, lo, scale)[faces])
        if not g["watertight"]:
            out.append({"name": name, "faces_in": int(len(tris)), "dropped_by_grid": dropped,
                        "faces_left": int(len(faces)), "lone": g["lone"]})
    return out


def measure_join() -> dict:
    """Gates 1b and 2: the joining."""
    corpus = mesh.our_corpus()
    train, _ = split(corpus, HELD)
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
            "closure_sealed": joiner.closure(scorer, sealed),
            "closure_by_grammar_alone": joiner.closure(joiner.CloseFloor(), sealed),
            "closure_ceiling": joiner.closure(None, sealed, oracle=True),
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
        if int(m.sum()) >= joiner.MIN_ROWS:
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


def measure_join_wide(seed_fraction: float = joiner.SEED_FRACTION,
                      progress=None) -> dict:
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
    names = ("OLD14", "NOFOLD", "FOLD_LINEAR", "GROVE_NOFOLD", "FOLD_GROVE",
             "FLOOR_mirror")
    clean = clean_solids()
    rows, hits, asked = [], {n: 0 for n in names}, 0
    right = {n: 0 for n in names}
    beyond_total = 0
    for i, (name, tris) in enumerate(clean):
        train = clean[:i] + clean[i + 1:]
        one = [(name, tris)]
        choosers = {"OLD14": fit_line_without(train, OLD_FOURTEEN_DROP),
                    "NOFOLD": fit_line_without(train),
                    "FOLD_LINEAR": joiner.fit_line(train),
                    "GROVE_NOFOLD": fit_grove_without(train),
                    "FOLD_GROVE": joiner.fit(train),
                    "FLOOR_mirror": joiner.MirrorFloor()}
        sc = joiner.score(choosers, one)
        row = {"name": name, "questions": sc["frames"],
               "beyond_reach": sc["beyond_reach"],
               "true_faces": int(len(mesh.table_and_faces(tris)[1])),
               "accuracy": {n: sc["accuracy"][n] for n in names},
               "right": {}, "said_faces": {}, "volume_ratio": {}, "watertight": {}}
        for n in names:
            c = joiner.closure(choosers[n], one, seed_fraction)
            s = c["shapes"][0]
            row["right"][n] = bool(s["solid"])
            row["said_faces"][n] = int(s["said_faces"])
            row["volume_ratio"][n] = float(s["volume_ratio"])
            row["watertight"][n] = bool(s["watertight"])
            right[n] += int(s["solid"])
            hits[n] += sc["accuracy"][n] * sc["frames"]
            row["seeded"] = int(s["seeded"])
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


def measure_join_narrow(seed_fraction: float = joiner.SEED_FRACTION) -> dict:
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
    choosers = {"OLD14": fit_line_without(train, OLD_FOURTEEN_DROP),
                "NOFOLD": fit_line_without(train),
                "FOLD_LINEAR": joiner.fit_line(train),
                "GROVE_NOFOLD": fit_grove_without(train),
                "FOLD_GROVE": joiner.fit(train),
                "FLOOR_mirror": joiner.MirrorFloor()}
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
            "accuracy": {n: sc["accuracy"][n] for n in COLUMNS},
            "right_solids": {n: right[n] for n in COLUMNS},
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


def verdict(r: dict) -> tuple[bool, list[str]]:
    """Gate 1."""
    a = r["sealed"]["accuracy"]
    e = r["sealed"]["mean_abs_error"]
    lines, ok = [], True
    for floor in ("FLOOR_common", "FLOOR_repeat"):
        if a["KAV"] > a[floor]:
            lines.append(f"PASS  gate 1 accuracy: KAV {a['KAV']:.4f} beats {floor} "
                         f"{a[floor]:.4f} on vertices it never saw")
        else:
            ok = False
            lines.append(f"FAIL  gate 1 accuracy: KAV {a['KAV']:.4f} did NOT beat "
                         f"{floor} {a[floor]:.4f}")
    if e["KAV"] < min(e["FLOOR_common"], e["FLOOR_repeat"]):
        lines.append(f"PASS  gate 1 error: KAV is off by {e['KAV']:.2f} of 127, better "
                     f"than both floors ({e['FLOOR_common']:.2f} / "
                     f"{e['FLOOR_repeat']:.2f})")
    else:
        ok = False
        lines.append(f"FAIL  gate 1 error: KAV off by {e['KAV']:.2f}, no better than a floor")
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
    lines.append(f"      ({r['sealed']['frames']} questions on sealed solids; "
                 f"{r['sealed']['beyond_reach']} true corners beyond the {joiner.NEAR}-nearest reach)")
    c = r["closure_sealed"]
    for s in c["shapes"]:
        lines.append(f"      {s['name']:8s} seeded {s['seeded']:3d}/{s['true_faces']:3d} faces -> "
                     f"said {s['said_faces']:3d}, {'SOLID' if s['solid'] else ('watertight but WRONG' if s['watertight'] else 'open')}"
                     f" ({s['shared']} shared / {s['lone']} lone), volume x{s['volume_ratio']:.3f}, "
                     f"restarts {s['restarts']}, dead edges {s['dead_edges']}")
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
    import json
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
    print("\nKAV GATE 1 (coordinates):", "PASSED" if ok1 else "FAILED")
    print("KAV GATE 1b (joining):    ", "PASSED" if ok1b else "FAILED")
    print("KAV GATE 2 (solid):       ", "PASSED" if ok2 else "FAILED")

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
