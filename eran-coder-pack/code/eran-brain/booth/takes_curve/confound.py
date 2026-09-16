"""confound.py -- THE CONFOUND, and how big it is.

The mtimes say the six deep units were NOT interleaved. Each unit owns its own
stretch of the day:

    ah    09:12 (3)   13:00-13:03 (73)   13:24-13:25 (24)
    ba    13:25-13:29 (100)
    abba  13:29-13:33 (100)
    ih    13:34-13:35 (24)   14:40-14:43 (76)
    ma    14:43-14:45 (34)   15:24-15:25 (24)   20:07-20:08 (42)
    ima   20:08-20:12 (100)

So "which unit" and "which minute of 2026-08-23" are nearly the same variable.
A 1-NN can score by matching recording conditions -- mic gain, distance, room,
how tired his voice was -- and never touch phonetics. This is the session-leak
scar in its purest form, and it means every 6-way number measured above is an
UPPER BOUND, not ERAN's phonetic discrimination.

Three probes, each answering a question the 6-way accuracy cannot:

  P1 SESSION CUE   Using clips of ONE unit only -- so phonetics is held constant
                   by construction -- can the ear tell which sub-session a clip
                   came from? Anything well above chance is a pure recording-
                   condition cue, present and available to any classifier.

  P2 DURATION LEAK Can clip DURATION alone, one number, classify the six units?
                   If it can, part of the 6-way score is a stopwatch.

  P3 CROSS-SESSION On the three units that DO have several sub-sessions
                   (ah, ma, ih -- a 3-way task, chance 33.33%): train inside one
                   sub-session and test in a DIFFERENT one, versus train and
                   test inside the same one, at matched N. The drop is what
                   repeats-in-one-sitting fail to buy.
"""
import glob
import json
import os
import sys
import wave

import numpy as np

CACHE = r"C:\Users\<user>\AppData\Local\Temp\claude\D--CLAUDE\8aa52163-564a-4846-8f48-cd46afaf48f4\scratchpad\t06_cochlea.npz"
STAGED = r"D:\CLAUDE\eran-brain\booth\staged\t06"
OUT = r"D:\CLAUDE\eran-brain\booth\TAKES-CURVE.json"
DEEP = ["ah", "ba", "ma", "ima", "ih", "abba"]
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

d = np.load(CACHE, allow_pickle=True)
X, unit, take = d["X"], d["unit"].astype(str), d["take"].astype(int)

# durations + mtimes, aligned to the cache order (both are sorted by filename)
paths = sorted(glob.glob(os.path.join(STAGED, "*.wav")))
dur, mt = [], []
for p in paths:
    with wave.open(p, "rb") as w:
        dur.append(w.getnframes() / float(w.getframerate()))
    mt.append(os.path.getmtime(p))
dur, mt = np.array(dur), np.array(mt)
names = [os.path.basename(p)[:-4] for p in paths]
assert list(unit) == [n.split("_")[0] for n in names]
assert list(take) == [int(n.split("_")[2]) for n in names]

# sub-session id per clip
SUB = np.zeros(len(unit), dtype=int)
subs = {}
for u in sorted(set(unit.tolist())):
    m = np.where(unit == u)[0]
    m = m[np.argsort(take[m])]
    t = mt[m]
    sid = np.concatenate([[0], np.cumsum(np.diff(t) > 60.0)])
    SUB[m] = sid
    subs[u] = [m[sid == k] for k in range(sid.max() + 1)]


def nn(Xtr, ytr, Xte, yte):
    mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-9
    A, B = (Xtr - mu) / sd, (Xte - mu) / sd
    dd = ((B[:, None, :] - A[None, :, :]) ** 2).sum(-1)
    return float(np.mean(ytr[np.argmin(dd, axis=1)] == yte))


res = {}
# ============================ P1 -- THE SESSION CUE ========================
print("=" * 80)
print("P1  SESSION CUE -- one unit at a time, so phonetics is CONSTANT.")
print("    Can the frozen cochlea say which sub-session a clip came from?")
print("=" * 80)
print("%6s | %4s | %8s | %8s | %8s | %s"
      % ("unit", "subs", "n", "acc", "chance", "verdict"))
p1 = {}
for u in ("ah", "ma", "ih"):
    segs = subs[u]
    rows = np.concatenate(segs)
    y = np.concatenate([np.full(len(s), k) for k, s in enumerate(segs)])
    accs = []
    for seed in range(30):
        rng = np.random.RandomState(500 + seed)
        # stratified half/half split WITHIN each sub-session
        tr, te = [], []
        for k, s in enumerate(segs):
            p = rng.permutation(len(s))
            h = len(s) // 2
            tr += list(np.where(y == k)[0][p[:h]])
            te += list(np.where(y == k)[0][p[h:]])
        tr, te = np.array(tr), np.array(te)
        accs.append(nn(X[rows[tr]], y[tr], X[rows[te]], y[te]))
    # chance = the majority sub-session's share (the honest baseline here)
    ch = max(len(s) for s in segs) / float(len(rows)) * 100
    p1[u] = {"n_sub_sessions": len(segs), "n_clips": int(len(rows)),
             "acc_pct": float(np.mean(accs) * 100),
             "sd_pct": float(np.std(accs) * 100), "majority_baseline_pct": ch}
    print("%6s | %4d | %8d | %6.2f%% | %6.2f%% | %s"
          % (u, len(segs), len(rows), np.mean(accs) * 100, ch,
             "SESSION IS READABLE" if np.mean(accs) * 100 > ch + 10 else "weak"))
res["P1_session_cue"] = p1

# ============================ P2 -- DURATION LEAK ==========================
print()
print("=" * 80)
print("P2  DURATION LEAK -- 1-NN on clip length ALONE (one number, no audio).")
print("    6 units, design-D protocol (leave a block of 10 out). CHANCE 16.67%")
print("=" * 80)
Dfeat = dur[:, None]
idx = {}
for u in DEEP:
    rows = np.where(unit == u)[0]
    idx[u] = rows[np.argsort(take[rows])]
p2 = {}
for N in (10, 30, 70):
    a_dur, a_ear = [], []
    for b in range(10):
        test_t = np.arange(b * 10, (b + 1) * 10)
        pool = np.setdiff1d(np.arange(100), test_t)
        for s in range(3):
            rng = np.random.RandomState(7000 + b * 97 + s)
            tr = {u: rng.permutation(pool)[:N] for u in DEEP}
            tr_r = np.concatenate([idx[u][tr[u]] for u in DEEP])
            te_r = np.concatenate([idx[u][test_t] for u in DEEP])
            a_dur.append(nn(Dfeat[tr_r], unit[tr_r], Dfeat[te_r], unit[te_r]))
            a_ear.append(nn(X[tr_r], unit[tr_r], X[te_r], unit[te_r]))
    p2[str(N)] = {"N": N, "duration_only_pct": float(np.mean(a_dur) * 100),
                  "duration_only_sd": float(np.std(a_dur) * 100),
                  "full_ear_pct": float(np.mean(a_ear) * 100)}
    print("  N=%2d : duration alone %6.2f%% (sd %4.2f)   full 192-d ear %6.2f%%"
          "   chance 16.67%%"
          % (N, np.mean(a_dur) * 100, np.std(a_dur) * 100, np.mean(a_ear) * 100))
res["P2_duration_leak"] = p2

# ============================ P3 -- CROSS-SESSION ==========================
print()
print("=" * 80)
print("P3  CROSS-SESSION vs SAME-SESSION, 3 units that have several sub-sessions")
print("    (ah, ma, ih).  CHANCE = 33.33%.  Matched N in both conditions.")
print("=" * 80)
U3 = ["ah", "ma", "ih"]
# usable sub-sessions: need >= 2 per unit with enough clips
pairs = {u: [s for s in subs[u] if len(s) >= 20] for u in U3}
for u in U3:
    print("    %s: %d usable sub-session(s) of >=20 clips, sizes %s"
          % (u, len(pairs[u]), [len(s) for s in pairs[u]]))
print()
print("%4s | %16s | %16s | %10s | chance"
      % ("N", "SAME-session", "CROSS-session", "drop"))
p3 = {}
for N in (1, 2, 3, 5, 8, 10, 15, 20):
    same, cross = [], []
    for seed in range(40):
        rng = np.random.RandomState(900 + seed)
        tr_s, te_s, tr_c, te_c, ys, yc, yts, ytc = [], [], [], [], [], [], [], []
        ok = True
        for u in U3:
            ss = pairs[u]
            if len(ss) < 2:
                ok = False
                break
            a, b = rng.choice(len(ss), 2, replace=False)
            A, B = ss[a], ss[b]
            if len(A) < N + 10 or len(B) < 10:
                ok = False
                break
            pa = rng.permutation(len(A))
            # SAME: train N from A, test 10 others from A
            tr_s += list(A[pa[:N]]); ys += [u] * N
            te_s += list(A[pa[N:N + 10]]); yts += [u] * 10
            # CROSS: train the SAME N from A, test 10 from B
            pb = rng.permutation(len(B))
            tr_c += list(A[pa[:N]]); yc += [u] * N
            te_c += list(B[pb[:10]]); ytc += [u] * 10
        if not ok:
            continue
        same.append(nn(X[np.array(tr_s)], np.array(ys),
                       X[np.array(te_s)], np.array(yts)))
        cross.append(nn(X[np.array(tr_c)], np.array(yc),
                        X[np.array(te_c)], np.array(ytc)))
    if not same:
        continue
    p3[str(N)] = {"N": N, "same_session_pct": float(np.mean(same) * 100),
                  "same_sd": float(np.std(same) * 100),
                  "cross_session_pct": float(np.mean(cross) * 100),
                  "cross_sd": float(np.std(cross) * 100),
                  "drop_points": float((np.mean(same) - np.mean(cross)) * 100),
                  "draws": len(same)}
    print("%4d | %7.2f%% sd %5.2f | %7.2f%% sd %5.2f | %+8.2f | 33.33%%"
          % (N, np.mean(same) * 100, np.std(same) * 100,
             np.mean(cross) * 100, np.std(cross) * 100,
             (np.mean(same) - np.mean(cross)) * 100))
res["P3_cross_session_3way"] = p3

print()
print("=" * 80)
print("READ-OUT")
print("=" * 80)
if p3:
    ks = sorted(p3, key=lambda k: int(k))
    lo, hi = p3[ks[0]], p3[ks[-1]]
    print("  SAME-session   N=%s -> N=%s : %.2f%% -> %.2f%%  (+%.2f points)"
          % (ks[0], ks[-1], lo["same_session_pct"], hi["same_session_pct"],
             hi["same_session_pct"] - lo["same_session_pct"]))
    print("  CROSS-session  N=%s -> N=%s : %.2f%% -> %.2f%%  (+%.2f points)"
          % (ks[0], ks[-1], lo["cross_session_pct"], hi["cross_session_pct"],
             hi["cross_session_pct"] - lo["cross_session_pct"]))
    print("  chance 33.33%. If the CROSS curve flattens far earlier than the SAME")
    print("  curve, extra repeats inside one sitting stop buying cross-time skill.")

with open(OUT, "r", encoding="utf-8") as f:
    results = json.load(f)
results["CONFOUND"] = res
results["CONFOUND_note"] = (
    "The six deep units were each recorded in their own stretch of 2026-08-23 "
    "(ah 09:12+13:00+13:24, ba 13:25, abba 13:29, ih 13:34+14:40, ma 14:43+15:24"
    "+20:07, ima 20:08). Unit identity and recording-time identity are nearly the "
    "same variable, so every 6-way number in this file is an UPPER BOUND on "
    "phonetic discrimination, not a measurement of it.")
results["session_map"] = {u: [[int(take[s].min()), int(take[s].max()), int(len(s))]
                              for s in subs[u]] for u in sorted(subs)}
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2, ensure_ascii=False)
print()
print("raw numbers -> %s" % OUT)
