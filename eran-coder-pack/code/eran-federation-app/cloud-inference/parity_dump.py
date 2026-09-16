# -*- coding: utf-8 -*-
"""parity_dump.py — the TRUTH side of the cloud ear's acceptance test.

Runs ERAN's real, frozen cochlea (eran-brain/body/ears.py) over a sample of his
own training wavs and writes what it heard to JSON. parity_test.mjs then runs
the JavaScript port over the SAME wavs and compares, number by number.

The point is not that the JS ear looks right. The point is that if it ever
drifts from ears.py by more than floating-point noise, the test says so and
names the file it drifted on. A cloud ear that hears something slightly
different from the ear the organism grew is not a cloud ear — it is a second,
unmeasured organism.

Usage (from anywhere):
    PYTHONIOENCODING=utf-8 python parity_dump.py [--n 24] [--out parity.json]
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ERAN_BRAIN = os.environ.get(
    "ERAN_BRAIN_DIR",
    os.path.abspath(os.path.join(HERE, "..", "..", "eran-brain")),
)
sys.path.insert(0, os.path.join(ERAN_BRAIN, "body"))

import numpy as np                                        # noqa: E402
import ears                                               # noqa: E402
import genome                                             # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=24, help="how many wavs to dump")
    ap.add_argument("--out", default=os.path.join(HERE, "parity.json"))
    ap.add_argument("--food", default=os.path.join(ERAN_BRAIN, "food", "train"))
    ap.add_argument("--brain", default=None,
                    help="brain.json.gz to score against. Defaults to the local "
                         "state/, which on the PC is a COPY and may be months "
                         "behind the organism actually living on the fleet.")
    args = ap.parse_args()

    paths = sorted(glob.glob(os.path.join(args.food, "*.wav")))
    if not paths:
        print(f"[parity] no wavs under {args.food}", file=sys.stderr)
        return 2
    # Spread the sample across the whole corpus (all units, all sessions)
    # instead of taking the alphabetical head, which would be one syllable.
    step = max(1, len(paths) // args.n)
    picked = paths[::step][: args.n]

    ear = ears.Ears()
    if ear.repr != "cochlea" or ear.dim != genome.EAR_SLICES * genome.N_BANDS:
        print(f"[parity] unexpected ear: repr={ear.repr} dim={ear.dim}", file=sys.stderr)
        return 2

    brain_path = args.brain or os.path.join(ERAN_BRAIN, "state", "brain.json.gz")
    protos = None
    if os.path.exists(brain_path):
        import gzip
        with gzip.open(brain_path, "rt", encoding="utf-8") as f:
            protos = json.load(f)["protos"]

    items = []
    for p in picked:
        v = ear.utterance(p)
        item = {
            "file": os.path.basename(p),
            "unit": os.path.basename(p).split("_")[0],
            "vec": [float(x) for x in v],
        }
        if protos:
            m = np.array([q["vec"] for q in protos], dtype=np.float64)
            scars = np.array([q["scar"] for q in protos], dtype=np.float64)
            sims = m @ np.asarray(v, dtype=np.float64)
            att = sims - scars
            i = int(np.argmax(att))
            item["nearest"] = {"index": i, "sim": float(sims[i]), "att": float(att[i])}
        items.append(item)

    out = {
        "produced_by": "eran-brain/body/ears.py (the frozen cochlea)",
        "ear": {
            "repr": ear.repr,
            "dim": int(ear.dim),
            "n_bands": int(ear.n_bands),
            "pooling": ear.pooling,
            "slices": [[int(a), int(b)] for a, b in ear.slices],
            "sample_rate": genome.SAMPLE_RATE,
            "n_fft": genome.N_FFT,
            "frame": int(ear.frame),
            "hop": int(ear.hop),
            "ear_slices": genome.EAR_SLICES,
            "speech_frac": genome.EAR_SPEECH_FRAC,
            "eps": genome.EAR_EPS,
        },
        "brain": None if not protos else {
            "path": os.path.basename(brain_path),
            "n_protos": len(protos),
        },
        "items": items,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f)
    print(f"[parity] {len(items)} utterances -> {args.out} "
          f"(dim {ear.dim}, {len(protos) if protos else 0} prototypes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
