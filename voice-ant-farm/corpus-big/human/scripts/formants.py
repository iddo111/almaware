# -*- coding: utf-8 -*-
"""Does the new corpus actually contain clean /a/ vowels?

LPC formant scan (pure numpy) over voiced frames, same measurement family as the
diagnosis that found ant-a/ant-d at F1=660 F2=1064 and Iddo's training
recordings at F1=510-546. /a/ target: F1 650-850, F2 1000-1500.
"""
import sys, os, json, glob, random, wave
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SR = 16000
WIN = 400
HOP = 160
ORDER = 12


def levinson(r, order):
    a = np.zeros(order + 1); a[0] = 1.0
    e = r[0]
    if e <= 0: return None
    for i in range(1, order + 1):
        acc = r[i] + np.dot(a[1:i], r[i - 1:0:-1]) if i > 1 else r[1]
        k = -acc / e
        a_new = a.copy()
        for j in range(1, i):
            a_new[j] = a[j] + k * a[i - j]
        a_new[i] = k
        a = a_new
        e *= (1 - k * k)
        if e <= 0: return None
    return a


def formants(frame):
    x = frame - frame.mean()
    x = np.append(x[0], x[1:] - 0.97 * x[:-1])       # pre-emphasis
    x = x * np.hamming(len(x))
    r = np.correlate(x, x, 'full')[len(x) - 1:len(x) + ORDER]
    if r[0] <= 1e-9: return None
    a = levinson(r / r[0], ORDER)
    if a is None: return None
    try:
        rts = np.roots(a)
    except Exception:
        return None
    rts = rts[np.imag(rts) > 0]
    if len(rts) == 0: return None
    f = np.angle(rts) * SR / (2 * np.pi)
    bw = -0.5 * (SR / (2 * np.pi)) * np.log(np.abs(rts) + 1e-12)
    keep = (f > 200) & (f < 5000) & (bw < 400)
    f = np.sort(f[keep])
    return f if len(f) >= 2 else None


def voiced_frames(x, want):
    """Return up to `want` strongly-voiced, high-energy frames."""
    n = 1 + (len(x) - WIN) // HOP
    if n <= 0: return []
    V = np.lib.stride_tricks.sliding_window_view(x, WIN)[::HOP][:n]
    e = np.sum(V.astype(np.float64) ** 2, axis=1)
    if not len(e): return []
    thr = np.percentile(e, 70)
    cand = np.flatnonzero(e >= max(thr, 1e-6))
    if len(cand) == 0: return []
    random.shuffle(list(cand))
    out = []
    for i in cand[:: max(1, len(cand) // (want * 3))]:
        fr = V[i].astype(np.float64)
        d = fr - fr.mean()
        d0 = np.dot(d, d)
        if d0 < 1e-9: continue
        ac = np.correlate(d, d, 'full')[WIN - 1:]
        seg = ac[40:229]
        if len(seg) == 0: continue
        if seg.max() / d0 > 0.45:            # clearly voiced
            out.append(fr)
        if len(out) >= want: break
    return out


def scan(paths, want_per_file=6, label=''):
    F1, F2 = [], []
    for p in paths:
        try:
            with wave.open(p) as w:
                if w.getframerate() != SR: continue
                x = np.frombuffer(w.readframes(w.getnframes()), '<i2').astype(np.float32) / 32768.0
        except Exception:
            continue
        for fr in voiced_frames(x, want_per_file):
            f = formants(fr)
            if f is not None and len(f) >= 2:
                F1.append(f[0]); F2.append(f[1])
    F1 = np.array(F1); F2 = np.array(F2)
    if len(F1) == 0:
        print('%-28s no frames' % label); return
    isa = (F1 >= 650) & (F1 <= 850) & (F2 >= 1000) & (F2 <= 1500)
    print('%-28s n=%-6d  F1 med=%3.0f p90=%3.0f   F2 med=%4.0f   /a/-region frames=%5.2f%%'
          % (label, len(F1), np.median(F1), np.percentile(F1, 90), np.median(F2), 100.0 * isa.mean()))
    return isa.mean()


if __name__ == '__main__':
    random.seed(7)
    old = sorted(glob.glob(r'D:\CLAUDE\voice-ant-farm\recordings\*\*.wav'))
    scan(old, want_per_file=40, label='OLD corpus (253 s, n=24)')
    root = r'D:\CLAUDE\voice-ant-farm\corpus-big\human'
    m = json.load(open(os.path.join(root, 'manifest.json'), encoding='utf-8'))
    for grp in ['vinput', 'almamic', 'kafe']:
        ps = [os.path.join(root, e['path']) for e in m['entries'] if e['source_group'] == grp]
        random.shuffle(ps)
        scan(ps[:500], want_per_file=8, label='NEW ' + grp)
    ps = [os.path.join(root, e['path']) for e in m['entries'] if e['split'] == 'train']
    random.shuffle(ps)
    scan(ps[:900], want_per_file=8, label='NEW train (all sources)')
