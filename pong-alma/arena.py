# -*- coding: utf-8 -*-
"""
ARENA — train all three ALMA Pong primitives, then a ROUND-ROBIN of
head-to-head Pong matches between their LEARNED controllers.
=====================================================================
100% ours. Pure Python 3 stdlib. Deterministic (seeded).

Three primitives (each a different "brain shape", each LEARNED by ES —
no hand-scripted ball tracking anywhere; we read the learned params and
let them fight):

  * BEIT-DIN     — 3 dayan/judge neurons, gist-gate + multi-channel edges
                   + LIF chambers, majority quorum ruling.   (player_beitdin)
  * GIST         — context -> gist-retrieval library, score==weight.
                   (player_gist)
  * MULTI-WEIGHT — obs->hidden->act MLP whose every edge is a 3-channel
                   amp/phase/gate bundle.                    (player_multiweight)

UNIFIED MATCH PROTOCOL (fair for all three):
  Any controller with .act(obs) plays LEFT; another plays RIGHT.
  The env is egocentric+mirrored, so RIGHT sees its own world through obsR.
  We serve, rally, and on a MISS the missing side loses a point; server
  re-serves. Score for a player = (its hits) - (its misses) over N ticks.
  A "match" is symmetric: we play A-as-LEFT-vs-B and B-as-LEFT-vs-A and
  sum, so neither side gets a court-advantage.

We ALSO measure every player vs a RANDOM baseline opponent, and report
each player's fitness at BIRTH (random newborn params) vs END (after its
own ES training) so learning is provable, not asserted.

Run:  python -s arena.py
"""
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pong_env import PongEnv
import player_beitdin as pb
import player_gist as pg
import player_multiweight as pm


# ── LOCKED SEED ────────────────────────────────────────────────────────
# One master seed pins the whole arena. Every per-component training seed
# and the held-out evaluation seeds are frozen so two runs are byte-for-byte
# identical (verified). Seeding the GLOBAL random module here also pins any
# accidental unseeded random.* call anywhere in the pipeline.
MASTER_SEED = 42
EVAL_SEEDS = (7001, 7002, 7003, 7004, 7005)   # held-out from every training run


def lock_seed(seed=MASTER_SEED):
    """Pin global RNG state for full reproducibility. Per-component trainers
    still build their own random.Random(...) with fixed seeds; this is the
    belt-and-suspenders global lock."""
    random.seed(seed)


# ── a random controller (baseline opponent / baseline player) ──────────
class RandomController:
    name = "RANDOM"

    def __init__(self, seed=0):
        self.rng = random.Random(seed)

    def act(self, obs):
        return self.rng.choice((-1, 0, 1))


# ── unified head-to-head: LEFT ctrl vs RIGHT ctrl ──────────────────────
def play_match(left, right, seeds, ticks_per_serve=2000):
    """Both controllers expose .act(obs). LEFT plays obsL, RIGHT plays obsR.
    Returns (left_score, right_score) = (hits - misses) summed over seeds.
    Server re-serves after every point so a rally-ending miss doesn't stop
    the whole match."""
    lscore = 0.0
    rscore = 0.0
    for sd in seeds:
        env = PongEnv(seed=sd)
        obsL, obsR = env.reset()
        for _ in range(ticks_per_serve):
            aL = left.act(obsL)
            aR = right.act(obsR)
            (obsL, obsR), rL, rR, done = env.step(aL, aR)
            lscore += rL          # +1 hit / -1 miss for LEFT
            rscore += rR          # +1 hit / -1 miss for RIGHT
            if done:
                obsL, obsR = env.reset()
    return lscore, rscore


def symmetric_duel(ctrlA, ctrlB, seeds, ticks_per_serve=2000):
    """Play A-left-vs-B-right AND B-left-vs-A-right; combine so the court
    side gives no advantage. Returns (scoreA, scoreB)."""
    aL, bR = play_match(ctrlA, ctrlB, seeds, ticks_per_serve)
    bL, aR = play_match(ctrlB, ctrlA, seeds, ticks_per_serve)
    return aL + aR, bL + bR


def vs_random(ctrl, seeds, ticks_per_serve=2000, opp_seed=9999):
    """Fitness of ctrl (as LEFT) against a fresh random RIGHT player.
    Same reward convention: hits - misses, per seed averaged."""
    opp = RandomController(seed=opp_seed)
    lscore, _ = play_match(ctrl, opp, seeds, ticks_per_serve)
    return lscore / len(seeds)


# ── build the three LEARNED controllers (read their learned params) ────
def train_all(verbose=True):
    """Run each primitive's OWN ES training, capture birth->end fitness on
    the primitive's native metric, and return LEARNED controllers plus the
    random-newborn controllers for an honest before/after."""
    report = {}

    # -- BEIT-DIN --------------------------------------------------------
    if verbose:
        print("[train] BEIT-DIN (3 judges, quorum) ...")
    # capture its random-newborn params to build the 'birth' controller
    rng_b = random.Random(42)
    birth_theta = [rng_b.gauss(0.0, 0.5) for _ in range(pb.N_PARAMS)]
    beit_theta, beit_hist, beit_base = pb.train(generations=30, npairs=12,
                                                seed=42, verbose=False)
    beit_learned = pb.BeitDinController(beit_theta)
    beit_birth = pb.BeitDinController(birth_theta)
    report["beitdin"] = dict(birth_native=beit_hist[0], end_native=beit_hist[-1],
                             native_base=beit_base)

    # -- GIST ------------------------------------------------------------
    if verbose:
        print("[train] GIST (context->gist retrieval) ...")
    rng_g = random.Random(1)
    gist_birth_p = [rng_g.gauss(0.0, 0.5) for _ in range(pg.PARAM_COUNT)]
    gist_p, gist_fit0, gist_fit1 = pg.train(generations=60, pop=10,
                                            episodes=14, seed=1, quiet=True)
    gist_learned = pg.GistPlayer(gist_p)
    gist_birth = pg.GistPlayer(gist_birth_p)
    report["gist"] = dict(birth_native=gist_fit0, end_native=gist_fit1)

    # -- MULTI-WEIGHT ----------------------------------------------------
    if verbose:
        print("[train] MULTI-WEIGHT (amp/phase/gate edges) ...")
    rng_m = random.Random(1)
    mw_birth_p = [rng_m.gauss(0.0, 0.5) for _ in range(pm.PARAM_COUNT)]
    mw_p, mw_fit0, mw_fit1 = pm.train(generations=200, pop=10, episodes=14,
                                      seed=1, quiet=True)
    mw_learned = pm.MultiWeightPlayer(mw_p)
    mw_birth = pm.MultiWeightPlayer(mw_birth_p)
    report["multiweight"] = dict(birth_native=mw_fit0, end_native=mw_fit1)

    learned = {"BEIT-DIN": beit_learned, "GIST": gist_learned,
               "MULTI-WEIGHT": mw_learned}
    birth = {"BEIT-DIN": beit_birth, "GIST": gist_birth,
             "MULTI-WEIGHT": mw_birth}
    # tag names for pretty printing
    for nm, c in learned.items():
        c.name = nm
    for nm, c in birth.items():
        c.name = nm
    return learned, birth, report


# ── main ───────────────────────────────────────────────────────────────
def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    lock_seed(MASTER_SEED)   # reproducibility lock — pin global RNG state

    print("=" * 70)
    print("ALMA PONG ARENA — train 3 primitives, round-robin their LEARNED brains")
    print("=" * 70)
    print(f"[seed] locked MASTER_SEED={MASTER_SEED} (reproducible run)")

    learned, birth, report = train_all(verbose=True)

    # common, fixed evaluation seeds (held-out from every training run)
    eval_seeds = EVAL_SEEDS

    # ── 1) each player vs random baseline: birth vs end ────────────────
    print("\n" + "-" * 70)
    print("FITNESS vs RANDOM BASELINE  (LEFT ctrl vs random RIGHT; hits-misses/seed)")
    print("-" * 70)
    baseline_ctrl = RandomController(seed=123)
    rand_fit = vs_random(baseline_ctrl, eval_seeds, opp_seed=9999)
    print(f"  {'RANDOM (control)':<16}: {rand_fit:+7.2f}")
    vs_rand = {}
    birth_vs_rand = {}
    for nm in ("BEIT-DIN", "GIST", "MULTI-WEIGHT"):
        b = vs_random(birth[nm], eval_seeds, opp_seed=9999)
        e = vs_random(learned[nm], eval_seeds, opp_seed=9999)
        birth_vs_rand[nm] = b
        vs_rand[nm] = e
        gain = e - b
        beat = "BEATS random" if e > rand_fit + 1.0 else "~random"
        print(f"  {nm:<16}: birth {b:+7.2f}  ->  end {e:+7.2f}   "
              f"(gain {gain:+.2f}, {beat})")

    # ── 2) ROUND ROBIN between the three LEARNED brains ────────────────
    print("\n" + "-" * 70)
    print("ROUND ROBIN  (symmetric duels; each pair plays both sides)")
    print("-" * 70)
    names = ["BEIT-DIN", "GIST", "MULTI-WEIGHT"]
    points = {n: 0 for n in names}       # match points: win=3 draw=1 loss=0
    net = {n: 0.0 for n in names}        # aggregate score differential
    duel_lines = []
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = names[i], names[j]
            sa, sb = symmetric_duel(learned[a], learned[b], eval_seeds)
            net[a] += sa - sb
            net[b] += sb - sa
            if sa > sb:
                points[a] += 3
                res = f"{a} WINS"
            elif sb > sa:
                points[b] += 3
                res = f"{b} WINS"
            else:
                points[a] += 1
                points[b] += 1
                res = "DRAW"
            line = f"  {a:<12} {sa:+7.1f}   vs   {sb:+7.1f} {b:<12}  -> {res}"
            print(line)
            duel_lines.append((a, b, sa, sb, res))

    # ── 3) STANDINGS ───────────────────────────────────────────────────
    print("\n" + "-" * 70)
    print("STANDINGS  (match pts, then net score differential)")
    print("-" * 70)
    order = sorted(names, key=lambda n: (points[n], net[n]), reverse=True)
    standings = []
    for rank, n in enumerate(order, 1):
        line = (f"  {rank}. {n:<14} pts={points[n]:<2}  "
                f"net={net[n]:+8.1f}  vsRandom(end)={vs_rand[n]:+.2f}")
        print(line)
        standings.append(dict(rank=rank, name=n, pts=points[n],
                              net=round(net[n], 1),
                              vs_random_end=round(vs_rand[n], 2),
                              vs_random_birth=round(birth_vs_rand[n], 2)))

    champ = order[0]
    print("\n" + "=" * 70)
    print(f"CHAMPION: {champ}")
    print("=" * 70)

    # machine-readable dump for the harness
    print("\n[RESULT-JSON]")
    import json
    out = dict(random_baseline=round(rand_fit, 2),
               vs_random_birth={k: round(v, 2) for k, v in birth_vs_rand.items()},
               vs_random_end={k: round(v, 2) for k, v in vs_rand.items()},
               native=report,
               duels=[dict(a=a, b=b, sa=round(sa, 1), sb=round(sb, 1), res=r)
                      for (a, b, sa, sb, r) in duel_lines],
               standings=standings, champion=champ)
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
