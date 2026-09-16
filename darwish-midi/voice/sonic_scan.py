"""sonic_scan.py -- listen to a render with instruments instead of opinions.

Iddo, 2026-08-23 09:40: "run sonic scanner ai model and see how bad it is --
use some ear to listen."

I have no ears. What I have is the signal, so this measures the handful of
things that actually decide whether a psytrance track is a track:

  KICK GRID      psy is four-on-the-floor. A 30-110 Hz envelope, peak-picked,
                 then the inter-onset intervals. A real track puts ~100% of its
                 kicks one beat apart. Anything else is not a groove.
  SPECTRAL       energy in sub / bass / low-mid / mid / high. Psy lives in the
  BALANCE        sub and the high; a render that is all low-mid is a mud pie.
  MOVEMENT       spectral flux: how much the spectrum changes second to second.
                 Zero flux is a drone with a metronome, not an arrangement.
  REPETITION     self-similarity of 8-second blocks. A real track repeats
                 (that's the genre) but also DEVELOPS. 0.99 everywhere means
                 one bar looped for six minutes.
  WIDTH          mid/side ratio. Mono is a red flag for electronic music.
  CREST          peak/rms in dB -- how much punch survived the mix.

Every number is printed next to the same number measured on a REAL Darwish
track from the corpus, because "bad" only means anything against a reference.

    python sonic_scan.py a.wav b.wav ...        (first file = reference)
"""
import array
import math
import os
import sys
import wave

import numpy as np


def load(path, max_s=300.0):
    w = wave.open(path, "rb")
    n, ch, sw, fr = w.getnframes(), w.getnchannels(), w.getsampwidth(), w.getframerate()
    n = min(n, int(max_s * fr))
    raw = w.readframes(n)
    w.close()
    a = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    if ch == 2:
        a = a.reshape(-1, 2)
        mid = a.mean(axis=1)
        side = (a[:, 0] - a[:, 1]) * 0.5
    else:
        mid, side = a, np.zeros_like(a)
    return mid, side, fr


def band_energy(x, fr, lo, hi):
    """RMS in a band, via rFFT on the whole signal (cheap and exact enough)."""
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1.0 / fr)
    m = (f >= lo) & (f < hi)
    return float(np.sqrt(np.sum(np.abs(X[m]) ** 2)) / len(x))


def kick_grid(x, fr):
    """Low-band onsets -> (kicks/min, % of gaps that are one steady beat)."""
    # crude but honest low-pass: decimate hard, then envelope
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1.0 / fr)
    X[(f < 30) | (f > 110)] = 0
    low = np.fft.irfft(X, n=len(x))
    env = np.abs(low)
    hop = fr // 200                                   # 5 ms
    e = np.array([env[i:i + hop].max() for i in range(0, len(env) - hop, hop)])
    if e.max() <= 0:
        return 0.0, 0.0, 0.0
    e = e / e.max()
    thr = max(0.18, float(np.percentile(e, 92)) * 0.55)
    onsets, last = [], -99
    for i in range(1, len(e) - 1):
        if e[i] > thr and e[i] >= e[i - 1] and e[i] > e[i + 1] and i - last > 12:
            onsets.append(i)
            last = i
    if len(onsets) < 8:
        return len(onsets) / (len(x) / fr / 60.0), 0.0, 0.0
    gaps = np.diff(onsets) * (hop / fr)
    med = float(np.median(gaps))
    steady = float(np.mean(np.abs(gaps - med) < med * 0.12)) * 100.0
    return len(onsets) / (len(x) / fr / 60.0), steady, 60.0 / med if med > 0 else 0.0


def flux_and_repetition(x, fr):
    win, hop = 2048, 1024
    nfr = (len(x) - win) // hop
    nfr = min(nfr, 6000)
    S = np.empty((nfr, win // 2 + 1), dtype=np.float32)
    w = np.hanning(win).astype(np.float32)
    for i in range(nfr):
        S[i] = np.abs(np.fft.rfft(x[i * hop:i * hop + win] * w))
    S = np.log1p(S * 100.0)
    flux = float(np.mean(np.abs(np.diff(S, axis=0))))
    # self-similarity of ~8 s blocks
    per = int(8.0 * fr / hop)
    blocks = [S[i:i + per].mean(axis=0) for i in range(0, nfr - per, per)]
    if len(blocks) < 3:
        return flux, float("nan"), 0.0, 0.0
    B = np.array(blocks)
    B = B / (np.linalg.norm(B, axis=1, keepdims=True) + 1e-9)
    sim = B @ B.T
    off = sim[~np.eye(len(B), dtype=bool)]
    centroid = float(np.sum(S.mean(axis=0) * np.fft.rfftfreq(win, 1.0 / fr))
                     / (np.sum(S.mean(axis=0)) + 1e-9))
    return flux, float(np.mean(off)), centroid, float(np.std(off))


def scan(path):
    mid, side, fr = load(path)
    dur = len(mid) / fr
    rms = float(np.sqrt(np.mean(mid ** 2)))
    peak = float(np.max(np.abs(mid)))
    bands = {"sub 20-60": (20, 60), "bass 60-250": (60, 250), "lomid 250-1k": (250, 1000),
             "mid 1k-4k": (1000, 4000), "high 4k-16k": (4000, 16000)}
    be = {k: band_energy(mid, fr, lo, hi) for k, (lo, hi) in bands.items()}
    tot = sum(be.values()) + 1e-12
    kpm, steady, bpm = kick_grid(mid, fr)
    flux, selfsim, centroid, simstd = flux_and_repetition(mid, fr)
    width = float(np.sqrt(np.mean(side ** 2)) / (rms + 1e-9))
    return {
        "file": os.path.basename(path), "dur": dur,
        "rms_db": 20 * math.log10(rms + 1e-12), "peak_db": 20 * math.log10(peak + 1e-12),
        "crest_db": 20 * math.log10((peak + 1e-12) / (rms + 1e-12)),
        "bands_pct": {k: 100.0 * v / tot for k, v in be.items()},
        "kicks_per_min": kpm, "kick_steady_pct": steady, "kick_bpm": bpm,
        "flux": flux, "selfsim": selfsim, "selfsim_std": simstd,
        "centroid_hz": centroid, "width": width,
    }


if __name__ == "__main__":
    paths = sys.argv[1:]
    if not paths:
        raise SystemExit("usage: sonic_scan.py <reference.wav> <candidate.wav> ...")
    res = [scan(p) for p in paths]
    ref = res[0]

    def row(label, key, fmt="%7.1f", sub=None):
        vals = []
        for r in res:
            v = r["bands_pct"][sub] if sub else r[key]
            vals.append(fmt % v)
        print(f"  {label:22s}" + "".join(f"{v:>16s}" for v in vals))

    print("\nSONIC SCAN  (first column is the REAL Darwish track = the reference)\n")
    print(f"  {'':22s}" + "".join(f"{r['file'][:15]:>16s}" for r in res))
    print("  " + "-" * (22 + 16 * len(res)))
    row("duration s", "dur")
    row("rms dBFS", "rms_db")
    row("peak dBFS", "peak_db")
    row("crest dB", "crest_db")
    print()
    for b in ("sub 20-60", "bass 60-250", "lomid 250-1k", "mid 1k-4k", "high 4k-16k"):
        row("energy% " + b, None, "%7.1f", sub=b)
    print()
    row("kicks / min", "kicks_per_min")
    row("kick BPM", "kick_bpm")
    row("kick steady %", "kick_steady_pct")
    print()
    row("spectral flux", "flux", "%7.3f")
    row("self-similarity", "selfsim", "%7.3f")
    row("  its std (variety)", "selfsim_std", "%7.3f")
    row("centroid Hz", "centroid_hz")
    row("stereo width", "width", "%7.3f")

    print("\n  VERDICT vs the real track")
    for r in res[1:]:
        d = []
        if r["kick_steady_pct"] < ref["kick_steady_pct"] - 15:
            d.append(f"kick grid {r['kick_steady_pct']:.0f}% vs {ref['kick_steady_pct']:.0f}% -- no steady four-on-the-floor")
        if r["bands_pct"]["sub 20-60"] < ref["bands_pct"]["sub 20-60"] * 0.5:
            d.append(f"sub {r['bands_pct']['sub 20-60']:.1f}% vs {ref['bands_pct']['sub 20-60']:.1f}% -- no bottom end")
        if r["bands_pct"]["high 4k-16k"] < ref["bands_pct"]["high 4k-16k"] * 0.5:
            d.append(f"highs {r['bands_pct']['high 4k-16k']:.1f}% vs {ref['bands_pct']['high 4k-16k']:.1f}% -- dull, no air")
        if r["flux"] < ref["flux"] * 0.6:
            d.append(f"flux {r['flux']:.3f} vs {ref['flux']:.3f} -- the spectrum barely moves")
        if r["selfsim"] > ref["selfsim"] + 0.08:
            d.append(f"self-similarity {r['selfsim']:.3f} vs {ref['selfsim']:.3f} -- it loops without developing")
        if r["width"] < ref["width"] * 0.5:
            d.append(f"width {r['width']:.3f} vs {ref['width']:.3f} -- effectively mono")
        print(f"\n  {r['file']}")
        print("    OK on every measured axis" if not d else "".join(f"\n      - {x}" for x in d))
    print()
