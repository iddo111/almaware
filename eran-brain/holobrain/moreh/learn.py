"""MOREH / מוֹרֶה — LEARNING: the decisions are classified, the amounts are solved.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

The lessons are the TEACHER's verified variants (throat-one-sample/school-v2/lessons/CLAUDE-<syl>-vNN.json,
every one passed by school-v2/ruler.py). Each lesson row is
    x       the ear's 14 facts (place, manner, nasal, voiced)
    dec     the 7 discrete decisions the teacher made
    amounts the 19 numbers, with a LIVE mask (an amount the decisions do not use is not a lesson)

Fit, all closed form (KAV's rule: an optimiser can hide a bad model, a closed form cannot):
  1. scorers  W_d, b_d : ridge from ear(x) = [x | place x manner conjunctions] to the one-hot of decision d;
                         argmax = the class (a linear scorer on the 14 facts alone cannot say "glottal stop")
  2. amounts  A, a0    : ridge from phi(x, dec) = [x | indicators | place x constr gates] to each amount,
                         fitted ONLY on rows where that amount is live (so c_area never sees a sealed row,
                         d_gap never sees a plain release) — this is what "amounts conditioned on the
                         decisions" means in numbers.

The three ridge lambdas are NOT constants of this module any more (MOREH-2, code revision 2026-09-06):
select_lams() picks them by a leave-one-syllable-out INSIDE the rows it is given, so a caller doing an
outer LOO can choose lambda without the held-out syllable ever being seen. The old module constant
LAM_CONJ = 100.0 was the argmin of the very LOO that was then published as the result.

Two floors live here too, so the verdict has a bar under it:
  flat    the 09-02 regressor's idea: ONE ridge straight to every number, decisions included as numbers,
          then rounded — the averaging model the diagnosis blamed. Since the code revision it is fed the
          SAME 49 features as MOREH (MOREH-3): a floor on a smaller feature set is not a floor.
  copy    nearest class-neighbour: take the teacher's median spec of the closest syllable by facts
"""
from __future__ import annotations

import glob
import hashlib
import json
import os

import numpy as np

import anatomy as A
from anatomy import AMOUNTS, DECISIONS, DEC_NAMES, NA, NF, NPHI, Posture, ear, facts, phi

_HERE = os.path.dirname(os.path.abspath(__file__))

def _roots(rel: str) -> list[str]:
    return [os.path.abspath(os.path.join(_HERE, "..", "..", "throat-one-sample", rel, "lessons")),
            os.path.expanduser("~/throat-one-sample/%s/lessons" % rel)]

# MOREH-5: the lesson source is a PARAMETER, not a module constant. school-v3 (134 renders gated by the
# Hebrew wav2vec2 phoneme judge instead of the self-confirming acoustic ruler) has been on disk since
# 2026-09-03 19:29 and was read by nothing. It covers 12 of the 24 syllables — report it as a
# 12-syllable LOO, never as 24.
SCHOOLS = {"v2": "school-v2", "v3": "school-v3"}
DEFAULT_SCHOOL = "v2"
LESSONS = _roots(SCHOOLS[DEFAULT_SCHOOL])       # kept: the default roots, in order of preference

def school_roots(school: str = DEFAULT_SCHOOL) -> list[str]:
    if school not in SCHOOLS:
        raise ValueError("unknown school %r (have %s)" % (school, ", ".join(sorted(SCHOOLS))))
    return _roots(SCHOOLS[school])

# an amount is a lesson only when the decisions make it live (mirror of gesture.live_amounts)
def live_mask(dec: dict) -> np.ndarray:
    a = {"d_vowel", "glide", "f0"}
    if dec["constr"] != "none" or dec["voice"] != "on" or dec["knots"] != "AH":
        a |= {"c_pos", "c_area", "ten", "voi", "d_cons", "d_trans", "trans_voi"}
    if dec["constr"] == "seal": a.discard("c_area")
    if dec["nasal"]: a.add("velum")
    if dec["release"] == "gap": a |= {"d_gap", "gap_pos", "gap_area", "gap_voi", "gap_ten", "d_bridge"}
    if dec["release"] == "fric": a |= {"d_gap", "gap_pos", "gap_area", "gap_voi", "gap_ten"}
    if dec["burst"]: a.add("gain")
    if dec["pre"]: a.add("d_pre")
    return np.array([k in a for k in AMOUNTS])

def _amount_vector(am: dict) -> np.ndarray:
    return np.array([float(am.get(k, 0.0) if am.get(k) is not None else (1.0 if k == "trans_voi" else 0.0))
                     for k in AMOUNTS])

def _row_from_json(d: dict, fname: str, facts_by_syl: dict | None) -> dict:
    """Two lesson schemas, one row.
    school-v2: {"facts": {...}, "decisions": {...}, "amounts": {...}}
    school-v3: {"spec": {decisions and amounts, flat}} — no facts, so they come from facts_by_syl,
               which is built from a corpus that HAS them. The 14 facts are never re-typed here."""
    syl = d["syl"]
    if "facts" in d and "decisions" in d and "amounts" in d:
        fa = d["facts"]; dec = dict(d["decisions"]); am = dict(d["amounts"])
        x = facts(fa["place"], fa["manner"], int(fa["nasal"]), int(fa["voiced"]))
    elif "spec" in d:
        sp = d["spec"]
        dec = {k: sp[k] for k in DEC_NAMES}
        am = {k: sp.get(k) for k in AMOUNTS}
        if not facts_by_syl or syl not in facts_by_syl:
            raise KeyError("lesson %s has no facts and none were supplied for %r" % (fname, syl))
        x = np.array(facts_by_syl[syl], float)
    else:
        raise KeyError("lesson %s is neither the school-v2 nor the school-v3 schema (keys: %s)"
                       % (fname, sorted(d)))
    dec["nasal"] = int(dec["nasal"]); dec["burst"] = int(dec["burst"]); dec["pre"] = int(dec["pre"])
    return {"syl": syl, "x": x, "dec": dec, "am": _amount_vector(am), "live": live_mask(dec), "file": fname}

def facts_by_syllable(rows: list[dict]) -> dict:
    """syl -> the 14 facts, taken from lessons that carry them (never re-typed)."""
    return {r["syl"]: r["x"] for r in rows}

def load_lessons(root: str | None = None, school: str | None = None,
                 facts_by_syl: dict | None = None) -> list[dict]:
    """rows: {syl, x, dec, am (NA floats), live (NA bool), file}

    root    an explicit lessons directory (wins over school)
    school  "v2" (the acoustic ruler's corpus, the default) or "v3" (the Hebrew judge's corpus)
    """
    roots = [root] if root else school_roots(school or DEFAULT_SCHOOL)
    rows = []
    for r in roots:
        files = sorted(glob.glob(os.path.join(r, "CLAUDE-*-v*.json")))
        if not files:
            continue
        fbs = facts_by_syl
        if fbs is None and "facts" not in json.load(open(files[0], encoding="utf-8")):
            # the facts come from the corpus that has them, not from a second hand-written table
            fbs = facts_by_syllable(load_lessons(school=DEFAULT_SCHOOL))
        for f in files:
            rows.append(_row_from_json(json.load(open(f, encoding="utf-8")), os.path.basename(f), fbs))
        if rows: break
    if not rows:
        raise FileNotFoundError("no lessons under %s" % roots)
    return rows

def corpus_fingerprint(rows: list[dict]) -> str:
    """sha256 of the actual training input (file, syl, decisions, amounts), so a published number can be
    traced to the corpus that produced it (MOREH-11 / MOREH-14)."""
    h = hashlib.sha256()
    for r in sorted(rows, key=lambda r: (r["syl"], r["file"])):
        h.update(json.dumps([r["file"], r["syl"], [r["dec"][d] for d in DEC_NAMES],
                             [round(float(v), 9) for v in r["am"]]], sort_keys=True).encode())
    return h.hexdigest()[:16]

def _ridge(X: np.ndarray, Y: np.ndarray, lam):
    """min |XW + b - Y|^2 + Σ lam_i W_i^2, the bias unpenalised. lam: a float or one per column.
    Returns (W (nx x ny), b (ny,))."""
    X1 = np.hstack([X, np.ones((len(X), 1))])
    lam = np.full(X.shape[1], float(lam)) if np.isscalar(lam) else np.asarray(lam, float)
    M = X1.T @ X1 + np.diag(np.append(lam, 0.0))
    S = np.linalg.solve(M, X1.T @ Y)
    return S[:-1], S[-1]

# The conjunction columns are penalised HARDER than the facts (lam_conj >> lam_dec): the shared, additive
# structure ("voiceless -> off", "stop -> seal") must live in the fact strands, where a held-out syllable can
# reach it; a conjunction that exists in one syllable only mops up that syllable's residual. Measured 09-03:
# with one lambda for both, the conjunctions swallowed the facts and LOO decisions went 9 -> 13 wrong;
# sweep (decisions-only LOO, PC): 0.01..30 -> 13 wrong, 100 -> 9 wrong with fit-on-all still 0 wrong,
# 1e4 -> 9 wrong but fit-on-all 2 wrong (aya, wa need the conjunction).
# 2026-09-06 CODE REVISION (MOREH-2): that sweep was scored on the very LOO that is published as the
# result, so 100.0 is the argmin of its own metric and the four syllables it "gained" are selection bias.
# These stay as DEFAULTS for a plain fit-on-all; the honest path is select_lams() inside the caller's fold.
LAM_DEC_DEFAULT, LAM_AMT_DEFAULT, LAM_CONJ = 1e-2, 1e-2, 100.0
DEC_GRID = (1e-3, 1e-2, 1e-1, 1.0)
CONJ_GRID = (0.01, 0.1, 1.0, 10.0, 30.0, 100.0, 300.0, 1000.0, 1e4)
AMT_GRID = (1e-3, 1e-2, 1e-1, 1.0, 3.0, 10.0, 30.0, 100.0)

def fit(rows: list[dict], lam_dec: float = LAM_DEC_DEFAULT, lam_amt: float = LAM_AMT_DEFAULT,
        lam_conj: float = LAM_CONJ) -> Posture:
    p = Posture()
    X = np.stack([ear(r["x"]) for r in rows])
    lam_e = np.concatenate([np.full(NF, lam_dec), np.full(A.NC, lam_conj)])
    for d in DEC_NAMES:
        classes = DECISIONS[d]
        Y = np.zeros((len(rows), len(classes)))
        for i, r in enumerate(rows): Y[i, classes.index(r["dec"][d])] = 1.0
        W, b = _ridge(X, Y, lam_e)
        p.W[d] = W.T.copy(); p.b[d] = b.copy()
    PHI = np.stack([phi(r["x"], r["dec"]) for r in rows])
    for a_i in range(NA):
        m = np.array([r["live"][a_i] for r in rows])
        p.n_live[a_i] = int(m.sum())
        y = np.array([r["am"][a_i] for r in rows])
        # MOREH-7: an amount with NO live lesson is a hole in the corpus, not a number to guess.
        if m.sum() == 0:
            raise ValueError("amount %r has no live lesson in this corpus (n_live=0): a hole, not a number"
                             % (AMOUNTS[a_i],))
        if m.sum() < 3:
            # MOREH-7: the median must come from the LIVE rows only. Over ALL rows it reads the loader's
            # 0.0 filler for the dead rows: measured 09-06, c_area 2.000 ("mouth wide open") for a
            # constricted sound, velum 0.000 ("nose shut") for a nasal.
            p.A[a_i] = 0.0; p.a0[a_i] = float(np.median(y[m]))
            continue
        W, b = _ridge(PHI[m], y[m][:, None], lam_amt)
        p.A[a_i] = W[:, 0]; p.a0[a_i] = float(b[0])
    return p

# ------------------------------------------------- MOREH-2: lambda chosen INSIDE the caller's fold
def _dec_blocks():
    blocks = {}; j = 0
    for d in DEC_NAMES:
        blocks[d] = (j, j + len(DECISIONS[d])); j += len(DECISIONS[d])
    return blocks, j

def _dec_targets(rows):
    blocks, n = _dec_blocks()
    Y = np.zeros((len(rows), n))
    for i, r in enumerate(rows):
        for d in DEC_NAMES:
            a, _ = blocks[d]; Y[i, a + DECISIONS[d].index(r["dec"][d])] = 1.0
    return Y, blocks

def majority_dec(rs: list[dict]) -> dict:
    return {d: max(set(r["dec"][d] for r in rs), key=[r["dec"][d] for r in rs].count) for d in DEC_NAMES}

def _wrong(scores, blocks, truth):
    return any(DECISIONS[d][int(np.argmax(scores[a:b]))] != truth[d] for d, (a, b) in blocks.items())

def select_lams(rows: list[dict], dec_grid=DEC_GRID, conj_grid=CONJ_GRID, amt_grid=AMT_GRID) -> dict:
    """Pick (lam_dec, lam_conj, lam_amt) by a leave-one-syllable-out INSIDE `rows`.

    The caller passes only its own training rows, so the outer held-out syllable is never seen — the
    thing LAM_CONJ = 100.0 did wrong. Deterministic: minimise (inner wrong syllables, then wrong under a
    fit over all of `rows`), tie-broken towards the HARDER-penalised conjunctions and the freer facts,
    which is this model's stated principle, not a new one."""
    by = by_syllable(rows); syls = sorted(by)
    if len(syls) < 3:
        return {"lam_dec": LAM_DEC_DEFAULT, "lam_conj": LAM_CONJ, "lam_amt": LAM_AMT_DEFAULT}
    E1 = np.hstack([np.stack([ear(r["x"]) for r in rows]), np.ones((len(rows), 1))])
    Y, blocks = _dec_targets(rows)
    idx = {s: np.array([r["syl"] == s for r in rows]) for s in syls}
    truth = {s: majority_dec(by[s]) for s in syls}
    e1 = {s: np.append(ear(by[s][0]["x"]), 1.0) for s in syls}
    grid = [(ld, lc) for ld in dec_grid for lc in conj_grid]
    pens = {k: np.diag(np.concatenate([np.full(NF, k[0]), np.full(A.NC, k[1]), [0.0]])) for k in grid}
    inner = {k: 0 for k in grid}
    for s in syls:
        tr = ~idx[s]
        G = E1[tr].T @ E1[tr]; B = E1[tr].T @ Y[tr]
        for k in grid:
            inner[k] += int(_wrong(e1[s] @ np.linalg.solve(G + pens[k], B), blocks, truth[s]))
    Gall = E1.T @ E1; Ball = E1.T @ Y
    on_all = {}
    for k in grid:
        S = np.linalg.solve(Gall + pens[k], Ball)
        on_all[k] = sum(int(_wrong(e1[s] @ S, blocks, truth[s])) for s in syls)
    # tie-break: held-out error first, then fidelity to the teacher on `rows`, then the MOST
    # regularised setting that still ties (the one-standard-error rule) -- so the choice does not
    # depend on how far down the grid happens to run. Measured 09-06 on the 24-syllable corpus:
    # (inner 9, on_all 0) is reached only at lam_conj=100 with lam_dec in 1e-4..0.1 -> (0.1, 100.0),
    # and both sit INSIDE the grid, not on its edge.
    ld, lc = min(grid, key=lambda k: (inner[k], on_all[k], -k[1], -k[0]))

    # the amounts: the same inner LOO, on the TRUE decisions (phi never depends on the decision lambdas)
    P1 = np.hstack([np.stack([phi(r["x"], r["dec"]) for r in rows]), np.ones((len(rows), 1))])
    AM = np.stack([r["am"] for r in rows]); LV = np.stack([r["live"] for r in rows])
    scale = np.array([max(float(np.std(AM[LV[:, i], i])) if LV[:, i].sum() > 1 else 1.0, 1e-9)
                      for i in range(NA)])
    err = {la: 0.0 for la in amt_grid}
    for s in syls:
        tr = ~idx[s]; te = idx[s]
        for a_i in range(NA):
            mtr = tr & LV[:, a_i]; mte = te & LV[:, a_i]
            if mtr.sum() < 3 or mte.sum() == 0: continue
            G2 = P1[mtr].T @ P1[mtr]; B2 = P1[mtr].T @ AM[mtr, a_i]
            for la in amt_grid:
                w = np.linalg.solve(G2 + np.diag(np.append(np.full(NPHI, la), 0.0)), B2)
                err[la] += float(np.sum(((P1[mte] @ w - AM[mte, a_i]) / scale[a_i]) ** 2))
    la = min(amt_grid, key=lambda k: (err[k], -k))
    return {"lam_dec": float(ld), "lam_conj": float(lc), "lam_amt": float(la)}

# ---------------------------------------------------------------- the floors
class Flat:
    """The 09-02 way: one ridge straight to every number; decisions are numbers too.

    MOREH-3 (code revision 2026-09-06): fed ear(x) — the SAME 49 columns MOREH gets — not the bare 14
    facts. On 14 it lost 19/24 on decisions and 13/24 on 49, so part of the published margin was a
    feature-set difference, not the decisions-then-amounts architecture."""
    def __init__(self, rows, lam=LAM_AMT_DEFAULT):
        X = np.stack([ear(r["x"]) for r in rows])
        cols = []
        for r in rows:
            v = [DECISIONS[d].index(r["dec"][d]) for d in DEC_NAMES]
            cols.append(np.concatenate([v, r["am"]]))
        Y = np.stack(cols)
        self.W, self.b = _ridge(X, Y, lam)
    def spec(self, x):
        y = ear(x) @ self.W + self.b
        s = {}
        for i, d in enumerate(DEC_NAMES):
            k = int(np.clip(round(y[i]), 0, len(DECISIONS[d]) - 1)); s[d] = DECISIONS[d][k]
        for j, a in enumerate(AMOUNTS): s[a] = float(y[len(DEC_NAMES) + j])
        if s["trans_voi"] > 0.5 or s["constr"] == "none": s["trans_voi"] = None
        return s

class Copy:
    """Nearest class-neighbour: the teacher's median spec of the closest syllable by facts."""
    def __init__(self, rows):
        self.by = {}
        for r in rows: self.by.setdefault(r["syl"], []).append(r)
        self.x = {s: rs[0]["x"] for s, rs in self.by.items()}
    def spec(self, x):
        near = min(self.x, key=lambda s: float(np.sum(np.abs(self.x[s] - x))))
        rs = self.by[near]
        s = {}
        for d in DEC_NAMES:
            vals = [r["dec"][d] for r in rs]; s[d] = max(set(vals), key=vals.count)
        med = np.median(np.stack([r["am"] for r in rs]), axis=0)
        for j, a in enumerate(AMOUNTS): s[a] = float(med[j])
        if s["trans_voi"] > 0.5 or s["constr"] == "none": s["trans_voi"] = None
        return s, near

def by_syllable(rows):
    out = {}
    for r in rows: out.setdefault(r["syl"], []).append(r)
    return out

def save(p: Posture, path: str, meta: dict | None = None):
    np.savez(path, **{"W_" + d: p.W[d] for d in DEC_NAMES}, **{"b_" + d: p.b[d] for d in DEC_NAMES},
             A=p.A, a0=p.a0, n_live=p.n_live, meta=json.dumps(meta or {}))

def load(path: str) -> Posture:
    z = np.load(path, allow_pickle=False)
    p = Posture(A=z["A"], a0=z["a0"], n_live=z["n_live"])
    for d in DEC_NAMES: p.W[d] = z["W_" + d]; p.b[d] = z["b_" + d]
    return p

def load_meta(path: str) -> dict:
    """MOREH-14: the meta beside the weights — the corpus fingerprint and the lambdas that made them."""
    z = np.load(path, allow_pickle=False)
    return json.loads(str(z["meta"]))
