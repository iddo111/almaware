"""proof_SNN-13 — food that is present and catalogued must have a consumer.

corpus-syllables/words/ holds 96 wavs, 12 items, 48 base renderings, listed in
the manifest's own totals — and grep for 'words' over the four chain files
returned nothing. A split sitting in the corpus with no consumer is the mirror
image of a menu that returns nothing: in both cases the audio never reaches
the network, and nothing says so.

  FAILS on train.py.bak-rev-20260906   PASSES on the fixed train.py
"""
import argparse
import os
import sys

import numpy as np

from _proofcommon import HERE, load, verdict


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=os.path.join(HERE, "train.py"))
    a = ap.parse_args()
    T = load(a.src, "train_under_test")

    lw = getattr(T, "load_words", None)
    if lw is None:
        print("train.py cannot load words/: 96 wavs, 116.61 seconds of audio, "
              "catalogued in the manifest and eaten by nobody")
        return verdict(False, "a split with no consumer is uneaten food")

    xtr, ytr, xte, yte, classes = lw(log=lambda *a: None)
    groups = T.cochlea.group_ids(T.CORPUS, "words")
    total = len(xtr) + len(xte)
    print(f"words: {total} percepts, {len(classes)} classes {classes}")
    print(f"       {len(xtr)} train / {len(xte)} exam, chance "
          f"{1/len(classes):.3%}")

    # The exam must be carved by base rendering, like every other split here.
    files = T.cochlea.split_files(T.CORPUS, "words")
    y_all = np.array([classes.index(T.cochlea.label_of(f)) for f in files])
    keep, held = T.group_split(y_all, groups, frac=0.25, seed=0)
    shared = set(groups[keep].tolist()) & set(groups[held].tolist())
    print(f"       exam carved by base rendering: {len(set(groups))} bases, "
          f"{len(shared)} shared across the split")

    accepted = T.parse(["--dataset", "words"])["dataset"] == "words"
    print(f"       train.py --dataset words accepted: {accepted}")

    ok = (total == 96 and len(classes) == 12 and not shared
          and len(xtr) > 0 and len(xte) > 0 and accepted)
    return verdict(ok, "words/ is a second exam now, with its own classes, its "
                       "own chance line and no borrowed baselines")


if __name__ == "__main__":
    sys.exit(main())
