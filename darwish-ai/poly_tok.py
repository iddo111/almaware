# -*- coding: utf-8 -*-
"""poly_tok.py — DARWISH tokenizer v2. The representation only.

לזכרו של לָאוֹר ז״ל.

WHY THIS FILE EXISTS — THE BLOCKER, STATED AS A FACT ABOUT THE ALPHABET
-----------------------------------------------------------------------
midi_lean.py's vocabulary is exactly 108 tokens:

    token = drums * 13 + bass_degree      (8 drum combos x 13 bass values)
    + BAR, PHRASE, BOS, EOS               = 108

One token IS one sixteenth note AND one bass degree. Two consequences follow
from the arithmetic alone, before any model is trained:

  * THERE IS NOWHERE TO PUT A SECOND SIMULTANEOUS PITCH. Not "the model did
    not learn harmony" — the language has no word for a chord. A progression
    layer bolted on top would be US composing, not the model.
  * THERE IS NO NOTE LENGTH. A note held for a bar is indistinguishable from
    sixteen re-attacks of the same degree.

So "no harmony" was a REPRESENTATION failure, and this file is the fix.

THE ONE STRUCTURAL CHANGE THAT BUYS POLYPHONY
----------------------------------------------
In v1, time advances because a token was emitted. In v2, time advances only on
an explicit STEP token. Everything emitted before a STEP happens AT that step.
So an unlimited number of pitches can share one sixteenth:

    ... PITCH(a) PITCH(c) PITCH(e)  STEP ...      <- a chord. Three voices.

That is the whole trick. Polyphony is not a feature bolted on; it is what you
get for free once time is its own token.

THE LANES — one fact per token, never a product of two facts
-------------------------------------------------------------
    STEP                       advance one sixteenth
    BAR / PHRASE / BOS / EOS   structure
    DRUM(which, vel)           kick|body|hat x soft|mid|hard, emitted when struck
    PITCH(idx)                 7 octaves x 12 key-relative degrees = 84
    DUR(idx)                   length in sixteenths, 40 values, STICKY;
                               EXACT for every length 1..32

    VOCAB = 138       (v1 was 108)

The vocabulary grew by 30 tokens and that is the entire material cost. A 1.36M
model's embedding table gains 30 rows. What it buys is the ability to say a
chord, a held note, and an octave -- three things v1 could not say at any
price. Both pitch reach and duration reach were WIDENED after the first round
trip measured 18-37% of notes falling outside a 5-octave window and 4.6% of
durations unspellable; the numbers are in roundtrip_report.json, before and
after.

v1's kick was scattered across ids 13-25, 39-51, 65-77, 91-103 because the
encoding multiplied drums by 13; `top_k` could and did delete it. Here a lane
is a contiguous slice, so masking a lane is a slice, and no sampler can
silently remove the kick.

STICKY DURATION, and why it is not a cheat
-------------------------------------------
Emitting a DUR after every single PITCH is the honest-but-fat encoding. A
psytrance bassline is a sixteenth roll, so that DUR token would be the same
value thousands of times in a row. DUR therefore SETS a current length that
holds until changed. The decoder applies the same rule, so the round trip is
still exact — this is compression, not approximation, and roundtrip.py proves
it note-for-note rather than asserting it.

KEY-RELATIVE PITCH, kept from v1 because it was right
------------------------------------------------------
    idx = midi - key_pc - PITCH_LO           PITCH_LO = 12
    degree = idx % 12,  octave = idx // 12   midi = idx + PITCH_LO + key_pc

A set in F# and a set in A playing the same riff produce the SAME tokens, so
the model learns the riff and not the transposition. Inversion is exact
arithmetic, so nothing is lost — unlike v1's `% 12`, which threw the octave
away and then had to guess it back (see body/midi_out.py, the pitch bug of
2026-09-05).

WHAT THIS FILE STILL DOES NOT CARRY, said here rather than discovered later
----------------------------------------------------------------------------
  * note velocity for pitched voices (drums have three levels, notes do not)
  * timbre, FX, filter movement — the renderer's job, on purpose
  * anything off the sixteenth grid; swing and human timing are quantised away.
    roundtrip.py MEASURES that quantisation error instead of hiding it.

THE PRICE, measured not hidden: ~2-3.5x the tokens per step of v1, because a
sixteenth of music is now several tokens instead of one. An 8192 window holds
proportionally less music. That is the cost of being able to say "chord" at
all, and roundtrip.py prints tok_per_step for every single case so the price is
never a guess.

numpy only. No torch, no audio. This is the alphabet, not the ear.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# ---------------------------------------------------------------- vocabulary

TOK_STEP = 0
TOK_BAR = 1
TOK_PHRASE = 2
TOK_BOS = 3
TOK_EOS = 4

DRUM_BASE = 5
N_DRUM_INST = 3                      # kick, body/clap, hat
N_DRUM_VEL = 3                       # soft, mid, hard
N_DRUM = N_DRUM_INST * N_DRUM_VEL    # 9

PITCH_BASE = DRUM_BASE + N_DRUM      # 14
N_OCT = 7
N_PITCH = N_OCT * 12                 # 84
PITCH_LO = 12                        # idx 0 == MIDI 12 + key_pc
# Absolute reach, worst case over every key: MIDI 23..95 (B-1..B6). Anything
# outside is OCTAVE-FOLDED into the window rather than dropped: pitch class and
# therefore all harmony survive exactly; only the register moves. roundtrip.py
# counts every fold. See _fold().

DUR_BASE = PITCH_BASE + N_PITCH      # 98
# 1..32 sixteenths EXACTLY (two bars at sixteenth resolution), then coarse
# values for the rare long pad. Nothing under two bars is ever approximated.
DUR_VALUES = tuple(range(1, 33)) + (36, 40, 48, 56, 64, 80, 96, 128)
N_DUR = len(DUR_VALUES)              # 40
MAX_DUR = DUR_VALUES[-1]

VOCAB = DUR_BASE + N_DUR             # 138

DRUM_NAMES = ("kick", "body", "hat")
STEPS_PER_BAR = 16
BARS_PER_PHRASE = 16

# General-MIDI drum notes, used when writing a .mid back out.
GM_DRUM = {0: 36, 1: 38, 2: 42}      # kick, snare/clap, closed hat
DRUM_VEL_MIDI = (56, 88, 120)


def drum_token(which: int, vel: int) -> int:
    return DRUM_BASE + which * N_DRUM_VEL + vel


def drum_of(tok: int) -> tuple[int, int]:
    i = tok - DRUM_BASE
    return i // N_DRUM_VEL, i % N_DRUM_VEL


def _fold(midi: int, key_pc: int) -> int:
    """Move a stray note by whole octaves until it lands inside the window.

    Pitch class is preserved exactly, so chords, intervals and every harmony
    measurement are untouched; only the octave changes. Dropping the note
    instead -- which is what a hard range check does -- would silently delete
    18-37% of the notes in the dressed GM files, measured 2026-09-05.
    """
    lo = PITCH_LO + key_pc
    hi = lo + N_PITCH - 1
    while midi < lo:
        midi += 12
    while midi > hi:
        midi -= 12
    return midi


def pitch_token(midi: int, key_pc: int) -> int | None:
    """Exactly invertible inside the window; octave-folded outside it."""
    idx = _fold(int(midi), key_pc) - PITCH_LO - key_pc
    if idx < 0 or idx >= N_PITCH:
        return None
    return PITCH_BASE + idx


def midi_of(tok: int, key_pc: int) -> int:
    return (tok - PITCH_BASE) + PITCH_LO + key_pc


def dur_token(steps: int) -> int:
    """Exact for 1..32; nearest value above that. Quantisation is measured."""
    best = min(range(N_DUR), key=lambda i: abs(steps - DUR_VALUES[i]))
    return DUR_BASE + best


def dur_of(tok: int) -> int:
    return DUR_VALUES[tok - DUR_BASE]


def lane_of(tok: int) -> str:
    if tok < DRUM_BASE:
        return "struct"
    if tok < PITCH_BASE:
        return "drum"
    if tok < DUR_BASE:
        return "pitch"
    return "dur"


LANE_SLICES = {
    "struct": (0, DRUM_BASE),
    "drum": (DRUM_BASE, PITCH_BASE),
    "pitch": (PITCH_BASE, DUR_BASE),
    "dur": (DUR_BASE, VOCAB),
}


# ---------------------------------------------------------------- the score

@dataclass
class Note:
    step: int
    midi: int
    dur: int          # in sixteenths

    def key(self):
        return (self.step, self.midi, self.dur)


@dataclass
class Drum:
    step: int
    which: int        # 0 kick, 1 body, 2 hat
    vel: int          # 0 soft, 1 mid, 2 hard

    def key(self):
        return (self.step, self.which, self.vel)


@dataclass
class Score:
    """What the music IS, independent of how it is spelled."""
    bpm: float = 143.55
    key_pc: int = 0
    n_steps: int = 0
    notes: list[Note] = field(default_factory=list)
    drums: list[Drum] = field(default_factory=list)
    source: str = ""

    def normalised(self) -> "Score":
        n = sorted({x.key() for x in self.notes})
        d = sorted({x.key() for x in self.drums})
        return Score(self.bpm, self.key_pc, self.n_steps,
                     [Note(*k) for k in n], [Drum(*k) for k in d], self.source)

    def polyphony_profile(self) -> dict:
        """How many pitches actually sound at the same time. The point of v2."""
        if not self.notes:
            return {"max": 0, "mean_sounding": 0.0, "onset_max": 0,
                    "frac_steps_poly": 0.0, "n_notes": 0}
        end = max(n.step + n.dur for n in self.notes)
        active = [0] * (end + 1)
        for n in self.notes:
            for s in range(n.step, min(n.step + n.dur, end)):
                active[s] += 1
        onset = {}
        for n in self.notes:
            onset[n.step] = onset.get(n.step, 0) + 1
        sounding = [a for a in active if a > 0]
        return {
            "max": max(active),
            "mean_sounding": round(sum(sounding) / max(len(sounding), 1), 3),
            "onset_max": max(onset.values()),
            "frac_steps_poly": round(sum(1 for a in active if a >= 2)
                                     / max(len(sounding), 1), 4),
            "n_notes": len(self.notes),
        }


# ---------------------------------------------------------------- encode

def encode(score: Score) -> list[int]:
    """Score -> tokens. Deterministic ordering, so the round trip can be exact."""
    by_step_notes: dict[int, list[Note]] = {}
    for n in score.notes:
        by_step_notes.setdefault(n.step, []).append(n)
    by_step_drums: dict[int, list[Drum]] = {}
    for d in score.drums:
        by_step_drums.setdefault(d.step, []).append(d)

    n_steps = score.n_steps
    if n_steps <= 0:
        cand = [0]
        if score.notes:
            cand.append(max(n.step for n in score.notes) + 1)
        if score.drums:
            cand.append(max(d.step for d in score.drums) + 1)
        n_steps = max(cand)

    toks = [TOK_BOS]
    cur_dur = None
    for s in range(n_steps):
        for d in sorted(by_step_drums.get(s, []), key=lambda x: (x.which, x.vel)):
            toks.append(drum_token(d.which, d.vel))
        # Sort by the TOKEN, not the raw MIDI. They differ whenever _fold()
        # moves a note: a note at MIDI 96 folds to 84, so sorting by MIDI puts
        # it AFTER a note at 90 while its token sorts before. The stream is
        # still perfectly decodable either way -- the decoded note set is
        # identical -- but encode(decode(x)) != x, i.e. the same music has two
        # spellings, and a model would have to spend capacity learning that
        # both are legal. Caught 2026-09-05 by corpus_rt.py on 10 of 323 tracks;
        # the sticky-DUR skip then amplified it into a length change on 1 of
        # them. Sorting by token makes the encoding canonical.
        for n in sorted(by_step_notes.get(s, []),
                        key=lambda x: (pitch_token(x.midi, score.key_pc) or 0, x.dur)):
            t = pitch_token(n.midi, score.key_pc)
            if t is None:
                continue                                   # out of range; counted by roundtrip
            dt = dur_token(n.dur)
            if dt != cur_dur:
                toks.append(dt)
                cur_dur = dt
            toks.append(t)
        toks.append(TOK_STEP)
        if s % STEPS_PER_BAR == STEPS_PER_BAR - 1:
            toks.append(TOK_BAR)
            bar = s // STEPS_PER_BAR
            if bar % BARS_PER_PHRASE == BARS_PER_PHRASE - 1:
                toks.append(TOK_PHRASE)
    toks.append(TOK_EOS)
    return toks


# ---------------------------------------------------------------- decode

def decode(toks, bpm: float = 143.55, key_pc: int = 0, source: str = "") -> Score:
    """Tokens -> Score. Tolerant of a model's malformed stream; never raises."""
    notes: list[Note] = []
    drums: list[Drum] = []
    step = 0
    cur_dur = DUR_VALUES[0]
    for t in toks:
        t = int(t)
        if t == TOK_STEP:
            step += 1
        elif t in (TOK_BAR, TOK_PHRASE, TOK_BOS):
            pass
        elif t == TOK_EOS:
            break
        elif DRUM_BASE <= t < PITCH_BASE:
            w, v = drum_of(t)
            drums.append(Drum(step, w, v))
        elif PITCH_BASE <= t < DUR_BASE:
            notes.append(Note(step, midi_of(t, key_pc), cur_dur))
        elif DUR_BASE <= t < VOCAB:
            cur_dur = dur_of(t)
    return Score(bpm, key_pc, step, notes, drums, source)


# ---------------------------------------------------------------- MIDI I/O

def score_from_midi(path, bpm_hint: float | None = None, key_pc: int | None = None,
                    grid: int = 16) -> Score:
    """Read a .mid into a Score, quantising onsets and lengths to sixteenths.

    Channel 9 is General MIDI percussion and is mapped onto the three drum
    lanes by note number; everything else is a pitched note.
    """
    import mido
    mf = mido.MidiFile(str(path))
    tpb = mf.ticks_per_beat
    tempo = 500000
    events = []
    for tr in mf.tracks:
        t = 0
        for msg in tr:
            t += msg.time
            if msg.type == "set_tempo":
                tempo = msg.tempo
            elif msg.type in ("note_on", "note_off"):
                on = msg.type == "note_on" and msg.velocity > 0
                events.append((t, on, msg.note, msg.channel, msg.velocity))
    events.sort(key=lambda e: (e[0], e[1]))

    ticks_per_step = tpb * 4.0 / grid
    bpm = bpm_hint if bpm_hint else round(60_000_000.0 / tempo, 2)

    pitched, drum = [], []
    open_notes: dict[tuple[int, int], int] = {}
    for t, on, note, ch, vel in events:
        st = int(round(t / ticks_per_step))
        if ch == 9:
            if on:
                which = 0 if note in (35, 36) else (2 if note in (42, 44, 46) else 1)
                lvl = 0 if vel < 70 else (1 if vel < 105 else 2)
                drum.append(Drum(st, which, lvl))
            continue
        if on:
            open_notes[(ch, note)] = st
        else:
            s0 = open_notes.pop((ch, note), None)
            if s0 is not None:
                pitched.append(Note(s0, note, max(1, st - s0)))
    for (ch, note), s0 in open_notes.items():
        pitched.append(Note(s0, note, 1))

    if key_pc is None:
        hist = [0] * 12
        for n in pitched:
            hist[n.midi % 12] += 1
        key_pc = hist.index(max(hist)) if pitched else 0

    n_steps = 0
    for n in pitched:
        n_steps = max(n_steps, n.step + n.dur)
    for d in drum:
        n_steps = max(n_steps, d.step + 1)
    return Score(bpm, key_pc, n_steps, pitched, drum, str(path)).normalised()


def score_to_midi(score: Score, path, grid: int = 16, program: int = 81):
    """Write a Score out as a real .mid — pitched notes on ch0, drums on ch9."""
    import mido
    tpb = 480
    ticks_per_step = int(tpb * 4 / grid)
    mf = mido.MidiFile(ticks_per_beat=tpb)
    tr = mido.MidiTrack()
    mf.tracks.append(tr)
    tr.append(mido.MetaMessage("set_tempo",
                               tempo=int(60_000_000 / max(score.bpm, 1e-6)), time=0))
    tr.append(mido.Message("program_change", channel=0, program=program, time=0))

    ev = []
    for n in score.notes:
        ev.append((n.step * ticks_per_step, 1, 0, n.midi, 100))
        ev.append(((n.step + n.dur) * ticks_per_step, 0, 0, n.midi, 0))
    for d in score.drums:
        ev.append((d.step * ticks_per_step, 1, 9, GM_DRUM[d.which], DRUM_VEL_MIDI[d.vel]))
        ev.append((d.step * ticks_per_step + ticks_per_step // 2, 0, 9,
                   GM_DRUM[d.which], 0))
    ev.sort(key=lambda e: (e[0], e[1]))

    last = 0
    for tick, on, ch, note, vel in ev:
        dt = max(0, tick - last)
        last = tick
        tr.append(mido.Message("note_on" if on else "note_off",
                               channel=ch, note=int(note), velocity=int(vel), time=dt))
    mf.save(str(path))
    return str(path)


__all__ = [
    "VOCAB", "TOK_STEP", "TOK_BAR", "TOK_PHRASE", "TOK_BOS", "TOK_EOS",
    "DRUM_BASE", "PITCH_BASE", "DUR_BASE", "DUR_VALUES", "N_PITCH", "PITCH_LO",
    "LANE_SLICES", "lane_of", "drum_token", "drum_of", "pitch_token", "midi_of",
    "dur_token", "dur_of", "Note", "Drum", "Score", "encode", "decode",
    "score_from_midi", "score_to_midi", "STEPS_PER_BAR", "BARS_PER_PHRASE",
]
