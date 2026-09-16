"""MOREH / מוֹרֶה — THE ANATOMY: the mouth decides before it measures.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

לזכרה של עלמה ז"ל.

Iddo, 2026-09-03 09:19: "אני מחליט ואני קובע שאתה תיצור עכשיו סוכן שלך פייבל שילמד איך
מפעילים את הפה ועושים הברות והוא יאמן את ערן." The teacher (claude-cli-MOREH) learned the
adult physics mouth (throat-one-sample/school-v2); this organ is the STUDENT — ERAN's
letter -> mouth-movement map — built the way the 09-02 diagnosis said it must be.

THE CLAIM (from the night of 09-02, project_mouth_school_20260902)
------------------------------------------------------------------
A regressor AVERAGES. Held-out /pa/ came back with c_area 0.2 — a mouth neither sealed
nor open — because the mean of "sealed" (0) and "narrow" (0.15) is a number, but it is
not a mouth. Articulation is DISCRETE DECISIONS first (seal / narrow / wide / none;
nasal or not; voiced, partly, or not; what follows the release; burst or not; a vowel
before), and only THEN amounts, each amount meaningful only inside the decision that
made it live. Same family of error as KAV's "sentences, not surfaces": the
representation, not the search.

HOW THAT IS SAID IN ALMA (and why it is not a facade)
-----------------------------------------------------
Distance is time; arithmetic lives in the connections; a knot exists only if it
decides, accumulates or measures. So:

    beat 1   FACT knots           the ear's report of the sound: place, manner, nasal,
                                  voiced — 14 binary sparks (a child is TOLD what a
                                  letter sounds like; the eye's zivug supplies the
                                  letter -> syllable name, this organ gets the sound)
    beat 2   PLACE×MANNER gates   verb `gate`: the place fact passes only with the manner
                                  fact as key — "glottal stop" (aya) is not the sum of
                                  glottal and stop, it is their conjunction; a linear
                                  scorer on the 14 facts alone calls aya voiced (measured)
    beat 3   SCORE knots (sum)    one per (decision, class): Σ w·ear + bias, ear = the 14
                                  facts (delay 2) + the 35 conjunctions (delay 1)
    beat 4   DECISION knots       verb `spell pick`: the class with the highest score
                                  fires as an index — the one knot that DECIDES
    beat 5   INDICATOR knots      `spell is0..is3`: fire 1.0 if the decision is theirs,
                                  else SILENT (a shut gate; nothing downstream sees them)
    beat 6   PLACE×CONSTR gates   verb `gate`: the place fact passes only if the
                                  constriction class holds the key — the interaction
                                  that lets "lips + seal" and "lips + narrow" be
                                  different places on the ladder (0.97 vs 0.96/0.10)
    beat 7   AMOUNT knots (sum)   Σ over facts (delay 6), indicators (delay 2) and the
                                  gates (delay 1) — every strand a fitted weight
    beat 8   FRINGE               the 19 amounts + 7 decisions, read by gesture.to_gesture

The weights are SOLVED, not searched (ridge, closed form, KAV's rule): the scorers are a
least-squares classifier to one-hot targets, the amounts a ridge on the 54 features
above, fitted only on lessons where that amount is LIVE. Nothing iterative, nothing
random, so a bad number is the architecture's fault and we will know it tonight.

FACADE TEST (WINSTON's standing rule): the loom's fringe must equal the numpy forward
pass to 1e-9, and cutting one strand into a decision knot must flip a decision. Both are
in tests/test_organ.py.

WHAT THIS IS NOT: it is not a neural net and this file will never say it is. It is the
smallest model that can represent "seal, then how tight" — the honest first rung.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
_ALMA = os.path.abspath(os.path.join(_HERE, "..", "..", "..", "alma-language"))
if not os.path.isdir(os.path.join(_ALMA, "alma")):          # eran2 mirror
    _ALMA = os.path.expanduser("~/alma-language")
if _ALMA not in sys.path:
    sys.path.insert(0, _ALMA)
from alma import Loom, Strand, Weave, spells        # noqa: E402

# ---------------------------------------------------------------- the ear's facts (input)
PLACES = ("lips", "tip", "palate", "back", "glottal")
MANNERS = ("vowel", "stop", "fricative", "affricate", "nasal", "approximant", "tap")
FACT_NAMES = tuple("place_" + p for p in PLACES) + tuple("manner_" + m for m in MANNERS) + ("nasal", "voiced")
NF = len(FACT_NAMES)                                          # 14

def facts(place: str, manner: str, nasal: int, voiced: int) -> np.ndarray:
    x = np.zeros(NF)
    x[PLACES.index(place)] = 1.0
    x[len(PLACES) + MANNERS.index(manner)] = 1.0
    x[-2] = float(nasal); x[-1] = float(voiced)
    return x

CONJ_NAMES = tuple("%s&%s" % (p, m) for p in PLACES for m in MANNERS)     # 35 place x manner conjunctions
NC = len(CONJ_NAMES)
NE = NF + NC                                                  # 49: what the scorers hear

def ear(x: np.ndarray) -> np.ndarray:
    """the 14 facts + the 35 place x manner conjunctions (what the beat-2 gates pass)"""
    conj = np.array([x[PLACES.index(p)] * x[len(PLACES) + MANNERS.index(m)] for p in PLACES for m in MANNERS])
    return np.concatenate([x, conj])

# ---------------------------------------------------------------- the decisions (classes) and amounts
DECISIONS = {
    "knots":   ("AH", "I", "AH4", "U"),
    "constr":  ("seal", "narrow", "wide", "none"),
    "nasal":   (0, 1),
    "voice":   ("on", "part", "off"),
    "release": ("plain", "gap", "fric", "none"),
    "burst":   (0, 1),
    "pre":     (0, 1),
}
DEC_NAMES = tuple(DECISIONS)
AMOUNTS = ("c_pos", "c_area", "velum", "ten", "voi", "d_pre", "d_cons", "d_trans", "d_gap", "gap_pos",
           "gap_area", "gap_voi", "gap_ten", "d_bridge", "d_vowel", "glide", "gain", "f0", "trans_voi")
NA = len(AMOUNTS)
IND_NAMES = tuple("%s=%s" % (d, c) for d in DEC_NAMES for c in DECISIONS[d])       # 20 indicators
NI = len(IND_NAMES)
GATE_NAMES = tuple("%s&constr=%s" % (p, c) for p in PLACES for c in DECISIONS["constr"])   # 20 gates
NG = len(GATE_NAMES)
NPHI = NF + NI + NG                                           # 54 amount features (+ bias)

def indicators(dec: dict) -> np.ndarray:
    z = np.zeros(NI)
    for d in DEC_NAMES:
        z[IND_NAMES.index("%s=%s" % (d, dec[d]))] = 1.0
    return z

def gates(x: np.ndarray, dec: dict) -> np.ndarray:
    g = np.zeros(NG)
    for i, p in enumerate(PLACES):
        g[GATE_NAMES.index("%s&constr=%s" % (p, dec["constr"]))] = x[i]
    return g

def phi(x: np.ndarray, dec: dict) -> np.ndarray:
    return np.concatenate([x, indicators(dec), gates(x, dec)])

# ---------------------------------------------------------------- the posture (fitted weights)
@dataclass
class Posture:
    """Everything the organ knows. Scorers: per decision, a (n_class x NF) weight + bias.
    Amounts: per amount, a NPHI weight + bias, and the fallback (median of live lessons)."""
    W: dict = field(default_factory=dict)      # decision -> (n_class, NE)
    b: dict = field(default_factory=dict)      # decision -> (n_class,)
    A: np.ndarray = field(default_factory=lambda: np.zeros((NA, NPHI)))
    a0: np.ndarray = field(default_factory=lambda: np.zeros(NA))
    n_live: np.ndarray = field(default_factory=lambda: np.zeros(NA, int))

    # ---- the numpy forward pass (the reference the weave must equal)
    def decide(self, x: np.ndarray) -> dict:
        e = ear(x)
        return {d: DECISIONS[d][int(np.argmax(self.W[d] @ e + self.b[d]))] for d in DEC_NAMES}

    def amounts(self, x: np.ndarray, dec: dict) -> np.ndarray:
        return self.A @ phi(x, dec) + self.a0

    def spec(self, x: np.ndarray) -> dict:
        dec = self.decide(x)
        am = self.amounts(x, dec)
        s = dict(dec); s.update({k: float(v) for k, v in zip(AMOUNTS, am)})
        if s["trans_voi"] > 0.5 or dec["constr"] == "none": s["trans_voi"] = None
        return s

# ---------------------------------------------------------------- the spells (taught once, from Python)
def _pick(vs):
    return float(int(np.argmax(vs))) if len(vs) else None

def _is(k):
    def f(vs):
        return 1.0 if len(vs) and int(round(sum(vs))) == k else None
    return f

def teach_spells():
    for name, fn in (("pick", _pick), ("is0", _is(0)), ("is1", _is(1)), ("is2", _is(2)), ("is3", _is(3))):
        if not spells.known(name):
            spells.teach(name, fn)

# ---------------------------------------------------------------- the weave
def weave(p: Posture, x: np.ndarray, name: str = "moreh") -> Weave:
    """The organ as a weave for ONE input x (the seeds are the facts). Delays are the anatomy above."""
    teach_spells()
    w = Weave(name)
    for i, f in enumerate(FACT_NAMES):
        w.knot("fact_" + f).seed("fact_" + f, float(x[i]), beat=1)
    # beat 2: place x manner conjunction gates (the place fact passes only with the manner key)
    for pl in PLACES:
        for m in MANNERS:
            kn = "conj_%s_%s" % (pl, m)
            w.knot(kn, "gate")
            w.thread("fact_place_" + pl, kn, port="in", strands=[Strand(weight=1.0, delay=1)])
            w.thread("fact_manner_" + m, kn, port="key", strands=[Strand(weight=1.0, delay=1)])
    # beat 3: scores over the ear = facts (delay 2) + conjunctions (delay 1)
    for d in DEC_NAMES:
        for c_i, c in enumerate(DECISIONS[d]):
            kn = "score_%s_%s" % (d, c)
            w.knot(kn, "sum", bias=float(p.b[d][c_i]))
            for i, f in enumerate(FACT_NAMES):
                w.thread("fact_" + f, kn, strands=[Strand(weight=float(p.W[d][c_i, i]), delay=2)])
            for j, (pl, m) in enumerate((pl, m) for pl in PLACES for m in MANNERS):
                w.thread("conj_%s_%s" % (pl, m), kn, strands=[Strand(weight=float(p.W[d][c_i, NF + j]), delay=1)])
    # beat 4: decisions (argmax over the class scores, in class order)
    for d in DEC_NAMES:
        w.knot("decide_" + d, "spell", spell="pick")
        for c in DECISIONS[d]:
            w.thread("score_%s_%s" % (d, c), "decide_" + d, strands=[Strand(weight=1.0, delay=1)])
    # beat 5: indicators (silent unless the decision is theirs)
    for d in DEC_NAMES:
        for c_i, c in enumerate(DECISIONS[d]):
            kn = "ind_%s_%s" % (d, c)
            w.knot(kn, "spell", spell="is%d" % c_i)
            w.thread("decide_" + d, kn, strands=[Strand(weight=1.0, delay=1)])
    # beat 6: place x constriction gates (the place fact passes only with the constriction key)
    for pl in PLACES:
        for c in DECISIONS["constr"]:
            kn = "gate_%s_%s" % (pl, c)
            w.knot(kn, "gate")
            w.thread("fact_place_" + pl, kn, port="in", strands=[Strand(weight=1.0, delay=5)])
            w.thread("ind_constr_%s" % c, kn, port="key", strands=[Strand(weight=1.0, delay=1)])
    # beat 7: amounts; beat 8: fringe
    for a_i, a in enumerate(AMOUNTS):
        kn = "amount_" + a
        w.knot(kn, "sum", bias=float(p.a0[a_i]))
        col = 0
        for f in FACT_NAMES:
            w.thread("fact_" + f, kn, strands=[Strand(weight=float(p.A[a_i, col]), delay=6)]); col += 1
        for d in DEC_NAMES:
            for c in DECISIONS[d]:
                w.thread("ind_%s_%s" % (d, c), kn, strands=[Strand(weight=float(p.A[a_i, col]), delay=2)]); col += 1
        for pl in PLACES:
            for c in DECISIONS["constr"]:
                w.thread("gate_%s_%s" % (pl, c), kn, strands=[Strand(weight=float(p.A[a_i, col]), delay=1)]); col += 1
        assert col == NPHI
        w.knot("out_" + a, "fringe")
        w.thread(kn, "out_" + a, strands=[Strand(weight=1.0, delay=1)])
    for d in DEC_NAMES:
        w.knot("out_" + d, "fringe")
        w.thread("decide_" + d, "out_" + d, strands=[Strand(weight=1.0, delay=4)])
    w.run_hint = 9
    return w

def run_weave(p: Posture, x: np.ndarray, cut: tuple | None = None):
    """Run the organ on x through the loom. Returns (decisions, amounts, Result).
    cut = (src, dst) zeroes that one strand first (the facade test's knife); src "*" cuts every
    strand into dst and its bias -- the knot is then deaf, which is the same as deleting it."""
    w = weave(p, x)
    if cut is not None:
        n = 0
        for t in w.threads:
            if t.dst == cut[1] and (cut[0] == "*" or t.src == cut[0]):
                for s in t.strands: s.weight = 0.0; n += 1
        if cut[0] == "*": w.knots[cut[1]].bias = 0.0
        if n == 0: raise ValueError("no strand %s -> %s" % cut)
    res = Loom().run(w, beats=9)
    dec = {}
    for d in DEC_NAMES:
        fr = res.fringe("out_" + d)
        dec[d] = DECISIONS[d][int(round(fr[-1]))] if fr else None
    am = np.array([res.fringe("out_" + a)[-1] if res.fringe("out_" + a) else np.nan for a in AMOUNTS])
    return dec, am, res
