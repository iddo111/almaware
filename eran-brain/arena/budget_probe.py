# -*- coding: utf-8 -*-
"""budget_probe.py — is the break ARCHITECTURAL, or just a starved search?

> BROKEN WINDOWS LAW: test the REAL output, never a proxy.

The matched budget is the fair currency, but it is also a confound: an arm that
searches 1,698 synaptic weights and an arm that searches 10 knobs are not
equally easy to optimise with the same number of environment steps. So before
saying "this architecture breaks at delay N", give the arms that broke FOUR
TIMES the budget and look again.

If the number moves, the break was the budget.
If the number does not move, the break is the architecture — and that is a
statement worth making.
"""
import json
import multiprocessing as mp
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import run_arena as RA                                            # noqa: E402

MULT = 4
PROBE_ARMS = ["ERAN-CTX", "LIF-FF", "LIF-REC", "Q-TAB"]
PROBE_DELAYS = [4, 8, 16]


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    b = RA.budgets(False)
    arms = {n: (n, k, c) for n, k, c in RA.ARMS}
    jobs = []
    for nm in PROBE_ARMS:
        n, k, c = arms[nm]
        for sd in RA.SEEDS:
            for d in PROBE_DELAYS:
                jobs.append((n, k, c, "dms", {"delay": d}, sd,
                             MULT * b["dms_trials"] * (d + 1), False))
            jobs.append((n, k, c, "rule", {}, sd, MULT * b["rule"], False))

    print(f"BUDGET PROBE — {MULT}x the matched budget, same held-out seeds, "
          f"nothing else changed. {len(jobs)} jobs.", flush=True)
    out = []
    with mp.Pool(12) as pool:
        for i, r in enumerate(pool.imap_unordered(RA.run_job, jobs), 1):
            out.append(r)
            key = r.get("acc")
            print(f"[{i:>3}/{len(jobs)}] {r['task']:<5} {r['arm']:<10} "
                  f"seed={r['seed']} delay={r.get('delay','-')} -> "
                  f"{round(key,4)} ({r['wall_s']}s)", flush=True)

    path = os.path.join(HERE, "results", "AGENTIC-BUDGET-PROBE-2026-08-21.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"multiplier": MULT, "budgets_1x": b, "runs": out}, f,
                  indent=1, ensure_ascii=False)

    print("\n" + "=" * 78)
    print(f"{MULT}x BUDGET vs 1x  (mean over 3 seeds)")
    print("=" * 78)
    base = json.load(open(os.path.join(HERE, "results",
                                       "AGENTIC-ARENA-2026-08-21.json"),
                          encoding="utf-8"))["runs"]
    for nm in PROBE_ARMS:
        for d in PROBE_DELAYS:
            b1 = [r["acc_frozen"] for r in base
                  if r["task"] == "dms" and r["arm"] == nm and r["delay"] == d]
            b4 = [r["acc_frozen"] for r in out
                  if r["task"] == "dms" and r["arm"] == nm and r["delay"] == d]
            print(f"  DMS  {nm:<10} N={d:<3} 1x {np.mean(b1)*100:5.1f}%  "
                  f"{MULT}x {np.mean(b4)*100:5.1f}%  "
                  f"delta {(np.mean(b4)-np.mean(b1))*100:+5.1f} pp   "
                  f"{MULT}x per-seed {[round(v*100,1) for v in b4]}")
        r1 = [r["acc_online"] for r in base
              if r["task"] == "rule" and r["arm"] == nm]
        r4 = [r["acc_online"] for r in out
              if r["task"] == "rule" and r["arm"] == nm]
        t1 = [r["ttc_mean_online"] for r in base
              if r["task"] == "rule" and r["arm"] == nm]
        t4 = [r["ttc_mean_online"] for r in out
              if r["task"] == "rule" and r["arm"] == nm]
        print(f"  RULE {nm:<10}      1x {np.mean(r1)*100:5.1f}% (ttc {np.mean(t1):4.1f})"
              f"  {MULT}x {np.mean(r4)*100:5.1f}% (ttc {np.mean(t4):4.1f})"
              f"  delta {(np.mean(r4)-np.mean(r1))*100:+5.1f} pp")
    print(f"\nwrote {path}")


if __name__ == "__main__":
    mp.set_start_method("fork", force=True)
    main()
