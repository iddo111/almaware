# -*- coding: utf-8 -*-
"""decompose.py - WHERE the bits/second gap comes from, lane by lane.

לזכרו של לָאוֹר ז״ל.

split_report.py says who wins. This says why, and it is exact: the total nats a
family spends is the sum over lanes of (count x per-lane CE), so the gap
decomposes with no residual. Every line is signed - negative means the SPLIT
spends fewer nats there.

THE REPAIR THAT DOES NOT EXIST, checked rather than assumed
-----------------------------------------------------------
The first thing this decomposition suggests is "send the clock once - transmit
the rhythm stream, then the pitch stream WITHOUT its STEP tokens". That scheme
is NOT DECODABLE, and the check is one line of counting.

The rhythm stream's clock tells you how many sixteenths there are and what the
drums do in each. It does NOT tell you which sixteenth each PITCH belongs to.
The pitch stream's STEP token is what assigns its notes to steps - it is the
"no more notes in this one" signal - and that is real information no other
stream carries. Strip it and a flat run of DUR/PITCH tokens cannot be placed in
time at all.

Measured on the heldout pitch stream: of its 451,886 struct tokens, 423,717
(93.8%) are STEP. Only BAR and PHRASE - 6.2%, and the cheapest tokens in the
alphabet - are genuinely derivable from the STEP count. Removing them cannot
recover the deficit.

So the duplicated step-boundary signal is INTRINSIC to factorising on the STEP
clock, not an artefact of this implementation. Any factorisation that puts the
notes and the drums in separate streams must say "this step is finished" in
both. That is the finding, and it is why this file no longer prints an estimate
for a scheme that cannot be built.
"""
from __future__ import annotations

import argparse
import json
import math

LN2 = math.log(2.0)
LANES = ("drum", "pitch", "dur", "struct")


def merge(paths):
    parts = [json.load(open(p.strip(), encoding="utf-8")) for p in paths if p.strip()]
    ev = parts[0]
    for q in parts[1:]:
        for alph, by_seed in q.get("models", {}).items():
            ev["models"].setdefault(alph, {})
            for seed, by_step in by_seed.items():
                ev["models"][alph].setdefault(seed, {}).update(by_step)
    return ev


def lane_nats(ev, alph, seed, step, lane):
    names = ev["lane_names"][alph]
    if lane not in names:
        return 0.0, 0
    i = names.index(lane)
    r = ev["models"][alph][str(seed)][str(step)]
    return r["per_lane_nats"][i], r["per_lane_counts"][i]


def mean_sd(v):
    n = len(v)
    m = sum(v) / n
    sd = (sum((x - m) ** 2 for x in v) / (n - 1)) ** 0.5 if n > 1 else 0.0
    return m, sd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--eval", required=True)
    ap.add_argument("--joint-step", type=int, default=1500)
    ap.add_argument("--split-step", type=int, default=750)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    ev = merge(a.eval.split(","))
    secs = ev["seconds_of_heldout_music"]
    seeds = sorted(ev["models"]["joint"].keys(), key=int)
    to_bps = 1.0 / LN2 / secs

    print("=" * 74)
    print("WHERE THE GAP COMES FROM   joint@%d  vs  rhythm@%d + pitch@%d"
          % (a.joint_step, a.split_step, a.split_step))
    print("heldout %.1f s of music, %d seeds, exact decomposition (no residual)"
          % (secs, len(seeds)))
    print("=" * 74)
    print("%-10s %14s %14s %14s %10s" %
          ("lane", "joint nats", "split nats", "split-joint", "bits/s"))

    rows = {}
    tot_j, tot_s = [0.0] * len(seeds), [0.0] * len(seeds)
    for lane in LANES:
        dj, ds = [], []
        for k, sd_ in enumerate(seeds):
            jn, _ = lane_nats(ev, "joint", sd_, a.joint_step, lane)
            sn = 0.0
            for alph in ("rhythm", "pitch"):
                v, _ = lane_nats(ev, alph, sd_, a.split_step, lane)
                sn += v
            dj.append(jn); ds.append(sn)
            tot_j[k] += jn; tot_s[k] += sn
        mj, _ = mean_sd(dj)
        ms, _ = mean_sd(ds)
        dm, dsd = mean_sd([b - c for b, c in zip(ds, dj)])
        rows[lane] = {"joint_nats": mj, "split_nats": ms,
                      "diff_nats": dm, "diff_sd": dsd,
                      "diff_bits_per_second": dm * to_bps}
        print("%-10s %14.0f %14.0f %14.0f %10.3f%s"
              % (lane, mj, ms, dm, dm * to_bps,
                 "   <- the clock, paid twice" if lane == "struct" else ""))
    mj, _ = mean_sd(tot_j)
    ms, _ = mean_sd(tot_s)
    dm, dsd = mean_sd([b - c for b, c in zip(tot_s, tot_j)])
    print("-" * 74)
    print("%-10s %14.0f %14.0f %14.0f %10.3f" % ("TOTAL", mj, ms, dm, dm * to_bps))
    print("\njoint  %.3f bits/s      split  %.3f bits/s      gap  %+.3f bits/s"
          % (mj * to_bps, ms * to_bps, dm * to_bps))

    non_clock = sum(rows[l]["diff_bits_per_second"] for l in ("drum", "pitch", "dur"))
    print("\nREAD IT LIKE THIS")
    print("  the duplicated clock costs the split      %+7.3f bits/s" %
          rows["struct"]["diff_bits_per_second"])
    print("  everything else the split gains is only   %+7.3f bits/s" % non_clock)
    print("  -> the clock %s the whole deficit."
          % ("MORE THAN ACCOUNTS FOR" if rows["struct"]["diff_bits_per_second"]
             > -non_clock else "does NOT account for"))

    # --- what the second copy of the step-boundary signal actually costs ---
    pj = []
    for k, sd_ in enumerate(seeds):
        pj.append(lane_nats(ev, "pitch", sd_, a.split_step, "struct")[0])
    pm, psd = mean_sd(pj)
    print("\nTHE SECOND COPY OF THE CLOCK, priced")
    print("  the PITCH stream's own struct tokens cost %.0f nats = %.3f bits/s"
          % (pm, pm * to_bps))
    print("  93.8% of them are STEP, which says WHICH SIXTEENTH each note belongs")
    print("  to. No other stream carries that, so it cannot be dropped and the")
    print("  stream stay decodable. Only BAR+PHRASE (6.2%, and the cheapest")
    print("  tokens there are) are derivable from the STEP count.")
    print("  -> the duplicated step-boundary signal is INTRINSIC to splitting on")
    print("     the STEP clock, not a fixable detail of this implementation.")

    out = {"joint_step": a.joint_step, "split_step": a.split_step,
           "seeds": seeds, "seconds": secs, "per_lane": rows,
           "total_joint_bits_per_second": mj * to_bps,
           "total_split_bits_per_second": ms * to_bps,
           "gap_bits_per_second": dm * to_bps,
           "clock_cost_bits_per_second": rows["struct"]["diff_bits_per_second"],
           "non_clock_gain_bits_per_second": non_clock,
           "pitch_stream_struct_nats": pm,
           "pitch_stream_struct_bits_per_second": pm * to_bps,
           "clock_is_intrinsic": ("93.8% of the pitch stream's struct tokens are "
                                  "STEP, which assigns each note to a sixteenth. "
                                  "No other stream carries that, so the second "
                                  "copy cannot be removed and the stream stay "
                                  "decodable. Only BAR+PHRASE (6.2%) are "
                                  "derivable.")}
    if a.out:
        json.dump(out, open(a.out, "w"), indent=1)
        print("\nwrote " + a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
