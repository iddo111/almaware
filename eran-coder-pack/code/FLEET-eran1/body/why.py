"""why.py — explainability. Given one wav: which prototypes it lands on,
what the chemistry looked like, and which curriculum unit was active.

Usage:  python3 body/why.py <path-to-wav>

Reads state only; changes nothing. Embodies: the legible brain — every answer
the organism gives can be traced to prototypes you can read.
"""
import json
import os
import sys

import numpy as np

import genome


def explain(wav_path, top=5):
    from brain import Brain
    from ears import Ears
    lines = []
    ears = Ears(exam=True)        # explaining may inspect any wav, incl. exams
    vec = ears.utterance(wav_path)
    if not os.path.exists(genome.BRAIN_FILE):
        return ["(no brain file yet — the organism has not lived)"]
    b = Brain.load()
    if b.dim != len(vec):
        return [f"(brain dim {b.dim} != ear dim {len(vec)} — reborn ears?)"]
    if not b.protos:
        return ["(empty brain — nothing heard yet)"]
    m = b._matrix()
    sims = m @ vec
    order = np.argsort(-sims)[:top]
    lines.append(f"utterance: {os.path.basename(wav_path)}")
    lines.append(f"nearest prototypes (of {len(b.protos)}):")
    for i in order:
        p = b.protos[int(i)]
        att = sims[i] - p["scar"]
        lines.append(f"  proto#{int(i)}: sim={sims[i]:.4f} "
                     f"attraction={att:.4f} mass={p['mass']:.1f} "
                     f"scar={p['scar']:.2f} born@{p['birth_step']}")
    # chemistry + unit at the time (latest metrics line)
    if os.path.exists(genome.METRICS_FILE):
        last = None
        with open(genome.METRICS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    last = line
        if last:
            try:
                m_line = json.loads(last)
                lines.append(f"chemistry now: da={m_line.get('da')} "
                             f"ach={m_line.get('ach')} ne={m_line.get('ne')} "
                             f"sht={m_line.get('sht')} oxt={m_line.get('oxt')}")
                lines.append(f"active curriculum unit: {m_line.get('unit')}")
            except ValueError:
                pass
    return lines


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    for out in explain(sys.argv[1]):
        print(out)
