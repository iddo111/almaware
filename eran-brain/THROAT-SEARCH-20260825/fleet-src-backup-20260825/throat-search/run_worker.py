# -*- coding: utf-8 -*-
"""run_worker.py -- one detached search worker. Checkpointed, resumable, honest.

    python3 run_worker.py --arm abba --seed 3 --out run/abba-3 --hours 47

Judge: the EXTENDED ear (frozen 192 untouched + 8-energy contour), targets from
Iddo's real t06 recordings only. Search: CMA-ES with IPOP-lite restarts for the
guided arms; uniform random search (same space, same bookkeeping) for the
control arms. Renderer: the verified fast say_sequence -- ONLY if
FASTSEQ-VERDICT.json says the equality test passed; otherwise the verbatim
reference loop. Refuses to start before sanity0.py has written its verdicts.

Files under --out, all small, all atomically replaced:
    heartbeat.jsonl   one line per generation (rotated at 4 MB)
    best.json         best-so-far: params, keyframes, every distance, controls
    best.wav          what the best trajectory actually sounds like
    state.json        full resume state (CMA internals, rng, deadline)
Exit 99 = deadline reached (the supervisor stops relaunching on 99).

SACRED AUDIO LAW: writes wavs, never plays them. eran1 is never touched.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
import tempfile
import time

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import arms                                      # noqa: E402
import fastseq                                   # noqa: E402
import mouth34                                   # noqa: E402
import targets                                   # noqa: E402
from cma import CMA                              # noqa: E402
from ears import write_wav                       # noqa: E402
from ears_extended import ExtendedEars           # noqa: E402
# Ear v2 (2026-08-25): frozen 192 + contour + a STRUCTURAL GATE. v1's contour
# weighed 13.9% and CMA traded it away — the winning "abba" was silence + one
# flat buzz (Iddo's ear: crap). The gate is a fixed +50 no timbre can buy back.
from ears_v2 import EarsV2                       # noqa: E402

PENALTY_REFUSED = 1.0e9
RESTART_STALL_GENS = 80
SIGMA_DEAD = 1e-9
COND_DEAD = 1e14


def utcnow():
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def atomic_json(path, obj):
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path) or ".", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(obj, f)
    os.replace(tmp, path)


def rotate(path, max_bytes=4_000_000, keep=2000):
    try:
        if os.path.exists(path) and os.path.getsize(path) > max_bytes:
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()[-keep:]
            fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.writelines(lines)
            os.replace(tmp, path)
    except OSError:
        pass


class Scorer:
    def __init__(self, arm, ext, all_stats, renderer):
        self.arm = arm
        self.ext = ext
        self.stats = all_stats[arm.unit]
        self.all_stats = all_stats
        self.render = renderer
        self.evals = 0

    def render_x(self, x, glottis_seed=0):
        return self.render(self.arm.to_keyframes(self.arm.clip(x)),
                           f0=arms.F0, seed=glottis_seed)

    def __call__(self, x):
        self.evals += 1
        xc = self.arm.clip(x)
        pen = float(np.sum(((x - xc) / (self.arm.hi - self.arm.lo)) ** 2))
        y = self.render(self.arm.to_keyframes(xc), f0=arms.F0, seed=0)
        if y is None:
            return PENALTY_REFUSED + pen
        if hasattr(self.ext, "utterance_with_rms"):
            v, rms = self.ext.utterance_with_rms(y)
            gate = self.ext.gated_penalty(self.arm.unit, rms)
        else:
            v = self.ext.utterance_from_samples(y)
            gate = 0.0
        return targets.wdist(v, self.stats) + 10.0 * pen + gate

    def report(self, x):
        """Everything an honest best.json needs about one candidate."""
        xc = self.arm.clip(x)
        y = self.render(self.arm.to_keyframes(xc), f0=arms.F0, seed=0)
        if y is None:
            return None, {"refused": True}
        v = self.ext.utterance_from_samples(y)
        multi = []
        for gs in range(5):
            yg = self.render(self.arm.to_keyframes(xc), f0=arms.F0, seed=gs)
            if yg is not None:
                multi.append(targets.wdist(
                    self.ext.utterance_from_samples(yg), self.stats))
        kfs = [{"areas": [round(float(a), 5) for a in kf],
                "seconds": round(float(s), 4)}
               for kf, s in self.arm.to_keyframes(xc)]
        gate_pass = None
        if hasattr(self.ext, "utterance_with_rms"):
            _, _rms = self.ext.utterance_with_rms(y)
            gate_pass = self.ext.gated_penalty(self.arm.unit, _rms) == 0.0
        return y, {
            "wdist": targets.wdist(v, self.stats),
            "structure_gate_pass": gate_pass,
            "plain192_vs_%s" % self.arm.unit: targets.plain192(v, self.stats),
            "real_wdist_mean": self.stats["real_wdist_mean"],
            "real_wdist_min": self.stats["real_wdist_min"],
            "real_plain192_mean": self.stats["real_plain192_mean"],
            "multi_glottis_seed": {"n": len(multi),
                                   "mean": float(np.mean(multi)) if multi else None,
                                   "sd": float(np.std(multi)) if multi else None},
            "nearest": targets.nearest_table(v, self.all_stats),
            "keyframes": kfs,
        }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", required=True, choices=arms.ALL)
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--hours", type=float, default=47.0)
    ap.add_argument("--checkpoint-min", type=float, default=10.0)
    a = ap.parse_args()

    verdict_path = os.path.join(_HERE, "FASTSEQ-VERDICT.json")
    if not os.path.exists(verdict_path):
        raise SystemExit("REFUSING: run sanity0.py first (no FASTSEQ-VERDICT.json)")
    with open(verdict_path) as f:
        verdict = json.load(f)
    # The fast path must be BOTH proven equal AND actually faster. Measured on
    # eran2 2026-08-25: equal to 9e-13, but SLOWER (58 vs 36 ms/eval) — scipy's
    # per-call overhead loses at 17-sample blocks. The verbatim loop is the
    # truth anyway; speed that is not real is not speed.
    renderer = (fastseq.say_sequence_fast
                if verdict.get("ok") and verdict.get("speedup", 0) > 1.0
                else mouth34.say_sequence)

    os.makedirs(a.out, exist_ok=True)
    hb_path = os.path.join(a.out, "heartbeat.jsonl")
    state_path = os.path.join(a.out, "state.json")
    best_path = os.path.join(a.out, "best.json")

    arm = arms.get(a.arm)
    ext = EarsV2()
    all_stats = targets.load_all(ext, verbose=True)
    sc = Scorer(arm, ext, all_stats, renderer)

    # ------------------------------------------------------------ resume/start
    state = None
    if os.path.exists(state_path):
        try:
            with open(state_path) as f:
                state = json.load(f)
        except (ValueError, OSError):
            state = None
    if state is not None:
        deadline = float(state["deadline_epoch"])
        best_f = float(state["best_f"])
        best_x = np.asarray(state["best_x"], dtype=float)
        sc.evals = int(state["evals"])
        restarts = int(state["restarts"])
        rs_rng = np.random.default_rng()
        rs_rng.bit_generator.state = state["restart_rng"]
        es = CMA.restore(state["cma"], seed=a.seed) if arm.guided else None
        stall = int(state.get("stall", 0))
        restart_best = float(state.get("restart_best", best_f))
        print("[%s] RESUMED %s-%d at evals=%d best=%.4f restarts=%d"
              % (utcnow(), a.arm, a.seed, sc.evals, best_f, restarts), flush=True)
    else:
        deadline = time.time() + a.hours * 3600.0
        best_f, best_x = float("inf"), None
        restarts, stall = 0, 0
        restart_best = float("inf")
        rs_rng = np.random.default_rng(10_000 + a.seed)
        es = (CMA(arm.x0(a.seed), 0.25 * float(np.mean(arm.hi - arm.lo)),
                  seed=a.seed) if arm.guided else None)
        print("[%s] START %s-%d dim=%d unit=%s guided=%s renderer=%s"
              % (utcnow(), a.arm, a.seed, arm.dim, arm.unit, arm.guided,
                 "fast" if renderer is fastseq.say_sequence_fast else
                 "reference"), flush=True)

    def save_state():
        atomic_json(state_path, {
            "deadline_epoch": deadline, "best_f": best_f,
            "best_x": (best_x.tolist() if best_x is not None else None),
            "evals": sc.evals, "restarts": restarts, "stall": stall,
            "restart_best": restart_best,
            "restart_rng": rs_rng.bit_generator.state,
            "cma": (es.state() if es is not None else None),
            "utc": utcnow()})

    def save_best():
        if best_x is None:
            return
        y, rep = sc.report(best_x)
        rep.update({"arm": a.arm, "seed": a.seed, "unit": arm.unit,
                    "guided": arm.guided, "evals": sc.evals,
                    "restarts": restarts, "utc": utcnow(),
                    "best_f_with_penalty": best_f,
                    "x": [float(v) for v in best_x]})
        atomic_json(best_path, rep)
        if y is not None:
            write_wav(os.path.join(a.out, "best.wav"), y)

    last_ckpt = time.time()
    last_hb_evals, last_hb_t = sc.evals, time.time()
    improved_since_ckpt = False

    while time.time() < deadline:
        if arm.guided:
            xs = es.ask()
            fs = np.array([sc(x) for x in xs])
            es.tell(xs, fs)
            gen_best_i = int(np.argmin(fs))
            cur = float(fs[gen_best_i])
            if cur < best_f:
                best_f, best_x = cur, np.array(xs[gen_best_i])
                improved_since_ckpt = True
            if cur < restart_best - 1e-6:
                restart_best, stall = cur, 0
            else:
                stall += 1
            if (stall > RESTART_STALL_GENS or es.sigma < SIGMA_DEAD
                    or es.condition > COND_DEAD):
                restarts += 1
                pop = min(4 * (4 + int(3 * np.log(arm.dim))),
                          int(es.lam * 1.5))
                es = CMA(rs_rng.uniform(arm.lo, arm.hi),
                         0.25 * float(np.mean(arm.hi - arm.lo)),
                         seed=a.seed * 1000 + restarts, popsize=pop)
                stall, restart_best = 0, float("inf")
            gen, sig = es.gen, es.sigma
        else:                                     # control: uniform random search
            xs = rs_rng.uniform(arm.lo, arm.hi, (16, arm.dim))
            fs = np.array([sc(x) for x in xs])
            i = int(np.argmin(fs))
            if float(fs[i]) < best_f:
                best_f, best_x = float(fs[i]), np.array(xs[i])
                improved_since_ckpt = True
            gen, sig = sc.evals // 16, 0.0

        now = time.time()
        eps = (sc.evals - last_hb_evals) / max(now - last_hb_t, 1e-9)
        last_hb_evals, last_hb_t = sc.evals, now
        with open(hb_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"utc": utcnow(), "gen": gen,
                                "evals": sc.evals, "best": round(best_f, 4),
                                "cur": round(float(np.min(fs)), 4),
                                "sigma": round(float(sig), 5),
                                "restarts": restarts,
                                "eps": round(eps, 2)}) + "\n")

        if now - last_ckpt > a.checkpoint_min * 60.0:
            rotate(hb_path)
            save_state()
            if improved_since_ckpt:
                save_best()
                improved_since_ckpt = False
            last_ckpt = now

    save_state()
    save_best()
    print("[%s] DEADLINE reached: %s-%d evals=%d best=%.4f"
          % (utcnow(), a.arm, a.seed, sc.evals, best_f), flush=True)
    sys.exit(99)


if __name__ == "__main__":
    main()
