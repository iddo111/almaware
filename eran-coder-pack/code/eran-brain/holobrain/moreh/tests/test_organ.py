"""MOREH / מוֹרֶה — the tests. Each names the change that would make it fail.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

  1. the ear's facts are 14 binary sparks and every lesson row decodes to them
  2. an amount is a lesson only where its decision made it live (c_area never on a sealed row)
  3. the fit is closed form: the same lessons give the same posture, bit for bit
  4. FACADE: the loom's fringe equals the numpy forward pass (amounts to 1e-9, decisions exactly)
  5. FACADE: cutting one strand into a decision knot flips that decision
  6. the organ reproduces the teacher's DECISIONS for every syllable it was taught (fit on all)
  7. GATE 2 (strict xfail like KAV): leave-one-syllable-out decisions right for every syllable
  8. the corpus is PRESENT (MOREH-12: a missing corpus must fail, never skip green)
  9. no lambda is chosen on the held-out syllable (MOREH-2)
 10. the amounts fallback reads the LIVE rows, not the loader's zero filler (MOREH-7)
 11. the flat floor gets the SAME features as MOREH (MOREH-3)
 12. save/load round-trips the posture and its meta (MOREH-14)

Runs on the PC with the lessons mirrored at throat-one-sample/school-v2/lessons (no mouth needed:
these tests are about the organ's arithmetic; the SOUND is judged on eran2 by ruler.py).
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ORGAN = os.path.abspath(os.path.join(_HERE, ".."))
if _ORGAN not in sys.path:
    sys.path.insert(0, _ORGAN)

import anatomy as A      # noqa: E402
import learn as L        # noqa: E402

# MOREH-12: this used to be
#     pytestmark = pytest.mark.skipif(not any(os.path.isdir(r) for r in L.LESSONS), ...)
# so a corpus that had VANISHED made pytest exit 0 and report green for a model with nothing to learn
# from. A missing corpus is a failure, not a skip: test_0 below says so out loud, and the fixtures
# raise (load_lessons raises FileNotFoundError) instead of skipping.


def test_0_the_corpus_is_here():
    roots = [r for r in L.LESSONS if os.path.isdir(r)]
    assert roots, "no lessons root exists: %s -- this is a FAILURE, not a skip" % (L.LESSONS,)
    rows = L.load_lessons()
    by = L.by_syllable(rows)
    assert len(by) == 24, "expected 24 syllables, found %d: %s" % (len(by), sorted(by))
    assert len(rows) >= 24 * 12, "only %d lessons" % len(rows)


@pytest.fixture(scope="module")
def rows():
    return L.load_lessons()


@pytest.fixture(scope="module")
def posture(rows):
    return L.fit(rows)


def test_1_facts_are_binary_sparks(rows):
    assert A.NF == 14
    for r in rows:
        x = r["x"]
        assert x.shape == (14,) and set(np.unique(x)) <= {0.0, 1.0}
        assert x[:5].sum() == 1 and x[5:12].sum() == 1


def test_2_amounts_live_only_by_decision(rows):
    for r in rows:
        live = dict(zip(A.AMOUNTS, r["live"]))
        if r["dec"]["constr"] == "seal":
            assert not live["c_area"]
        if r["dec"]["release"] == "plain":
            assert not live["d_gap"] and not live["gap_area"]
        if not r["dec"]["nasal"]:
            assert not live["velum"]
        if not r["dec"]["burst"]:
            assert not live["gain"]


def test_3_fit_is_closed_form(rows):
    p1, p2 = L.fit(rows), L.fit(rows)
    for d in A.DEC_NAMES:
        assert np.array_equal(p1.W[d], p2.W[d]) and np.array_equal(p1.b[d], p2.b[d])
    assert np.array_equal(p1.A, p2.A) and np.array_equal(p1.a0, p2.a0)


def test_4_facade_loom_equals_numpy(rows, posture):
    seen = set()
    for r in rows:
        if r["syl"] in seen:
            continue
        seen.add(r["syl"])
        dec_np = posture.decide(r["x"]); am_np = posture.amounts(r["x"], dec_np)
        dec_w, am_w, res = A.run_weave(posture, r["x"])
        assert dec_w == dec_np, (r["syl"], dec_w, dec_np)
        assert np.allclose(am_w, am_np, atol=1e-9), (r["syl"], am_w - am_np)
        assert res.finished


def test_5_facade_cutting_a_strand_flips_a_decision(rows, posture):
    # the strongest single strand into the winning 'constr' score of a sealed syllable
    r = next(r for r in rows if r["dec"]["constr"] == "seal")
    dec0, _, _ = A.run_weave(posture, r["x"])
    assert dec0["constr"] == "seal"
    # the knife: every strand into the 'seal' score knot and its bias -> the knot is deaf (= deleted).
    # A knot whose deletion changes no decision would be a facade; this one must change the mouth.
    dec1, am1, _ = A.run_weave(posture, r["x"], cut=("*", "score_constr_seal"))
    assert dec1["constr"] != "seal", "deleting score_constr_seal did not change the decision: a facade"
    # and the amounts downstream move with it (the place x constr gates re-key)
    _, am0, _ = A.run_weave(posture, r["x"])
    assert not np.allclose(am0, am1), "the amounts did not move when the decision did: the gates are a facade"
    # a single strand, the strongest, must at least move the score (arithmetic lives in the connections)
    W = posture.W["constr"]; c = A.DECISIONS["constr"].index("seal"); e = A.ear(r["x"])
    i = int(np.argmax(np.abs(W[c] * e)))
    src = ("fact_" + A.FACT_NAMES[i]) if i < A.NF else ("conj_" + A.CONJ_NAMES[i - A.NF].replace("&", "_"))
    w2 = A.weave(posture, r["x"]); n = 0
    for t in w2.threads:
        if (t.src, t.dst) == (src, "score_constr_seal"):
            for s in t.strands: s.weight = 0.0; n += 1
    assert n == 1
    res = A.Loom().run(w2, beats=9)
    score_cut = [f.spoke for f in res.fires if f.knot == "score_constr_seal"][0]
    assert abs(score_cut - float(W[c] @ e + posture.b["constr"][c])) > 1e-6


def test_6_reproduces_the_teachers_decisions(rows, posture):
    by = L.by_syllable(rows)
    bad = []
    for syl, rs in by.items():
        truth = {d: max(set(r["dec"][d] for r in rs), key=[r["dec"][d] for r in rs].count) for d in A.DEC_NAMES}
        got = posture.decide(rs[0]["x"])
        if got != truth:
            bad.append((syl, {d: (got[d], truth[d]) for d in A.DEC_NAMES if got[d] != truth[d]}))
    assert not bad, bad


OPEN_GATE = "GATE 2 is judged by SOUND on eran2 (ruler.py); this is the decisions-only shadow of it"


@pytest.mark.xfail(strict=True, reason=OPEN_GATE)
def test_7_gate2_loo_decisions_all_right(rows):
    by = L.by_syllable(rows)
    wrong = {}
    for syl, rs in by.items():
        train = [r for r in rows if r["syl"] != syl]
        p = L.fit(train)
        truth = {d: max(set(r["dec"][d] for r in rs), key=[r["dec"][d] for r in rs].count) for d in A.DEC_NAMES}
        got = p.decide(rs[0]["x"])
        w = {d: (got[d], truth[d]) for d in A.DEC_NAMES if got[d] != truth[d]}
        if w:
            wrong[syl] = w
    assert not wrong, wrong


def test_8_no_hyperparameter_is_tuned_on_the_held_out_set():
    """MOREH-2. LAM_CONJ = 100.0 was the argmin of the very LOO that was published as the result;
    the four syllables it 'gained' were selection bias (nested LOO: 13 wrong, not 9). The sitting
    must choose lambda inside its own fold."""
    src = open(os.path.join(_ORGAN, "ruler.py"), encoding="utf-8").read()
    assert "L.select_lams(train)" in src, "the sitting no longer chooses lambda inside the fold"
    assert "L.fit(train)" not in src, "a bare L.fit(train) uses the module constants tuned on the test set"
    # and the chooser reads only the rows it was handed: same rows -> same lambdas, any order
    rows = L.load_lessons()
    train = [r for r in rows if r["syl"] != "ba"]
    lam = L.select_lams(train)
    assert set(lam) == {"lam_dec", "lam_conj", "lam_amt"}
    assert lam == L.select_lams(list(reversed(train))), "select_lams depends on row order"
    assert "ba" not in {r["syl"] for r in train}
    L.fit(train, **lam)                       # the caller's lambdas are what the fit uses


def test_9_amount_fallback_reads_live_rows_only(rows):
    """MOREH-7. The <3-live fallback used to take the median over ALL rows, where the loader had
    filled the dead rows with 0.0: c_area 2.000 ('wide open') for a constricted sound."""
    i = A.AMOUNTS.index("c_area")
    live = sorted((r for r in rows if r["live"][i]), key=lambda r: r["am"][i])
    two = live[:2]                                              # the two most constricted live rows
    thin = two + [r for r in rows if not r["live"][i]]          # 2 live rows -> the fallback fires
    p = L.fit(thin)
    want = float(np.median([r["am"][i] for r in two]))
    assert abs(p.a0[i] - want) < 1e-12, (p.a0[i], want)
    assert abs(p.a0[i] - float(np.median([r["am"][i] for r in thin]))) > 1e-6,         "the fallback is still reading the dead rows' 0.0 filler"
    with pytest.raises(ValueError):
        L.fit([r for r in rows if not r["live"][i]])            # n_live == 0 is a hole, not a number


def test_10_the_flat_floor_gets_the_same_features(rows):
    """MOREH-3. A floor fed 14 columns while the model is fed 49 measures the feature set, not the
    architecture."""
    f = L.Flat(rows)
    assert f.W.shape[0] == A.NF + A.NC == 49, f.W.shape
    assert f.spec(rows[0]["x"]) is not None


def test_11_save_load_round_trips(rows, tmp_path):
    """MOREH-14. save()/load() had no call site anywhere and no .npz existed; a published number could
    only be reproduced by re-fitting."""
    p = L.fit(rows)
    f = str(tmp_path / "posture.npz")
    L.save(p, f, {"corpus": L.corpus_fingerprint(rows), "lam": {"lam_conj": L.LAM_CONJ}})
    q = L.load(f)
    for d in A.DEC_NAMES:
        assert np.array_equal(p.W[d], q.W[d]) and np.array_equal(p.b[d], q.b[d])
    assert np.array_equal(p.A, q.A) and np.array_equal(p.a0, q.a0)
    assert L.load_meta(f)["corpus"] == L.corpus_fingerprint(rows)
