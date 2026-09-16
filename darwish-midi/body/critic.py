"""critic.py — the groove homeostat. The world's whisper (the parent speaks x10).

Set-points are MEASURED from the train corpus (setpoints.json) — numbers,
never taste. Valence = negative distance from the corpus bands.
"""
import json
import os

import genome


def _stats(tokens):
    """Groove stats of a token stream: kick-bit downbeat affinity per drum bit,
    bass activity, mean repetition run-length."""
    phase = 0
    bit_hits = [[0, 0], [0, 0], [0, 0]]   # per bit: [on-quarter, off-quarter]
    bass_on = 0
    musical = 0
    runs, cur = [], 1
    prev = None
    for tok in tokens:
        if tok == genome.TOK_BAR:
            phase = 0
            continue
        if tok in genome.STRUCTURAL:
            continue
        drums, bass = divmod(tok, genome.DRUM_BASE)
        for b in range(3):
            if (drums >> b) & 1:
                bit_hits[b][0 if phase % 4 == 0 else 1] += 1
        if bass > 0:
            bass_on += 1
        if prev is not None:
            if tok == prev:
                cur += 1
            else:
                runs.append(cur)
                cur = 1
        prev = tok
        musical += 1
        phase = (phase + 1) % genome.STEPS_PER_BAR
    runs.append(cur)
    if musical == 0:
        return None
    return {
        "downbeat_affinity": [h[0] / max(1, h[0] + h[1]) for h in bit_hits],
        "bass_rate": bass_on / musical,
        "mean_run": sum(runs) / len(runs),
        "musical": musical,
    }


def measure_setpoints(ears, names, out_path):
    """Measure the corpus bands once, write setpoints.json."""
    agg = []
    for name in names:
        shard = ears.load(name)
        s = _stats(shard["tokens"])
        if s:
            agg.append(s)
    n = len(agg)
    sp = {
        "n_tracks": n,
        "downbeat_affinity": [sum(a["downbeat_affinity"][b] for a in agg) / n
                              for b in range(3)],
        "bass_rate": sum(a["bass_rate"] for a in agg) / n,
        "mean_run": sum(a["mean_run"] for a in agg) / n,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(sp, f, indent=1)
    return sp


class Critic:
    def __init__(self, setpoints_path):
        with open(setpoints_path, "r", encoding="utf-8") as f:
            self.sp = json.load(f)
        # the KICK bit = the one the corpus lands hardest on downbeats
        self.kick_bit = max(range(3), key=lambda b: self.sp["downbeat_affinity"][b])

    def judge(self, tokens):
        """Return (valence, detail). Valence in [-1, 1]: distance from the bands."""
        s = _stats(tokens)
        if s is None or s["musical"] < genome.STEPS_PER_BAR:
            return -1.0, {"reason": "empty or non-musical"}
        pen = 0.0
        d = {}
        d["kick_downbeat"] = s["downbeat_affinity"][self.kick_bit]
        pen += min(1.0, abs(d["kick_downbeat"] - self.sp["downbeat_affinity"][self.kick_bit]) * 2)
        d["bass_rate"] = s["bass_rate"]
        pen += min(1.0, abs(s["bass_rate"] - self.sp["bass_rate"]) * 2)
        d["mean_run"] = s["mean_run"]
        rel = abs(s["mean_run"] - self.sp["mean_run"]) / max(1.0, self.sp["mean_run"])
        pen += min(1.0, rel)
        valence = 1.0 - 2.0 * (pen / 3.0)
        return max(-1.0, min(1.0, valence)), d
