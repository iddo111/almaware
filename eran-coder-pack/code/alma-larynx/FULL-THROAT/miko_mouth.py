# -*- coding: utf-8 -*-
"""miko_mouth.py — MIKO's own learning rule, driving a mouth by FEEL.

Iddo, 2026-08-30 04:55: run the real MIKO on this, and propose the build. Start
from the mouth alone — build proprioceptors in the mouth, then in the whole mouth
and throat. Solving it letter by letter is fine.

WHY MIKO IS THE RIGHT LEARNER, AND NOT A DECORATION
---------------------------------------------------
You cannot differentiate through silicone, air and a microphone. Backprop needs a
differentiable model of the body; a real mouth does not provide one. MIKO's
ThreeFactor rule (miko/model/loop.py) needs no gradient at all:

    factor 1  pre-synaptic activity   <- what the PROPRIOCEPTORS felt
    factor 2  post-synaptic activity  <- what the motor unit did
    factor 3  ONE global scalar       <- the ear says right, or wrong

Factors 1 and 2 lay a tag that changes nothing. Factor 3 captures it. Nothing
travels backwards. That is exactly the wiring a physical mouth can actually
provide, which is why this is the rule to build the hardware around.

WHAT IS SIMULATED, SAID PLAINLY
-------------------------------
The BODY is simulated: a Kelly-Lochbaum tube (reused from alma-larynx/
simulate_voicebox.py, the same tube maths ERAN's digital voice already uses),
pinched at 5 stations, exactly the 5 stations the printed PINCH-RAIL carries.
The PROPRIOCEPTORS are simulated as noisy local strain readings — what a
conductive-silicone strand cast into the tongue would actually report.
Nothing here has been built. This decides whether the hardware is worth building.

THE CONTROLS — the project's standing rule is that an experiment without a
size-matched control does not count, and the MIKO sweep was corrected on exactly
this point on 2026-08-30 04:10. All four arms use the IDENTICAL network:

    miko            ThreeFactor, signal tied to whether the ear improved
    no_signal       ThreeFactor present, factor 3 always 0 (tags never captured)
    shuffled        ThreeFactor, signal drawn from the same distribution but
                    DECOUPLED from performance  <- the strong control
    random          no learning at all, motor commands drawn at random

    python miko_mouth.py
"""
from __future__ import annotations

import sys
import numpy as np
import torch

sys.path.insert(0, r"D:\CLAUDE\miko\model")
sys.path.insert(0, r"D:\CLAUDE\alma-larynx")

from loop import ThreeFactor                      # MIKO's real rule, not a copy
from simulate_voicebox import kl_filter           # our real tube, not a copy

FS = 44100
N_SEC = 34          # ERAN's convention: 34 cross-sections
N_STATION = 5       # the five pinch stations on the printed PINCH-RAIL
N_PROP = 12         # proprioceptors along the tube
TRIALS = 300
SEEDS = 8


# ─────────────────────────────────────────── the body
def areas_from_motor(m: np.ndarray) -> np.ndarray:
    """5 pinch depths -> 34 cross-sectional areas (cm^2).

    Each station squeezes a Gaussian neighbourhood of the tube. A servo cannot
    pinch a tube to nothing, so depth is capped at 0.85 — that cap is a real
    hardware limit, not a modelling convenience."""
    x = np.arange(N_SEC)
    A = np.full(N_SEC, 4.0)
    centres = np.linspace(3, N_SEC - 4, N_STATION)
    for depth, c in zip(m, centres):
        A *= 1.0 - 0.85 * float(np.clip(depth, 0, 1)) * np.exp(-((x - c) ** 2) / 8.0)
    return np.maximum(A, 0.06)


def proprioception(m: np.ndarray, rng) -> np.ndarray:
    """What the mouth FEELS: local strain at N_PROP sites, 2% sensor noise.

    This is the quantity a conductive-silicone strand cast into the wall reports —
    how much it is stretched. It is NOT the motor command: the mouth feels the
    consequence of its act, which is the whole point of a proprioceptor."""
    A = areas_from_motor(m)
    sites = np.linspace(0, N_SEC - 1, N_PROP).astype(int)
    strain = 1.0 - A[sites] / 4.0
    return strain + rng.normal(0, 0.02, N_PROP)


def formants(m: np.ndarray) -> tuple[float, float]:
    """F1, F2 of the tube in this posture, from its impulse response."""
    imp = np.zeros(512)
    imp[0] = 1.0
    y = kl_filter(imp, areas_from_motor(m))
    NFFT = 8192                     # zero-padding: resolution without extra physics
    spec = np.abs(np.fft.rfft(y * np.hanning(len(y)), NFFT))
    freqs = np.fft.rfftfreq(NFFT, 1 / FS)
    k = 33
    sm = np.convolve(spec, np.ones(k) / k, mode="same")
    band = (freqs > 200) & (freqs < 3200)
    f, s = freqs[band], sm[band]
    peaks = [i for i in range(1, len(s) - 1) if s[i] > s[i - 1] and s[i] >= s[i + 1]]
    peaks.sort(key=lambda i: -s[i])
    got = sorted(f[i] for i in peaks[:2]) if len(peaks) >= 2 else []
    while len(got) < 2:
        got.append(3200.0)
    return float(got[0]), float(got[1])


def err(m: np.ndarray, target: tuple[float, float]) -> float:
    """Distance the EAR reports, in log-frequency — how a cochlea hears it."""
    f1, f2 = formants(m)
    t1, t2 = target
    return float(np.hypot(np.log(f1 / t1), np.log(f2 / t2)))


# ─────────────────────────────────────────── the learner
class Mouth(torch.nn.Module):
    """proprioception -> motor delta. Deliberately tiny: this must one day fit
    on the board bolted to the mouth, not on a DGX."""

    def __init__(self, hidden=24):
        super().__init__()
        self.W1 = torch.nn.Parameter(torch.randn(N_PROP, hidden) * 0.3)
        self.W2 = torch.nn.Parameter(torch.randn(hidden, N_STATION) * 0.3)

    def forward(self, p):
        h = torch.tanh(p @ self.W1)
        return torch.tanh(h @ self.W2), h


def run(arm: str, seed: int) -> dict:
    rng = np.random.default_rng(seed)
    torch.manual_seed(seed)
    net = Mouth()
    tf = ThreeFactor(net, lr=6e-3, decay=0.85)
    params = {"W1": net.W1.data, "W2": net.W2.data}

    # a target that is provably reachable: render a random posture and aim at it
    target_m = rng.uniform(0.1, 0.9, N_STATION)
    target = formants(target_m)

    m = rng.uniform(0.2, 0.8, N_STATION)
    best = err(m, target)
    baseline = best
    curve = [best]

    for t in range(TRIALS):
        p = proprioception(m, rng)
        pt = torch.tensor(p, dtype=torch.float32).unsqueeze(0)
        with torch.no_grad():
            delta, h = net(pt)
        step = delta.numpy()[0] * 0.12
        if arm == "random":
            step = rng.normal(0, 0.12, N_STATION)
        cand = np.clip(m + step + rng.normal(0, 0.03, N_STATION), 0, 1)
        e = err(cand, target)

        # factors 1 and 2: the tag. Only laid where a rule is running.
        if arm != "random":
            tf.observe(pt, h, "W1")
            tf.observe(h, delta, "W2")

        # factor 3: ONE scalar.
        if arm == "miko":
            signal = 1.0 if e < baseline else -1.0
        elif arm == "shuffled":
            signal = 1.0 if rng.random() < 0.5 else -1.0
        else:
            signal = 0.0
        if arm != "random":
            tf.apply(signal, params)

        # the body only keeps a posture the ear liked; this is the same accept
        # rule in every arm, so it cannot be what separates them
        if e < baseline:
            m, baseline = cand, e
        best = min(best, e)
        curve.append(baseline)

    return {"final": baseline, "best": best, "curve": curve}


def main():
    arms = ["miko", "no_signal", "shuffled", "random"]
    res = {a: [] for a in arms}
    for seed in range(SEEDS):
        for a in arms:
            res[a].append(run(a, seed))
        print("  seed %d done" % seed, flush=True)

    print()
    print("MIKO's ThreeFactor driving a mouth by proprioception")
    print("=" * 74)
    print("%d seeds x %d trials  ·  5 pinch stations  ·  %d proprioceptors  ·  "
          "identical net in every arm" % (SEEDS, TRIALS, N_PROP))
    print("-" * 74)
    print("%-11s %10s %10s %10s   %s" % ("arm", "median", "mean", "best", "final error, per seed"))
    for a in arms:
        f = np.array([r["final"] for r in res[a]])
        print("%-11s %10.4f %10.4f %10.4f   %s"
              % (a, np.median(f), f.mean(), f.min(),
                 " ".join("%.3f" % v for v in f)))
    print("-" * 74)
    mk = np.array([r["final"] for r in res["miko"]])
    for ctrl in ("no_signal", "shuffled", "random"):
        c = np.array([r["final"] for r in res[ctrl]])
        wins = int((mk < c).sum())
        print("miko vs %-10s : wins %d/%d seeds   median %.4f vs %.4f   %s"
              % (ctrl, wins, SEEDS, np.median(mk), np.median(c),
                 "MIKO better" if np.median(mk) < np.median(c) else "*** CONTROL BETTER ***"))
    print("=" * 74)
    np.save("miko_mouth_curves.npy",
            np.array([[r["curve"] for r in res[a]] for a in arms]))
    print("curves -> miko_mouth_curves.npy")
    return res


if __name__ == "__main__":
    main()
