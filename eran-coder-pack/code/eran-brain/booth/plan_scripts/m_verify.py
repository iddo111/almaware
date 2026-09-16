# -*- coding: utf-8 -*-
"""Re-measure, myself, the four claims the plan leans on that I inherited."""
import json, collections
import numpy as np

rows = json.load(open("feats.json"))
rows.sort(key=lambda r: r["mtime"])
sit = 0; last = None
for r in rows:
    if last is not None and r["mtime"] - last > 120: sit += 1
    r["sit"] = sit; last = r["mtime"]
X = np.array([r["vec"] for r in rows])
mu, sd = X.mean(0), X.std(0) + 1e-9
Z = (X - mu) / sd
for i, r in enumerate(rows): r["z"] = Z[i]
DEEP = ["ah", "ba", "ma", "ima", "ih", "abba"]
by = collections.defaultdict(list)
for r in rows:
    if r["unit"] in DEEP: by[r["unit"]].append(r)
for u in by: by[u].sort(key=lambda r: r["take"])


def nn1(Xtr, ytr, Xte, yte):
    d = (Xte * Xte).sum(1)[:, None] + (Xtr * Xtr).sum(1)[None, :] - 2.0 * (Xte @ Xtr.T)
    return float(np.mean(ytr[np.argmin(d, axis=1)] == yte))


def two_way(a, b, N, rng, draws=400):
    """train on N takes from the EARLY third, test on the LATE third: time-separated."""
    accs = []
    A, B = by[a], by[b]
    for _ in range(draws):
        tr_x, tr_y, te_x, te_y = [], [], [], []
        ok = True
        for u, U in ((a, A), (b, B)):
            early = [r for r in U if r["take"] <= 32]
            late = [r for r in U if r["take"] >= 67]
            if len(early) < N or len(late) < 8: ok = False; break
            for r in rng.choice(len(early), N, replace=False):
                tr_x.append(early[r]["z"]); tr_y.append(u)
            for r in rng.choice(len(late), 8, replace=False):
                te_x.append(late[r]["z"]); te_y.append(u)
        if not ok: return None
        accs.append(nn1(np.array(tr_x), np.array(tr_y), np.array(te_x), np.array(te_y)))
    return float(np.mean(accs))


rng = np.random.default_rng(0)
print("TWO-WAY CONTRASTS, train on takes 0-32, test on takes 67-99 (time-separated)")
print("chance = 50.0%   (units with >=100 takes only)")
for pair, kind in [(("ah", "ih"), "VOWEL"), (("ba", "ma"), "CONSONANT"),
                   (("ba", "abba"), "CONSONANT"), (("ah", "ba"), "CONSONANT"),
                   (("ih", "ima"), "CONSONANT"), (("ah", "ima"), "VOWEL")]:
    for N in (10, 33):
        a = two_way(pair[0], pair[1], N, rng)
        if a is not None:
            print("   %-9s {%s,%s}  N=%2d  %.1f%%" % (kind, pair[0], pair[1], N, 100 * a))

print("\nPROTOTYPE COSINE: same syllable across two sittings vs different syllables")
psit = {}
for r in rows:
    if r["unit"] in DEEP: psit.setdefault((r["unit"], r["sit"]), []).append(r["z"])
psit = {k: np.mean(v, 0) for k, v in psit.items() if len(v) >= 8}
def cos(a, b): return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b)))
same = []
for u in DEEP:
    ks = [k for k in psit if k[0] == u]
    for i in range(len(ks)):
        for j in range(i + 1, len(ks)):
            same.append((u, ks[i][1], ks[j][1], cos(psit[ks[i]], psit[ks[j]])))
diff = []
us = sorted(set(k[0] for k in psit))
for i in range(len(us)):
    for j in range(i + 1, len(us)):
        a = np.mean([psit[k] for k in psit if k[0] == us[i]], 0)
        b = np.mean([psit[k] for k in psit if k[0] == us[j]], 0)
        diff.append((us[i], us[j], cos(a, b)))
print("   SAME syllable, two sittings (n=%d):" % len(same))
for u, s1, s2, c in sorted(same, key=lambda t: t[3]):
    print("      %-5s sit%d vs sit%d  cos %.4f" % (u, s1, s2, c))
print("      mean %.4f" % np.mean([t[3] for t in same]))
print("   DIFFERENT syllables (n=%d): mean %.4f  closest pair %s/%s %.4f" %
      (len(diff), np.mean([t[2] for t in diff]),
       max(diff, key=lambda t: t[2])[0], max(diff, key=lambda t: t[2])[1],
       max(diff, key=lambda t: t[2])[2]))

print("\nPER-UNIT RECALL, 6-way, train early block / test late block (time-separated)")
print("chance = 16.67%")
for N in (3, 10, 33):
    rec = collections.Counter(); tot = collections.Counter()
    for _ in range(400):
        tr_x, tr_y, te_x, te_y = [], [], [], []
        for u in DEEP:
            early = [r for r in by[u] if r["take"] <= 32]
            late = [r for r in by[u] if r["take"] >= 67]
            for k in rng.choice(len(early), N, replace=False):
                tr_x.append(early[k]["z"]); tr_y.append(u)
            for k in rng.choice(len(late), 8, replace=False):
                te_x.append(late[k]["z"]); te_y.append(u)
        Xtr = np.array(tr_x); ytr = np.array(tr_y); Xte = np.array(te_x); yte = np.array(te_y)
        d = (Xte * Xte).sum(1)[:, None] + (Xtr * Xtr).sum(1)[None, :] - 2.0 * (Xte @ Xtr.T)
        pred = ytr[np.argmin(d, axis=1)]
        for p, y in zip(pred, yte):
            tot[y] += 1
            if p == y: rec[y] += 1
    print("   N=%2d  overall %.1f%%   " % (N, 100 * sum(rec.values()) / sum(tot.values())) +
          "  ".join("%s %.1f%%" % (u, 100 * rec[u] / tot[u]) for u in DEEP))
