"""voice.py — singing. Sampling from the brain at serotonin temperature.

Performance is ACh=0: the stage never rewires, it only tags (trace.json).
The bar/phrase skeleton is emitted by the body, not left to chance.
"""
import json
import math
import random

import genome


def sing(brain, chem, bars=genome.SONG_BARS, seed=None):
    rng = random.Random(seed)
    T = max(0.2, chem.temperature())
    chem.mode(genome.ACH_PERFORM)
    brain.history = [genome.TOK_BOS]
    brain.elig = {}
    tokens = [genome.TOK_BOS]
    for bar in range(bars):
        for phase in range(genome.STEPS_PER_BAR):
            p = brain.predict(phase)
            for t in genome.STRUCTURAL:          # the skeleton is the body's job
                p[t] = 0.0
            if T != 1.0:
                p = [x ** (1.0 / T) for x in p]
            s = sum(p)
            if s <= 0:
                tok = rng.randrange(0, genome.TOK_BAR)
            else:
                r = rng.random() * s
                acc = 0.0
                tok = 0
                for i, x in enumerate(p):
                    acc += x
                    if acc >= r:
                        tok = i
                        break
            brain.tag_only(tok, phase)
            tokens.append(tok)
        tokens.append(genome.TOK_BAR)
        brain.tag_only(genome.TOK_BAR, 0)
        if (bar + 1) % genome.BARS_PER_PHRASE == 0:
            tokens.append(genome.TOK_PHRASE)
    tokens.append(genome.TOK_EOS)
    trace = brain.snapshot_trace()
    chem.mode(genome.ACH_FEED)
    return tokens, trace


def save_song(song_id, tokens, trace, outbox):
    import os
    os.makedirs(outbox, exist_ok=True)
    with open(os.path.join(outbox, song_id + ".tokens.json"), "w") as f:
        json.dump({"song_id": song_id, "tokens": tokens}, f)
    with open(os.path.join(outbox, song_id + ".trace.json"), "w") as f:
        json.dump({"song_id": song_id, "trace": trace}, f)
