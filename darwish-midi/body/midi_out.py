"""midi_out.py — format-0 MIDI by hand, stdlib struct only.

Clean-room rewrite in the spirit of the archived detokenize.py (credited).
Drums ch10 (kick 36, snare/body 38, hat 42), bass ch1 over A minor by default.
"""
import struct

import genome
import modes

TPQ = 480
TICKS_16TH = TPQ // 4
MINOR = [0, 2, 3, 5, 7, 8, 10]           # natural minor degrees 1..7 (then +octave)

# --- 2026-09-05 PITCH FIX -----------------------------------------------------
# bass_note() used to read the token's bass value as a DIATONIC scale degree and
# look it up in MINOR[]. The tokenizer does not mean that. midi_lean.py line 217:
#
#     deg = int(round(midi) - key) % 12 + 1     # 1..12, 0 means rest
#
# i.e. deg-1 is a CHROMATIC semitone offset from the track's key. Reading a
# chromatic offset through a diatonic table put 11 of the 12 degrees on the wrong
# pitch -- deg 2 landed +1 semitone out, deg 12 landed +8 out -- and stretched a
# 12-semitone span into 20. It also meant only 7 pitch classes were reachable at
# all, so "100% of notes fit A natural minor" was a tautology of this function,
# not a fact about the model. Measured on a real Darwish track: the diatonic map
# reports mean melodic interval 5.89 semitones, the chromatic map 3.42.
# The legacy mapping is kept below so old renders stay reproducible.
# ------------------------------------------------------------------------------


def _vlq(n):
    out = bytearray([n & 0x7F])
    n >>= 7
    while n:
        out.insert(0, 0x80 | (n & 0x7F))
        n >>= 7
    return bytes(out)


def _note(events, dt, ch, note, vel, dur):
    events.append(_vlq(dt) + bytes([0x90 | ch, note, vel]))
    events.append(_vlq(dur) + bytes([0x80 | ch, note, 0]))


def bass_note(degree, root=45):          # degree 1..12 = 0..11 semitones over A1=45
    return root + (degree - 1)


def bass_note_diatonic_legacy(degree, root=45):
    """The pre-2026-09-05 mapping. Wrong (see PITCH FIX above); kept only so the
    v1-v4 renders and the blind-test clips can still be reproduced bit-for-bit."""
    d = degree - 1
    return root + 12 * (d // 7) + MINOR[d % 7]


def write(path, tokens, bpm=140, mode="chromatic"):
    """mode="chromatic" (default) is byte-identical to the pre-2026-09-12
    behaviour — every degree maps straight to bass_note(), nothing changes
    unless a mode is explicitly asked for. Any other mode ("minor",
    "freygish", "hijaz", see body/modes.py) reinterprets the SAME degree
    stream through modes.bass_note_mode() instead."""
    events = []
    tempo = int(60_000_000 / bpm)
    events.append(b"\x00\xff\x51\x03" + struct.pack(">I", tempo)[1:])
    pending = 0
    for tok in tokens:
        if tok in genome.STRUCTURAL:
            continue
        drums, bass = divmod(tok, genome.DRUM_BASE)
        fired = False
        for bit, note in ((0, 36), (1, 38), (2, 42)):
            if (drums >> bit) & 1:
                _note(events, pending if not fired else 0, 9, note, 110, 10)
                pending = 0
                fired = True
        if bass > 0:
            pitch = bass_note(bass) if mode == "chromatic" else modes.bass_note_mode(bass, mode=mode)
            _note(events, pending if not fired else 0, 0, pitch, 96,
                  TICKS_16TH - 20)
            pending = 0
            fired = True
        pending += TICKS_16TH if not fired else (TICKS_16TH - 10 if fired else 0)
        if fired:
            pending = TICKS_16TH - 10
    events.append(b"\x00\xff\x2f\x00")
    track = b"".join(events)
    with open(path, "wb") as f:
        f.write(b"MThd" + struct.pack(">IHHH", 6, 0, 1, TPQ))
        f.write(b"MTrk" + struct.pack(">I", len(track)) + track)
