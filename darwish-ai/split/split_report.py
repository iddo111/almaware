# -*- coding: utf-8 -*-
"""split_report.py - turn split_eval.json into the table a decision can be made on.

לזכרו של לָאוֹר ז״ל.

Everything here is paired BY SEED: seed s's joint model against seed s's rhythm
and pitch models, so the error bar is on the DIFFERENCE, not on two independent
means. With three seeds that is the only honest way to put a bar on it.

THE HEADLINE, and the only cross-alphabet quantity that IS a quantity:

    bits per second of heldout music
      joint  = nats(joint)                    / ln2 / seconds
      split  = nats(rhythm) + nats(pitch)     / ln2 / seconds

The split's number INCLUDES the STEP/BAR/PHRASE clock twice, because both
streams carry it. Nothing is netted out. Lower is better; it is a description
length, and the two families describe the identical music because
split_tok.merge_streams is a bijection verified on all 323 corpus files.

THEN TWO PER-LANE VIEWS, and they answer different questions:

  RAW  -log p(t)                       what the token costs in its stream.
       Flatters the split: the joint model must also spend part of every
       prediction deciding whether a drum or a pitch comes next, and the
       rhythm model never faces that question because its stream has no
       pitches in it. Read it as "what the stream costs", not "what the
       model knows".

  LANE-RESTRICTED  -log p(t | lane(t))  the same quantity with that advantage
       removed from BOTH sides. GIVEN that a note sounds here, which note?
       This is the number that answers Iddo's actual complaint about melody
       and harmony, and it is the one to trust for that question.

Every column is printed beside its floor. A number without its floor is
inadmissible.
"""
from __future__ import annotations

import argparse
import json
import math

LN2 = math.log(2.0)


def lane_index(names, want):
    return names.index(want) if want in names else None


def get(ev, alph, seed, step):
    return ev["models"][alph][str(seed)][str(step)]


def lane_ce(ev, alph, seed, step, lane, key="per_lane_nats"):
    r = get(ev, alph, seed, step)
    i = lane_index(ev["lane_names"][alph], lane)
    if i is None or key not in r:
        return None, 0
    n = r["per_lane_counts"][i]
    return (r[key][i] / n if n else None), n


def floor_lane_ce(ev, alph, lane, which):
    f = ev["floors"][alph]
    i = lane_index(ev["lane_names"][alph], lane)
    if i is None:
        return None
    n = f["counts"][i]
    return f["per_lane_nats"][which][i] / n if n else None


def stat(vals):
    vals = [v for v in vals if v is not None]
    if not vals:
        return None
    n = len(vals)
    m = sum(vals) / n
    sd = (sum((v - m) ** 2 for v in vals) / (n - 1)) ** 0.5 if n > 1 else 0.0
    return {"mean": m, "sd": sd, "n": n, "sem": sd / (n ** 0.5) if n > 1 else 0.0}


def fmt(s, d=4):
    if s is None:
        return "        n/a         "
    return "%.*f +/- %.*f" % (d, s["mean"], d, s["sd"])


def nan(x):
    return float("nan") if x is None else x


def merge(paths):
    parts = [json.load(open(f.strip(), encoding="utf-8"))
             for f in paths if f.strip()]
    ev = parts[0]
    for q in parts[1:]:
        # The heldout facts must AGREE between partials, or they were not
        # produced against the same measuring instrument.
        for k in ("seconds_of_heldout_music", "heldout_tokens", "seq_len",
                  "context_matched"):
            if ev.get(k) != q.get(k):
                raise SystemExit("partial eval files disagree on %r - they were "
                                 "not measured against the same heldout set" % k)
        for alph, by_seed in q.get("models", {}).items():
            ev["models"].setdefault(alph, {})
            for seed, by_step in by_seed.items():
                ev["models"][alph].setdefault(seed, {}).update(by_step)
    return ev


VIEWS = (
    ("per_lane_nats", "unigram",
     "RAW  -log p(t)  -  what the token costs in its own stream.\n"
     "  Flatters the split: the joint model also pays, on every prediction, for\n"
     "  knowing WHICH lane comes next. The split gets that for free (and pays for\n"
     "  it instead in the duplicated clock, which the headline above counts)."),
    ("per_lane_nats_lane_restricted", "lane_marginal",
     "LANE-RESTRICTED  -log p(t | t is in this lane)  -  the lane-identification\n"
     "  advantage removed from BOTH sides. GIVEN that a note sounds here, WHICH note?\n"
     "  This is the number for Iddo's question about melody and harmony."),
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--eval", required=True,
                    help="one split_eval.json, or several comma-separated partials")
    ap.add_argument("--pairs", default="750:375:1.00,1500:750:1.00,1500:1500:2.00",
                    help="jointStep:splitStep:splitComputeRelativeToJoint")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    ev = merge(a.eval.split(","))
    secs = ev["seconds_of_heldout_music"]
    seeds = sorted(ev["models"]["joint"].keys(), key=int)

    print("=" * 78)
    print("DARWISH  rhythm/pitch SPLIT  vs  joint v2   -   heldout, full coverage")
    print("=" * 78)
    print("heldout: %d tracks, %.1f s of music (%.2f h)"
          % (ev["heldout_tracks"], secs, secs / 3600.0))
    ht = ev["heldout_tokens"]
    print("heldout tokens : joint %d | rhythm %d | pitch %d  (split/joint = %.4f)"
          % (ht["joint"], ht["rhythm"], ht["pitch"],
             (ht["rhythm"] + ht["pitch"]) / ht["joint"]))
    for k, v in ev.get("coverage", {}).items():
        print("  coverage %-7s %.4f%% of heldout targets scored, %d windows, seq %d"
              % (k, 100.0 * v["fraction"], v["n_windows"], ev["seq_len"][k]))
    print("seeds: %s   context_matched=%s" % (", ".join(seeds), ev["context_matched"]))

    print("\nFLOORS (nats/token, fitted on TRAIN, scored on heldout)")
    print("%-8s %9s %9s %9s %9s" % ("", "uniform", "unigram", "lane-marg", "bigram"))
    for alph in ("joint", "rhythm", "pitch"):
        f = ev["floors"][alph]
        print("%-8s %9.4f %9.4f %9.4f %9.4f"
              % (alph, f["uniform_ce"], f["ce"]["unigram"],
                 f["ce"]["lane_marginal"], f["ce"]["bigram"]))

    fj, fr, fp = (ev["floors"][k] for k in ("joint", "rhythm", "pitch"))
    print("\nFLOORS as bits/second of music (the same headline quantity)")
    for nm in ("unigram", "bigram"):
        j = fj["total_nats"][nm] / LN2 / secs
        s = (fr["total_nats"][nm] + fp["total_nats"][nm]) / LN2 / secs
        print("  %-8s  joint %8.2f   split %8.2f   (split-joint %+7.2f)"
              % (nm, j, s, s - j))

    out = {"seeds": seeds, "seconds_of_heldout_music": secs, "pairs": {},
           "floors_bits_per_second": {
               k: {"joint": fj["total_nats"][k] / LN2 / secs,
                   "split": (fr["total_nats"][k] + fp["total_nats"][k]) / LN2 / secs}
               for k in ("unigram", "bigram")}}

    for spec in a.pairs.split(","):
        js, ss, ratio = spec.split(":")
        js, ss, ratio = int(js), int(ss), float(ratio)
        label = ("joint@%d  vs  rhythm@%d + pitch@%d   (split compute = %.2fx joint)"
                 % (js, ss, ss, ratio))
        print("\n" + "-" * 78)
        print(label)
        print("-" * 78)

        jb, sb, db = [], [], []
        for s in seeds:
            try:
                jn = get(ev, "joint", s, js)["total_nats"]
                rn = get(ev, "rhythm", s, ss)["total_nats"]
                pn = get(ev, "pitch", s, ss)["total_nats"]
            except KeyError:
                continue
            jb.append(jn / LN2 / secs)
            sb.append((rn + pn) / LN2 / secs)
            db.append(sb[-1] - jb[-1])
        SJ, SS_, SD = stat(jb), stat(sb), stat(db)
        if SJ is None:
            print("  (no checkpoints for this pairing)")
            continue
        print("  BITS PER SECOND OF MUSIC   (lower is better; the headline)")
        print("    joint v2      %s" % fmt(SJ, 3))
        print("    split (r+p)   %s   clock counted twice, in full" % fmt(SS_, 3))
        print("    difference    %s   paired by seed  ->  %s"
              % (fmt(SD, 3), "SPLIT WINS" if SD["mean"] < 0 else "JOINT WINS"))
        if SD["n"] > 1 and SD["sem"]:
            t = SD["mean"] / SD["sem"]
            print("                  paired t = %+.2f on %d seeds "
                  "(|t| > 4.30 is p < 0.05 at n=3)" % (t, SD["n"]))

        rows = {}
        for key, floorkey, title in VIEWS:
            have_any = False
            print("\n  " + title)
            print("  %-8s %-24s %-24s %-9s %-9s"
                  % ("lane", "joint model", "split model", "floor", "bigram"))
            for lane, other in (("drum", "rhythm"), ("pitch", "pitch"),
                                ("dur", "pitch"), ("struct", None)):
                jv = []
                ov = []
                jn = on = 0
                for s in seeds:
                    try:
                        v, n = lane_ce(ev, "joint", s, js, lane, key)
                    except KeyError:
                        continue
                    if v is None:
                        continue
                    jv.append(v)
                    jn = n
                    if other:
                        try:
                            v2, n2 = lane_ce(ev, other, s, ss, lane, key)
                        except KeyError:
                            continue
                        if v2 is not None:
                            ov.append(v2)
                            on = n2
                    else:
                        # struct is carried by BOTH streams: the split pays twice
                        try:
                            a1, n1 = lane_ce(ev, "rhythm", s, ss, "struct", key)
                            a2, n2 = lane_ce(ev, "pitch", s, ss, "struct", key)
                        except KeyError:
                            continue
                        if a1 is not None and a2 is not None:
                            ov.append((a1 * n1 + a2 * n2) / max(n1 + n2, 1))
                            on = n1 + n2
                SJl, SOl = stat(jv), stat(ov)
                if SJl is None:
                    continue
                have_any = True
                fl = floor_lane_ce(ev, "joint", lane, floorkey)
                big = floor_lane_ce(ev, "joint", lane, "bigram")
                rows.setdefault(key, {})[lane] = {
                    "joint": SJl, "split": SOl, "joint_n": jn, "split_n": on,
                    "floor": fl, "floor_kind": floorkey, "floor_bigram": big}
                note = "   (the split pays this TWICE)" if lane == "struct" else ""
                print("  %-8s %-24s %-24s %9.4f %9.4f%s"
                      % (lane, fmt(SJl), fmt(SOl), nan(fl), nan(big), note))
            if not have_any:
                print("  (this view is not present in the eval file)")
        if rows:
            k0 = next(iter(rows))
            print("  token counts: " + ", ".join(
                "%s joint=%d split=%d" % (k, v["joint_n"], v["split_n"])
                for k, v in rows[k0].items()))

        out["pairs"][spec] = {
            "label": label, "joint_step": js, "split_step": ss,
            "split_compute_x": ratio,
            "bits_per_second": {"joint": SJ, "split": SS_, "difference": SD},
            "per_lane": rows}

    if a.out:
        json.dump(out, open(a.out, "w"), indent=1)
        print("\nwrote " + a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
