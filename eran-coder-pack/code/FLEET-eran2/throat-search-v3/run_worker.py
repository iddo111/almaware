# -*- coding: utf-8 -*-
"""run_worker.py -- one detached v3 search worker. Checkpointed, resumable,
honest. The PROVEN v1 machine with the organs swapped:

    mouth34 (34-tube, adult-ish, no nose)  ->  mouth2 (child KL tract +
                                               nasal branch + LF source,
                                               C twin, bit-parity 0.0)
    ears_extended/ears_v2 (192+8+gate)     ->  ear3 (996d: frozen 192 as
                                               block 0 -- THE GROWTH LAW --
                                               + level/cochleagram/pitch/
                                               modulation) + gates_v3
    targets.py (200d cache)                ->  targets_v3 (ear3-t06 cache,
                                               REUSED, spec-hash-guarded)

    python3 run_worker.py --arm ba-cv --seed 3 --out run/ba-cv-3 --hours 47

Judge: Ear v3 wdist to Iddo's real-clip centroids ONLY (never synthetic).
Search: CMA-ES + IPOP-lite restarts for guided arms; uniform random (same
space, same bookkeeping) for control arms. Renderer: mouth2 say_gesture,
C backend by default (parity 0.0 vs the numpy reference), reference
fallback only when the .so is genuinely absent.

REFUSES to start unless:
  * ORGANS.lock verifies (CORTEX-FREEZE LAW -- every organ hash matches),
  * the newest SANITY0-V3-*.json says ALL_OK true.

Files under --out, all small, all atomically replaced:
    heartbeat.jsonl   one line per generation (rotated at 4 MB)
    best.json         best-so-far: params, gesture, every distance, gates,
                      organ versions, 5-glottis-seed rescore, controls
    best.wav          what the best trajectory actually sounds like
    state.json        full resume state (CMA internals, rng, deadline)
Exit 99 = deadline reached (the supervisor stops relaunching on 99).

DISTANCE-SANITY (the splice lesson): any best whose wdist would qualify
as a WIN (<= 1.3x the unit's real-clip mean) is copied into review/ and
marked review_flagged -- for Iddo's ears, never auto-celebrated.

SACRED AUDIO LAW: writes wavs, never plays them. eran1 is never touched.
"""
from __future__ import annotations

import argparse
import datetime
import glob
import json
import os
import shutil
import sys
import tempfile
import time

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
for _p in (os.path.expanduser("~/ear-v3"), os.path.expanduser("~/mouth-v2")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import arms_v3 as arms                           # noqa: E402
import gates_v3                                  # noqa: E402
import organs_lock                               # noqa: E402
import targets_v3 as targets                     # noqa: E402
from cma import CMA                              # noqa: E402

import mouth2                                    # noqa: E402
from ear3 import features as EF                  # noqa: E402

IDENTITY_LAMBDA = 3.0      # measured on Iddo's 105 verdicts; ba only
PENALTY_REFUSED = 1.0e9
RESTART_STALL_GENS = 80
SIGMA_DEAD = 1e-9
COND_DEAD = 1e14
N_RESCORE_SEEDS = 5


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


def write_wav(path, samples, fs=16000):
    """float32 [-1,1] -> 16-bit PCM mono (legacy ears.write_wav convention)."""
    import wave
    y = np.clip(np.asarray(samples, dtype=np.float64), -1.0, 1.0)
    pcm = (y * 32767.0).astype("<i2").tobytes()
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(fs)
        w.writeframes(pcm)


def verdicted_tags(review_dir):
    """Tags Iddo has already ruled on. SO-04 will write verdicts.jsonl; until it exists
    this is empty and the pruner simply keeps the newest few."""
    p = os.path.join(os.path.dirname(os.path.abspath(review_dir)), "verdicts.jsonl")
    tags = set()
    try:
        with open(p) as f:
            for line in f:
                try:
                    t = json.loads(line).get("tag")
                except ValueError:
                    continue
                if t:
                    tags.add(t)
    except OSError:
        pass
    return tags


def prune_review(review_dir, arm, keep=3):
    """SO-13 2026-09-06: review/ is where a flagged would-be winner waits for a HUMAN ear,
    and nothing pruned it -- 1,536 files (25 MB) in v3 and 416 in v4, none of them triaged.
    A folder that keeps every candidate ever made keeps none a person will actually reach.

    Keeps the newest `keep` per arm. Everything older MOVES to review-archive/ -- never
    deleted, and every move gets a manifest line. Anything Iddo has ruled on stays, and
    LISTENED-*.txt is never touched (it is not <arm>-*.wav).
    """
    moved = 0
    try:
        wavs = sorted(glob.glob(os.path.join(review_dir, "%s-*.wav" % arm)),
                      key=os.path.getmtime, reverse=True)
        if len(wavs) <= keep:
            return 0
        spared = verdicted_tags(review_dir)
        arch = os.path.join(os.path.dirname(os.path.abspath(review_dir)), "review-archive")
        for wav in wavs[keep:]:
            tag = os.path.basename(wav)[:-4]
            if tag in spared:
                continue
            os.makedirs(arch, exist_ok=True)
            for ext in (".wav", ".json"):
                s = os.path.join(review_dir, tag + ext)
                if os.path.exists(s):
                    shutil.move(s, os.path.join(arch, tag + ext))
            with open(os.path.join(arch, "MANIFEST.jsonl"), "a") as f:
                f.write(json.dumps({"tag": tag, "arm": arm, "utc": utcnow(),
                                    "from": review_dir,
                                    "why": "kept the newest %d per arm" % keep}) + "\n")
            moved += 1
        if moved:
            print("[%s] review: archived %d older %s candidates, kept the newest %d "
                  "(moved to review-archive/, nothing deleted)"
                  % (utcnow(), moved, arm, keep), flush=True)
    except OSError as exc:                       # a full disk must not kill the search
        print("[%s] review: prune skipped (%s: %s)"
              % (utcnow(), type(exc).__name__, exc), flush=True)
    return moved

def newest_sanity():
    files = sorted(glob.glob(os.path.join(_HERE, "SANITY0-V3-*.json")))
    return files[-1] if files else None


class Scorer:
    def __init__(self, arm, all_stats, backend):
        self.arm = arm
        self.stats = all_stats[arm.unit]
        self.all_stats = all_stats
        # Identity guard, `ba` only (2026-08-27). wdist asks "how close to the
        # average ba"; it never asks "is this a ba at all". All 24 judged ba
        # candidates were nearer the `ma` target than their own -- ERAN was
        # nasalising, and the objective could not see it. MEASURED on Iddo's
        # 105 verdicts: L=3 lifts ba AUC(👍+🎯) 0.430 -> 0.555 and never fires
        # on ma. NOT applied to `ah` -- there it COSTS (0.939 -> 0.868), because
        # 3 of his ah thumbs-up are clips our ear itself calls `ma`. His ear
        # tolerates a nasal-tinted /a/; it does not tolerate a nasal /b/.
        self.identity_units = [u for u in all_stats if u != arm.unit
                               and u in targets.UNITS]
        self.identity_lambda = IDENTITY_LAMBDA if arm.unit == "ba" else 0.0
        self.backend = backend
        self.evals = 0

    def render_x(self, x, glottis_seed=0):
        g = self.arm.to_gesture(self.arm.clip(x))
        try:
            return mouth2.say_gesture(g, seed=glottis_seed,
                                      backend=self.backend)
        except (ValueError, FloatingPointError):
            return None

    def __call__(self, x):
        self.evals += 1
        xc = self.arm.clip(x)
        pen = float(np.sum(((x - xc) / (self.arm.hi - self.arm.lo)) ** 2))
        y = self.render_x(xc)
        if y is None:
            return PENALTY_REFUSED + pen
        v, aux = EF.features_with_aux(y)
        gs = gates_v3.gate_stats(aux, y)
        gate = gates_v3.penalty(self.arm.unit, gs)
        wd = targets.wdist(v, self.stats)
        return wd + 10.0 * pen + gate + self.identity_penalty(v, wd)

    def identity_penalty(self, v, wd):
        """Pay for every unit that this sound resembles more than its own."""
        if not self.identity_lambda:
            return 0.0
        rival = min(targets.wdist(v, self.all_stats[u])
                    for u in self.identity_units)
        return self.identity_lambda * max(0.0, wd - rival)

    def report(self, x, organs):
        """Everything an honest best.json needs about one candidate."""
        xc = self.arm.clip(x)
        y = self.render_x(xc)
        if y is None:
            return None, {"refused": True}
        v, aux = EF.features_with_aux(y)
        gs = gates_v3.gate_stats(aux, y)
        gate_ok, gate_detail = gates_v3.check(self.arm.unit, gs)
        wd = targets.wdist(v, self.stats)
        multi = []
        for gseed in range(N_RESCORE_SEEDS):
            yg = self.render_x(xc, glottis_seed=gseed)
            if yg is not None:
                multi.append(targets.wdist(EF.features(yg), self.stats))
        g = self.arm.to_gesture(xc)
        return y, {
            "wdist": wd,
            "gate_pass": bool(gate_ok),
            "gate_detail": {k: bool(b) for k, b in gate_detail.items()},
            "gate_stats": {k: (float(gs[k]) if not isinstance(gs[k], int)
                               else gs[k]) for k in gs},
            "review_flagged": bool(gates_v3.review_flag(wd, self.stats)),
            "real_wdist_mean": self.stats["real_wdist_mean"],
            "real_wdist_min": self.stats["real_wdist_min"],
            "real_wdist_max": self.stats["real_wdist_max"],
            "win_bar_1p3x_mean": 1.3 * self.stats["real_wdist_mean"],
            "multi_glottis_seed": {"n": len(multi),
                                   "mean": float(np.mean(multi)) if multi else None,
                                   "sd": float(np.std(multi)) if multi else None},
            "nearest": targets.nearest_table(v, self.all_stats),
            "gesture": {
                "keyframes": [[round(float(k), 5) for k in kf]
                              for kf in g["keyframes"]],
                "durations": [round(float(d), 4) for d in g["durations"]],
                "f0_knots": [round(float(f), 2) for f in g["f0_knots"]],
                "glide": g.get("glide", 0.35),
                # 2026-08-28: RECORD WHAT YOU CHANGE. The burst dials went live
                # and were omitted here, so the only way to see what the search
                # had chosen was to ssh each box and read state.json by hand.
                # None for every unit that does not use them -- ma, ah, ih.
                "burst": g.get("burst")},
            "organs": organs,
        }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", required=True, choices=arms.ALL)
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--hours", type=float, default=47.0)
    ap.add_argument("--checkpoint-min", type=float, default=10.0)
    a = ap.parse_args()

    # -------------------------------------------------- refuse-first gates
    lock, backend = organs_lock.verify()          # CORTEX-FREEZE LAW
    sp = newest_sanity()
    if sp is None:
        raise SystemExit("REFUSING: run sanity0_v3.py first "
                         "(no SANITY0-V3-*.json)")
    with open(sp, encoding="utf-8") as f:
        sanity = json.load(f)
    if not sanity.get("ALL_OK"):
        raise SystemExit("REFUSING: %s has ALL_OK=false -- fix the failure, "
                         "rerun sanity0_v3.py" % os.path.basename(sp))

    import socket
    organs = {
        "ear3_spec_hash": lock["ear3"]["spec_hash"],
        "carfac_sha": lock["ear3"]["carfac_sha"],
        "patch_id": lock["ear3"]["patch_id"],
        "cortex": lock["cortex"],
        "mouth2_sha256": lock["mouth2"]["mouth2.py"],
        "libvoc_sha256": lock["libvoc_sha256"].get(socket.gethostname()),
        "geometry": lock["geometry"],
        "backend": backend,
        "sanity_file": os.path.basename(sp),
    }

    os.makedirs(a.out, exist_ok=True)
    hb_path = os.path.join(a.out, "heartbeat.jsonl")
    state_path = os.path.join(a.out, "state.json")
    best_path = os.path.join(a.out, "best.json")
    review_dir = os.path.join(_HERE, "review")

    arm = arms.get(a.arm)
    all_stats = targets.load_all()                # refuses on spec mismatch
    sc = Scorer(arm, all_stats, backend)

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
              % (utcnow(), a.arm, a.seed, sc.evals, best_f, restarts),
              flush=True)
    else:
        deadline = time.time() + a.hours * 3600.0
        best_f, best_x = float("inf"), None
        restarts, stall = 0, 0
        restart_best = float("inf")
        rs_rng = np.random.default_rng(10_000 + a.seed)
        es = (CMA(arm.x0(a.seed), 0.25 * float(np.mean(arm.hi - arm.lo)),
                  seed=a.seed) if arm.guided else None)
        print("[%s] START %s-%d dim=%d unit=%s guided=%s backend=%s "
              "ear3=%s..." % (utcnow(), a.arm, a.seed, arm.dim, arm.unit,
                              arm.guided, backend,
                              organs["ear3_spec_hash"][:12]), flush=True)

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
        y, rep = sc.report(best_x, organs)
        rep.update({"arm": a.arm, "seed": a.seed, "unit": arm.unit,
                    "guided": arm.guided, "evals": sc.evals,
                    "restarts": restarts, "utc": utcnow(),
                    "best_f_with_penalty": best_f,
                    "x": [float(v) for v in best_x]})
        atomic_json(best_path, rep)
        if y is not None:
            write_wav(os.path.join(a.out, "best.wav"), y)
            if rep.get("review_flagged"):
                # the splice lesson: would-be winners go to HUMAN review
                os.makedirs(review_dir, exist_ok=True)
                tag = "%s-%d-%s" % (a.arm, a.seed,
                                    utcnow().replace(":", ""))
                shutil.copy2(os.path.join(a.out, "best.wav"),
                             os.path.join(review_dir, tag + ".wav"))
                atomic_json(os.path.join(review_dir, tag + ".json"), rep)
                print("[%s] REVIEW-FLAGGED %s wdist=%.3f <= 1.3x real mean "
                      "%.3f -- copied to review/, NOT a win until Iddo "
                      "listens" % (utcnow(), tag, rep["wdist"],
                                   rep["real_wdist_mean"]), flush=True)
                prune_review(review_dir, a.arm)          # SO-13: keep the ear reachable

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
