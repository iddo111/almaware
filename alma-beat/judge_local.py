# -*- coding: utf-8 -*-
"""THE MATHEMATICAL JUDGE -- pure code, no model call, deterministic, <1 ms.

Iddo, 2026-09-12 02:56: "תעשה שופט סטטיסטי מתמטי, כלומר קוד".

THIS IS THE TEMPORARY ONE. claude-cli-SONNET-darwishjudge claimed the shared
judge at 02:56 and it was not on disk when this organ needed a reward, so this
file implements EXACTLY the contract published to RAMCHAT at 03:0x:

    score_bar(bar, ref=None) -> {"score": float in [0,1], "parts": {...}}
    bar = {"kick": [0/1]*16, "snare": [0/1]*16, "hat": [0/1]*16,
           "bass": [0..12]*16}          # 0 = rest, 1..12 = semitone over key

When theirs lands, `cook.py --judge shared` swaps it in and nothing else moves.

THE FIVE PARTS, and which of them is TAUGHT rather than discovered
-----------------------------------------------------------------
  scale         share of sounded bass degrees inside the target scale.
                NOT taught: the organ emits all 12 chromatic degrees and must
                learn to stay inside. Chance is 7/12 = 0.583. THIS IS THE
                HEADLINE NUMBER.
  regularity    4-on-the-floor kick, offbeat hat, snare on 2 and 4.
                TAUGHT, openly: the judge knows what psytrance is. A high score
                here is obedience, not discovery. Reported separately so it can
                never hide inside the total.
  independence  the bass must not be a tracing of the kick, and must not be one
                note repeated. Two real lines or nothing.
  energy        kick and bass density inside a live band -- not empty, not mud.
  similarity    distance to Chai's measured profile. WEIGHT 0.10 on purpose;
                see reference.py for why imitating it closely is not a goal.
"""
from __future__ import annotations

import json
from pathlib import Path

BAR = 16
HERE = Path(__file__).resolve().parent

# Phrygian dominant / freygish -- the psytrance staple, semitones over the key.
FREYGISH = (0, 1, 4, 5, 7, 8, 10)
MINOR = (0, 2, 3, 5, 7, 8, 10)
SCALES = {"freygish": FREYGISH, "minor": MINOR}

WEIGHTS = {"scale": 0.25, "regularity": 0.25, "independence": 0.20,
           "energy": 0.20, "similarity": 0.10}

_REF: dict | None = None


def reference(path: str | None = None) -> dict | None:
    global _REF
    if _REF is None:
        p = Path(path) if path else HERE / "reference.json"
        _REF = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    return _REF or None


def _band(x: float, lo: float, hi: float) -> float:
    """1.0 inside [lo,hi], falling linearly to 0 one half-width outside."""
    if lo <= x <= hi:
        return 1.0
    w = max(1e-9, (hi - lo) * 0.5)
    d = (lo - x) if x < lo else (x - hi)
    return max(0.0, 1.0 - d / w)


def _entropy(counts: list[int]) -> float:
    import math
    n = sum(counts)
    if n <= 0:
        return 0.0
    h = 0.0
    for c in counts:
        if c:
            p = c / n
            h -= p * math.log(p, 2)
    return h


def score_bar(bar: dict, ref: dict | None = None, scale: str = "freygish") -> dict:
    k = list(bar["kick"])[:BAR]
    s = list(bar["snare"])[:BAR]
    h = list(bar["hat"])[:BAR]
    b = list(bar["bass"])[:BAR]
    ref = ref if ref is not None else reference()
    allowed = SCALES[scale]

    # 1. SCALE -- learned, not enforced.
    sounded = [d for d in b if d]
    in_scale = sum(1 for d in sounded if (d - 1) % 12 in allowed)
    p_scale = (in_scale / len(sounded)) if sounded else 0.0

    # 2. REGULARITY -- taught, and said so.
    downs = (0, 4, 8, 12)
    offs = (2, 6, 10, 14)
    backs = (4, 12)
    kick_hit = sum(k[i] for i in downs) / 4.0
    kick_off = sum(k[i] for i in range(BAR) if i not in downs) / 12.0
    hat_off = sum(h[i] for i in offs) / 4.0
    snare_back = sum(s[i] for i in backs) / 2.0
    p_reg = max(0.0, 0.5 * kick_hit - 0.2 * kick_off + 0.3 * hat_off * 0.5
                + 0.2 * snare_back + 0.15 * hat_off * 0.5)
    p_reg = min(1.0, p_reg / 0.85)

    # 3. INDEPENDENCE -- two lines, not one line twice.
    bon = [1 if d else 0 for d in b]
    agree = sum(1 for i in range(BAR) if bon[i] == k[i]) / BAR
    lock = abs(agree - 0.5) * 2.0            # 0 = independent, 1 = locked/anti
    counts = [0] * 12
    for d in sounded:
        counts[(d - 1) % 12] += 1
    import math
    ent = _entropy(counts) / math.log(max(2, min(12, len(set(sounded)) or 2)), 2) \
        if sounded else 0.0
    variety = min(1.0, _entropy(counts) / 2.0)   # 2 bits ~ 4 pitches used evenly
    p_ind = max(0.0, 0.6 * (1.0 - lock) + 0.4 * variety)

    # 4. ENERGY
    p_energy = 0.5 * _band(sum(k) / BAR, 0.20, 0.45) + \
               0.5 * _band(sum(bon) / BAR, 0.30, 0.80)

    # 5. SIMILARITY -- lowest weight on purpose.
    if ref:
        def l1(v, r):
            return sum(abs(a - c) for a, c in zip(v, r)) / BAR
        d = (l1(k, ref["kick_pos"]) + l1(s, ref["snare_pos"]) +
             l1(h, ref["hat_pos"]) + l1(bon, ref["bass_pos"])) / 4.0
        p_sim = max(0.0, 1.0 - d)
    else:
        p_sim = 0.0

    parts = {"scale": round(p_scale, 5), "regularity": round(p_reg, 5),
             "independence": round(p_ind, 5), "energy": round(p_energy, 5),
             "similarity": round(p_sim, 5)}
    total = sum(WEIGHTS[n] * v for n, v in parts.items())
    return {"score": round(min(1.0, max(0.0, total)), 5), "parts": parts}


def score_notes(notes, **kw) -> dict:
    """The alternate door named in the RAMCHAT contract: [(step,pitch,vel,lane)]."""
    bar = {"kick": [0] * BAR, "snare": [0] * BAR, "hat": [0] * BAR,
           "bass": [0] * BAR}
    for step, pitch, _vel, lane in notes:
        i = step % BAR
        if lane in ("kick", "snare", "hat"):
            bar[lane][i] = 1
        else:
            bar["bass"][i] = ((pitch - 45) % 12) + 1
    return score_bar(bar, **kw)


if __name__ == "__main__":
    import random
    rng = random.Random(0)
    rand = {"kick": [rng.randint(0, 1) for _ in range(BAR)],
            "snare": [rng.randint(0, 1) for _ in range(BAR)],
            "hat": [rng.randint(0, 1) for _ in range(BAR)],
            "bass": [rng.randint(0, 12) for _ in range(BAR)]}
    good = {"kick": [1 if i % 4 == 0 else 0 for i in range(BAR)],
            "snare": [1 if i in (4, 12) else 0 for i in range(BAR)],
            "hat": [1 if i % 4 == 2 else 0 for i in range(BAR)],
            "bass": [0, 0, 1, 0, 0, 0, 8, 0, 0, 0, 6, 0, 0, 5, 0, 2]}
    empty = {"kick": [0] * BAR, "snare": [0] * BAR, "hat": [0] * BAR,
             "bass": [0] * BAR}
    for name, bar in (("random", rand), ("hand-written psy", good), ("silence", empty)):
        r = score_bar(bar)
        print(f"{name:18s} score={r['score']:.3f}  {r['parts']}")
