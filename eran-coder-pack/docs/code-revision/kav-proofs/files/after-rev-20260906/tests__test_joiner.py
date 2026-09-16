"""KAV / קָו — the tests for the vertex-indexed tongue and the joiner.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

Iddo, 2026-09-03 02:15: "קדימה, תקן את קו עם אינדקסי קודקודים". These are written
BEFORE the code, and each one names the change that would make it fail:

  1. the sentence is table + SEP + index faces, and it survives the round trip
  2. shuffling faces and vertices does not move the sentence
  3. a face that points at a vertex the table does not have is complained about
  4. the joiner's legal candidates respect orientation and valence (the grammar)
  5. the grammar alone, with the flat-guess floor, closes a box from three faces
  6. the fitted scorer beats every floor on the sealed shapes (learning)
  7. GATE 2: all three sealed shapes come back as the RIGHT solid (watertight, the
     truth's face count, the truth's volume) — "watertight" alone let a sixth of a
     box pass on the first run
  8. 2026-09-05: GATE 2's DENOMINATOR is the 19 clean solids, not 3. The 49-question
     gate ranked the WORST of five learners first; see GATE2_DECISION_20260905 below,
     which is the permanent record of both denominators and of the ruling on the fold.
  9. 2026-09-06 (KAV-01): and the SUITE now watches that denominator. Until this
     morning it pinned the narrow one to four decimals and skipped the wide one, so
     any real improvement to the learner failed the suite while the number that would
     vindicate it never ran. See WATCHED below.
"""
from __future__ import annotations

import os
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
_ORGAN = os.path.abspath(os.path.join(_HERE, ".."))
if _ORGAN not in sys.path:
    sys.path.insert(0, _ORGAN)

import pytest

import mesh                                      # noqa: E402
import joiner                                    # noqa: E402
import ruler                                     # noqa: E402

# 2026-09-03 03:10, measured: the learner is the open gate. Phase-gated pairwise
# ridge reaches 0.551 on the 49 sealed questions; the flat-mirror floors reach 0.571
# (one question apart), and every wrong answer spoils the solid. strict=True: the
# day these pass, pytest FAILS until someone removes the mark and looks.
#
# 2026-09-05, SOMEONE LOOKED. The alarm fired on gate 1b and the mark is gone: the
# learner now reaches 0.6327 sealed against mirror 0.5714 (31 of 49 questions
# against 28), after two fixes to how it is FITTED -- not to what it can see:
#   * one question is one vote (joiner.fit): rows were one per (answer, rival), so
#     a shape with many vertices outvoted one with few. Measured, the three
#     grid-decimated STL parts supplied 97.8% of the 66,308 rows.
#   * only intact shapes teach the joining (joiner.intact_only): the Q=128 grid
#     collapses most faces of the real printed parts, so their joins are the
#     grid's, not the part's.
# Both were chosen by leave-one-shape-out cross-validation on the TRAINING shapes
# alone; the sealed shapes were scored once, afterwards.
#
# 2026-09-05, LATER: the learner was replaced (32 more descriptions, the fold among
# them, and a gradient-boosted grove instead of a line -- all chosen by
# leave-one-SHAPE-out CV on the training shapes, sealed read once at the end). The
# two denominators disagree and both are recorded here:
#   leave-one-out over all 19 clean solids, 271 questions:
#       per-step 0.6162 -> 0.8339 (floor 0.5867), right solids 9/19 -> 13/19 (floor 8/19)
#   the ruler's own gate 1b, 49 questions on 3 shapes:
#       0.6327 -> 0.6122 -- ONE question, 31 hits to 30. Still ahead of every floor.
# 49 questions cannot resolve a difference this size. Do not tune against them.
#
# GATE 2 IS STILL OPEN and its mark stays: 1/3 right solids -- but a different 1/3.
# plate now comes back exact (12/12 faces, volume x1.000) where drum8 did before;
# drum8 is open at 0.950 of the volume and stack at 0.652.
OPEN_GATE_2 = ("gate 2: 1/3 sealed shapes come back as the RIGHT solid (plate); "
               "drum8 and stack come back open. On the denominator that can actually "
               "resolve this -- leave-one-shape-out over all 19 clean solids, 271 "
               "questions -- it is 13/19 right against 8/19 for the flat-mirror floor "
               "that learns nothing. Both numbers are MEASURED and kept, in "
               "GATE2_DECISION_20260905 below and in ruler.measure_join_wide() / "
               "ruler.measure_join_narrow(). Reproduce: python ruler.py --wide")


# ------------------------------------------------ the ruling of 2026-09-05, kept
#
# THE GATE WAS THE BROKEN THING. 49 questions on 3 shapes cannot resolve a 22-point
# change, and worse than that: measured, the 3-shape gate's ORDERING is inverted at
# the top. It calls the pre-fold fourteen-description learner the best of the six
# (0.6327) when on 19 solids that learner is the worst of the five (0.6162, 9/19),
# and it awards the flat-mirror floor -- which learns nothing -- the same 1/3 right
# solids as the shipped learner. Everything below was run on this machine, CPU numpy
# only, on 2026-09-05, and neither denominator may be dropped without the other.
#
GATE2_DECISION_20260905 = {
    "date": "2026-09-05",
    "what": "the denominator of KAV's gate 1b / gate 2 was widened from 3 shapes to "
            "the 19 clean solids, and the FOLD was put on trial on the wide one",
    "columns": ('OLD14', 'NOFOLD', 'FOLD_LINEAR', 'GROVE_NOFOLD', 'FOLD_GROVE', 'FLOOR_mirror'),
    "column_meaning": {
        "OLD14": "linear, the fourteen descriptions that existed before 2026-09-05 "
                 "(joiner.step_of columns 0-13); the learner the fold was reported against",
        "NOFOLD": "linear, all 46 descriptions EXCEPT the fold's four -- the strongest "
                  "no-fold control",
        "FOLD_LINEAR": "linear, all 46 descriptions (joiner.fit_line)",
        "GROVE_NOFOLD": "the SHIPPED grove with the fold's four columns blinded -- the "
                        "ablation this ruling rests on",
        "FOLD_GROVE": "the SHIPPED learner: the grove over all 46 (joiner.fit)",
        "FLOOR_mirror": "the flat guess; learns nothing",
    },
    "fold_columns": (14, 15, 16, 17),

    # ---- THE OLD DENOMINATOR, kept so it cannot be quietly dropped ----
    # ruler.measure_join_narrow(): fit on the corpus minus HELD, score the three
    # SOLID_HELD shapes (plate, stack, drum8). 49 questions.
    "narrow": {
        "how": "3 shapes (plate, stack, drum8), 49 questions, sealed",
        "questions": 49, "solids": 3,
        "accuracy": {"OLD14": 0.6327, "NOFOLD": 0.6122, "FOLD_LINEAR": 0.5918, "GROVE_NOFOLD": 0.5918, "FOLD_GROVE": 0.6122, "FLOOR_mirror": 0.5714},
        "right_solids": {"OLD14": 1, "NOFOLD": 0, "FOLD_LINEAR": 0, "GROVE_NOFOLD": 1, "FOLD_GROVE": 1, "FLOOR_mirror": 1},
    },

    # ---- THE WIDE DENOMINATOR, the one to believe ----
    # ruler.measure_join_wide(): leave-one-SHAPE-out over the 19 clean solids,
    # the same joiner.score / joiner.closure, seed fraction 0.25. 271 questions.
    "wide": {
        "how": "19 clean solids, 271 questions, leave-one-shape-out",
        "questions": 271, "solids": 19,
        "accuracy": {"OLD14": 0.6162, "NOFOLD": 0.7232, "FOLD_LINEAR": 0.7048, "GROVE_NOFOLD": 0.8229, "FOLD_GROVE": 0.8339, "FLOOR_mirror": 0.5867},
        "right_solids": {"OLD14": 9, "NOFOLD": 11, "FOLD_LINEAR": 12, "GROVE_NOFOLD": 11, "FOLD_GROVE": 13, "FLOOR_mirror": 8},
    },
    "wide_rows": (
        # (solid, questions, accuracy per column, right per column) -- column order above
        ("cube", 11, (0.8182, 0.9091, 0.9091, 1.0000, 1.0000, 0.9091), (1, 1, 1, 1, 1, 1)),
        ("slab", 11, (0.6364, 0.9091, 0.9091, 1.0000, 1.0000, 0.6364), (0, 1, 1, 0, 1, 0)),
        ("post", 11, (0.6364, 0.9091, 0.9091, 1.0000, 0.9091, 0.6364), (1, 1, 1, 0, 1, 0)),
        ("tower", 11, (0.6364, 0.9091, 0.9091, 1.0000, 1.0000, 0.6364), (1, 1, 1, 1, 1, 0)),
        ("plate", 11, (0.2727, 0.7273, 0.8182, 1.0000, 1.0000, 0.8182), (0, 0, 0, 1, 1, 1)),
        ("beam", 11, (0.5455, 0.9091, 0.9091, 1.0000, 1.0000, 0.6364), (1, 1, 1, 1, 1, 0)),
        ("brick", 11, (0.7273, 0.7273, 0.7273, 1.0000, 1.0000, 0.9091), (1, 1, 1, 1, 1, 1)),
        ("cell", 11, (0.8182, 0.9091, 0.9091, 1.0000, 1.0000, 0.8182), (1, 1, 1, 1, 1, 1)),
        ("tri-prism", 7, (0.8571, 0.8571, 0.8571, 1.0000, 1.0000, 0.8571), (1, 1, 1, 1, 1, 1)),
        ("wedge", 7, (0.8571, 0.8571, 0.7143, 0.8571, 0.8571, 0.8571), (1, 1, 1, 0, 1, 1)),
        ("pent-prism", 15, (0.7333, 0.7333, 0.7333, 0.8667, 0.8667, 0.5333), (0, 0, 0, 1, 0, 0)),
        ("drum6", 19, (0.6842, 0.7368, 0.7368, 0.8421, 0.8947, 0.4211), (0, 0, 0, 1, 1, 0)),
        ("drum8", 27, (0.6296, 0.5556, 0.5556, 0.6296, 0.7037, 0.5926), (0, 0, 1, 0, 0, 0)),
        ("drum12", 43, (0.4419, 0.6744, 0.6047, 0.7442, 0.7442, 0.3953), (0, 0, 0, 0, 0, 0)),
        ("frustum", 11, (0.7273, 0.9091, 1.0000, 0.8182, 0.9091, 0.9091), (0, 1, 1, 1, 1, 1)),
        ("cone8", 27, (0.5556, 0.4815, 0.4815, 0.6667, 0.7037, 0.2963), (0, 0, 0, 0, 0, 0)),
        ("pyramid", 5, (1.0000, 1.0000, 1.0000, 1.0000, 1.0000, 1.0000), (1, 1, 1, 1, 1, 1)),
        ("pair", 11, (0.4545, 0.5455, 0.4545, 0.7273, 0.5455, 0.5455), (0, 0, 0, 0, 0, 0)),
        ("stack", 11, (0.5455, 0.4545, 0.2727, 0.3636, 0.4545, 0.2727), (0, 0, 0, 0, 0, 0)),
    ),

    # ---- WHAT THE TWO DENOMINATORS SAY ABOUT EACH OTHER ----
    "the_gate_was_the_broken_thing": (
        "The 49-question gate ranks OLD14 FIRST (0.6327, the best of the six) and the "
        "shipped learner joint-second (0.6122). On the 19 solids OLD14 is LAST of the "
        "five learners (0.6162, 9/19 right) and the shipped learner is first (0.8339, "
        "13/19). The narrow gate also gives FLOOR_mirror -- which learns nothing and is "
        "8/19 wide -- the same 1/3 right solids as the shipped learner. A gate whose "
        "ordering inverts against the honest denominator is not measuring the model."
    ),

    # ---- THE RULING ----
    "ruling": "THE FOLD STAYS",
    "reasoning": (
        "On the honest 19-solid denominator the fold never loses on the gate's own "
        "currency: blinding it costs the shipped grove two right solids (13/19 -> 11/19) "
        "and 3 questions of 271 (0.8339 -> 0.8229), and it costs one right solid in the "
        "linear model too (12/19 -> 11/19). It is four columns and no runtime, so a gain "
        "that small still pays. But the fold's headline claim is RETIRED: the 0.6162 -> "
        "0.8339 jump belongs to the grove and the 28 other new descriptions, not to the "
        "fold -- the fold's own marginal share is +0.0110, which even 271 questions can "
        "barely resolve."
    ),
    "reproduce": r"cd D:\CLAUDE\eran-brain\holobrain\kav && python ruler.py --wide",
}
#
# ---------------------------------------------------------------------------------


# ------------------------------------------------------------------ the tongue

def test_indexed_sentence_round_trips():
    """table, SEP, faces — and the shape comes back whole and watertight."""
    tris = mesh.box([0, 0, 0], [1, 2, 0.5])
    toks, lo, sc = mesh.speak(tris)
    assert toks[0] == mesh.BOS and toks[-1] == mesh.EOS
    assert toks.count(mesh.SEP) == 1
    sep = toks.index(mesh.SEP)
    assert (sep - 1) % 3 == 0, "the vertex part is x y z per vertex"
    assert (len(toks) - sep - 2) % mesh.PER_FACE == 0, "the face part is three indices per face"
    assert (sep - 1) // 3 == 8, "a box has eight vertices, not thirty-six corners"
    back, complaint = mesh.hear(toks, lo, sc)
    assert complaint is None
    assert mesh.geometry(back)["watertight"]
    ta, fa = mesh.table_and_faces(tris)
    tb, fb = mesh.table_and_faces(back)
    assert np.array_equal(ta, tb) and np.array_equal(fa, fb)


def test_one_shape_one_sentence_indexed():
    """Shuffle the faces and rotate their corners: the sentence must not move."""
    tris = mesh.box([0, 0, 0], [1, 1, 1])
    rng = np.random.default_rng(3)
    shuffled = tris[rng.permutation(len(tris))].copy()
    for i in range(len(shuffled)):
        shuffled[i] = np.roll(shuffled[i], rng.integers(0, 3), axis=0)
    assert mesh.speak(tris)[0] == mesh.speak(shuffled)[0]


def test_a_face_pointing_nowhere_is_complained_about():
    """An index past the end of the table is not a vertex, and must not be clipped in silence."""
    toks, lo, sc = mesh.speak(mesh.box([0, 0, 0], [1, 1, 1]))
    sep = toks.index(mesh.SEP)
    bad = list(toks)
    bad[sep + 1] = 8                     # a box has vertices 0..7
    _, complaint = mesh.hear(bad, lo, sc)
    assert complaint is not None and "vertex" in complaint


# ------------------------------------------------------------------ the grammar

def test_legal_candidates_respect_orientation_and_valence():
    """Two faces of a cube share the edge (0,2). Growing from any OTHER front edge:

    the far corner may not be a corner of the edge's own face, may not reuse a
    directed edge that already exists (that would flip the surface inside out),
    and may not put a third face on an edge that already has two.
    """
    table, faces = mesh.table_and_faces(mesh.box([0, 0, 0], [1, 1, 1]))
    first = faces[0]
    mate = next(f for f in faces[1:] if len(set(first.tolist()) & set(f.tolist())) == 2)
    seed = np.array([first, mate])
    front = joiner.front_of(seed)
    assert len(front) == 4, "two triangles sharing one edge have four boundary edges"
    a, b = front[0]
    known = joiner.known_corner(seed, a, b)
    cands = joiner.legal(seed, a, b, len(table))
    assert a not in cands and b not in cands and known not in cands
    directed = joiner.directed_edges(seed)
    for c in cands:
        for e in ((b, a), (a, c), (c, b)):
            assert e not in directed, f"candidate {c} would reuse directed edge {e}"
    # the shared edge is full: it is not on the front at all
    for e in front:
        assert len(joiner.edge_faces(seed)[e]) == 1


def test_the_grammar_rebuilds_every_sealed_solid_when_the_answers_are_right():
    """The CEILING: with the truth as chooser, a quarter of each sealed solid grows
    back into the RIGHT solid — the truth's faces, the truth's volume. This is the
    proof that the grammar is not the gate that is open."""
    r = joiner.closure(None, [(n, t) for n, t in mesh.our_corpus() if n in ruler.SOLID_HELD],
                       oracle=True)
    assert r["solid"] == r["tried"] == 3, [(x["name"], x["solid"], round(x["volume_ratio"], 3))
                                           for x in r["shapes"]]


def test_the_grammar_alone_closes_a_box():
    """With the flat-guess floor as the only chooser, three faces grow into a watertight box.

    CREDIT: the grammar. If this fails the grammar is broken; if it passes, no
    learning has been shown yet.
    """
    tris = mesh.box([0, 0, 0], [1, 1, 1])
    table, faces = mesh.table_and_faces(tris)
    said = joiner.grow(table, faces[:3], joiner.MirrorFloor(), budget=len(faces) - 3)
    got = mesh.dequantise(table, np.zeros(3), 1.0)[said]
    g = mesh.geometry(got)
    assert g["watertight"], g
    assert g["faces"] == 12, g


# ------------------------------------------------------------------ the gates

def test_scorer_beats_every_floor_on_sealed_shapes():
    """Learning, credited only where the grammar cannot take it. PASSES since
    2026-09-05: KAV 0.6122 on the 49 sealed questions, every floor below it
    (mirror and point-mirror 0.5714)."""
    r = ruler.measure_join()
    a = r["sealed"]["accuracy"]
    for floor in ("FLOOR_mirror", "FLOOR_mid", "FLOOR_pmirror", "FLOOR_close", "FLOOR_common"):
        assert a["KAV"] > a[floor], f"KAV {a['KAV']:.4f} did not beat {floor} {a[floor]:.4f}"


@pytest.mark.xfail(strict=True, reason=OPEN_GATE_2)
def test_gate2_all_sealed_shapes_watertight():
    """GATE 2, the one the picture forced: what it SAYS must be a solid."""
    r = ruler.measure_join()
    c = r["closure_sealed"]
    assert c["solid"] == c["tried"] == 3, [(s["name"], s["said_faces"], s["true_faces"],
                                            s["watertight"], round(s["volume_ratio"], 3))
                                           for s in c["shapes"]]


# --------------------------------------------------- gate 2's widened denominator

def test_the_widened_denominator_is_the_nineteen_clean_solids():
    """The decision above names 19 solids and 271 questions. If the corpus moves, or
    a shape stops being clean on the grid, this fails and someone must RE-MEASURE
    rather than let the recorded ruling drift away from the code it ruled on."""
    named = tuple(row[0] for row in GATE2_DECISION_20260905["wide_rows"])
    on_disk = tuple(n for n, _ in ruler.clean_solids())
    assert on_disk == named, (on_disk, named)
    assert len(named) == GATE2_DECISION_20260905["wide"]["solids"] == 19
    assert (sum(row[1] for row in GATE2_DECISION_20260905["wide_rows"])
            == GATE2_DECISION_20260905["wide"]["questions"] == 271)


def test_blinding_a_description_really_blinds_it():
    """The fold ablation is only honest if a blinded column gets weight EXACTLY zero.
    It does, because a zero column decouples the ridge: lam * w_j = 0."""
    train = ruler.clean_solids()[:6]
    sc = ruler.fit_line_without(train, ruler.FOLD_COLUMNS)
    cols = list(ruler.FOLD_COLUMNS)
    assert np.all(sc.w[cols] == 0.0), sc.w[cols]
    for row in sc.W.values():
        assert np.all(row[cols] == 0.0), row[cols]
    assert np.any(sc.w != 0.0), "blinding four columns must not blank the whole line"


WATCHED = ("FOLD_GROVE", "FLOOR_mirror")
"""KAV-01, 2026-09-06 — THE GATE WAS WIRED BACKWARDS, AND THIS IS THE FIX.

Until this morning the always-on regression test pinned the NARROW 49-question /
3-shape table to four decimal places for all six columns INCLUDING FOLD_GROVE, the
shipped learner -- the denominator this very file calls "the broken thing", whose
ordering inverts against the honest one. The test that pins the WIDE 271-question /
19-solid table, the one the ruling says to believe, was `skipif(not KAV_WIDE)` and
was SKIPPED in every ordinary run.

The arithmetic consequence: any real improvement to joiner.fit moves FOLD_GROVE's
narrow accuracy and FAILS the suite, while the test that would vindicate it never
runs. A gate that punishes the improvement it exists to detect is not a gate.

So: the WIDE gate is now always on, over the two columns that carry the ruling --
the shipped learner and the floor that learns nothing -- which is 19 fits instead of
114 and fits inside an ordinary run. The full six-column ablation stays behind
KAV_WIDE, because that is a re-measurement of the ruling, not a regression check.
The narrow gate stays computable and is now a REPORTED DIAGNOSTIC with floors, not
an exact pin: neither denominator may be dropped, but only one may be believed."""


def test_the_widened_gate_is_the_one_the_suite_watches():
    """GATE 2 on the honest denominator: 19 clean solids, 271 questions, always on."""
    r = ruler.measure_join_wide(columns=WATCHED)
    rec = GATE2_DECISION_20260905["wide"]
    assert r["questions"] == rec["questions"] == 271
    assert r["solids"] == rec["solids"] == 19
    for name in WATCHED:
        assert round(r["accuracy"][name], 4) == rec["accuracy"][name], \
            (name, r["accuracy"][name], rec["accuracy"][name])
        assert r["right_solids"][name] == rec["right_solids"][name], \
            (name, r["right_solids"][name], rec["right_solids"][name])
    # the learner must stay ahead of the floor that learns nothing, on both currencies
    assert r["accuracy"]["FOLD_GROVE"] > r["accuracy"]["FLOOR_mirror"]
    assert r["right_solids"]["FOLD_GROVE"] > r["right_solids"]["FLOOR_mirror"]


def test_the_old_three_shape_gate_is_still_computable():
    """Neither denominator may be quietly dropped — but only one may be PINNED.

    This asks the old 49-question gate and checks the things that are true of it
    whatever the learner does: it is still askable, it is still 49 questions on the
    three sealed solids, and the learner is still above the flat-mirror floor on it.
    Its six-column table is REPORTED (see -s) and recorded in GATE2_DECISION_20260905,
    and it is deliberately no longer asserted to four decimal places: 49 questions
    cannot resolve a change worth 22 accuracy points, and pinning them made every real
    improvement fail the suite.
    """
    r = ruler.measure_join_narrow()
    assert r["questions"] == GATE2_DECISION_20260905["narrow"]["questions"] == 49
    assert r["solids"] == 3
    print("\n    the narrow gate today (diagnostic, not pinned):")
    for name in ruler.COLUMNS:
        was = GATE2_DECISION_20260905["narrow"]["accuracy"][name]
        print(f"      {name:13s} {r['accuracy'][name]:.4f} (2026-09-05: {was:.4f})   "
              f"right solids {r['right_solids'][name]}/{r['solids']}")
    assert r["accuracy"]["FOLD_GROVE"] > r["accuracy"]["FLOOR_mirror"], \
        "on its own narrow denominator the learner has fallen below the flat floor"


@pytest.mark.skipif(not os.environ.get("KAV_WIDE"),
                    reason="the six-column ABLATION is ~5 minutes; set KAV_WIDE=1 to "
                           "re-measure the fold ruling. The wide GATE itself is always on.")
def test_the_fold_ruling_still_holds_on_the_wide_denominator():
    """THE ABLATION, not the gate: all six columns, so 'THE FOLD STAYS' can be re-judged.
    `KAV_WIDE=1 python -m pytest tests/test_joiner.py -k fold_ruling`"""
    r = ruler.measure_join_wide()
    rec = GATE2_DECISION_20260905["wide"]
    assert r["questions"] == rec["questions"] and r["solids"] == rec["solids"]
    for name, want in rec["accuracy"].items():
        assert round(r["accuracy"][name], 4) == want, (name, r["accuracy"][name], want)
    for name, want in rec["right_solids"].items():
        assert r["right_solids"][name] == want, (name, r["right_solids"][name], want)
    # and the ruling itself: the fold must not be costing the shipped learner anything
    assert r["accuracy"]["FOLD_GROVE"] >= r["accuracy"]["GROVE_NOFOLD"]
    assert r["right_solids"]["FOLD_GROVE"] >= r["right_solids"]["GROVE_NOFOLD"]


def test_blinding_the_grove_really_blinds_it():
    """KAV-18: the ablation the fold ruling rests on is GROVE_NOFOLD, and its exactness
    lived only in a docstring ("a constant-zero column can never be split on"). If that
    argument stopped holding, the ruling would be built on a leaky control and nothing
    in the suite would notice. Now something does: no tree may SPLIT on a blinded
    column, and perturbing those columns may not move a single prediction."""
    train = ruler.clean_solids()[:6]
    sc = ruler.fit_grove_without(train, ruler.FOLD_COLUMNS)
    used = set()
    for tree in sc.grove.trees:
        stack = [tree]
        while stack:
            nd = stack.pop()
            if isinstance(nd, tuple) and len(nd) == 4:
                used.add(int(nd[0]))
                stack.extend([nd[2], nd[3]])
    assert not (used & set(ruler.FOLD_COLUMNS)), sorted(used & set(ruler.FOLD_COLUMNS))
    assert used, "a grove that splits on nothing at all proves nothing"
    rng = np.random.default_rng(11)
    X = rng.normal(size=(64, joiner.FEAT))
    before = sc.grove.predict(X.copy())
    X[:, list(ruler.FOLD_COLUMNS)] += rng.normal(size=(64, len(ruler.FOLD_COLUMNS))) * 100
    assert np.array_equal(before, sc.grove.predict(X)), \
        "the blinded columns still move the grove's answer"
