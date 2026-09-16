# -*- coding: utf-8 -*-
"""split_tok.py - cut the v2 stream into a RHYTHM stream and a PITCH stream.

לזכרו של לָאוֹר ז״ל.

WHY
---
Iddo, 2026-09-06: "איזה מין מודל מוזיקה אין לו תווים ואין לו קצב?"
Music is notes in time. His ear's verdict, twice: the RHYTHM IS GOOD, the
melody and harmony were not. So the drums do not need help and the pitches do.
Drums are the only part of the score that genuinely does not care what key you
are in, so that is the one real seam in the alphabet.

Melody and harmony are NOT split from each other. dj-alma/booth/compose.py:264
already derives the roles from the vertical structure (top of a stack = lead,
bottom = bass, middle = pad) - a melody note and a chord tone are the same kind
of object, a pitch in time. Two models would have to predict each other or drift.

WHAT THIS FILE IS
-----------------
A bijection, not a model:

    joint v2 stream  <-->  (rhythm stream, pitch stream)

    split_stream(joint) -> (r, p)
    merge_streams(r, p) -> joint          exactly, token for token

The clock is the STEP token that v2 ALREADY has. It appears in BOTH streams,
which is the entire coordination scheme - no new synchronisation was invented,
and the duplicated clock is paid for honestly in the measurement (both copies
are counted in the total description length of the music).

THE TWO ALPHABETS
-----------------
    rhythm  STEP BAR PHRASE BOS EOS + DRUM(3 inst x 3 vel)      VOCAB_R = 14
    pitch   STEP BAR PHRASE BOS EOS + PITCH(84) + DUR(40)       VOCAB_P = 129
    joint (v2, the control)                                      VOCAB   = 138

The rhythm ids are IDENTICAL to the joint ids (0..13) - poly_tok laid the lanes
out as contiguous slices, so the drum sub-alphabet is already a prefix. Only the
pitch stream is renumbered, to close the hole the drums leave behind.

MERGE ORDER - why it is exact and not merely plausible
-------------------------------------------------------
poly_tok.encode() emits, for every sixteenth:

    [drums, sorted]  [DUR? PITCH]*  STEP  [BAR]  [PHRASE]

so a step's content is always rhythm-first, then pitch, then a clock token that
both streams carry. Merging is therefore: drain the rhythm stream's non-clock
tokens, drain the pitch stream's non-clock tokens, emit the one clock token both
agree on, repeat. Sticky DUR survives because the pitch stream keeps the whole
DUR/PITCH sequence in its original order - nothing is reordered, only
deinterleaved.

The round trip is asserted on every file of the corpus by make_substreams.py,
not assumed here.

stdlib only. No numpy, no torch. This is the seam, not the ear.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import poly_tok as PT                                              # noqa: E402

# ------------------------------------------------------------------ clock

# The tokens that both streams carry. STEP is the shared clock; BAR/PHRASE are
# deterministic functions of the STEP count but are kept so the bar-memory layer
# in midi_model.py sees the same structure in both streams.
CLOCK = (PT.TOK_STEP, PT.TOK_BAR, PT.TOK_PHRASE, PT.TOK_EOS)
STRUCT = (PT.TOK_STEP, PT.TOK_BAR, PT.TOK_PHRASE, PT.TOK_BOS, PT.TOK_EOS)

# ------------------------------------------------------------------ rhythm

# Identity on 0..13: struct(5) + drums(9). Nothing to remap.
R_VOCAB = PT.PITCH_BASE                       # 14
R_BAR, R_PHRASE, R_BOS, R_EOS = PT.TOK_BAR, PT.TOK_PHRASE, PT.TOK_BOS, PT.TOK_EOS
R_STEP = PT.TOK_STEP
R_DRUM_BASE = PT.DRUM_BASE                    # 5
R_LANES = {"struct": (0, 5), "drum": (5, 14)}

# ------------------------------------------------------------------ pitch

P_STEP, P_BAR, P_PHRASE, P_BOS, P_EOS = 0, 1, 2, 3, 4
P_PITCH_BASE = 5                              # joint 14..97  -> 5..88
P_DUR_BASE = P_PITCH_BASE + PT.N_PITCH        # 89; joint 98..137 -> 89..128
P_VOCAB = P_DUR_BASE + PT.N_DUR               # 129
P_SHIFT = PT.PITCH_BASE - P_PITCH_BASE        # 9
P_LANES = {"struct": (0, 5), "pitch": (5, 89), "dur": (89, 129)}


def to_pitch_id(tok: int) -> int:
    """joint id -> pitch-stream id."""
    return tok if tok < PT.DRUM_BASE else tok - P_SHIFT


def from_pitch_id(tok: int) -> int:
    """pitch-stream id -> joint id."""
    return tok if tok < P_PITCH_BASE else tok + P_SHIFT


# ------------------------------------------------------------------ split

def split_stream(toks):
    """joint v2 tokens -> (rhythm tokens, pitch tokens).

    Both keep BOS/STEP/BAR/PHRASE/EOS; drums go left, PITCH+DUR go right.
    """
    r = []
    p = []
    for t in toks:
        t = int(t)
        if t in STRUCT:
            r.append(t)
            p.append(to_pitch_id(t))
        elif PT.DRUM_BASE <= t < PT.PITCH_BASE:
            r.append(t)
        elif PT.PITCH_BASE <= t < PT.VOCAB:
            p.append(to_pitch_id(t))
        else:
            raise ValueError("token %d outside the v2 alphabet" % t)
    return r, p


def merge_streams(r, p):
    """(rhythm, pitch) -> joint v2 tokens. The inverse of split_stream().

    Tolerant of a model's malformed streams - it never raises - because this is
    also the function that assembles GENERATED music, where the two models can
    disagree about how long the piece is. Whichever stream runs out first, the
    other's remaining clock ticks are still honoured, and a mismatched clock
    token is resolved in favour of the RHYTHM stream (the one Iddo's ear already
    approved). Every such repair is counted by merge_report().
    """
    out, i, j = [], 0, 0
    nr, np_ = len(r), len(p)
    if i < nr and int(r[i]) == PT.TOK_BOS:
        i += 1
    if j < np_ and int(p[j]) == P_BOS:
        j += 1
    out.append(PT.TOK_BOS)

    while i < nr or j < np_:
        while i < nr and int(r[i]) not in CLOCK:
            t = int(r[i])
            if PT.DRUM_BASE <= t < PT.PITCH_BASE:
                out.append(t)
            i += 1
        while j < np_ and from_pitch_id(int(p[j])) not in CLOCK:
            t = from_pitch_id(int(p[j]))
            if PT.PITCH_BASE <= t < PT.VOCAB:
                out.append(t)
            j += 1
        rc = int(r[i]) if i < nr else None
        pc = from_pitch_id(int(p[j])) if j < np_ else None
        if rc is None and pc is None:
            break
        tick = rc if rc is not None else pc
        if rc is not None:
            i += 1
        if pc is not None and (rc is None or pc == rc):
            j += 1
        if tick == PT.TOK_EOS:
            break
        out.append(tick)
    out.append(PT.TOK_EOS)
    return out


def merge_report(r, p):
    """How far apart the two streams' clocks ran. 0 disagreements on real data."""
    rc = [int(t) for t in r if int(t) in CLOCK]
    pc = [from_pitch_id(int(t)) for t in p if from_pitch_id(int(t)) in CLOCK]
    n = min(len(rc), len(pc))
    dis = sum(1 for a, b in zip(rc[:n], pc[:n]) if a != b)
    return {"r_clocks": len(rc), "p_clocks": len(pc),
            "compared": n, "disagreements": dis,
            "len_gap": abs(len(rc) - len(pc))}


# ------------------------------------------------------------------ lanes

def lane_of_joint(tok):
    return PT.lane_of(int(tok))


def lane_of_rhythm(tok):
    return "struct" if int(tok) < PT.DRUM_BASE else "drum"


def lane_of_pitch(tok):
    t = int(tok)
    if t < P_PITCH_BASE:
        return "struct"
    return "pitch" if t < P_DUR_BASE else "dur"


ALPHABETS = {
    "joint":  {"vocab": PT.VOCAB, "bar": PT.TOK_BAR, "bos": PT.TOK_BOS,
               "eos": PT.TOK_EOS, "phrase": PT.TOK_PHRASE,
               "lane": lane_of_joint, "lanes": PT.LANE_SLICES},
    "rhythm": {"vocab": R_VOCAB, "bar": R_BAR, "bos": R_BOS, "eos": R_EOS,
               "phrase": R_PHRASE, "lane": lane_of_rhythm, "lanes": R_LANES},
    "pitch":  {"vocab": P_VOCAB, "bar": P_BAR, "bos": P_BOS, "eos": P_EOS,
               "phrase": P_PHRASE, "lane": lane_of_pitch, "lanes": P_LANES},
}


# ------------------------------------------------------------------ selftest

def _selftest():
    """Adversarial cases first; the corpus is checked by make_substreams.py."""
    from random import Random
    rng = Random(1337)
    bad = 0

    cases = []
    cases.append(PT.Score(143.0, 0, 32, [], [], "silence"))
    cases.append(PT.Score(143.0, 3, 16, [],
                          [PT.Drum(s, s % 3, s % 3) for s in range(16)], "drums"))
    cases.append(PT.Score(143.0, 7, 16,
                          [PT.Note(0, 40, 16), PT.Note(0, 47, 16), PT.Note(0, 52, 16)],
                          [], "chord"))
    n, d = [], []
    for s in range(64):
        for k in range(5):
            n.append(PT.Note(s, 36 + k * 7, rng.choice([1, 2, 4, 8, 16])))
        for w in range(3):
            d.append(PT.Drum(s, w, rng.randint(0, 2)))
    cases.append(PT.Score(143.0, 11, 64, n, d, "dense"))
    cases.append(PT.Score(143.0, 5, 8,
                          [PT.Note(0, 4, 3), PT.Note(0, 126, 3), PT.Note(4, 21, 1)],
                          [PT.Drum(0, 0, 2)], "extreme"))
    n2 = [PT.Note(s, 40 + (s % 12), 2) for s in range(0, 512, 3)]
    d2 = [PT.Drum(s, 0, 2) for s in range(0, 512, 4)]
    cases.append(PT.Score(143.0, 0, 512, n2, d2, "phrases"))

    for sc in cases:
        joint = PT.encode(sc.normalised())
        r, p = split_stream(joint)
        back = merge_streams(r, p)
        ok = back == joint
        rep = merge_report(r, p)
        if not ok:
            bad += 1
            k = next((i for i, (a, b) in enumerate(zip(joint, back)) if a != b), None)
            print("FAIL %s: first diff at %s len %d vs %d"
                  % (sc.source, k, len(joint), len(back)))
        s1 = PT.decode(joint, key_pc=sc.key_pc).normalised()
        s2 = PT.decode(back, key_pc=sc.key_pc).normalised()
        same_music = (s1.notes == s2.notes and s1.drums == s2.drums)
        if not same_music:
            bad += 1
            print("FAIL %s: decoded music differs" % sc.source)
        print("%s%-9s joint=%6d  rhythm=%6d  pitch=%6d  sum/joint=%.3f  "
              "clock_disagree=%d"
              % ("ok   " if ok and same_music else "BAD  ", sc.source,
                 len(joint), len(r), len(p),
                 (len(r) + len(p)) / max(len(joint), 1), rep["disagreements"]))

    print("vocab: joint=%d rhythm=%d pitch=%d" % (PT.VOCAB, R_VOCAB, P_VOCAB))
    print("SELFTEST " + ("PASS" if bad == 0 else "FAIL (%d)" % bad))
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    raise SystemExit(_selftest())
