# -*- coding: utf-8 -*-
"""sanity0_v3.py -- STAGE 0 for the v3 campaign: nothing long-running
launches until this passes (plan Phase 3 §pre-launch).

  A  CMA-ES on a 31-d sphere reaches < 1e-6      (the optimizer works)
  B  mouth2 C backend: deterministic (bit-identical twice) AND parity
     vs the numpy reference on a random Stage-A gesture (must be 0.0,
     the eran2 battery standard -- any nonzero is REPORTED, not hidden)
  C  ORGANS.lock verifies on this box            (CORTEX-FREEZE LAW)
  D  LOO through Ear v3: REUSE the stored EAR3-ACCEPT numbers (0.695
     six-way LOO >= 0.687 bar); re-assert live spec_hash == accept ==
     targets cache. The 600-clip LOO is NOT recomputed here -- the ear
     is frozen, its acceptance stands, this asserts nothing drifted.
  E  real-clip bars written from the ear3 cache (the new "13.9")
  F  gate calibration: >=95% joint real pass per unit (from
     ear3-calib.json, computed on Iddo's real takes) AND 6/6 archived
     v1 cheat wavs FAIL the campaign criterion (regression/v1cheat/)
  G  NASAL AUDIBILITY -- the whole reason for the nose, MEASURED:
     the same /ma/ gesture with velum OPEN vs velum SEALED must
     separate in Ear v3 in the ma-vs-ba direction, beyond 5-seed noise
  H  closure visibility: /ah/ hold vs /a-seal-burst-a/ must separate
     in the abba-vs-ah direction AND the closure must raise the dip
     statistic (what G1 gates on)
  I  measured evals/s, single core pinned (informational, printed into
     the worker-math table; plan expects ~9-13 with the 72 ms ear)

Writes SANITY0-V3-<utc>.json next to this file; run_worker.py refuses
to start unless the newest one says ALL_OK true. Honest by
construction: every expected number is printed beside the measured one.
"""
from __future__ import annotations

import os

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

import datetime                                   # noqa: E402
import glob                                       # noqa: E402
import json                                       # noqa: E402
import sys                                        # noqa: E402
import time                                       # noqa: E402

import numpy as np                                # noqa: E402

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
for _p in (os.path.expanduser("~/ear-v3"), os.path.expanduser("~/mouth-v2")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import arms_v3 as arms                            # noqa: E402
import gates_v3                                   # noqa: E402
import organs_lock                                # noqa: E402
import targets_v3 as targets                      # noqa: E402
from cma import CMA                               # noqa: E402

import mouth2                                     # noqa: E402
from ear3 import features as EF                   # noqa: E402

EAR_DIR = os.path.expanduser("~/ear-v3")

# MIKO-style memory check (plan §MIKO): the scars that touch Phase 3.
MEMORY_CHECK = (
    "v1-abba-cheat: a weighted dim can be traded, a gate cannot -> "
    "GATE_PENALTY 50 + regression/v1cheat permanent negatives. "
    "splice-fake passed all gates -> distance-sanity review folder, "
    "never auto-celebrate. session-leak: dev split leaked sessions -> "
    "LOO protocol only, targets recomputed only at stage boundaries. "
    "synthetic corpus dead (6.1% ~ chance) -> Iddo's real takes only. "
    "Iddo's real f0 falls through 60-80 Hz and he called 220 Hz flat "
    "'too high' -> F0_LO/F0_HI are constants awaiting his listen. "
    "ear speed 72 ms > 25 ms plan bar -> ~9-13 evals/s/worker until "
    "the C++ cochlea port. eran3 disk 84% -> run-state only there.")


def utc():
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y%m%dT%H%M%SZ")


def main():
    import socket
    out = {"utc": utc(), "host": socket.gethostname(),
           "memory_check": MEMORY_CHECK}
    ok_all = True

    # ------------------------------------------------------------------ A
    print("=== A. CMA-ES sphere sanity (31-d) ===")
    es = CMA(np.full(31, 3.0), 1.0, seed=1)
    bf = float("inf")
    for _ in range(600):
        xs = es.ask()
        fs = np.sum(xs ** 2, axis=1)
        es.tell(xs, fs)
        bf = min(bf, float(fs.min()))
        if bf < 1e-6:
            break
    a_ok = bf < 1e-6
    print("   sphere best %.2e after gen %d  -> %s" % (bf, es.gen, a_ok))
    out["A_cma_sphere"] = {"best": bf, "gens": es.gen, "ok": bool(a_ok)}
    ok_all &= a_ok

    # ------------------------------------------------------------------ C
    # (before B so the backend question is answered by the lock)
    print("=== C. ORGANS.lock verify ===")
    try:
        lock, backend = organs_lock.verify()
        c_ok = True
        print("   VERIFIED: ear3 spec %s... carfac %s+%s cortex=%r "
              "backend=%s" % (lock["ear3"]["spec_hash"][:12],
                              lock["ear3"]["carfac_sha"],
                              lock["ear3"]["patch_id"], lock["cortex"],
                              backend))
    except SystemExit as e:
        c_ok, backend, lock = False, "ref", None
        print("   FAIL: %s" % e)
    out["C_organs_lock"] = {"ok": bool(c_ok), "backend": backend}
    ok_all &= c_ok

    # ------------------------------------------------------------------ B
    print("=== B. mouth2 C determinism + parity spot-check ===")
    arm = arms.get("ba-cv")
    rng = np.random.default_rng(42)
    x = arm.clip(rng.uniform(arm.lo, arm.hi))
    g = arm.to_gesture(x)
    b_ok = True
    if backend == "c":
        y1 = mouth2.say_gesture(g, seed=0, backend="c")
        y2 = mouth2.say_gesture(g, seed=0, backend="c")
        det = (y1 is not None) and np.array_equal(y1, y2)
        yr = mouth2.say_gesture(g, seed=0, backend="ref")
        if y1 is None or yr is None:
            par, par_ok = None, False
        else:
            par = float(np.max(np.abs(y1.astype(np.float64)
                                      - yr.astype(np.float64))))
            par_ok = par == 0.0
        b_ok = det and par_ok
        print("   C twice bit-identical: %s   C-vs-ref max|diff|: %s -> %s"
              % (det, par, "PASS" if par_ok else "FAIL (must be 0.0)"))
        out["B_mouth"] = {"deterministic": bool(det), "parity_max_abs":
                          par, "ok": bool(b_ok)}
    else:
        y1 = mouth2.say_gesture(g, seed=0, backend="ref")
        y2 = mouth2.say_gesture(g, seed=0, backend="ref")
        det = (y1 is not None) and np.array_equal(y1, y2)
        b_ok = det
        print("   NO .so -- reference backend. deterministic: %s" % det)
        out["B_mouth"] = {"deterministic": bool(det), "parity_max_abs":
                          None, "backend": "ref", "ok": bool(b_ok)}
    ok_all &= b_ok

    # ------------------------------------------------------------------ D
    print("=== D. Ear v3 LOO -- stored acceptance re-asserted ===")
    accepts = sorted(glob.glob(os.path.join(EAR_DIR, "EAR3-ACCEPT-*.json")))
    d_ok = False
    if accepts:
        with open(accepts[-1], encoding="utf-8") as f:
            acc = json.load(f)
        live = EF.spec_hash()
        with open(os.path.join(EAR_DIR, "targets-cache", "ear3-t06.json"),
                  encoding="utf-8") as f:
            cache_spec = json.load(f)["spec_hash"]
        hashes_ok = (acc["spec_hash"] == live == cache_spec)
        loo = acc["items"]["loo"]
        d_ok = hashes_ok and bool(loo["pass"])
        print("   accept %s: loo_six %.3f (bar %.3f) pass=%s"
              % (os.path.basename(accepts[-1]), loo["loo_six"],
                 loo["plan_bar"]["six"], loo["pass"]))
        print("   spec_hash accept==live==cache: %s (%s...)"
              % (hashes_ok, live[:12]))
        out["D_loo"] = {"accept_file": os.path.basename(accepts[-1]),
                        "loo_six": loo["loo_six"],
                        "lno_six": loo["lno_six"],
                        "spec_hashes_match": bool(hashes_ok),
                        "ok": bool(d_ok)}
    else:
        print("   FAIL: no EAR3-ACCEPT-*.json in %s" % EAR_DIR)
        out["D_loo"] = {"ok": False, "error": "no accept file"}
    ok_all &= d_ok

    # ------------------------------------------------------------------ E
    print("=== E. real-clip bars (the new '13.9') ===")
    stats = targets.load_all()                    # refuses on mismatch
    bars = targets.write_bars(stats)
    e_ok = all(bars["units"][u]["real_wdist_mean"] > 0 for u in targets.UNITS)
    for u in targets.UNITS:
        r = bars["units"][u]
        print("   %-5s mean %.3f  min %.3f  max %.3f  win<=%.3f"
              % (u, r["real_wdist_mean"], r["real_wdist_min"],
                 r["real_wdist_max"], r["win_bar_1p3x_mean"]))
    out["E_real_clip_bars"] = {"path": targets.BARS_PATH,
                               "units": bars["units"], "ok": bool(e_ok)}
    ok_all &= e_ok

    # ------------------------------------------------------------------ F
    print("=== F. gates: real pass rates + 6/6 v1 cheats must FAIL ===")
    gates = gates_v3.load_gates()
    rates = {u: gates[u]["joint_real_pass"] for u in targets.UNITS}
    rates_ok = all(v >= 0.95 for v in rates.values())
    print("   joint real pass: %s -> %s"
          % (" ".join("%s %.2f" % kv for kv in rates.items()),
             "PASS" if rates_ok else "FAIL"))
    cheat_dir = os.path.join(_HERE, "regression", "v1cheat")
    wavs = sorted(glob.glob(os.path.join(cheat_dir, "*.wav")))
    cheats = []
    for p in wavs:
        u = "abba"                                # all six are abba-arm cheats
        v, aux = EF.features_with_aux(EF.read_wav(p))
        gs = gates_v3.gate_stats(aux)
        g_ok, detail = gates_v3.check(u, gs)
        wd = targets.wdist(v, stats[u])
        ratio = wd / stats[u]["real_wdist_mean"]
        caught = (ratio > gates_v3.REVIEW_RATIO) or not g_ok
        cheats.append({"wav": os.path.basename(p),
                       "wdist": round(wd, 3), "x_real_mean": round(ratio, 3),
                       "gates_pass": bool(g_ok), "caught": bool(caught)})
        print("   %-28s wdist %.2f = %.2fx mean  gates %s  -> %s"
              % (os.path.basename(p), wd, ratio,
                 "pass" if g_ok else "FAIL",
                 "CAUGHT" if caught else "**SLIPPED**"))
    f_ok = rates_ok and len(cheats) == 6 and all(c["caught"] for c in cheats)
    out["F_gates"] = {"joint_real_pass": rates, "n_cheats": len(cheats),
                      "cheats": cheats, "ok": bool(f_ok)}
    ok_all &= f_ok

    # ------------------------------------------------------------------ G
    print("=== G. NASAL AUDIBILITY (velum open vs sealed, ma-vs-ba) ===")
    ka = mouth2.vowel_knots("a")
    seal = dict(c_pos=0.97, c_area=0.0)

    def ma_gesture(velum1, velum2):
        return {"keyframes": [mouth2.keyframe(ka, velum=velum1, **seal),
                              mouth2.keyframe(ka, velum=velum2),
                              mouth2.keyframe(ka),
                              mouth2.keyframe(ka, tenseness=0.5)],
                "durations": [0.16, 0.05, 0.20, 0.15],
                "f0_knots": [290.0, 280.0, 245.0],
                "tenseness_knots": [0.55, 0.6, 0.5]}

    def direction(y):
        v = EF.features(y)
        return (targets.wdist(v, stats["ma"])
                - targets.wdist(v, stats["ba"]))

    d_open, d_closed = [], []
    for s in range(5):
        d_open.append(direction(mouth2.say_gesture(
            ma_gesture(0.5, 0.15), seed=s, backend=backend)))
        d_closed.append(direction(mouth2.say_gesture(
            ma_gesture(0.0, 0.0), seed=s, backend=backend)))
    mo, so = float(np.mean(d_open)), float(np.std(d_open))
    mc, sc_ = float(np.mean(d_closed)), float(np.std(d_closed))
    gap = mc - mo                   # >0 means velum-open sits closer to ma
    noise = max(so, sc_, 1e-12)
    ratio = gap / noise
    g_ok = (gap > 0) and (ratio > 1.0)
    print("   d(ma)-d(ba): open %.4f±%.4f   sealed %.4f±%.4f" %
          (mo, so, mc, sc_))
    print("   nasal separation %.4f = %.1fx the 5-seed noise -> %s"
          % (gap, ratio, "AUDIBLE" if g_ok else "FAIL -- the ear cannot "
             "hear the velum; the ma arm is pointless until this is fixed"))
    out["G_nasal_audibility"] = {
        "dir_open_mean": mo, "dir_open_sd": so,
        "dir_sealed_mean": mc, "dir_sealed_sd": sc_,
        "separation": gap, "x_noise": ratio, "ok": bool(g_ok)}
    ok_all &= g_ok

    # ------------------------------------------------------------------ H
    print("=== H. closure visibility (hold vs seal-burst, abba-vs-ah) ===")
    hold = {"keyframes": [mouth2.keyframe(ka)],
            "durations": [0.66],
            "f0_knots": [300.0, 285.0, 245.0],
            "tenseness_knots": [0.6, 0.6, 0.5]}
    closure = {"keyframes": [mouth2.keyframe(ka),
                             mouth2.keyframe(ka, voicing=0.25, **seal),
                             mouth2.keyframe(ka, voicing=0.25),
                             mouth2.keyframe(ka),
                             mouth2.keyframe(ka, tenseness=0.5)],
               "durations": [0.20, 0.12, 0.004, 0.024, 0.32],
               "f0_knots": [300.0, 285.0, 245.0],
               "tenseness_knots": [0.6, 0.6, 0.5]}

    def ab_dir_and_dip(gest):
        y = mouth2.say_gesture(gest, seed=0, backend=backend)
        v, aux = EF.features_with_aux(y)
        gs = gates_v3.gate_stats(aux)
        return (targets.wdist(v, stats["abba"]) - targets.wdist(v, stats["ah"]),
                gs["dip"], gs["humps"])

    dir_hold, dip_hold, humps_hold = ab_dir_and_dip(hold)
    dir_cl, dip_cl, humps_cl = ab_dir_and_dip(closure)
    h_ok = (dir_cl < dir_hold) and (dip_cl > dip_hold)
    print("   d(abba)-d(ah): hold %.4f -> closure %.4f (moved %s abba)"
          % (dir_hold, dir_cl,
             "TOWARD" if dir_cl < dir_hold else "AWAY FROM"))
    print("   dip: hold %.3f (humps %d) -> closure %.3f (humps %d) -> %s"
          % (dip_hold, humps_hold, dip_cl, humps_cl,
             "PASS" if h_ok else "FAIL"))
    out["H_closure_visibility"] = {
        "dir_hold": dir_hold, "dir_closure": dir_cl,
        "dip_hold": dip_hold, "dip_closure": dip_cl,
        "humps_hold": humps_hold, "humps_closure": humps_cl,
        "ok": bool(h_ok)}
    ok_all &= h_ok

    # ------------------------------------------------------------------ I
    print("=== I. throughput, single core pinned (informational) ===")
    try:
        os.sched_setaffinity(0, {0})
        pinned = True
    except (AttributeError, OSError):
        pinned = False
    arm = arms.get("ba-cv")
    rng = np.random.default_rng(7)
    warm = [arm.clip(rng.uniform(arm.lo, arm.hi)) for _ in range(10)]
    for x in warm:                                # JIT every duration bucket
        y = mouth2.say_gesture(arm.to_gesture(x), seed=0, backend=backend)
        if y is not None:
            EF.features(y)
    t0 = time.perf_counter()
    n_ev = 0
    while time.perf_counter() - t0 < 30.0:
        x = arm.clip(rng.uniform(arm.lo, arm.hi))
        y = mouth2.say_gesture(arm.to_gesture(x), seed=0, backend=backend)
        if y is not None:
            v = EF.features(y)
            targets.wdist(v, stats["ba"])
        n_ev += 1
    eps = n_ev / (time.perf_counter() - t0)
    print("   %.2f evals/s/worker (pinned=%s, backend=%s; plan expects "
          "~9-13)" % (eps, pinned, backend))
    out["I_throughput"] = {"evals_per_s": eps, "pinned": pinned,
                           "backend": backend, "n": n_ev}

    out["ALL_OK"] = bool(ok_all)
    p = os.path.join(_HERE, "SANITY0-V3-%s.json" % out["utc"])
    with open(p, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    print()
    print("ALL_OK = %s   wrote %s" % (ok_all, p))
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
