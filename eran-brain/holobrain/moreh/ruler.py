"""MOREH / מוֹרֶה — THE RULER: a held-out syllable is judged by RENDERING it and measuring the sound.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

Runs on eran2 only (the mouth lives there): ~/eran-brain/holobrain/moreh/ruler.py, with the lessons at
~/throat-one-sample/school-v2/lessons and the verifier at ~/throat-one-sample/school-v2/ruler.py — the
SAME ruler that passed every lesson. Parameter error is never the score; the sound is.

    python3 ruler.py            # the whole sitting: LOO x 24, floors, ceiling, held-out variants
    python3 ruler.py ba pa      # a subset (LOO only)
    python3 ruler.py --school v3   # the Hebrew judge's corpus instead (12 syllables — say so)

Writes  loo/loo-results.json, loo/posture-<school>.npz, loo/ERAN-<syl>-loo.wav (+ .json spec)
        — ERAN's sounds, Label Law.

  GATE 2   held-out syllables that pass the verifier / 24, and WHICH decision failed when it failed
  FLOORS   flat regressor (the 09-02 idea, on today's corpus, on the SAME features — MOREH-3) and
           class-copy; the published 09-02 baseline: class-only MLP 3/21 (honest 1/21)
  CEILING  the teacher's own variants under the same ruler, recomputed from ledger.jsonl (MOREH-11);
           gate1.json is only a snapshot and went 360 rows stale
  VARIANTS held-out variants of SEEN syllables: fit on 75% of each syllable's lessons, predict the
           syllable, render, verify (and sample around the prediction to estimate a pass rate)

Code revision 2026-09-06:
  * lambda is chosen by L.select_lams() INSIDE each fold's training rows, never on the held-out
    syllable (MOREH-2). The number this file prints is the nested one.
  * a crash is not a verdict: V2.judge() returns ok=None for an error, those rows are counted in
    their own column, and NO summary is published when any exist (MOREH-6).
  * a syllable filter that matches nothing is an error, not "all 24" (MOREH-9).
"""
from __future__ import annotations

import json
import os
import sys
import time
import wave

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
import anatomy as A                     # noqa: E402
import learn as L                       # noqa: E402

SV2 = os.path.expanduser("~/throat-one-sample/school-v2")
sys.path.insert(0, SV2)
import ruler as V2                      # noqa: E402  the verifier (school-v2/ruler.py)
import gesture as G                     # noqa: E402

# MOREH-6: off eran2 there is no mouth2, gesture.clean() silently rewrites I/U knots to AH and every
# render raises — which judge() used to score as an ordinary acoustic failure, i.e. 0/24 with no error
# and no log line. Fail here, loudly, by name, instead of publishing a zero.
if getattr(G, "mouth2", None) is None:
    raise RuntimeError("MOREH ruler needs the REAL mouth: gesture.mouth2 is None (no ~/mouth-v2 on this "
                       "box). This sitting must run on eran2. Refusing to score silence as 0/24.")

OUT = os.path.join(_HERE, "loo"); os.makedirs(OUT, exist_ok=True)

def wav_write(path, y):
    w = wave.open(path, "wb"); w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
    w.writeframes((np.clip(np.asarray(y, float), -1, 1) * 32767).astype(np.int16).tobytes()); w.close()

def teacher_decisions(rows):
    """the majority decision per syllable in the lessons (what the teacher DID for that syllable)"""
    return {syl: L.majority_dec(rs) for syl, rs in L.by_syllable(rows).items()}

def judge_spec(syl, spec):
    """-> (ok, fails, brief, y, cleaned spec, coercions).  ok is True / False / None(=error)."""
    spec, coerced = G.clean(dict(spec), report=True)     # MOREH-8: the coercions are recorded, not silent
    ok, fails, brief, y = V2.judge(syl, spec)
    return ok, fails, brief, y, spec, coerced

def loo(rows, syls, tag="moreh", model="moreh", verbose=True):
    """leave-one-SYLLABLE-out: fit on the others, choose lambda inside those, predict, render, verify."""
    truth = teacher_decisions(rows)
    res = {}
    for syl in syls:
        train = [r for r in rows if r["syl"] != syl]
        x = next(r["x"] for r in rows if r["syl"] == syl)
        near = None; lam = None
        if model == "moreh":
            # MOREH-2: the lambdas come from an inner LOO over `train` only — the held-out syllable is
            # never seen by the hyperparameter search either.
            lam = L.select_lams(train)
            p = L.fit(train, **lam); spec = p.spec(x)
        elif model == "flat":
            spec = L.Flat(train).spec(x)
        elif model == "copy":
            spec, near = L.Copy(train).spec(x)
        else:
            raise ValueError(model)
        ok, fails, brief, y, spec_c, coerced = judge_spec(syl, spec)
        wrong = [d for d in A.DEC_NAMES if spec_c[d] != truth[syl][d]]
        res[syl] = {"ok": ok, "error": ok is None, "fails": fails[:6],
                    "wrong_decisions": {d: [spec_c[d], truth[syl][d]] for d in wrong},
                    "spec": {k: spec_c[k] for k in spec_c}, "near": near, "lam": lam,
                    "coercions": coerced, "brief": brief[:600]}
        if y is not None and model == "moreh":
            wav_write(os.path.join(OUT, "ERAN-%s-loo.wav" % syl), y)
            json.dump({"speaker": "ERAN", "syl": syl, "how": "leave-one-syllable-out prediction of holobrain/moreh (fit on the other 23 syllables' lessons)",
                       "spec": spec_c, "gesture": G.readable(spec_c), "verifier_ok": ok, "fails": fails,
                       "wrong_decisions": res[syl]["wrong_decisions"], "lam": lam, "coercions": coerced,
                       # MOREH-7: which amounts were LEARNED and which were a median fallback
                       "n_live": {a: int(p.n_live[i]) for i, a in enumerate(A.AMOUNTS)},
                       "amounts_guessed": [a for i, a in enumerate(A.AMOUNTS) if p.n_live[i] < 3]},
                      open(os.path.join(OUT, "ERAN-%s-loo.json" % syl), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=float)
        if verbose:
            state = "ERROR" if ok is None else ("PASS" if ok else "FAIL")
            print("  [%s] %-4s %s  wrong=%s  %s" % (tag, syl, state, wrong or "-", "; ".join(fails)[:110]), flush=True)
    return res

def variants(rows, syls, rng_seed=0, n_sample=12, verbose=True):
    """held-out VARIANTS of seen syllables: fit on 75% of each syllable's lessons, predict, render, verify;
    then sample n_sample specs around the prediction (residual sd of the live amounts) and count passes.

    NOTE (MOREH open question, unresolved): the sampled pass rate is NOT comparable to the teacher's
    ceiling — sampling within one residual sd of a correct prediction is a different experiment from a
    random draw over the whole window. Both numbers are reported; do not subtract them."""
    rng = np.random.RandomState(rng_seed)
    by = L.by_syllable(rows); train = []; held = {}
    for syl, rs in by.items():
        idx = rng.permutation(len(rs)); k = max(1, int(round(0.25 * len(rs))))
        held[syl] = [rs[i] for i in idx[:k]]; train += [rs[i] for i in idx[k:]]
    lam = L.select_lams(train)
    p = L.fit(train, **lam)
    # residual sd per amount on the training rows (live only)
    PHI = np.stack([A.phi(r["x"], r["dec"]) for r in train])
    pred = PHI @ p.A.T + p.a0
    sd = np.zeros(A.NA)
    for a_i in range(A.NA):
        m = np.array([r["live"][a_i] for r in train])
        if m.sum() > 2: sd[a_i] = float(np.std(np.array([r["am"][a_i] for r in train])[m] - pred[m, a_i]))
    res = {}
    for syl in syls:
        x = by[syl][0]["x"]; spec = p.spec(x)
        ok, fails, brief, y, spec_c, coerced = judge_spec(syl, spec)
        n_ok = 0; n_err = int(ok is None)
        for j in range(n_sample):
            s2 = dict(spec)
            for a_i, a in enumerate(A.AMOUNTS):
                if a in spec and spec[a] is not None: s2[a] = float(spec[a] + rng.randn() * sd[a_i])
            ok2, f2, b2, y2, s2c, co2 = judge_spec(syl, s2)
            if ok2 is None: n_err += 1
            elif ok2: n_ok += 1
        res[syl] = {"prediction_ok": ok, "error": ok is None, "fails": fails[:4], "sampled_pass": n_ok,
                    "sampled_n": n_sample, "sampled_errors": n_err, "held_out_lessons": len(held[syl])}
        if verbose: print("  [var] %-4s pred %s  sampled %d/%d  errors %d" % (
            syl, "ERROR" if ok is None else ("PASS" if ok else "FAIL"), n_ok, n_sample, n_err), flush=True)
    return res, lam

def ceiling_from_ledger(path):
    """MOREH-11: the teacher's reachable bar, recomputed from ledger.jsonl NOW.

    gate1.json is a 2026-09-03 09:43 snapshot; by 09-06 the ledger had grown 360 rows past it
    (1354 attempts / 362 passes = 26.7%, not the published 33.5%) because later probe runs appended
    to it. Read the ledger, not the snapshot."""
    if not os.path.exists(path):
        return None, None
    n = {}; ok = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line: continue
            try: r = json.loads(line)
            except ValueError: continue
            s = r.get("syl")
            if s is None or r.get("ok") is None: continue   # MOREH-6: a crash was never an attempt
            n[s] = n.get(s, 0) + 1; ok[s] = ok.get(s, 0) + int(bool(r.get("ok")))
    per = {s: {"attempts": n[s], "passed": ok[s], "pass_rate": round(ok[s] / n[s], 4)} for s in n}
    tot = {"attempts": sum(n.values()), "passed": sum(ok.values()),
           "pass_rate": round(sum(ok.values()) / max(1, sum(n.values())), 4)}
    return per, tot

def main(argv):
    t0 = time.time()
    school = L.DEFAULT_SCHOOL
    if "--school" in argv:
        i = argv.index("--school"); school = argv[i + 1]; argv = argv[:i] + argv[i + 2:]
    rows = L.load_lessons(school=school)
    by = L.by_syllable(rows)
    # MOREH-9: a filter that matches nothing used to fall through the `or` to all 24 AND suppress the
    # floors, producing a full-looking but incomparable sitting from a typo. Name the bad arguments.
    unknown = [a for a in argv if a not in by]
    if unknown:
        raise SystemExit("unknown syllable(s): %s. This corpus (school-%s) has: %s"
                         % (" ".join(unknown), school, " ".join(sorted(by))))
    syls = [a for a in argv if a in by] or [s for s in V2.SYLS if s in by]
    print("moreh ruler: school-%s, %d lessons, %d syllables: %s" % (
        school, len(rows), len(by), " ".join("%s:%d" % (s, len(by[s])) for s in syls)), flush=True)
    if len(by) < len(V2.SYLS):
        print("  NOTE: this corpus covers %d of the %d syllables — report it as a %d-syllable LOO."
              % (len(by), len(V2.SYLS), len(by)), flush=True)
    print("LOO moreh (decisions then amounts, lambda chosen inside each fold):", flush=True)
    R = {"moreh": loo(rows, syls, "moreh", "moreh")}
    var_lam = None
    if not argv:
        print("LOO flat (the 09-02 regressor idea, SAME 49 features, on today's corpus):", flush=True)
        R["flat"] = loo(rows, syls, "flat", "flat")
        print("LOO copy (nearest class neighbour):", flush=True)
        R["copy"] = loo(rows, syls, "copy", "copy")
        print("held-out variants of seen syllables:", flush=True)
        R["variants"], var_lam = variants(rows, syls)

    per_ledger, tot_ledger = ceiling_from_ledger(os.path.join(SV2, "lessons", "ledger.jsonl"))
    gate1 = {}
    p1 = os.path.join(SV2, "lessons", "gate1.json")
    if os.path.exists(p1): gate1 = json.load(open(p1))["per_syllable"]
    twins = {s: V2.FACTS[s][7] for s in syls if V2.FACTS[s][7]}
    summary = {}
    errors = []
    for m in ("moreh", "flat", "copy"):
        if m in R:
            errs = [s for s in syls if R[m][s]["error"]]
            errors += ["%s/%s: %s" % (m, s, "; ".join(R[m][s]["fails"])[:160]) for s in errs]
            passed = [s for s in syls if R[m][s]["ok"]]
            summary[m] = {"pass": len(passed), "of": len(syls), "passed": passed, "errors": len(errs),
                          "errored": errs,
                          "genuine_excluding_twins": len([s for s in passed if s not in twins])}
    wrong_hist = {}
    for s in syls:
        for d in R["moreh"][s]["wrong_decisions"]: wrong_hist[d] = wrong_hist.get(d, 0) + 1

    # MOREH-14: the fit-on-all posture beside the results, so a published number can be reproduced from
    # the artefact and not only from a re-fit.
    lam_all = L.select_lams(rows)
    npz = os.path.join(OUT, "posture-school-%s.npz" % school)
    L.save(L.fit(rows, **lam_all), npz,
           {"school": school, "corpus": L.corpus_fingerprint(rows), "lessons": len(rows),
            "syllables": sorted(by), "lam": lam_all, "written": time.strftime("%Y-%m-%d %H:%M")})

    out = {"what": "MOREH gate 2: leave-one-syllable-out, rendered through mouth2 and judged by school-v2/ruler.py",
           "school": school, "corpus_fingerprint": L.corpus_fingerprint(rows),
           "requested_filter": list(argv), "syllables_scored": syls,
           "lessons": len(rows), "per_syllable_lessons": {s: len(by[s]) for s in syls},
           "lam_fit_on_all": lam_all, "lam_variants": var_lam, "posture_npz": os.path.basename(npz),
           "summary": summary, "errors": errors, "wrong_decision_histogram": wrong_hist,
           "baseline_0902": {"mlpc": "3/21 (kha/cha twins -> honest 1/21)", "ridge": "2/21", "nn": "2/21", "mlp_letter": "0/21"},
           "ceiling_teacher_variants": {s: (per_ledger or {}).get(s, {}).get("pass_rate") for s in syls},
           "ceiling_source": "ledger.jsonl (recomputed now)" if per_ledger else "gate1.json snapshot",
           "ceiling_total": tot_ledger,
           "ceiling_gate1_snapshot": {s: gate1.get(s, {}).get("pass_rate") for s in syls},
           "twins": twins, "results": R, "seconds": round(time.time() - t0, 1),
           "written_by": "claude-cli-MOREH holobrain/moreh/ruler.py " + time.strftime("%Y-%m-%d %H:%M")}
    if errors:
        # MOREH-6: a crash is not a verdict. Do not publish a pass count that is partly a crash rate.
        out["summary"] = None
        out["summary_withheld"] = "%d error row(s): a crash is not an acoustic failure" % len(errors)
        json.dump(out, open(os.path.join(OUT, "loo-results.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=float)
        for e in errors: print("  ERROR " + e, flush=True)
        raise SystemExit("REFUSING to publish a summary: %d error row(s) above. Fix the box, re-run."
                         % len(errors))
    json.dump(out, open(os.path.join(OUT, "loo-results.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=float)
    print("GATE 2: " + "; ".join("%s %d/%d (genuine %d)" % (m, v["pass"], v["of"], v["genuine_excluding_twins"]) for m, v in summary.items()), flush=True)
    print("wrong decisions when it failed:", wrong_hist, flush=True)
    if tot_ledger:
        print("ceiling (teacher, recomputed from ledger.jsonl): %d/%d = %.1f%%" % (
            tot_ledger["passed"], tot_ledger["attempts"], 100 * tot_ledger["pass_rate"]), flush=True)
    if "variants" in R:
        vs = R["variants"]; print("variants: prediction pass %d/%d; sampled %d/%d (NOT comparable to the ceiling)" % (
            sum(bool(v["prediction_ok"]) for v in vs.values()), len(vs), sum(v["sampled_pass"] for v in vs.values()), sum(v["sampled_n"] for v in vs.values())), flush=True)

if __name__ == "__main__":
    main(sys.argv[1:])
