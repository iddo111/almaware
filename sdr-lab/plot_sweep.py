# -*- coding: utf-8 -*-
"""Turn an rtl_power CSV into a spectrum plot — the picture that shows WHERE the
signals are. rtl_power rows: date, time, hz_low, hz_high, hz_step, samples, db, db, ...
We average all time steps per frequency bin and mark the peaks."""
import sys, os, csv
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

def load(path):
    freqs, powers = [], []
    acc = {}
    with open(path) as f:
        for row in csv.reader(f):
            if len(row) < 7:
                continue
            low, high, step = float(row[2]), float(row[3]), float(row[4])
            vals = [float(v) for v in row[6:] if v.strip() not in ("", "-inf", "nan")]
            for i, db in enumerate(vals):
                fhz = low + i * step
                acc.setdefault(round(fhz), []).append(db)
    for fhz in sorted(acc):
        freqs.append(fhz / 1e6)
        powers.append(np.mean(acc[fhz]))
    return np.array(freqs), np.array(powers)

def main():
    if len(sys.argv) < 2:
        print("usage: python plot_sweep.py <sweep.csv>   (make one with scan.ps1)")
        return
    path = sys.argv[1]
    if not os.path.exists(path):
        print(f"no such file: {path}")
        return
    f, p = load(path)
    if len(f) == 0:
        print("no data in CSV"); return
    noise = np.median(p)
    peaks = []
    for i in range(2, len(p) - 2):
        if p[i] > noise + 6 and p[i] >= p[i-1] and p[i] >= p[i+1]:
            peaks.append((f[i], p[i]))
    peaks.sort(key=lambda t: -t[1])

    plt.figure(figsize=(14, 6), dpi=120)
    plt.plot(f, p, lw=0.8, color="#2176c7")
    plt.axhline(noise, color="#999", ls="--", lw=1, label=f"noise floor {noise:.0f} dB")
    for fmhz, db in peaks[:12]:
        plt.plot(fmhz, db, "v", color="#c72121")
        plt.annotate(f"{fmhz:.3f}", (fmhz, db), fontsize=8,
                     ha="center", va="bottom", color="#c72121")
    plt.xlabel("MHz"); plt.ylabel("power (dB)")
    plt.title(f"RTL-SDR sweep — {os.path.basename(path)}  ({len(peaks)} peaks over floor)")
    plt.grid(alpha=0.25); plt.legend()
    out = os.path.splitext(path)[0] + ".png"
    plt.tight_layout(); plt.savefig(out)
    print("wrote", out)
    print("\nStrongest signals:")
    for fmhz, db in peaks[:12]:
        print(f"  {fmhz:9.3f} MHz   {db:6.1f} dB")

if __name__ == "__main__":
    main()
