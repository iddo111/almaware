"""proof_SNN-8 — the cochlear cache must know which corpus it heard.

load_syllables() returned data/syllables_cochlea.npz whenever the file existed.
Its keys were exactly ['xtr','ytr','xte','yte'] — no count, no mtime, no
manifest hash — so re-recording, adding or relabelling a wav would have left
the lab training on the 2026-08-21 snapshot forever, silently, and the new
audio would never have reached the network.

Runs against a throw-away corpus in /tmp; the real one is never touched.

  FAILS on train.py.bak-rev-20260906   PASSES on the fixed train.py
"""
import argparse
import os
import shutil
import sys
import tempfile
import wave

import numpy as np

from _proofcommon import HERE, load, verdict


def write_wav(path, freq, seconds=0.3, rate=16000):
    n = int(rate * seconds)
    t = np.arange(n) / rate
    x = 0.3 * np.sin(2 * np.pi * freq * t) + 0.02 * np.sin(2 * np.pi * 3 * freq * t)
    pcm = (x * 32767).astype("<i2").tobytes()
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)


def build_corpus(root):
    for split, tok in (("train", "t"), ("heldout", "h")):
        d = os.path.join(root, split)
        os.makedirs(d, exist_ok=True)
        for i, cls in enumerate(("ba", "da", "ga")):
            for k in range(2):
                write_wav(os.path.join(d, f"{cls}_{tok}0{k}_0.wav"),
                          200 + 90 * i + 7 * k)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=os.path.join(HERE, "train.py"))
    a = ap.parse_args()
    T = load(a.src, "train_under_test")

    tmp = tempfile.mkdtemp(prefix="proof_snn8_")
    try:
        corpus = os.path.join(tmp, "corpus-syllables")
        build_corpus(corpus)
        T.CORPUS = corpus
        T.DATA = os.path.join(tmp, "data")
        quiet = lambda *a: None

        xtr1, _, _, _ = T.load_syllables(quiet)
        cache = os.path.join(T.DATA, "syllables_cochlea.npz")
        keys = list(np.load(cache).files)
        print(f"first hearing: {len(xtr1)} training percepts, cache keys {keys}")

        # The corpus grows by one wav — exactly what re-recording looks like.
        write_wav(os.path.join(corpus, "train", "ba_t09_0.wav"), 411)
        n_on_disk = len([f for f in os.listdir(os.path.join(corpus, "train"))
                         if f.endswith(".wav")])
        xtr2, _, _, _ = T.load_syllables(quiet)
        print(f"after adding one wav: {n_on_disk} on disk, "
              f"load_syllables returned {len(xtr2)}")

        ok = (len(xtr1) == 6 and len(xtr2) == n_on_disk == 7
              and "corpus_sha256" in keys)
        if len(xtr2) == 6:
            print("the new audio never reached the network — the cache was "
                  "returned unchecked")
        return verdict(ok, "a cache with no fingerprint is a silent stale feed")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
