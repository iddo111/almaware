#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""locus.py -- the PLACE cue a listener uses to tell nun from mem, dalet from bet: where F2 starts
when the closure opens (the "locus"). numpy only, so it runs on the PC and on eran2 alike.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

Born 2026-09-03 15:27 from Iddo's ruling on hear_claude :8859: "קלוד NA אתה אומר MA". The ruler had
murmur, nose/lip ratio and antiformant checks for na, but no check on F2 at the release -- and the
teacher's na closure sat at c_pos 0.93, a hair behind the lips (ma = 0.97). Same front cavity, same
F2 start, same sound to his ear.

    python locus.py file.wav [file2.wav ...]      # prints onset F2, F2 +40 ms, F2 vowel per file
    from locus import onset_formants              # -> dict(t_on, F_on, F_40, F_vow, ...)
"""
import sys, wave
import numpy as np

SR = 16000


def read_wav(path):
    w = wave.open(path, "rb")
    sr, n, ch, sw = w.getframerate(), w.getnframes(), w.getnchannels(), w.getsampwidth()
    raw = w.readframes(n); w.close()
    dt = {1: np.int8, 2: np.int16, 4: np.int32}[sw]
    y = np.frombuffer(raw, dtype=dt).astype(np.float64)
    if ch > 1: y = y.reshape(-1, ch).mean(axis=1)
    y /= float(2 ** (8 * sw - 1))
    if sr != SR:                                  # crude but adequate resample (anti-aliased decimation)
        from math import gcd
        g = gcd(sr, SR); up, down = SR // g, sr // g
        if up == 1:
            # low-pass by moving-average then decimate
            k = down
            y = np.convolve(y, np.ones(k) / k, mode="same")[::down]
        else:
            t_old = np.arange(len(y)) / sr; t_new = np.arange(int(len(y) * SR / sr)) / SR
            y = np.interp(t_new, t_old, y)
    return y


def lpc(x, order):
    """autocorrelation LPC via Levinson-Durbin -> polynomial a[0..order], a[0]=1"""
    r = np.correlate(x, x, "full")[len(x) - 1: len(x) + order]
    if r[0] <= 0: return None
    a = np.zeros(order + 1); a[0] = 1.0; e = r[0]
    for i in range(1, order + 1):
        acc = r[i] + np.dot(a[1:i], r[i - 1:0:-1])
        k = -acc / e
        a_new = a.copy(); a_new[i] = k
        a_new[1:i] = a[1:i] + k * a[i - 1:0:-1]
        a = a_new; e *= (1 - k * k)
        if e <= 0: return None
    return a


def formants(frame, sr=SR, order=None, fmin=150.0, fmax=5000.0, bw_max=600.0):
    order = order or (2 + sr // 1000)
    x = np.asarray(frame, float)
    x = np.append(x[0], x[1:] - 0.97 * x[:-1])      # pre-emphasis
    x = x * np.hanning(len(x))
    a = lpc(x, order)
    if a is None: return []
    rts = np.roots(a); rts = rts[np.imag(rts) > 0]
    f = np.angle(rts) * sr / (2 * np.pi)
    bw = -0.5 * sr / np.pi * np.log(np.abs(rts) + 1e-12)
    keep = [(fi, bi) for fi, bi in zip(f, bw) if fmin < fi < fmax and bi < bw_max]
    return sorted(keep)


def band_energy(x, sr, lo, hi):
    X = np.abs(np.fft.rfft(x * np.hanning(len(x)))) ** 2
    fr = np.fft.rfftfreq(len(x), 1.0 / sr)
    return float(X[(fr >= lo) & (fr < hi)].sum() + 1e-12)


def onset_formants(y, sr=SR, t_rel=None, frame=0.025, hop=0.005):
    """Find the release (murmur -> vowel) and read F1..F3 at onset, +40 ms, and in the vowel middle.
    Release = the first frame where energy above 1 kHz jumps to within 12 dB of its plateau."""
    n = int(frame * sr); h = int(hop * sr)
    times, hi_db, F = [], [], []
    for s in range(0, len(y) - n, h):
        seg = y[s:s + n]
        times.append((s + n / 2) / sr)
        hi_db.append(10 * np.log10(band_energy(seg, sr, 1000, 4000)))
        F.append(formants(seg, sr))
    times = np.array(times); hi_db = np.array(hi_db)
    if t_rel is None:
        plateau = np.percentile(hi_db, 90)
        cand = np.where(hi_db > plateau - 12)[0]
        i_on = int(cand[0]) if len(cand) else 0
    else:
        i_on = int(np.argmin(np.abs(times - t_rel)))
    def pick(i):
        i = max(0, min(len(F) - 1, i)); fs = [f for f, b in F[i]]
        return [int(round(v)) for v in fs[:3]] + [None] * (3 - min(3, len(fs)))
    i40 = i_on + int(0.040 / hop)
    # vowel middle = midpoint between onset and end of high-band plateau
    tail = np.where(hi_db > np.percentile(hi_db, 90) - 12)[0]
    i_vow = int((i_on + (tail[-1] if len(tail) else len(F) - 1)) / 2)
    return {"t_on": round(float(times[i_on]), 3), "F_on": pick(i_on), "F_10": pick(i_on + 2), "F_40": pick(i40),
            "F_vow": pick(i_vow), "hi_db_before": round(float(hi_db[max(0, i_on - 3)]), 1),
            "hi_db_on": round(float(hi_db[i_on]), 1)}


def describe(path, t_rel=None):
    y = read_wav(path); r = onset_formants(y, SR, t_rel)
    return r


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    for p in args:
        r = describe(p)
        print("%-34s t_on %.3f  F_on %-18s F+10 %-18s F+40 %-18s vowel %s" % (
            p.split("/")[-1].split("\\")[-1], r["t_on"], r["F_on"], r["F_10"], r["F_40"], r["F_vow"]))
