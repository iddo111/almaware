#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""COOKING IN THE BACKGROUND. One long run that survives a reboot.

    python3 cook.py --arm alma-pert --hidden 32 --trials 2000000

Iddo, 2026-09-12 02:56: "ותן לו להתבשל ברקע". So: lowest priority, a memory
guard that PAUSES rather than competes, a checkpoint and a rendered sample every
N trials into a dated folder, and a resume that makes a reboot a pause instead
of a loss.

THE ARMS. Every run writes its own; a result without a control is a story.
    alma-pert   the organ. node perturbation on the hidden cords, the loom's
                three-factor rule at the heads.
    alma-3f     three-factor everywhere, including the hidden cords. This is the
                ABLATION that shows the wall, not a contender.
    frozen      the same weave, never updated. The floor. Anything that does not
                beat this learned nothing.
    shuffled    the organ, paid with a reward belonging to some OTHER bar. Same
                reward distribution, no relation to what it just played. IT MUST
                LEARN NOTHING. If it climbs, the experiment is broken and every
                other number in the folder is void.
    vanilla     REINFORCE on a 32->H->15 policy with the identical parameter
                count (baseline.py). The honest bar.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import judge_local                                                 # noqa: E402
import render_mid                                                  # noqa: E402
import weave as W                                                  # noqa: E402
from baseline import VHyper, VanillaBeat                           # noqa: E402

ARMS = ("alma-pert", "alma-pert-heads", "alma-3f", "frozen", "shuffled", "vanilla")


# ------------------------------------------------------------------ the guard

def free_gb() -> float:
    """Available memory in GB. Iddo's live brains must never be endangered."""
    try:
        with open("/proc/meminfo", encoding="ascii") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) / 1024.0 / 1024.0
    except OSError:
        pass
    try:
        import ctypes

        class MS(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        m = MS()
        m.dwLength = ctypes.sizeof(MS)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
        return m.ullAvailPhys / 1024.0 ** 3
    except Exception:                                              # noqa: BLE001
        return 999.0


def be_polite() -> None:
    try:
        os.nice(19)
    except Exception:                                              # noqa: BLE001
        try:
            import ctypes
            ctypes.windll.kernel32.SetPriorityClass(
                ctypes.windll.kernel32.GetCurrentProcess(), 0x00004000)
        except Exception:                                          # noqa: BLE001
            pass


def build(arm: str, hidden: int, seed: int, gain: float):
    if arm == "vanilla":
        return VanillaBeat(VHyper(hidden=hidden, seed=seed))
    rule = {"alma-pert": "perturbation", "alma-pert-heads": "perturbation-all",
            "alma-3f": "three-factor", "frozen": "frozen",
            "shuffled": "perturbation"}[arm]
    return W.BeatWeave(W.Hyper(hidden=hidden, rule=rule, seed=seed, gain=gain))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", default="alma-pert", choices=ARMS)
    ap.add_argument("--hidden", type=int, default=32)
    ap.add_argument("--trials", type=int, default=200000)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--gain", type=float, default=4.0)
    ap.add_argument("--every", type=int, default=2000, help="checkpoint + sample")
    ap.add_argument("--min-free-gb", type=float, default=15.0)
    ap.add_argument("--out", default=None)
    ap.add_argument("--judge", default="local", choices=("local", "shared"))
    ap.add_argument("--bpm", type=float, default=143.0)
    args = ap.parse_args()

    be_polite()
    out = Path(args.out) if args.out else (
        HERE / "runs" / f"{datetime.now():%Y%m%d}-{args.arm}-h{args.hidden}-s{args.seed}")
    out.mkdir(parents=True, exist_ok=True)
    (out / "samples").mkdir(exist_ok=True)
    ckpt = out / "checkpoint.json"
    curve = out / "curve.csv"

    scorer = judge_local.score_bar
    if args.judge == "shared":
        sys.path.insert(0, str(HERE.parent / "darwish-midi"))
        import judge as shared
        scorer = shared.score_bar

    model = build(args.arm, args.hidden, args.seed, args.gain)
    rng = random.Random(args.seed + 991)
    start, ema = 0, 0.5
    if ckpt.exists():
        st = json.loads(ckpt.read_text(encoding="utf-8"))
        model.load(st["weights"])
        start, ema = st["trial"], st["ema"]
        print(f"resumed at trial {start}", flush=True)
    else:
        with curve.open("w", encoding="utf-8") as f:
            f.write("trial,score,scale,regularity,independence,energy,similarity,moved,ema\n")
        (out / "hyper.json").write_text(json.dumps({
            "arm": args.arm, "hidden": args.hidden, "seed": args.seed,
            "gain": args.gain, "judge": args.judge, "bpm": args.bpm,
            "n_params": model.n_params(),
            "hyper": getattr(model.hyper, "line", lambda: str(model.hyper))(),
        }, indent=2), encoding="utf-8")

    past: list[float] = []
    state = {"ema": ema}

    def reward_fn(bar):
        r = scorer(bar)
        s = float(r["score"])
        paid = s
        if args.arm == "shuffled":
            # THE CONTROL: a real score, belonging to a DIFFERENT bar.
            paid = rng.choice(past) if past else 0.5
        past.append(s)
        if len(past) > 512:
            past.pop(0)
        state["ema"] = 0.995 * state["ema"] + 0.005 * paid
        return (paid - state["ema"]) * args.gain, paid, r

    t0 = time.time()
    paused = 0.0
    best = -1.0
    trial = start
    for trial in range(start, args.trials):
        fg = free_gb()
        if fg < args.min_free_gb:
            # PAUSE, never compete. His live brains come first.
            with (out / "paused.log").open("a", encoding="utf-8") as f:
                f.write(f"{datetime.now():%F %T} free={fg:.1f}GB < "
                        f"{args.min_free_gb}GB, sleeping 120s\n")
            time.sleep(120)
            paused += 120
            continue
        if args.arm == "vanilla":
            res = model.play_and_learn(reward_fn, rng)
        else:
            res = model.play_and_learn(reward_fn)
        rep = res["report"]
        p = rep["parts"]
        with curve.open("a", encoding="utf-8") as f:
            f.write(f"{trial},{rep['score']:.5f},{p['scale']:.5f},{p['regularity']:.5f},"
                    f"{p['independence']:.5f},{p['energy']:.5f},{p['similarity']:.5f},"
                    f"{res['moved']:.6f},{state['ema']:.5f}\n")
        if rep["score"] > best:
            best = rep["score"]
        if (trial + 1) % args.every == 0:
            tmp = ckpt.with_suffix(".tmp")
            tmp.write_text(json.dumps({
                "trial": trial + 1, "ema": state["ema"], "best": best,
                "weights": model.weights(), "when": f"{datetime.now():%F %T}",
            }), encoding="utf-8")
            tmp.replace(ckpt)                 # atomic: a reboot mid-write is safe
            render_mid.write(str(out / "samples" / f"t{trial+1:08d}.mid"),
                             [res["bar"]], bpm=args.bpm, repeats=4)
            (out / "samples" / f"t{trial+1:08d}.json").write_text(
                json.dumps({"bar": res["bar"], "report": rep}, indent=1),
                encoding="utf-8")
            el = time.time() - t0 - paused
            print(f"[{datetime.now():%T}] trial {trial+1} ema={state['ema']:.4f} "
                  f"best={best:.4f} scale={p['scale']:.3f} "
                  f"{(trial+1-start)/max(1e-9, el):.1f} trials/s free={fg:.0f}GB",
                  flush=True)
    print(f"done at trial {trial+1}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
