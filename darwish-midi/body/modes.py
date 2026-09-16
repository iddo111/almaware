"""body/modes.py — render-time SCALE/MODE mapping. New module, swarm slice
"claude-cli-SONNET-psymode" (RAMCHAT, 2026-09-12).

WHERE "A MINOR" ACTUALLY LIVES (found, not guessed — see the swarm report):
  * PC renderer: body/midi_out.py line 12 `MINOR = [0, 2, 3, 5, 7, 8, 10]`
    is a diatonic natural-minor table, but since the 2026-09-05 PITCH FIX
    (same file, lines 14-28) it is used ONLY by `bass_note_diatonic_legacy()`
    — dead code kept for bit-reproducibility of v1-v4 renders. The LIVE path,
    `bass_note(degree, root=45)`, is fully CHROMATIC: every one of the 12
    incoming degree values reaches a distinct semitone, no scale filter at
    all. root=45 fixes the pitch centre at A1, nothing else.
  * eran4 (~/darwish-ai/code-midi/, read-only, not modified by this slice):
    `midi_sample.py:77  CORPUS_KEY_PC = 9  # A, the most common key (38/191)`
    is a COLD-START STAND-IN (say_what_is_real(), ~line 124) used only when
    there is no seed track — it is corpus statistics, not something the
    model or Chai ever chooses. `detokenize.py` reconstructs pitch the same
    chromatic way: `BASS_OCTAVE_ROOT + (key_pc + deg - 1) % 12`.
  * The composer itself — darwish_life.py + body/brain.py/chemistry.py/
    drives.py/parent.py, i.e. the actual "dmidi-life tree" driving
    dmidi-life.service on eran4 — contains NO mention of "minor" or "scale"
    anywhere (grepped, zero hits). Chai emits abstract degree tokens 0-12;
    it has no concept of a scale at all. "A minor" is a renderer/doc
    convention (DESIGN.md lines 71 & 156), not something composed.
  * Conclusion: because the composer never reasoned in a scale to begin
    with, retargeting the mode is legitimately a RENDER-TIME choice — we are
    not fighting the model's own harmonic intent, we are choosing, for the
    first time, what its already-abstract degree stream is allowed to mean.

MODE DEFINITIONS (semitone offsets from the root pitch class):
  chromatic  0..11, all twelve — TODAY'S DEFAULT, byte-identical to
             midi_out.bass_note(). Nothing changes unless a mode is asked for.
  minor      natural minor / Aeolian:            0,2,3,5,7,8,10
  freygish   Phrygian dominant / Ahava Raba:      0,1,4,5,7,8,10  (b2 maj3 b6 b7)
  hijaz      double-harmonic / "Hijaz Kar":       0,1,4,5,7,8,11  (b2 maj3 b6 NAT7)
             Freygish and Hijaz share the lower tetrachord (root, b2, maj3, 4)
             which is *the* Middle-Eastern colour and the two names are used
             interchangeably in casual practice; they are kept genuinely
             distinct here (b7 vs natural 7) so the three renders are
             actually three different things to listen to and measure, not
             two copies of the same scale under two names. Say this plainly:
             it is a defensible convention, not the only correct one.
"""
from __future__ import annotations

import math
import struct
import wave

SCALES = {
    "minor":    (0, 2, 3, 5, 7, 8, 10),
    "freygish": (0, 1, 4, 5, 7, 8, 10),
    "hijaz":    (0, 1, 4, 5, 7, 8, 11),
}


def snap_to_scale(chroma, scale):
    """Nearest member of `scale` to `chroma`, both pitch classes 0..11,
    distance measured on the 12-tone circle (so 11 is 1 semitone from 0)."""
    def circ(a, b):
        d = abs(a - b) % 12
        return min(d, 12 - d)
    return min(scale, key=lambda s: circ(chroma, s))


def bass_note_mode(degree, root=45, mode="chromatic"):
    """Same contract as midi_out.bass_note(degree, root): degree 1..12,
    root default A1=45. mode="chromatic" reproduces midi_out.bass_note()
    exactly (root + degree - 1) — the current live behaviour, unconditionally.
    Any other mode snaps that same chromatic offset onto a 7-note scale
    rooted at `root`, so the SAME degree stream (the same composition) is
    reinterpreted, not resampled."""
    chroma = (degree - 1) % 12
    if mode == "chromatic" or mode not in SCALES:
        return root + chroma
    return root + snap_to_scale(chroma, SCALES[mode])


# --------------------------------------------------------------- measurement

def note_sequence(tokens, drum_base, mode="chromatic", root=45):
    """Walk a v0 token stream (token = drums*DRUM_BASE + bass_degree) and
    return the sequence of sounding bass MIDI notes for one mode. Rests
    (bass_degree == 0) and structural tokens are skipped — this is exactly
    the information midi_out.write() turns into note-on events."""
    notes = []
    for tok in tokens:
        if tok >= 104:            # STRUCTURAL: TOK_BAR/PHRASE/BOS/EOS (>=104)
            continue
        _, bass = divmod(tok, drum_base)
        if bass > 0:
            notes.append(bass_note_mode(bass, root=root, mode=mode))
    return notes


def pitch_class_histogram(notes):
    hist = [0] * 12
    for n in notes:
        hist[n % 12] += 1
    total = sum(hist) or 1
    return [c / total for c in hist]


def interval_histogram(notes):
    """Unsigned semitone interval between consecutive sounding notes."""
    ivals = [abs(b - a) for a, b in zip(notes, notes[1:])]
    if not ivals:
        return {}, 0.0
    hist = {}
    for iv in ivals:
        hist[iv] = hist.get(iv, 0) + 1
    mean = sum(ivals) / len(ivals)
    return hist, mean


# --------------------------------------------------------------- tiny preview synth
# Deliberately NOT psy_synth.py (owned by the "voices" slice of this swarm) and
# NOT body/synth.py (documented "kept, untouched" fallback). This is a third,
# minimal, stdlib-only bass+kick preview so a mode's audible identity can be
# checked without touching either file. It borrows synth.py's spirit (falling-
# sine kick, square-wave bass, sidechain duck) but is its own code.

SR = 22050


def render_preview_wav(path, tokens, drum_base, bpm=143.55, mode="chromatic", root=45):
    step_s = 60.0 / bpm / 4.0
    step_n = int(SR * step_s)
    steps = [t for t in tokens if t < 104]
    total = len(steps) * step_n + SR
    buf = [0.0] * total
    pos = 0
    for tok in steps:
        drums, bass = divmod(tok, drum_base)
        kick = (drums >> 0) & 1
        if kick:
            for i in range(min(int(0.12 * SR), total - pos)):
                f = 150.0 * math.exp(-i / (0.03 * SR)) + 45.0
                env = math.exp(-i / (0.04 * SR))
                buf[pos + i] += 0.9 * env * math.sin(2 * math.pi * f * i / SR)
        if bass > 0:
            note = bass_note_mode(bass, root=root, mode=mode)
            f = 440.0 * 2 ** ((note - 69) / 12.0)
            period = SR / f
            for i in range(min(int(step_n * 0.9), total - pos)):
                duck = 0.35 + 0.65 * min(1.0, i / (0.09 * SR)) if kick else 1.0
                sq = 0.5 if (i % period) < period / 2 else -0.5
                buf[pos + i] += 0.5 * duck * sq
        pos += step_n
    peak = max(1e-9, max(abs(x) for x in buf))
    scale = 0.9 / peak
    frames = b"".join(struct.pack("<h", int(max(-1.0, min(1.0, x * scale)) * 32767)) for x in buf)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(frames)
    return total / SR
