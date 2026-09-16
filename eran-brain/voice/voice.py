"""voice.py — v0 echo-babble, honestly labeled.

The organism composes a babble by CHOOSING: for each of its strongest
prototypes it finds the central train snippet (the train wav its prototype
sits closest to) and re-sequences those snippets into one wav in
songs/outbox/. That is a real choice made by its own memory — and it is NOT
synthesis and NOT his own voice yet. The sidecar .json says exactly that.

Embodies: never-fake-a-milestone. The first true voice will be earned, not
staged. Sacred Audio: this file only WRITES wavs; nothing ever plays aloud.
"""
import datetime
import json
import os
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(ROOT, "body"))

import genome                                     # noqa: E402
from ears import read_wav, write_wav              # noqa: E402

GAP_S = 0.12          # short breath between snippets
SCAN_CAP = 200        # bounded: train wavs scanned per babble


def _train_index(ears):
    """(names, matrix) of a bounded, deterministic sample of train wavs."""
    d = genome.FOOD_TRAIN
    if not os.path.isdir(d):
        return [], None
    names = sorted(n for n in os.listdir(d) if n.endswith(".wav"))
    stride = max(1, len(names) // SCAN_CAP)
    names = names[::stride]
    vecs, ok = [], []
    for n in names:
        try:
            vecs.append(ears.utterance(os.path.join(d, n)))
            ok.append(n)
        except (OSError, ValueError):
            continue
    return (ok, np.stack(vecs)) if vecs else ([], None)


def babble(brain, ears, out_dir=None):
    """Write babble-<ts>.wav + sidecar. Returns the wav path (or None)."""
    if not brain.protos:
        return None
    names, mat = _train_index(ears)
    if mat is None:
        return None
    out_dir = out_dir or genome.OUTBOX_DIR
    os.makedirs(out_dir, exist_ok=True)
    chosen = []
    for i in brain.top_protos(genome.BABBLE_PROTOS):
        sims = mat @ brain.protos[i]["vec"]
        j = int(np.argmax(sims))
        chosen.append((i, names[j], float(sims[j])))
    gap = np.zeros(int(GAP_S * genome.SAMPLE_RATE), dtype=np.float32)
    pieces = []
    for _, name, _ in chosen:
        pieces.append(read_wav(os.path.join(genome.FOOD_TRAIN, name)))
        pieces.append(gap)
    audio = np.concatenate(pieces[:-1]) if pieces else gap
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    wav_path = os.path.join(out_dir, f"babble-{ts}.wav")
    write_wav(wav_path, audio)
    sidecar = {
        "mode": ("echo-babble-v0 (heard audio re-sequenced by the organism's "
                 "own choice - NOT synthesis, NOT his own voice yet)"),
        "ts": ts,
        "chosen": [{"proto": i, "snippet": n, "sim": round(s, 4)}
                   for i, n, s in chosen],
        "seconds": round(len(audio) / genome.SAMPLE_RATE, 2),
    }
    with open(wav_path.replace(".wav", ".json"), "w", encoding="utf-8") as f:
        json.dump(sidecar, f, indent=1)
    return wav_path
