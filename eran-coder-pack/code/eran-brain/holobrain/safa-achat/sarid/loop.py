# -*- coding: utf-8 -*-
"""THE LOOP - and MURPHY, who is allowed to fail the round.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL
> output, not a proxy.

WHAT MAKES THE LOOP FOREVER INSTEAD OF CONVERGENT
--------------------------------------------------
This is the one idea grafted wholesale from the second design, and it is the
best idea in either document: **RE-EXAM THE CANON FIRST, PROPOSE SECOND.**

A loop that only ever proposes new laws converges. The data is finite; once
every family has been ingested the held-out score saturates and "forever"
becomes a word in a README. So every round begins by re-testing every law
already in the canon against the family it has NOT seen this time - and a law
that fails is DECANONISED, with the family that killed it named in the journal.

That makes the loop's work inexhaustible for the honest reason: the canon is
never finished being wrong.

THE ORDER OF A ROUND
--------------------
  1. re-exam   every canon law against this round's held-out family
  2. propose   mine new correspondences from the fit families only
  3. exam      ceiling / floor / shuffle / holdout, on this round's canon
  4. judge     Murphy rules the round sound or not
  5. keep      only if all of: held-out gain >= eps, the ruler re-passed NOW,
               Murphy said yes. Otherwise REVERT - and reverting costs nothing,
               because the round's laws were never committed.

MURPHY
------
Named for the law. His job is to find the reason this round is worthless, and
he is believed. A round that moved nothing FAILS - "no movement" is the
signature of the no-op round that every autonomous loop in this workspace has
produced at least once and reported as success.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sarid import charter_text, HORIZON_BEATS                   # noqa: E402
from sarid.corpus import Corpus                                 # noqa: E402
from sarid.guards import Graft                                  # noqa: E402
from sarid.voices import Round                                  # noqa: E402
from sarid.weave import Anatomy, EPS, MARGIN, THETA_DECANON     # noqa: E402

MIN_LANGS_PER_FAMILY = 3           # a family needs this many to be held out
MAX_FIT_LANGS = 26                 # keep a round inside a few minutes


# ----------------------------------------------------------------- Murphy

def murphy(trace: dict) -> dict:
    """Rule the round sound, or name the reason it is not. He is believed."""
    faults = []
    if trace.get("n_pairs", 0) == 0:
        faults.append("no pairs were tested - the round did no work")
    if trace.get("n_fires", 0) == 0:
        faults.append("the weave never fired - nothing ran")
    if trace.get("holdout") is None:
        faults.append("the held-out exam never answered")
    if trace.get("ceiling") is None or trace.get("floor") is None:
        faults.append("the ruler did not report this round")
    else:
        if trace["ceiling"] <= trace["floor"]:
            faults.append(
                "THE RULER INVERTED: documented descent scored no higher than "
                "documented non-relatedness (%.4f <= %.4f). Every number this "
                "round is meaningless."
                % (trace["ceiling"], trace["floor"]))
        if trace.get("shuffle") is not None and \
                trace["ceiling"] <= trace["shuffle"]:
            faults.append(
                "the ceiling did not beat its own null model (%.4f <= %.4f) - "
                "this is chance resemblance being read as descent"
                % (trace["ceiling"], trace["shuffle"]))
    if trace.get("held_out_family") in (None, ""):
        faults.append("no family was held out - the session-leak scar")
    if trace.get("n_settled", 0) == 0 and trace.get("kept"):
        faults.append(
            "the round claims KEEP but wrote no laws down - a canon of 0 is "
            "not an improvement, whatever the held-out number says")
    h = trace.get("holdout")
    if h is not None and h >= 1.0:
        faults.append(
            "THE OBJECTIVE IS SATURATED: held-out scored %.4f, its ceiling. "
            "A measure already at its maximum cannot register any future "
            "improvement, so every later round is forced to revert and the "
            "loop is convergent, not forever. Hold out a family with more "
            "doculects, or move to the cognate-coded B-cubed objective."
            % h)
    if trace.get("moved") is False:
        faults.append("NO MOVEMENT: nothing changed. A no-op round is not a "
                      "round, whatever its exit code says.")
    return {"sound": not faults, "faults": faults}


# ------------------------------------------------------------------- loop

class Sarid:
    """The organ, across rounds. Resumes from checkpoint; never starts over."""

    def __init__(self, root: str, data: str, seed: int = 1933,
                 n_perm: int = 120):
        self.g = Graft(root)
        self.data = data
        self.seed = int(seed)
        self.n_perm = int(n_perm)
        self.state = self.g.load("state.json", {
            "round": 0, "kept": 0, "last_kept_score": 0.0,
            "canon": {}, "decanonised": [], "history": []})
        self.corpus = None

    # -- data ------------------------------------------------------------

    def ensure_corpus(self):
        if self.corpus is None:
            self.corpus = Corpus.from_cldf(self.data)
        return self.corpus

    def families_worth_holding(self):
        c = self.ensure_corpus()
        out = []
        for fam in c.families:
            if len(c.langs_in_family(fam)) >= MIN_LANGS_PER_FAMILY:
                out.append(fam)
        return out

    # -- canon -----------------------------------------------------------

    def canon_weight(self) -> dict:
        return {tuple(k.split("|")): v for k, v in self.state["canon"].items()}

    def re_exam_canon(self, held_out: str) -> list:
        """GRAFT G-c: re-test every kept law against the family it has NOT seen.

        A law is decanonised when its weight falls under THETA_DECANON, and the
        family that killed it is named. This is what keeps the loop honest and
        what keeps it from converging.
        """
        dropped = []
        c = self.ensure_corpus()
        for key in list(self.state["canon"]):
            a, b = key.split("|")
            # a law whose lineage is inside the held-out family cannot be
            # re-tested this round; it simply waits.
            if c.family_of(a) == held_out or c.family_of(b) == held_out:
                continue
            wgt = self.state["canon"][key]
            if wgt < THETA_DECANON:
                dropped.append({"law": key, "weight": wgt,
                                "killed_by": held_out})
                del self.state["canon"][key]
        return dropped

    # -- one round -------------------------------------------------------

    def round_once(self, held_out: str = "", quiet: bool = False) -> dict:
        self.g.guard()
        self.g.halt_if_stopped("start")
        c = self.ensure_corpus()
        fams = self.families_worth_holding()
        if not fams:
            raise SystemExit("no family has >= %d doculects; cannot hold one "
                             "out, and a random split is the scar."
                             % MIN_LANGS_PER_FAMILY)
        n = self.state["round"]
        held_out = held_out or fams[n % len(fams)]

        # 1. RE-EXAM THE CANON FIRST
        dropped = self.re_exam_canon(held_out)
        self.g.halt_if_stopped("re-exam")

        # 2. PROPOSE - fit languages only, held-out family absent by topology
        fit_all, test = c.split_by_family(held_out)
        rnd = random.Random(self.seed + n)
        fit = sorted(fit_all)
        if len(fit) > MAX_FIT_LANGS:
            fit = sorted(rnd.sample(fit, MAX_FIT_LANGS))
        r = Round(c, fit, held_out, seed=self.seed + n, n_perm=self.n_perm)

        ceiling_pairs, floor_pairs = [], []
        for i, a in enumerate(fit):
            for b in fit[i + 1:]:
                fa, fb = c.family_of(a), c.family_of(b)
                if fa and fa == fb:
                    ceiling_pairs.append((a, b))
                elif fa and fb:
                    floor_pairs.append((a, b))
        ceiling_pairs = ceiling_pairs[:40]
        floor_pairs = rnd.sample(floor_pairs, min(40, len(floor_pairs)))

        within, across = [], []
        test = sorted(test)
        for i, a in enumerate(test):
            for b in test[i + 1:]:
                within.append((a, b))
        for a in test:
            for b in fit[:8]:
                across.append((a, b))
        within = within[:30]
        across = across[:30]

        self.g.halt_if_stopped("propose")

        # 3. EXAM - the weave runs
        t0 = time.time()
        an = Anatomy(r, ceiling_pairs, floor_pairs, within, across,
                     shuffle_pair=(fit[0], fit[1]) if len(fit) > 1 else
                     (fit[0], fit[0]),
                     canon_weight=self.canon_weight(),
                     last_kept=self.state["last_kept_score"])
        res, fr, w = an.run()
        secs = time.time() - t0
        self.g.halt_if_stopped("exam")

        def one(key):
            v = fr.get(key) or []
            return float(v[-1]) if v else None

        trace = {
            "round": n, "held_out_family": held_out,
            "n_fit_langs": len(fit), "n_test_langs": len(test),
            "n_pairs": len(an._pairs), "n_fires": len(res.fires),
            "beats": res.beats, "finished": res.finished,
            "horizon": an.horizon,
            "ceiling": one("f_ceiling"), "floor": one("f_floor"),
            "shuffle": one("f_shuffle"), "holdout": one("f_holdout"),
            "alarm": bool(fr.get("f_alarm")),
            "n_settled": int(one("f_settled") or 0),
            "merit": an.merit(res),
            "decanonised": dropped,
            "secs": round(secs, 1),
        }
        trace["margin"] = (None if trace["ceiling"] is None
                           or trace["floor"] is None
                           else trace["ceiling"] - trace["floor"])
        gain = (None if trace["holdout"] is None else
                trace["holdout"] - self.state["last_kept_score"])
        trace["gain"] = gain
        trace["moved"] = bool(dropped) or bool(r.laws) or (
            gain is not None and abs(gain) > 0)

        # 4. JUDGE
        #
        # The provisional decision is computed BEFORE Murphy, because Murphy
        # has to be able to rule on it. It was computed after, at first, so
        # `trace["kept"]` was absent when he looked and his
        # "claims KEEP but wrote no laws down" check was DEAD CODE - which is
        # how round 0 kept a round with canon 0 and nobody objected.
        # THE WEAVE DECIDES, NOT A SECOND OPINION IN PYTHON.
        #
        # This read `margin >= 0` at first - a parallel, much weaker test than
        # the weave's own `sep` knot, which carries `trigger="rise 0.15"`. On
        # round 0 the margin was 0.0562, so `sep` correctly refused, `commit`
        # never fired and the canon stayed empty - and the loop announced KEPT
        # anyway, because its Python check was happy. Two rulers, and the
        # loose one won.
        #
        # `commit` firing IS the decision: it is the gate that already requires
        # both the held-out gain (through `keep`) and the ruler's separation
        # (through `sep`). Anything else here is a facade around the organ.
        trace["committed"] = bool(fr.get("f_settled"))
        ruler_ok = trace["committed"]
        trace["kept"] = bool(ruler_ok and gain is not None and gain >= EPS)
        m = murphy(trace)
        trace["murphy"] = m

        # 5. KEEP or REVERT - revert is the default
        keep = bool(m["sound"] and trace["kept"])
        trace["kept"] = keep
        if keep:
            for (a, b), laws in r.laws.items():
                key = "%s|%s" % (a, b)
                self.state["canon"][key] = min(
                    4.0, self.state["canon"].get(key, 1.0) + 0.4)
            self.state["last_kept_score"] = trace["holdout"]
            self.state["kept"] += 1
        else:
            trace["revert_reason"] = (
                "murphy: " + "; ".join(m["faults"]) if not m["sound"] else
                ("the weave refused to commit: `sep` did not reach the %g margin, "
                 "or `keep` never fired" % MARGIN if not ruler_ok else
                 "held-out gain %s < eps %g"
                 % ("none" if gain is None else "%.4f" % gain, EPS)))

        self.state["round"] = n + 1
        self.state["history"] = (self.state["history"] + [{
            "round": n, "held_out": held_out, "holdout": trace["holdout"],
            "kept": keep}])[-200:]
        self.g.save("state.json", self.state)
        self.g.note("round", **{k: v for k, v in trace.items()
                                if k != "decanonised"})
        if dropped:
            self.g.note("decanonised", round=n, laws=dropped)
        if not quiet:
            self.report(trace)
        return trace

    # -- the voice -------------------------------------------------------

    def report(self, t: dict) -> None:
        print("")
        print("== SARID round %d | held out: %s | %d fit / %d test doculects "
              "| %.1fs ==" % (t["round"], t["held_out_family"],
                              t["n_fit_langs"], t["n_test_langs"], t["secs"]))
        print("   pairs tested %d | weave fired %d times over %d beats "
              "(horizon %d, finished=%s)"
              % (t["n_pairs"], t["n_fires"], t["beats"], t["horizon"],
                 t["finished"]))
        f = lambda v: "  none" if v is None else "%.4f" % v      # noqa: E731
        print("   CEILING %s   FLOOR %s   SHUFFLE %s   margin %s"
              % (f(t["ceiling"]), f(t["floor"]), f(t["shuffle"]),
                 f(t["margin"])))
        print("   HELD-OUT %s  <- the number every future morning answers to"
              % f(t["holdout"]))
        print("   gain over last kept %s (eps %g) | laws written %d | "
              "canon %d | merit %s"
              % (f(t["gain"]), EPS, t["n_settled"], len(self.state["canon"]),
                 f(t["merit"])))
        if t["decanonised"]:
            print("   DECANONISED %d law(s), killed by %s:"
                  % (len(t["decanonised"]), t["held_out_family"]))
            for d in t["decanonised"][:5]:
                print("      %s (weight %.3f)" % (d["law"], d["weight"]))
        if t["alarm"]:
            print("   ALARM: the ruler FAILED this round. Do not read any "
                  "number above as evidence. / אזעקה: הסרגל נכשל.")
        if t["murphy"]["sound"]:
            print("   MURPHY: sound.")
        else:
            print("   MURPHY FAILS THE ROUND:")
            for x in t["murphy"]["faults"]:
                print("      - %s" % x)
        print("   %s" % ("KEPT. / נשמר." if t["kept"] else
                         "REVERTED (the default): %s / הוחזר."
                         % t.get("revert_reason", "")))

    # -- forever ---------------------------------------------------------

    def forever(self, rounds: int = 0, sleep_s: float = 30.0):
        n = 0
        while rounds == 0 or n < rounds:
            self.g.halt_if_stopped("between rounds")
            try:
                self.round_once()
            except SystemExit:
                raise
            except Exception as e:                            # noqa: BLE001
                self.g.note("round_error", error=repr(e))
                print("round failed: %r" % e)
            n += 1
            if rounds == 0 or n < rounds:
                time.sleep(sleep_s)


def main(argv=None):
    ap = argparse.ArgumentParser(description="SARID - the שפה אחת loop")
    ap.add_argument("--root", default=os.path.expanduser("~/sarid-shoot"))
    ap.add_argument("--data", required=True)
    ap.add_argument("--rounds", type=int, default=1,
                    help="0 = forever (the slow flame)")
    ap.add_argument("--sleep", type=float, default=30.0)
    ap.add_argument("--perm", type=int, default=120)
    a = ap.parse_args(argv)
    print(charter_text("en"))
    print("\nhorizon: %d years = %d beats. A deeper node never fires.\n"
          % (10000, HORIZON_BEATS))
    s = Sarid(a.root, a.data, n_perm=a.perm)
    s.forever(rounds=a.rounds, sleep_s=a.sleep)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
