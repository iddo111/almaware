# -*- coding: utf-8 -*-
"""A bar (or many) -> a format-0 MIDI file. Stdlib struct, ~40 lines.

The conventions are darwish-midi/body/midi_out.py's, credited: TPQ 480, drums on
channel 10 (kick 36, snare 38, hat 42), bass on channel 1, degree 1..12 read as
a CHROMATIC semitone over A1=45 (the 2026-09-05 pitch fix).

It is a COPY of those conventions rather than an import on purpose: three other
agents were editing darwish-midi tonight, and a run that has to survive weeks
and a reboot must not break because a sibling file moved.
"""
from __future__ import annotations

import struct

TPQ = 480
T16 = TPQ // 4
ROOT = 45


def _vlq(n: int) -> bytes:
    out = bytearray([n & 0x7F])
    n >>= 7
    while n:
        out.insert(0, 0x80 | (n & 0x7F))
        n >>= 7
    return bytes(out)


def write(path: str, bars: list[dict], bpm: float = 143.0, repeats: int = 1) -> str:
    ev = [b"\x00\xff\x51\x03" + struct.pack(">I", int(60_000_000 / bpm))[1:]]
    pending = 0
    for _ in range(repeats):
        for bar in bars:
            for i in range(len(bar["kick"])):
                hits = []
                for lane, note in (("kick", 36), ("snare", 38), ("hat", 42)):
                    if bar[lane][i]:
                        hits.append((9, note, 110, 10))
                d = bar["bass"][i]
                if d:
                    hits.append((0, ROOT + (d - 1), 96, T16 - 20))
                if not hits:
                    pending += T16
                    continue
                for n, (ch, note, vel, dur) in enumerate(hits):
                    ev.append(_vlq(pending if n == 0 else 0) +
                              bytes([0x90 | ch, note, vel]))
                    ev.append(_vlq(dur) + bytes([0x80 | ch, note, 0]))
                    pending = 0
                pending = T16 - max(h[3] for h in hits)
                if pending < 0:
                    pending = 0
    ev.append(b"\x00\xff\x2f\x00")
    track = b"".join(ev)
    with open(path, "wb") as f:
        f.write(b"MThd" + struct.pack(">IHHH", 6, 0, 1, TPQ))
        f.write(b"MTrk" + struct.pack(">I", len(track)) + track)
    return path
