"""proof_SNN-9 — a baseline without a date and a corpus is not a baseline.

BASELINES and ORGANISM were frozen literals from 2026-08-21 and the GUI printed
a win/lose verdict 'vs organism' against them forever. Nothing re-read what the
organism scores today, and the constant could not know that the exam behind it
had since been ruled mislabeled.

  FAILS on cochlea.py.bak-rev-20260906   PASSES on the fixed cochlea.py
"""
import argparse
import os
import shutil
import sys
import tempfile
import time
import wave

import numpy as np

from _proofcommon import HERE, load, verdict

PUBLISHED = {
    "chance": 0.045454545454545456,
    "duration_only_floor": 0.05303030303030303,
    "random_real_frames_codebook": 0.4621212121212121,
    "raw_features_speech_span": 0.5378787878787878,
    "raw_features_loudest60": 0.6893939393939394,
    "prototype_organism_heldout": 0.6287878787878788,
    "frozen_cochlea_nearest_centroid": 0.7954545454545454,
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=os.path.join(HERE, "cochlea.py"))
    a = ap.parse_args()
    C = load(a.src, "cochlea_under_test")

    meta = getattr(C, "BASELINES_META", None)
    if meta is None:
        print("cochlea has no BASELINES_META: the numbers carry no date and no "
              "corpus, and the GUI compares against them anyway")
        return verdict(False, "a frozen literal cannot know its corpus changed")

    entries = meta.get("entries", {})
    dated = {k: v for k, v in entries.items()
             if v.get("measured") and v.get("corpus_sha256")}
    print(f"baselines.json: {len(entries)} entries, {len(dated)} carry both a "
          f"date and a corpus fingerprint")
    for k in sorted(entries):
        print(f"  {k:38s} {entries[k]['value']:.4%}  "
              f"measured {entries[k].get('measured')}")

    values = dict(C.BASELINES, **C.ORGANISM)
    same = all(abs(values.get(k, -1) - v) < 1e-12 for k, v in PUBLISHED.items())
    print(f"values still identical to the published ones: {same}")

    # The gate needs a signal: a changed corpus must change the fingerprint.
    tmp = tempfile.mkdtemp(prefix="proof_snn9_")
    try:
        d = os.path.join(tmp, "corpus", "train")
        os.makedirs(d)
        p = os.path.join(d, "ba_t00_0.wav")
        with wave.open(p, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes((np.zeros(4000, dtype="<i2")).tobytes())
        f1 = C.corpus_fingerprint(os.path.join(tmp, "corpus"), splits=("train",))
        time.sleep(0.01)
        os.utime(p, (time.time(), time.time() + 5))
        f2 = C.corpus_fingerprint(os.path.join(tmp, "corpus"), splits=("train",))
        moved = f1["sha256"] != f2["sha256"]
        print(f"corpus fingerprint reacts to a touched wav: {moved}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    ok = bool(dated) and len(dated) == len(entries) and same and moved
    return verdict(ok, "every comparison must say WHEN and on WHAT it was true")


if __name__ == "__main__":
    sys.exit(main())
