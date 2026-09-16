# -*- coding: utf-8 -*-
"""make_listening_kit.py -- build ~/ear-v3/listening-kit/ for Iddo's human
gate (plan item 8). ASCII filenames here (ssh-safe); manifest.json carries
the final Hebrew names + why each file is in the kit; the PC side renames.

Contents:
  pitch-70.wav / pitch-290.wav   same tract shape (uniform 34x1.0), f0=70
                                 vs 290, seed 0 -- the pair the OLD ear
                                 could not tell apart (raw-192 L2 0.158).
  abba-real.wav                  the real abba take the ear classifies with
                                 the LARGEST margin (its "clearest abba").
  abba-fake-splice.wav           real ah + 0.25 s silence + real ah, the
                                 splice cheat -- ear puts it 11.7 wdist from
                                 abba (real clips sit <= 6.0).
  best-1/2.wav, worst-1/2.wav    the 2 real clips the ear LOO-classifies
                                 with the largest margin and the 2 it gets
                                 most wrong (distinct units each).
"""
import json
import os
import shutil
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))
sys.path.insert(0, os.path.join(ROOT, "legacy"))

import _common                     # noqa: E402
from ear3 import features as F     # noqa: E402
from ear3 import judge as J        # noqa: E402
from ear3 import calib as C        # noqa: E402
import mouth34                     # noqa: E402
import wave                        # noqa: E402

KIT = os.path.join(ROOT, "listening-kit")
HEB_UNIT = {"ah": "אה", "ba": "בה", "ih": "אי",
            "ma": "מה", "abba": "אבא", "ima": "אמא"}


def write_wav(path, x, fs=16000):
    x = np.asarray(x, dtype=np.float64)
    pcm = np.clip(x * 32767.0, -32768, 32767).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(fs)
        w.writeframes(pcm.tobytes())


def loo_margins(z, idx, units):
    """Per clip: (name, unit, pred, d_own_loo, d_best_other, rel_margin).
    rel_margin > 0 = correct with room; < 0 = misclassified."""
    X = z["X"]
    names = [str(n) for n in z["names"]]
    full = {u: (X[idx[u]].mean(axis=0),
                J.spread_floor(X[idx[u]].std(axis=0))) for u in units}
    rows = []
    for u in units:
        P = X[idx[u]]
        n = P.shape[0]
        S, Q = P.sum(axis=0), (P ** 2).sum(axis=0)
        for k, i in enumerate(idx[u]):
            v = X[i]
            m = (S - v) / (n - 1)
            var = np.maximum((Q - v ** 2) / (n - 1) - m ** 2, 0.0)
            w = J.spread_floor(np.sqrt(var))
            d_own = float(np.sqrt(np.sum(((v - m) / w) ** 2)))
            others = {cu: float(np.sqrt(np.sum(
                ((v - full[cu][0]) / full[cu][1]) ** 2)))
                for cu in units if cu != u}
            best_o = min(others, key=others.get)
            d_o = others[best_o]
            pred = u if d_own < d_o else best_o
            rows.append({"name": names[i], "unit": u, "pred": pred,
                         "d_own": d_own, "d_other": d_o,
                         "margin": (d_o - d_own) / d_own})
    return rows


def pick_distinct(rows, k=2):
    out, seen = [], set()
    for r in rows:
        if r["unit"] not in seen:
            out.append(r)
            seen.add(r["unit"])
        if len(out) == k:
            break
    return out


def main():
    os.makedirs(KIT, exist_ok=True)
    z = _common.load_t06()
    names, idx = _common.by_unit(z)
    units = J.UNITS
    manifest = {"files": []}

    def add(ascii_name, heb_name, why_he, why_en, src=None, meta=None):
        manifest["files"].append({
            "ascii": ascii_name, "hebrew": heb_name,
            "why_he": why_he, "why_en": why_en,
            "source": src, "meta": meta or {}})

    # 1+2 -- the pitch pair
    areas = np.ones(34)
    for f0, ascii_name, heb in (
            (70.0, "pitch-70.wav", "1-זוג-גובה-צליל-70.wav"),
            (290.0, "pitch-290.wav", "2-זוג-גובה-צליל-290.wav")):
        r = mouth34.say(areas, f0=f0, seconds=0.5, seed=0)
        assert r is not None
        write_wav(os.path.join(KIT, ascii_name), r)
        add(ascii_name, heb,
            f"אותה צורת פה בדיוק, גובה צליל {f0:.0f} הרץ",
            f"same mouth shape exactly, pitch {f0:.0f} Hz",
            src="mouth34.say(uniform, seed 0)",
            meta={"f0": f0})

    # 3 -- clearest real abba
    rows = loo_margins(z, idx, units)
    abba_best = max((r for r in rows if r["unit"] == "abba"
                     and r["pred"] == "abba"), key=lambda r: r["margin"])
    src = os.path.join(_common.CORPUS, abba_best["name"])
    shutil.copy2(src, os.path.join(KIT, "abba-real.wav"))
    add("abba-real.wav", "3-אבא-אמיתי.wav",
        "הקלטה אמיתית של עידו אומר אבא — זו שהאוזן הכי בטוחה בה",
        "a real take of Iddo saying abba -- the one the ear is surest of",
        src=abba_best["name"], meta=abba_best)

    # 4 -- the splice fake (same construction as test_splice)
    ah2 = sorted(C.clips("ah"))[:2]
    fake = np.concatenate([F.read_wav(ah2[0]),
                           np.zeros(4000, dtype=np.float32),
                           F.read_wav(ah2[1])])
    write_wav(os.path.join(KIT, "abba-fake-splice.wav"), fake)
    cache = J.load_cache()
    dfake = J.wdist(F.features(fake), cache["abba"])
    add("abba-fake-splice.wav", "4-אבא-מזויף-הדבקה.wav",
        "זיוף: שתי הקלטות אה אמיתיות מודבקות עם שקט באמצע — לא אבא",
        "a fake: two real ah takes glued with silence -- NOT abba",
        src=f"{os.path.basename(ah2[0])} + 0.25s silence + "
            f"{os.path.basename(ah2[1])}",
        meta={"wdist_to_abba": round(dfake, 2),
              "real_abba_max": round(cache["abba"]["real_wdist_max"], 2)})

    # 5-8 -- best 2 / worst 2 LOO clips (distinct units)
    correct = sorted((r for r in rows if r["pred"] == r["unit"]),
                     key=lambda r: -r["margin"])
    wrong = sorted((r for r in rows if r["pred"] != r["unit"]),
                   key=lambda r: r["margin"])
    for i, r in enumerate(pick_distinct(correct, 2), start=1):
        ascii_name = f"best-{i}.wav"
        shutil.copy2(os.path.join(_common.CORPUS, r["name"]),
                     os.path.join(KIT, ascii_name))
        add(ascii_name, f"{4 + i}-הכי-ברור-{HEB_UNIT[r['unit']]}.wav",
            f"ההקלטה שהאוזן מזהה הכי בקלות ({HEB_UNIT[r['unit']]})",
            f"the take the ear finds easiest ({r['unit']})",
            src=r["name"], meta=r)
    for i, r in enumerate(pick_distinct(wrong, 2), start=1):
        ascii_name = f"worst-{i}.wav"
        shutil.copy2(os.path.join(_common.CORPUS, r["name"]),
                     os.path.join(KIT, ascii_name))
        add(ascii_name,
            f"{6 + i}-הכי-קשה-{HEB_UNIT[r['unit']]}"
            f"-נשמע-כמו-{HEB_UNIT[r['pred']]}.wav",
            f"ההקלטה שהאוזן הכי טועה בה: {HEB_UNIT[r['unit']]} "
            f"שנשמע לה כמו {HEB_UNIT[r['pred']]}",
            f"the take the ear gets most wrong: real {r['unit']} "
            f"heard as {r['pred']}",
            src=r["name"], meta=r)

    with open(os.path.join(KIT, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    print(f"kit written to {KIT}:")
    for e in manifest["files"]:
        print(f"  {e['ascii']:22s} -> {e['hebrew']}   [{e['source']}]")


if __name__ == "__main__":
    main()
