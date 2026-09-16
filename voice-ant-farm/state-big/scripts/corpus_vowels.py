# -*- coding: utf-8 -*-
"""What is actually IN each training pool, vowel-wise.

Same LPC estimator as the ant measurement (two lowest poles, no bandwidth gate),
run over strongly voiced frames of a random sample of each pool. This is the
input-side number that the ant-side number has to be explained by.
"""
from __future__ import annotations

import json
import random
import sys
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(r"D:\CLAUDE\voice-ant-farm")
sys.path.insert(0, str(Path(__file__).resolve().parent))
from exemplar_formants import classify_vowel, formants_primary, is_a  # noqa: E402
from fastfeat import read_pcm16  # noqa: E402

WIN, HOP = 400, 160


def voiced(x: np.ndarray, want: int) -> list[np.ndarray]:
    n = 1 + (len(x) - WIN) // HOP
    if n <= 0:
        return []
    V = np.lib.stride_tricks.sliding_window_view(x, WIN)[::HOP][:n]
    e = (V.astype(np.float64) ** 2).sum(axis=1)
    cand = np.flatnonzero(e >= max(np.percentile(e, 70), 1e-6))
    out = []
    for i in cand[::max(1, len(cand) // (want * 3))]:
        fr = V[i].astype(np.float64)
        d = fr - fr.mean()
        d0 = float(np.dot(d, d))
        if d0 < 1e-9:
            continue
        ac = np.correlate(d, d, "full")[WIN - 1:]
        if ac[40:229].max() / d0 > 0.45:
            out.append(fr)
        if len(out) >= want:
            break
    return out


def scan(paths, per_file=8):
    F1, F2, seconds = [], [], 0.0
    for p in paths:
        try:
            x, rate = read_pcm16(p)
        except Exception:
            continue
        if rate != 16000:
            continue
        seconds += len(x) / 16000
        for fr in voiced(x, per_file):
            f = formants_primary(fr)
            if f is not None:
                F1.append(f[0]); F2.append(f[1])
    F1, F2 = np.asarray(F1), np.asarray(F2)
    if not len(F1):
        return None
    a = np.array([is_a(f1, f2) for f1, f2 in zip(F1, F2)])
    vow = Counter(classify_vowel(f1, f2)[0] for f1, f2 in zip(F1, F2)
                  if classify_vowel(f1, f2)[1])
    return {
        "frames": int(len(F1)), "sampled_seconds": round(seconds, 1),
        "f1_median": float(np.median(F1)), "f1_p90": float(np.percentile(F1, 90)),
        "f2_median": float(np.median(F2)),
        "a_rate": float(a.mean()),
        "a_frames_per_sampled_second": float(a.sum() / max(seconds, 1e-9)),
        "vowel_box_hits": dict(vow),
    }


def main() -> None:
    random.seed(7)
    items = json.loads((ROOT / "state-big" / "corpus" / "items.json").read_text(encoding="utf-8"))
    train = [i for i in items if i["split"] == "train"]
    pools = {
        "original 253 s (BEFORE)": [i for i in train if i["corpus"] == "original-253s"],
        "Iddo big (human-big)": [i for i in train if i["corpus"] == "human-big"],
        "  .. kafe sessions": [i for i in train if i["group"] == "kafe"],
        "  .. voice-input": [i for i in train if i["group"] == "vinput"],
        "  .. alma-mic": [i for i in train if i["group"] == "almamic"],
        "open multi-speaker": [i for i in train if i["corpus"] == "open"],
        "  .. FLEURS he_il": [i for i in train if i["group"] == "fleurs_he_il"],
        "  .. Common Voice 17": [i for i in train if i["group"] == "cv17_he"],
    }
    out = {}
    print(f"{'pool':<26}{'files':>7}{'hours':>8}{'frames':>9}{'F1med':>7}{'F2med':>7}"
          f"{'/a/ %':>8}{'/a/ per s':>11}  vowel boxes hit")
    for name, sel in pools.items():
        hours = sum(i["duration_s"] for i in sel) / 3600
        sample = random.sample(sel, min(400, len(sel)))
        r = scan([i["path"] for i in sample])
        if r is None:
            continue
        r.update({"pool_files": len(sel), "pool_hours": round(hours, 3)})
        out[name.strip()] = r
        boxes = ",".join(f"{k}:{v}" for k, v in sorted(r["vowel_box_hits"].items()))
        print(f"{name:<26}{len(sel):>7}{hours:>8.2f}{r['frames']:>9}"
              f"{r['f1_median']:>7.0f}{r['f2_median']:>7.0f}"
              f"{100*r['a_rate']:>8.2f}{r['a_frames_per_sampled_second']:>11.2f}  {boxes}")
    (ROOT / "state-big" / "corpus-vowels.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
