"""proof_cochlea.py — is our ported ear the SAME ear ERAN wears?

Runs the real D:\\CLAUDE\\eran-brain\\body\\ears.py (exam=True, so it may open
the heldout) and our cochlea.py side by side over every wav in the corpus, and
prints the largest absolute disagreement. Anything above ~1e-6 means the port
drifted and every comparison in this lab is worthless.

PC-only — eran-brain lives on the PC. Run it here, ship cochlea.py there.
"""
import os
import sys

import numpy as np

sys.path.insert(0, r"D:\CLAUDE\eran-brain\body")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ears as real_ears                      # noqa: E402  the frozen original
import cochlea as ours                        # noqa: E402  the port

CORPUS = r"D:\CLAUDE\voice-ant-farm\corpus-syllables"


def main():
    theirs = real_ears.Ears(exam=True)         # exam=True: may open the heldout
    mine = ours.Cochlea()
    assert theirs.repr == "cochlea", theirs.repr
    assert theirs.dim == mine.dim == 192, (theirs.dim, mine.dim)

    worst, worst_file, n = 0.0, None, 0
    for split in ("train", "heldout"):
        d = os.path.join(CORPUS, split)
        for f in sorted(os.listdir(d)):
            if not f.endswith(".wav"):
                continue
            p = os.path.join(d, f)
            a = theirs.utterance(p)                     # (192,)
            b = mine.utterance(p).ravel()               # (8,24) -> (192,)
            e = float(np.max(np.abs(a - b)))
            n += 1
            if e > worst:
                worst, worst_file = e, f
    print(f"compared {n} wavs")
    print(f"max |ears.py - cochlea.py| = {worst:.3e}   (worst: {worst_file})")
    ok = worst < 1e-6
    print("VERDICT:", "IDENTICAL EAR" if ok else "PORT DRIFTED — DO NOT TRUST")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
