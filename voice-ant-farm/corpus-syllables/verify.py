#!/usr/bin/env python3
"""Independent audit of corpus-syllables/. Pure numpy -- no torch, no GPU.

Re-derives every claim from the WAV bytes on disk instead of trusting the
manifest that shipped with them: format, silence, clipping, hashes, and the
train/held-out disjointness. Also runs a discrimination probe, because the
project already learned the hard way that k-means quantisation error rewards a
codebook covering a broader feature cloud and therefore cannot tell you whether
a corpus carries phonetic structure at all.

    python verify.py
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import wave

import numpy as np

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
SR = 16000


def read_wav(path):
    with wave.open(path, "rb") as w:
        p = (w.getnchannels(), w.getsampwidth(), w.getframerate())
        raw = w.readframes(w.getnframes())
    x = np.frombuffer(raw, dtype=np.int16).astype(np.float64) / 32768.0
    return x, p, raw


def frame_features(audio, frame=400, hop=160, bands=12):
    """Byte-for-byte the ants' own 14-dim feature: log energy, ZCR, 12 log bands."""
    feats = []
    for start in range(0, max(0, audio.size - frame + 1), hop):
        seg = audio[start:start + frame]
        win = seg * np.hanning(seg.size)
        energy = np.log(np.sum(seg ** 2) + 1e-10)
        zcr = float(np.mean(np.abs(np.diff(np.sign(seg))) > 0))
        sp = np.abs(np.fft.rfft(win)) ** 2
        edges = np.linspace(0, sp.size, bands + 1).astype(int)
        band = [np.log(sp[edges[i]:edges[i + 1]].sum() + 1e-10) for i in range(bands)]
        feats.append(np.array([energy, zcr] + band))
    return np.array(feats) if feats else np.zeros((0, 2 + bands))


def voiced_profile(x):
    """Mean+std of features over the loudest 60% of frames, then z-scored.

    Restricted to loud frames because the padding is deliberately near-silent
    room tone; including it would let the probe classify on how much silence a
    clip happens to carry rather than on its phonetics.
    """
    f = frame_features(x)
    if f.shape[0] < 4:
        return np.zeros(28)
    keep = f[:, 0] >= np.quantile(f[:, 0], 0.40)
    f = f[keep] if keep.sum() >= 3 else f
    return np.concatenate([f.mean(axis=0), f.std(axis=0)])


def main():
    man = json.load(open(os.path.join(HERE, "manifest.json"), encoding="utf-8"))
    entries = man["entries"]
    print(f"manifest: {len(entries)} entries, {len(man['base_renderings'])} base renderings\n")

    problems = []
    rows = {}
    pcm_sha = {}
    for e in entries:
        path = os.path.join(HERE, e["path"].replace("/", os.sep))
        if not os.path.exists(path):
            problems.append(f"MISSING {e['path']}")
            continue
        x, (ch, sw, fr), raw = read_wav(path)
        if (ch, sw, fr) != (1, 2, SR):
            problems.append(f"FORMAT {e['path']} ch={ch} width={sw} rate={fr}")
        r = float(np.sqrt(np.mean(x ** 2))) if x.size else 0.0
        peak = float(np.max(np.abs(x))) if x.size else 0.0
        if r < 1e-4:
            problems.append(f"SILENT {e['path']} rms={r:.2e}")
        if peak >= 0.999:
            problems.append(f"CLIP {e['path']} peak={peak:.4f}")
        n_at_full = int(np.sum(np.abs(x) >= 32767 / 32768.0))
        if n_at_full:
            problems.append(f"CLIPSAMPLES {e['path']} n={n_at_full}")
        got = hashlib.sha256(open(path, "rb").read()).hexdigest()
        if got != e["file_sha256"]:
            problems.append(f"SHA {e['path']}")
        if abs(r - e["rms"]) > 2e-3:
            problems.append(f"RMSDRIFT {e['path']} disk={r:.5f} manifest={e['rms']}")
        rows.setdefault(e["split"], []).append((e, x, r, peak))
        pcm_sha.setdefault(hashlib.sha256(raw).hexdigest(), []).append(e["path"])

    dupes = {k: v for k, v in pcm_sha.items() if len(v) > 1}
    if dupes:
        problems.append(f"DUPLICATE AUDIO: {list(dupes.values())[:3]}")

    print("=== format / level ===")
    tot_files = tot_secs = 0
    for split in ("train", "heldout", "words"):
        rs = rows.get(split, [])
        if not rs:
            continue
        secs = sum(e["duration_s"] for e, _, _, _ in rs)
        rr = np.array([r for _, _, r, _ in rs])
        pk = np.array([p for _, _, _, p in rs])
        tot_files += len(rs)
        tot_secs += secs
        print(f"{split:8s} {len(rs):4d} files {secs:8.2f}s  "
              f"rms {rr.min():.4f}-{rr.max():.4f} (med {np.median(rr):.4f}, "
              f"{20*np.log10(np.median(rr)):.1f} dBFS)  peak max {pk.max():.4f}")
    print(f"{'TOTAL':8s} {tot_files:4d} files {tot_secs:8.2f}s")

    print("\n=== split disjointness ===")
    base_ids, base_shas, aug_seeds = {}, {}, {}
    for e in entries:
        base_ids.setdefault(e["split"], set()).add(e["base_rendering_id"])
        base_shas.setdefault(e["split"], set()).add(e["base_pcm_sha256"])
        aug_seeds.setdefault(e["split"], set()).add(e["aug_seed"])
    names = ["train", "heldout", "words"]
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = names[i], names[j]
            sid = base_ids[a] & base_ids[b]
            ssh = base_shas[a] & base_shas[b]
            sse = aug_seeds[a] & aug_seeds[b]
            print(f"  {a:7s} vs {b:7s}: shared base ids {len(sid)}, "
                  f"shared base audio (sha256) {len(ssh)}, shared aug seeds {len(sse)}")
            if sid or ssh or sse:
                problems.append(f"OVERLAP {a}/{b}")
    lo_t, hi_t = man["seed_ranges"]["train_aug"]
    lo_h, hi_h = man["seed_ranges"]["heldout_aug"]
    print(f"  aug seed ranges: train [{lo_t},{hi_t}] heldout [{lo_h},{hi_h}] "
          f"-> overlap {max(0, min(hi_t,hi_h)-max(lo_t,lo_h)+1)}")

    print("\n=== discrimination probe (1-NN, train -> heldout) ===")
    print("    quantisation error is not usable here; this measures whether the")
    print("    22 classes are separable in the ants' own 14-dim feature space.")
    tr = [(e["item_id"], voiced_profile(x)) for e, x, _, _ in rows["train"]]
    ho = [(e["item_id"], voiced_profile(x)) for e, x, _, _ in rows["heldout"]]
    Xtr = np.array([v for _, v in tr])
    ytr = np.array([k for k, _ in tr])
    Xho = np.array([v for _, v in ho])
    yho = np.array([k for k, _ in ho])
    mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-9
    Xtr, Xho = (Xtr - mu) / sd, (Xho - mu) / sd
    d = ((Xho[:, None, :] - Xtr[None, :, :]) ** 2).sum(-1)
    pred = ytr[np.argmin(d, axis=1)]
    acc = float(np.mean(pred == yho))
    top5 = np.mean([yho[i] in ytr[np.argsort(d[i])[:5]] for i in range(len(yho))])
    print(f"  held-out 1-NN accuracy : {acc*100:.1f}%  (chance {100/22:.1f}%)")
    print(f"  held-out top-5 accuracy: {top5*100:.1f}%")

    nn_dist = np.sqrt(d.min(axis=1))
    dw = ((Xho[:, None, :] - Xho[None, :, :]) ** 2).sum(-1)
    np.fill_diagonal(dw, np.inf)
    print(f"  nearest train neighbour distance: median {np.median(nn_dist):.3f} "
          f"min {nn_dist.min():.3f}")
    print(f"  nearest heldout-internal distance: median "
          f"{np.median(np.sqrt(dw.min(axis=1))):.3f}")
    if nn_dist.min() < 1e-3:
        problems.append("LEAK: a held-out clip is numerically identical to a train clip")

    print("\n=== result ===")
    if problems:
        print(f"{len(problems)} PROBLEM(S):")
        for p in problems[:25]:
            print("  " + p)
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
