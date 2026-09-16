# -*- coding: utf-8 -*-
"""summarize.py — turn the arena JSON into the tables, and into the one line.

> BROKEN WINDOWS LAW: test the REAL output, never a proxy.

Prints the chance line first, then per-task tables with EVERY seed visible, the
delay-to-break curve for DMS, trials-to-criterion and perseverative errors for
RULE, and the chemistry ablation contrast (ERAN-CTX vs ERAN-CTX+CHEM).
"""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ARM_ORDER = ["RANDOM", "ORACLE", "Q-TAB", "Q-TAB-MEM",
             "ERAN-PROTO", "ERAN-TRACE", "ERAN-CTX", "ERAN-CTX+CHEM",
             "LIF-FF", "LIF-REC", "LIF-REC-BIG"]
HOLD = 0.60          # "still working": >= 60% on a 50%-chance task


def sel(runs, task, arm, **kw):
    out = []
    for r in runs:
        if r["task"] != task or r["arm"] != arm:
            continue
        if all(r.get(k) == v for k, v in kw.items()):
            out.append(r)
    return out


def fmt_seeds(vals, pct=True, w=6):
    if pct:
        return " ".join(f"{v*100:{w}.1f}" for v in vals)
    return " ".join(f"{v:+{w}.1f}" for v in vals)


def main(path):
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    runs = d["runs"]
    delays = d["delays"]
    seeds = d["seeds"]
    nE = d["dms_eval_episodes"]
    one_trial_pp = 100.0 / nE
    se = math.sqrt(0.25 / (nE * len(seeds))) * 100

    print("=" * 96)
    print("AGENTIC ARENA — ERAN's prototype substrate vs a spiking network, AS AGENTS")
    print(f"host={d['host']}  date={d['date']}  wall={d['wall_s']}s  seeds={seeds}")
    print("=" * 96)
    print("\nCHANCE FIRST, as the house law requires")
    print(f"  DMS  : chance 50.00%.  {nE} held-out trials per seed, {len(seeds)} seeds"
          f"  ->  ONE trial = {one_trial_pp:.2f} pp;  1 SE at chance = {se:.2f} pp"
          f"  ->  'still working' bar = {HOLD*100:.0f}%")
    print("  RULE : chance 33.33% (3 actions). Trials-to-criterion at chance = 60 "
          "= the block timed out = never got there.")
    print("  PONG : score = hits - misses over 2,000 ticks vs a random opponent. "
          "Negative = losing.")
    print(f"\nBUDGETS (environment steps, identical for every arm on a task): "
          f"{json.dumps(d['budgets'])}")
    print(f"Train seeds {d['train_seed_range']}, eval seeds from {d['eval_seed_lo']} "
          f"— disjoint, opened once per arm at the end.")

    # ── DMS ───────────────────────────────────────────────────────────────
    print("\n" + "=" * 96)
    print("TASK 2 — DELAYED MATCH TO SAMPLE (working memory).  accuracy %, "
          "held-out, POLICY FROZEN at eval")
    print("=" * 96)
    hdr = "  " + f"{'arm':<15}" + "".join(f"{'N='+str(n):>9}" for n in delays) \
          + "   break-at   n_params"
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    dms_summary = {}
    for arm in ARM_ORDER:
        cells, means = [], []
        npar = None
        for n in delays:
            rs = sel(runs, "dms", arm, delay=n)
            if not rs:
                cells.append("     -")
                means.append(None)
                continue
            v = [r["acc_frozen"] for r in rs]
            means.append(float(np.mean(v)))
            cells.append(f"{np.mean(v)*100:8.1f}")
            npar = rs[0]["stats"].get("n_params", rs[0]["stats"].get("memory_cells"))
        brk = "never"
        if means and means[0] is not None and means[0] >= HOLD:
            brk = ">" + str(delays[-1])
            for n, m in zip(delays, means):
                if m is not None and m < HOLD:
                    brk = str(n)
                    break
        print(f"  {arm:<15}" + "".join(f"{c:>9}" for c in cells)
              + f"   {brk:>7}   {npar}")
        dms_summary[arm] = {"means": means, "break_at": brk}

    print("\n  per-seed, every number (accuracy %, frozen policy):")
    for arm in ARM_ORDER:
        line = []
        for n in delays:
            rs = sorted(sel(runs, "dms", arm, delay=n), key=lambda r: r["seed"])
            line.append("N=%d[%s]" % (n, "/".join(f"{r['acc_frozen']*100:.1f}"
                                                  for r in rs)))
        print(f"    {arm:<15} " + "  ".join(line))

    print("\n  ONLINE eval (the online arms allowed to keep learning during the "
          "held-out trials — their nature, reported separately so it can never "
          "be confused with the frozen number):")
    for arm in ARM_ORDER:
        rs0 = sel(runs, "dms", arm, delay=delays[0])
        if not rs0 or rs0[0]["kind"] not in ("online", "hybrid"):
            continue
        cells = []
        for n in delays:
            rs = sel(runs, "dms", arm, delay=n)
            cells.append(f"{np.mean([r['acc_online'] for r in rs])*100:8.1f}"
                         if rs else "     -")
        print(f"    {arm:<15}" + "".join(f"{c:>9}" for c in cells))

    # ── RULE ──────────────────────────────────────────────────────────────
    print("\n" + "=" * 96)
    print("TASK 3 — RULE SWITCHING (logic / cognitive flexibility).  "
          "Wisconsin card sort, rule flips silently at criterion")
    print("=" * 96)
    print(f"  {'arm':<15}{'acc%':>8}{'ttc':>8}{'reached':>9}{'persev%':>9}"
          f"   per-seed acc%            ttc per block")
    print("  " + "-" * 94)
    rule_summary = {}
    for arm in ARM_ORDER:
        rs = sorted(sel(runs, "rule", arm), key=lambda r: r["seed"])
        if not rs:
            continue
        acc = [r["acc_online"] for r in rs]
        ttc = [r["ttc_mean_online"] for r in rs if r["ttc_mean_online"] is not None]
        rch = [r["ttc_reached_frac_online"] for r in rs
               if r.get("ttc_reached_frac_online") is not None]
        pv = [r["persev_rate_online"] for r in rs
              if r.get("persev_rate_online") is not None]
        blocks = np.mean([r["ttc_per_block_online"] for r in rs], axis=0) \
            if rs[0].get("ttc_per_block_online") else []
        print(f"  {arm:<15}{np.mean(acc)*100:8.1f}{np.mean(ttc):8.1f}"
              f"{np.mean(rch)*100:8.0f}%{(np.mean(pv)*100 if pv else float('nan')):9.1f}"
              f"   [{'/'.join(f'{a*100:.1f}' for a in acc)}]"
              + "   " + " ".join(f"{b:5.1f}" for b in blocks))
        rule_summary[arm] = {"acc": float(np.mean(acc)),
                             "ttc": float(np.mean(ttc)),
                             "persev": float(np.mean(pv)) if pv else None,
                             "reached": float(np.mean(rch)) if rch else None}
    print("\n  acc%   = fraction of all trials answered correctly (chance 33.3)")
    print("  ttc    = trials to criterion (8 correct in 10) after each silent "
          "switch; 60 = block timed out, never got there")
    print("  reached= fraction of blocks where criterion was actually reached")
    print("  persev%= of the errors that had a dead-rule answer available, how "
          "many played the DEAD rule's answer")

    print("\n  FROZEN eval for the online arms (learning switched OFF during the "
          "held-out episodes) — this separates 'learned a policy' from "
          "'adapts while playing':")
    for arm in ARM_ORDER:
        rs = sel(runs, "rule", arm)
        if not rs or rs[0]["kind"] not in ("online", "hybrid"):
            continue
        af = [r["acc_frozen"] for r in rs]
        ao = [r["acc_online"] for r in rs]
        print(f"    {arm:<15} frozen {np.mean(af)*100:5.1f}%   "
              f"online {np.mean(ao)*100:5.1f}%   "
              f"delta {(np.mean(ao)-np.mean(af))*100:+5.1f} pp")

    # ── PONG ──────────────────────────────────────────────────────────────
    print("\n" + "=" * 96)
    print("TASK 1 — PONG (sensorimotor).  score = hits - misses per 2,000 ticks "
          "vs a random opponent, held-out serves")
    print("=" * 96)
    print(f"  {'arm':<15}{'score':>9}   per-seed                     units")
    print("  " + "-" * 70)
    pong_summary = {}
    for arm in ARM_ORDER:
        rs = sorted(sel(runs, "pong", arm), key=lambda r: r["seed"])
        if not rs:
            continue
        sc = [r["score_frozen"] for r in rs]
        st = rs[0]["stats"]
        units = st.get("n_params") if "n_params" in st else st.get("n_states")
        if rs[0]["arm"].startswith("ERAN"):
            units = f"{rs[0]['stats_final'].get('n_prototypes')} prototypes"
        print(f"  {arm:<15}{np.mean(sc):+9.1f}   "
              f"[{'/'.join(f'{s:+.1f}' for s in sc)}]".ljust(28) + f" {units}")
        pong_summary[arm] = float(np.mean(sc))

    hp = os.path.join(HERE, "results", "HOUSE-PONG-2026-08-21.json")
    if os.path.exists(hp):
        with open(hp, encoding="utf-8") as f:
            house = json.load(f)
        print("\n  HOUSE RECORD — Iddo's existing pong-alma players, their OWN "
              "(unmatched) training budgets, this arena's eval contract:")
        for nm in ("GIST", "MULTI-WEIGHT", "BEIT-DIN"):
            if nm in house:
                print(f"    {nm:<15}{house[nm]['score_frozen']:+9.1f}   "
                      f"[{'/'.join(f'{s:+.1f}' for s in house[nm]['scores_frozen'])}]"
                      f"   {house[nm]['n_params']} params   "
                      f"({house[nm]['budget']})")

    # ── chemistry ablation ────────────────────────────────────────────────
    print("\n" + "=" * 96)
    print("THE CHEMISTRY ABLATION — does the neuromodulator vector earn its place?")
    print("  ERAN-CTX = chemistry FROZEN at baseline (plasticity() == 1.0).")
    print("  ERAN-CTX+CHEM = identical code with DA on reward-prediction-error "
          "and NE on change-point live. Nothing else differs.")
    print("=" * 96)
    for n in delays:
        a = sel(runs, "dms", "ERAN-CTX", delay=n)
        b = sel(runs, "dms", "ERAN-CTX+CHEM", delay=n)
        if a and b:
            ma = np.mean([r["acc_frozen"] for r in a])
            mb = np.mean([r["acc_frozen"] for r in b])
            print(f"  DMS  N={n:<3} ablated {ma*100:5.1f}%   chemistry "
                  f"{mb*100:5.1f}%   delta {(mb-ma)*100:+5.1f} pp"
                  f"   ({abs(mb-ma)*nE*len(seeds):.0f} trials of "
                  f"{nE*len(seeds)})")
    a = sel(runs, "rule", "ERAN-CTX")
    b = sel(runs, "rule", "ERAN-CTX+CHEM")
    if a and b:
        for k, lbl, pct in (("acc_online", "accuracy", True),
                            ("ttc_mean_online", "trials-to-criterion", False),
                            ("persev_rate_online", "perseverative rate", True)):
            va = [r[k] for r in a if r.get(k) is not None]
            vb = [r[k] for r in b if r.get(k) is not None]
            if va and vb:
                f = 100.0 if pct else 1.0
                print(f"  RULE {lbl:<22} ablated {np.mean(va)*f:7.2f}   "
                      f"chemistry {np.mean(vb)*f:7.2f}   "
                      f"delta {(np.mean(vb)-np.mean(va))*f:+7.2f}")
        ne = [r["stats_final"].get("ne_events", 0) for r in b]
        ne0 = [r["stats_final"].get("ne_events", 0) for r in a]
        print(f"  RULE NE spike events during the run: chemistry {ne}, "
              f"ablated {ne0} (ablated must be 0 — that is the ablation working)")
    ap = sel(runs, "pong", "ERAN-CTX")
    bp = sel(runs, "pong", "ERAN-CTX+CHEM")
    if ap and bp:
        print(f"  PONG score            ablated "
              f"{np.mean([r['score_frozen'] for r in ap]):+7.1f}   chemistry "
              f"{np.mean([r['score_frozen'] for r in bp]):+7.1f}")

    # ── machine-readable roll-up appended to the json ─────────────────────
    d["summary"] = {"dms": dms_summary, "rule": rule_summary,
                    "pong": pong_summary, "hold_bar": HOLD,
                    "one_trial_pp": one_trial_pp, "se_pp": se}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=1, ensure_ascii=False)
    print(f"\n[summary written back into {path}]")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main(sys.argv[1] if len(sys.argv) > 1
         else os.path.join(HERE, "results", "AGENTIC-ARENA-2026-08-21.json"))
