# -*- coding: utf-8 -*-
"""house_pong.py — the HOUSE RECORD on Pong, on the arena's own eval contract.

> BROKEN WINDOWS LAW: test the REAL output, never a proxy.

Iddo already has three Pong brains in D:\\CLAUDE\\pong-alma — GIST,
MULTI-WEIGHT and BEIT-DIN — trained by their own ES scripts and previously
ranked in `results/arena-20260820-eran4.json`. They belong in this arena as the
house record, but their training budgets are THEIR OWN and are NOT matched to
the agentic arena's budget. That is stated on the line, not buried: these are a
reference mark, not a matched arm.

What IS matched: the evaluation. Same held-out seeds (7,000,000+), same 5
episodes of 2,000 ticks, same random opponent (seed 9999), same score
convention (+1 per hit, -1 per miss).
"""
import json
import os
import random
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import es as ES                                     # noqa: E402
from tasks import PongTask, RandomOpp               # noqa: E402
import player_gist as pg                            # noqa: E402
import player_multiweight as pm                     # noqa: E402
import player_beitdin as pb                         # noqa: E402

EVAL_LO = 7_000_000
EPISODES = 5
TICKS = 2000


class HouseWrap:
    """The house players read the RAW 5-dim pong obs and return -1/0/+1.
    The arena hands out a 9-dim obs (raw | prev action | prev reward) and wants
    0/1/2. This wrapper is the only thing between them — no behaviour change."""
    online = False

    def __init__(self, inner):
        self.inner = inner

    def reset_episode(self):
        pass

    def act(self, obs):
        return int(self.inner.act(tuple(obs[:5]))) + 1

    def learn(self, r, done=False):
        pass

    def stats(self):
        return {}


def evaluate(ctrl):
    fac = lambda: PongTask(ticks=TICKS, opponent=RandomOpp(9999))   # noqa: E731
    scores = []
    for i in range(EPISODES):
        tot, _, _, _ = ES.rollout(ctrl, fac, EVAL_LO + i, learn=False)
        scores.append(float(tot))
    return float(np.mean(scores)), scores


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    random.seed(42)
    out = {}

    t0 = time.time()
    print("[house] GIST ...", flush=True)
    gp, g0, g1 = pg.train(generations=60, pop=10, episodes=14, seed=1, quiet=True)
    out["GIST"] = dict(n_params=int(pg.PARAM_COUNT), native_birth=g0, native_end=g1,
                       budget="own: 60 gen x pop 10 x 14 eps (NOT matched)")

    print("[house] MULTI-WEIGHT ...", flush=True)
    mp_, m0, m1 = pm.train(generations=200, pop=10, episodes=14, seed=1, quiet=True)
    out["MULTI-WEIGHT"] = dict(n_params=int(pm.PARAM_COUNT), native_birth=m0,
                               native_end=m1,
                               budget="own: 200 gen x pop 10 x 14 eps (NOT matched)")

    print("[house] BEIT-DIN ...", flush=True)
    bt, bh, bbase = pb.train(generations=30, npairs=12, seed=42, verbose=False)
    out["BEIT-DIN"] = dict(n_params=int(pb.N_PARAMS), native_birth=bh[0],
                           native_end=bh[-1],
                           budget="own: 30 gen x 12 pairs (NOT matched)")

    ctrls = {"GIST": HouseWrap(pg.GistPlayer(gp)),
             "MULTI-WEIGHT": HouseWrap(pm.MultiWeightPlayer(mp_)),
             "BEIT-DIN": HouseWrap(pb.BeitDinController(bt))}
    for nm, c in ctrls.items():
        mean, scores = evaluate(c)
        out[nm]["score_frozen"] = mean
        out[nm]["scores_frozen"] = [round(s, 1) for s in scores]
        print(f"  {nm:<14} arena-eval score = {mean:+.1f}   {scores}", flush=True)

    out["_meta"] = {"eval_seed_lo": EVAL_LO, "episodes": EPISODES,
                    "ticks": TICKS, "opponent": "random seed 9999",
                    "wall_s": round(time.time() - t0, 1),
                    "note": "house budgets are their own, NOT matched to the "
                            "agentic arena. Reference mark only."}
    path = os.path.join(HERE, "results", "HOUSE-PONG-2026-08-21.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    print("wrote", path)


if __name__ == "__main__":
    main()
