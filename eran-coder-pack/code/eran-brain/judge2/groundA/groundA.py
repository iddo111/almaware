#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""groundA.py -- THE JUDGE, Ground A: the features and the ear.

  demo   extract the ear3 996-d vector for THREE wavs (human t06 ba, an ERAN
         queue candidate, and the same human ba with its burst removed) and
         print how every block responds.

  probe  MEASURE which blocks carry burst information.

TWO MANIPULATIONS, because the obvious one has an artifact:

  CUT60   delete 60 ms starting at the energy onset, 5 ms linear crossfade at
          the splice. This is what the bet-barrier inquiry did. ARTIFACT: the
          leading silence is kept, so the clip now steps from silence into a
          full-amplitude vowel in 5 ms -- a NEW transient, SHARPER than the
          /b/ release it replaced. Measured on ba_t06_0: onset-map slice 0
          rose 3.588 -> 4.195. Any block that "notices" CUT60 may be noticing
          the splice, not the missing burst.

  RAMP60  multiply the 60 ms starting at the onset by a linear 0->1 ramp.
          Same duration, same samples elsewhere, NO splice, no click; the
          abrupt release is simply gone and the attack becomes 60 ms of
          gradual growth. This is the honest burst removal.

CONTROL: the identical operation on 100 /ah/ takes -- a vowel with no stop
release to remove. A block that moves as much on ah is reacting to "the first
60 ms changed", not to the burst.

ONSET (both): first 10 ms frame whose plain-RMS envelope exceeds 0.10 of the
clip's peak frame RMS -- the same 0.10 the ear's speech-span rule uses, on raw
energy so it needs no cochlea.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import wave

import numpy as np

EARV3 = os.path.expanduser("~/ear-v3")
sys.path.insert(0, EARV3)

from ear3 import features as F      # noqa: E402
from ear3 import judge as J         # noqa: E402

CORPUS = os.path.expanduser("~/eran-cortex/data/t06")
OUT = os.path.expanduser("~/judge2-groundA")
FS = 16000
HOP = 160
AMP_MS = 60.0
XFADE_MS = 5.0
FRAC = 0.10

# Fine blocks: the coarse five, split where the burst could plausibly hide.
FINE = [("legacy192", 0, 192),
        ("level", 192, 202),
        ("coch_slice0", 202, 267),
        ("coch_slice1", 267, 332),
        ("coch_slice2-7", 332, 722),
        ("pitch", 722, 853),
        ("mod_energy", 853, 908),
        ("onset_slice0", 908, 919),
        ("onset_slice1", 919, 930),
        ("onset_slice2-7", 930, 996)]


# --------------------------------------------------------------- manipulations

def env_rms(x, hop=HOP):
    nf = x.size // hop
    if nf == 0:
        return np.zeros(0)
    return np.sqrt((x[:nf * hop].reshape(nf, hop) ** 2).mean(axis=1))


def onset_sample(x, frac=FRAC, hop=HOP):
    e = env_rms(x, hop)
    if e.size == 0 or e.max() <= 0:
        return 0
    idx = np.where(e > e.max() * frac)[0]
    return int(idx[0]) * hop if idx.size else 0


def cut60(x, ms=AMP_MS, xfade_ms=XFADE_MS, fs=FS):
    a = onset_sample(x)
    n = int(round(ms * fs / 1000.0))
    xf = int(round(xfade_ms * fs / 1000.0))
    b = a + n
    if b + xf >= x.size:
        y = np.concatenate([x[:a], x[min(b, x.size):]])
        return y.astype(np.float32), a, n, 0.0
    head, tail = x[:a].copy(), x[b:].copy()
    if head.size >= xf and tail.size >= xf:
        r = np.linspace(0.0, 1.0, xf, dtype=np.float32)
        blend = head[-xf:] * (1.0 - r) + tail[:xf] * r
        y = np.concatenate([head[:-xf], blend, tail[xf:]])
    else:
        y = np.concatenate([head, tail])
    lo, hi = max(0, a - xf - 2), min(y.size, a + 2)
    seam = float(np.max(np.abs(np.diff(y[lo:hi])))) if hi - lo > 2 else 0.0
    return y.astype(np.float32), a, n, seam


def ramp60(x, ms=AMP_MS, fs=FS):
    """Linear 0->1 ramp over `ms` starting at the onset. No splice, no click."""
    a = onset_sample(x)
    n = min(int(round(ms * fs / 1000.0)), max(0, x.size - a))
    y = x.copy()
    if n > 1:
        y[a:a + n] = y[a:a + n] * np.linspace(0.0, 1.0, n, dtype=np.float32)
    return y.astype(np.float32), a, n, 0.0


def attack_stats(x, fs=FS):
    """Attack time 10->90% of peak envelope (ms) and 15 ms rise (dB)."""
    e = env_rms(x)
    if e.size < 3 or e.max() <= 0:
        return float("nan"), float("nan")
    pk = e.max()
    i10 = np.where(e >= 0.10 * pk)[0]
    i90 = np.where(e >= 0.90 * pk)[0]
    if not len(i10) or not len(i90) or i90[0] < i10[0]:
        return float("nan"), float("nan")
    att = (i90[0] - i10[0]) * HOP / fs * 1000.0
    a = i10[0]
    lo = max(e[max(0, a - 1)], 1e-9)
    hi = max(e[min(e.size - 1, a + 1)], 1e-9)   # +-15 ms window on a 10 ms grid
    return att, 20.0 * np.log10(hi / lo)


def natural_step(x):
    return float(np.max(np.abs(np.diff(x)))) if x.size > 1 else 0.0


def write_wav(path, x, fs=FS):
    pcm = np.clip(np.asarray(x, dtype=np.float64), -1.0, 1.0)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(fs)
        w.writeframes((pcm * 32767.0).astype("<i2").tobytes())


def _sha(v):
    return hashlib.sha256(
        np.ascontiguousarray(v, dtype=np.float64).tobytes()).hexdigest()[:12]


def per_block_wdist2(v, stats, rngs):
    t = np.asarray(stats["target"], dtype=np.float64)
    w = np.asarray(stats["w"], dtype=np.float64)
    r = ((np.asarray(v, dtype=np.float64) - t) / w) ** 2
    return np.array([r[lo:hi].sum() for _, lo, hi in rngs])


def auc(pos, neg):
    """P(a random pos > a random neg), ties 0.5."""
    pos, neg = np.asarray(pos), np.asarray(neg)
    allv = np.concatenate([pos, neg])
    r = np.empty(allv.size, dtype=np.float64)
    order = np.argsort(allv, kind="mergesort")
    sv = allv[order]
    i = 0
    while i < sv.size:
        j = i
        while j + 1 < sv.size and sv[j + 1] == sv[i]:
            j += 1
        r[order[i:j + 1]] = (i + j) / 2.0 + 1.0
        i = j + 1
    n1 = pos.size
    return float((r[:n1].sum() - n1 * (n1 + 1) / 2.0) / (n1 * neg.size))


# ------------------------------------------------------------------------ demo

def demo():
    human = os.path.join(CORPUS, "ba_t06_0.wav")
    eranc = os.path.expanduser(
        "~/burstfix/wav/20260826T164235Z_eran2_ba-cv-1_4.982.wav")
    x = F.read_wav(human)
    yc, a, k, seam = cut60(x)
    yr, _, _, _ = ramp60(x)
    write_wav(os.path.join(OUT, "ba_t06_0_CUT60.wav"), yc)
    write_wav(os.path.join(OUT, "ba_t06_0_RAMP60.wav"), yr)
    print("manipulation on ba_t06_0: onset at sample %d (%.1f ms)" % (a, a / FS * 1000))
    print("  CUT60  removed %d samples, %d -> %d; splice max|diff|=%.5f vs the "
          "clip's own natural max|diff|=%.5f" % (k, x.size, yc.size, seam,
                                                 natural_step(x)))
    print("  RAMP60 length unchanged (%d)" % yr.size)
    for nm, s in (("intact", x), ("CUT60", yc), ("RAMP60", yr)):
        at, rz = attack_stats(s)
        print("  attack %-7s 10->90%%: %6.1f ms   +-15 ms rise: %+6.1f dB"
              % (nm, at, rz))
    print()
    print("=" * 78)
    print("DEMO -- ear3 feature extraction on arbitrary wavs")
    print("=" * 78)
    print("spec_hash = " + F.spec_hash())
    print("DIM       = %d" % F.DIM)
    print("blocks    = " + ", ".join("%s[%d:%d) d=%d" % (n, lo, hi, hi - lo)
                                     for n, lo, hi in F.block_ranges()))
    print()
    units = J.load_cache()
    paths = [(human, "HUMAN  ba_t06_0.wav"),
             (eranc, "ERAN   20260826T164235Z_eran2_ba-cv-1_4.982.wav"),
             (os.path.join(OUT, "ba_t06_0_CUT60.wav"),
              "HUMAN-CUT60   ba_t06_0, 60 ms deleted at onset"),
             (os.path.join(OUT, "ba_t06_0_RAMP60.wav"),
              "HUMAN-RAMP60  ba_t06_0, release ramped away")]
    for p, lab in paths:
        s = F.read_wav(p)
        t0 = time.perf_counter()
        v, aux = F.features_with_aux(s)
        dt = (time.perf_counter() - t0) * 1e3
        print("--- " + lab)
        print("    file        %s" % p)
        print("    samples     %d  (%.3f s)  peak=%.4f"
              % (s.size, s.size / FS, np.abs(s).max()))
        print("    vector      shape=%s dtype=%s finite=%s sha=%s"
              % (v.shape, v.dtype, bool(np.isfinite(v).all()), _sha(v)))
        print("    wall        %.0f ms  per-part %s" % (dt, aux["timing"]))
        print("    span        frames %s  span_dur=%.3fs occupancy=%.3f"
              % (aux["span"], aux["span_dur"], aux["occupancy"]))
        print("    voiced_frac %s  median_f0=%s"
              % (aux.get("voiced_frac"), aux.get("median_f0")))
        for name, lo, hi in F.block_ranges():
            b = v[lo:hi]
            print("    %-12s d=%-4d mean=%+.4f std=%.4f min=%+.4f max=%+.4f"
                  % (name, hi - lo, b.mean(), b.std(), b.min(), b.max()))
        print("    nearest     " + ", ".join(
            "%s=%.2f" % (r["unit"], r["wdist"]) for r in J.nearest_table(v, units)))
        o = v[908:996].reshape(8, 11)
        print("    onset slice0 " + " ".join("%.3f" % q for q in o[0]))
        print("    onset row-max " + " ".join("%.3f" % q for q in o.max(axis=1)))
        print()


# ----------------------------------------------------------------------- probe

def collect(unit, n):
    files = sorted(f for f in os.listdir(CORPUS)
                   if f.startswith(unit + "_t06_") and f.endswith(".wav"))[:n]
    V, C, R, meta = [], [], [], []
    for i, f in enumerate(files):
        x = F.read_wav(os.path.join(CORPUS, f))
        yc, a, k, seam = cut60(x)
        yr, _, _, _ = ramp60(x)
        V.append(F.features(x))
        C.append(F.features(yc))
        R.append(F.features(yr))
        at_i, rz_i = attack_stats(x)
        at_c, _ = attack_stats(yc)
        at_r, rz_r = attack_stats(yr)
        meta.append((a / FS, seam, natural_step(x), at_i, at_c, at_r, rz_i, rz_r))
        if (i + 1) % 25 == 0:
            print("    %s %d/%d" % (unit, i + 1, len(files)), flush=True)
    return np.asarray(V), np.asarray(C), np.asarray(R), np.asarray(meta), files


def zshift(V, W, s, rngs):
    """Per clip, per block: RMS z-shift per dim."""
    return np.array([[np.sqrt((((V[i] - W[i]) / s)[lo:hi] ** 2).mean())
                      for _, lo, hi in rngs] for i in range(len(V))])


def probe():
    n = int(os.environ.get("N", "100"))
    print("=" * 78)
    print("PROBE -- which blocks carry burst information (n=%d per unit)" % n)
    print("=" * 78)
    D = {}
    for unit in ("ba", "ah"):
        t0 = time.time()
        V, C, R, meta, files = collect(unit, n)
        D[unit] = (V, C, R)
        print("  %s: %d takes in %.0fs | onset p50=%.0f ms | splice step p50="
              "%.4f vs natural p50=%.4f | attack 10-90%% p50: intact %.1f ms, "
              "CUT60 %.1f ms, RAMP60 %.1f ms"
              % (unit, len(files), time.time() - t0, np.median(meta[:, 0]) * 1000,
                 np.median(meta[:, 1]), np.median(meta[:, 2]),
                 np.nanmedian(meta[:, 3]), np.nanmedian(meta[:, 4]),
                 np.nanmedian(meta[:, 5])), flush=True)
        np.savez_compressed(os.path.join(OUT, "probe-%s.npz" % unit),
                            intact=V, cut60=C, ramp60=R, meta=meta,
                            files=np.array(files))

    report = {"n": n, "spec_hash": F.spec_hash(), "judge_spec": J.judge_spec(),
              "fine_blocks": [list(b) for b in FINE], "blocks": {}}
    Z = {}
    for unit in ("ba", "ah"):
        V, C, R = D[unit]
        s = V.std(axis=0)
        s = np.maximum(s, np.maximum(1e-9, 1e-3 * np.median(s)))
        Z[(unit, "cut")] = zshift(V, C, s, FINE)
        Z[(unit, "ramp")] = zshift(V, R, s, FINE)

    for tag, key in (("RAMP60 (honest burst removal)", "ramp"),
                     ("CUT60 (delete + splice)", "cut")):
        print()
        print("A-%s. RAW BLOCK RESPONSE to %s" % (key.upper(), tag))
        print("   RMS z-shift per dim, z by the human corpus's own per-dim")
        print("   spread on the INTACT clips. ba = a stop release removed;")
        print("   ah = the same operation where there is no release.")
        print("   AUC = can this block's response alone tell a ba clip from an")
        print("   ah clip? 0.5 = blind to the burst, 1.0 = perfect.")
        print("   %-15s%5s%10s%10s%8s%8s" % ("block", "d", "ba", "ah(ctrl)",
                                             "ratio", "AUC"))
        for bi, (name, lo, hi) in enumerate(FINE):
            zb = Z[("ba", key)][:, bi]
            za = Z[("ah", key)][:, bi]
            a_ = auc(zb, za)
            print("   %-15s%5d%10.3f%10.3f%8.2f%8.3f"
                  % (name, hi - lo, zb.mean(), za.mean(),
                     zb.mean() / za.mean() if za.mean() else float("nan"), a_))
            report["blocks"].setdefault(name, {"d": hi - lo})[key] = {
                "z_ba": float(zb.mean()), "z_ah": float(za.mean()),
                "ratio": float(zb.mean() / za.mean()) if za.mean() else None,
                "auc": float(a_)}

    units = J.load_cache()
    st = units["ba"]
    Vb, Cb, Rb = D["ba"]
    print()
    print("B. WHAT THE CURRENT JUDGE ACTUALLY COUNTS -- wdist against the")
    print("   frozen ba target, decomposed by block.")
    c_i = np.array([per_block_wdist2(v, st, FINE) for v in Vb])
    c_c = np.array([per_block_wdist2(v, st, FINE) for v in Cb])
    c_r = np.array([per_block_wdist2(v, st, FINE) for v in Rb])
    wi, wc, wr = (np.sqrt(c.sum(axis=1)) for c in (c_i, c_c, c_r))
    print("   wdist intact   %.4f +- %.4f" % (wi.mean(), wi.std()))
    print("   wdist CUT60    %.4f  (delta %+.4f = %.3f sd of the human spread,"
          " AUC vs intact %.3f)"
          % (wc.mean(), wc.mean() - wi.mean(),
             (wc.mean() - wi.mean()) / wi.std(), auc(wc, wi)))
    print("   wdist RAMP60   %.4f  (delta %+.4f = %.3f sd of the human spread,"
          " AUC vs intact %.3f)"
          % (wr.mean(), wr.mean() - wi.mean(),
             (wr.mean() - wi.mean()) / wi.std(), auc(wr, wi)))
    share = c_i.mean(axis=0) / c_i.mean(axis=0).sum()
    d_r = c_r.mean(axis=0) - c_i.mean(axis=0)
    d_c = c_c.mean(axis=0) - c_i.mean(axis=0)
    print("   %-15s%10s%12s%12s" % ("block", "share%", "d(RAMP60)", "d(CUT60)"))
    for bi, (name, lo, hi) in enumerate(FINE):
        print("   %-15s%10.1f%12.4f%12.4f" % (name, share[bi] * 100, d_r[bi], d_c[bi]))
        report["blocks"][name].update({"wdist2_share": float(share[bi]),
                                       "wdist2_d_ramp": float(d_r[bi]),
                                       "wdist2_d_cut": float(d_c[bi])})
    report.update({"wdist_intact": float(wi.mean()),
                   "wdist_intact_sd": float(wi.std()),
                   "wdist_cut60": float(wc.mean()),
                   "wdist_ramp60": float(wr.mean()),
                   "auc_cut_vs_intact": float(auc(wc, wi)),
                   "auc_ramp_vs_intact": float(auc(wr, wi))})

    print()
    print("C. THE x12 LEGACY WEIGHT -- where it lives and what it costs.")
    print("   Share of wdist^2 held by each block under three weightings of")
    print("   the SAME 996 features. Only the weights change.")
    tgt = np.asarray(st["target"])
    cj = np.array([(((Vb - tgt) / np.asarray(st["w"])) ** 2)[:, lo:hi].sum(axis=1).mean()
                   for _, lo, hi in FINE])
    w1 = _w_with_gains(Vb, {k: 1.0 for k in J.BLOCK_GAINS})
    cg = np.array([(((Vb - tgt) / w1) ** 2)[:, lo:hi].sum(axis=1).mean()
                   for _, lo, hi in FINE])
    s_all = Vb.std(axis=0)
    s_all = np.maximum(s_all, np.maximum(1e-9, 1e-3 * np.median(s_all)))
    cz = np.array([(((Vb - Vb.mean(axis=0)) / s_all) ** 2)[:, lo:hi].sum(axis=1).mean()
                   for _, lo, hi in FINE])
    print("   %-15s%13s%11s%11s" % ("block", "judge(x12)", "gains=1", "plain z"))
    for bi, (name, lo, hi) in enumerate(FINE):
        print("   %-15s%12.1f%%%10.1f%%%10.1f%%"
              % (name, cj[bi] / cj.sum() * 100, cg[bi] / cg.sum() * 100,
                 cz[bi] / cz.sum() * 100))
        report["blocks"][name].update(
            {"share_judge": float(cj[bi] / cj.sum()),
             "share_gains1": float(cg[bi] / cg.sum()),
             "share_plain_z": float(cz[bi] / cz.sum())})

    with open(os.path.join(OUT, "groundA-report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1)
    print()
    print("wrote " + os.path.join(OUT, "groundA-report.json"))


def _w_with_gains(P, gains):
    std = P.std(axis=0)
    w = std.copy()
    for name, lo, hi in F.block_ranges():
        med = float(np.median(std[lo:hi]))
        floor = max(J.W_FLOOR_ABS, J.W_FLOOR_REL * med)
        w[lo:hi] = np.maximum(std[lo:hi], floor) * np.sqrt(hi - lo) / np.sqrt(gains[name])
    return w


def main():
    os.makedirs(OUT, exist_ok=True)
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    if what in ("demo", "all"):
        demo()
    if what in ("probe", "all"):
        probe()


if __name__ == "__main__":
    main()
