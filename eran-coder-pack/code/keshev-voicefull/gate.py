#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""STEP 6 - THE GATE.  Accepts or REFUSES the fine-tune.

The rules are written here, in code, BEFORE the numbers exist, so that they
cannot be relaxed once the numbers are disappointing.  A gate that has never
refused anything has not been demonstrated - so gate.py is run against a known
no-op arm as well as against the real one, and both outcomes are reported.

THE RULES, in the order they are applied:

  R1  no FAIL in cheshbon.py.  Contamination or teacher-imitation is
      disqualifying on its own, whatever the table says.
  R2  the margin must clear the measured harness noise floor.  If the harness
      cannot tell the two arms apart when run twice on the SAME model, it cannot
      tell them apart at all.
  R3  the NAMES column must strictly improve.  This is the only column no part
      of the training pipeline can flatter.
  R4  no guardrail may regress: not empties, not output length collapse.
  R5  CER/WER against ref.jsonl may NOT be used to pass this gate.  It is the
      teacher's own output; the student was trained on it.  It is reported and
      it is ignored.
  R6  the NAMES margin must clear SAMPLING noise, not just harness noise - a
      bootstrap CI over the eval clips must exclude zero.  ADDED 2026-09-06
      after this gate passed a +1 margin whose CI was [-2, +5]; see the note at
      R6 in the code.  It did not rewrite that verdict, it binds later runs.

A tie is a loss.  A win on CER alone is a loss.  Silence is a loss.
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from judge import norm, rates, degenerate, GOOD, BAD


def bootstrap_names(rows, inc, cand, n=20000, seed=1729):
    """Sampling variability of the NAMES margin over the eval clips.

    The gate's admissible column is a count of ~13 events across 209 clips. A
    delta of +1 in such a count is not a result, and R3 alone cannot tell the
    difference. This is what R6 uses.
    """
    import numpy as np
    x = np.array([sum(r[inc]["text"].count(k) for k in GOOD) for r in rows], dtype=float)
    y = np.array([sum(r[cand]["text"].count(k) for k in GOOD) for r in rows], dtype=float)
    d = y - x
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(d), size=(n, len(d)))
    s = d[idx].sum(1)
    return (int(np.percentile(s, 2.5)), int(np.percentile(s, 97.5)), float((s <= 0).mean()))


def col(rows, arm):
    ok = sum(r[arm]["text"].count(h) for r in rows for h in GOOD)
    bad = sum(r[arm]["text"].count(b) for r in rows for b in BAD)
    emp = sum(1 for r in rows if not r[arm]["text"].strip())
    ch = sum(len(r[arm]["text"]) for r in rows) / max(len(rows), 1)
    ce = rc = 0
    for r in rows:
        if not r["ref"] or degenerate(r["ref"]):
            continue
        _, _, c, d = rates(r[arm]["text"], r["ref"])
        ce += c; rc += d
    return {"names_ok": ok, "names_bad": bad, "empties": emp, "chars": ch,
            "cer": ce / max(rc, 1) * 100}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--judged", required=True)
    ap.add_argument("--cheshbon", default="")
    ap.add_argument("--candidate", required=True)
    ap.add_argument("--incumbent", required=True)
    ap.add_argument("--noise-cer", type=float, default=-1.0,
                    help="measured run-to-run CER of the harness, in %%")
    args = ap.parse_args()

    rows = [json.loads(l) for l in
            Path(args.judged).read_text(encoding="utf-8").splitlines() if l.strip()]
    for a in (args.candidate, args.incumbent):
        if a not in rows[0]:
            sys.exit("GATE ERROR: arm %r is not in %s" % (a, args.judged))

    cand = col(rows, args.candidate)
    inc = col(rows, args.incumbent)
    print("=" * 78)
    print("THE GATE   candidate=%s   incumbent=%s" % (args.candidate, args.incumbent))
    print("=" * 78)
    print("%-22s %14s %14s %10s" % ("", "incumbent", "candidate", "delta"))
    for k, fmt in (("names_ok", "%d"), ("names_bad", "%d"), ("empties", "%d"),
                   ("chars", "%.1f"), ("cer", "%.2f")):
        d = cand[k] - inc[k]
        print("%-22s %14s %14s %10s" % (k, fmt % inc[k], fmt % cand[k], ("%+.2f" % d)))

    fails = []

    # R1
    if args.cheshbon and Path(args.cheshbon).exists():
        ch = json.loads(Path(args.cheshbon).read_text(encoding="utf-8"))
        bad = [c["test"] for c in ch if c["verdict"] == "FAIL"]
        if bad:
            fails.append("R1 cheshbon FAILED: %s" % "; ".join(bad))
        else:
            print("\nR1  cheshbon: no FAIL verdicts.  PASS")
    else:
        fails.append("R1 cheshbon results were not supplied - cannot pass a gate blind")

    # R2
    if args.noise_cer < 0:
        fails.append("R2 harness noise floor was never measured - no margin can be trusted")
    else:
        print("R2  harness noise floor %.2f%% CER measured.  PASS" % args.noise_cer)

    # R3  -- the only admissible column
    dn = cand["names_ok"] - inc["names_ok"]
    if dn > 0:
        print("R3  names %d -> %d (%+d).  PASS" % (inc["names_ok"], cand["names_ok"], dn))
    else:
        fails.append("R3 names did not improve: %d -> %d (%+d). A tie is a loss."
                     % (inc["names_ok"], cand["names_ok"], dn))

    # R4
    if cand["names_bad"] > inc["names_bad"]:
        fails.append("R4 garbled names increased %d -> %d" % (inc["names_bad"], cand["names_bad"]))
    if cand["empties"] > inc["empties"]:
        fails.append("R4 empty outputs increased %d -> %d" % (inc["empties"], cand["empties"]))
    if cand["chars"] < 0.85 * inc["chars"]:
        fails.append("R4 output collapsed: %.1f -> %.1f chars/clip (a model that says "
                     "less scores better on CER without being better)"
                     % (inc["chars"], cand["chars"]))
    if not any(f.startswith("R4") for f in fails):
        print("R4  no guardrail regressed.  PASS")

    # R5
    print("R5  CER %.2f%% -> %.2f%% (%+.2f) is REPORTED AND IGNORED - it is the "
          "teacher's\n    own output and the candidate was trained on it."
          % (inc["cer"], cand["cer"], cand["cer"] - inc["cer"]))

    # R6 -- ADDED 2026-09-06, AFTER the first real run, and this note is part of
    # the rule.  That run moved names 13 -> 14 and this gate PASSED it, because
    # R3 as written asks only for a positive delta.  A bootstrap over the 209
    # clips then put that +1 at 95% CI [-2, +5], P(delta<=0)=0.40 - a margin
    # indistinguishable from zero.  The gate had passed noise.
    #
    # R6 is the repair.  It did NOT retroactively change that run's recorded
    # verdict (PASS); changing a rule after seeing the numbers to get the answer
    # you wanted is the whole failure this program exists to prevent.  It binds
    # every run from here on.
    lo, hi, p = bootstrap_names(rows, args.incumbent, args.candidate)
    print("R6  names delta %+d, 95%% CI [%+d, %+d], P(delta<=0)=%.2f"
          % (cand["names_ok"] - inc["names_ok"], lo, hi, p))
    if lo <= 0:
        fails.append("R6 the name margin does not clear sampling noise: 95%% CI "
                     "[%+d, %+d] includes zero (P(delta<=0)=%.2f). A margin you "
                     "cannot distinguish from zero is not a win." % (lo, hi, p))
    else:
        print("    the margin excludes zero.  PASS")

    print("\n" + "=" * 78)
    if fails:
        print("VERDICT:  REFUSED")
        for f in fails:
            print("   - " + f)
        print("=" * 78)
        print("A refusal is a result. It is not a failure of the run; it is the run\n"
              "working. Nothing is deployed and nothing is claimed.")
        sys.exit(1)
    print("VERDICT:  PASS - the candidate cleared every rule that was written down\n"
          "          before the numbers existed. Deployment remains Iddo's call.")
    print("=" * 78)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
