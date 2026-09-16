# -*- coding: utf-8 -*-
r"""midi_in.py -- a MIDI READER, stdlib struct only.

D:\CLAUDE could WRITE midi (darwish-midi/body/midi_out.py) and could CHECK that
a file began with MThd (darwish-midi/proof/measure.py), but nothing in the tree
could READ one back. So the reference profile the judge measures similarity
against could not have been extracted from Chai's real work. This is that file.

Clean-room, format 0 and 1, running status, meta and sysex skipped correctly.
No dependency: mido is not installed on the fleet and we are not installing it.
"""
from __future__ import annotations

import struct

DRUM_CH = 9
KICK = (35, 36)
SNARE = (37, 38, 39, 40)
HAT = (42, 44, 46)


def _vlq(data: bytes, i: int) -> tuple[int, int]:
    n = 0
    while True:
        b = data[i]
        i += 1
        n = (n << 7) | (b & 0x7F)
        if not (b & 0x80):
            return n, i


def read(path: str) -> dict:
    """-> {'division', 'format', 'notes': [(tick, ch, pitch, vel)], 'tempos': [...]}"""
    with open(path, "rb") as f:
        data = f.read()
    if data[:4] != b"MThd":
        raise ValueError(f"{path}: not a MIDI file (no MThd)")
    hlen, fmt, ntrk, div = struct.unpack_from(">IHHH", data, 4)
    if div & 0x8000:
        raise ValueError(f"{path}: SMPTE division {div} unsupported")
    i = 8 + hlen
    notes: list[tuple[int, int, int, int]] = []
    tempos: list[tuple[int, int]] = []
    for _ in range(ntrk):
        if data[i:i + 4] != b"MTrk":
            break
        tlen = struct.unpack_from(">I", data, i + 4)[0]
        j, end = i + 8, i + 8 + tlen
        t, status = 0, 0
        while j < end:
            dt, j = _vlq(data, j)
            t += dt
            if data[j] & 0x80:
                status = data[j]
                j += 1
            # else: RUNNING STATUS -- the byte is data, the status stands
            if status == 0xFF:
                mtype = data[j]
                j += 1
                ln, j = _vlq(data, j)
                if mtype == 0x51 and ln == 3:
                    tempos.append((t, (data[j] << 16) | (data[j + 1] << 8) | data[j + 2]))
                j += ln
            elif status in (0xF0, 0xF7):
                ln, j = _vlq(data, j)
                j += ln
            elif (status & 0xF0) in (0x80, 0x90, 0xA0, 0xB0, 0xE0):
                d1, d2 = data[j], data[j + 1]
                j += 2
                if (status & 0xF0) == 0x90 and d2 > 0:
                    notes.append((t, status & 0x0F, d1, d2))
            elif (status & 0xF0) in (0xC0, 0xD0):
                j += 1
            else:
                raise ValueError(f"{path}: unknown status 0x{status:02x} at {j}")
        i = end
    notes.sort()
    return {"division": div, "format": fmt, "notes": notes, "tempos": tempos}


def lanes(path: str, bass_max: int = 59) -> dict:
    """Quantise one file onto the 16th grid and split into the four ALMA lanes.

    Returns {'steps': N, 'kick'/'snare'/'hat': [0/1]*N, 'bass': [0..12]*N, 'key': pc}
    where bass 0 is a rest and 1..12 is a CHROMATIC semitone over the key --
    the same meaning midi_out.bass_note() gives it after the 2026-09-05 pitch fix.
    """
    m = read(path)
    per16 = max(1, m["division"] // 4)
    raw = m["notes"]
    if not raw:
        return {"steps": 0, "kick": [], "snare": [], "hat": [], "bass": [], "key": 0}
    n = max(1, raw[-1][0] // per16 + 1)
    kick = [0] * n
    snare = [0] * n
    hat = [0] * n
    low: list[int | None] = [None] * n
    for tick, ch, pitch, _vel in raw:
        s = tick // per16
        if s >= n:
            continue
        if ch == DRUM_CH:
            if pitch in KICK:
                kick[s] = 1
            elif pitch in SNARE:
                snare[s] = 1
            elif pitch in HAT:
                hat[s] = 1
        elif pitch <= bass_max:
            if low[s] is None or pitch < low[s]:
                low[s] = pitch
    pcs = [0] * 12
    for p in low:
        if p is not None:
            pcs[p % 12] += 1
    key = max(range(12), key=lambda k: pcs[k]) if any(pcs) else 0
    bass = [0 if p is None else ((p - key) % 12) + 1 for p in low]
    return {"steps": n, "kick": kick, "snare": snare, "hat": hat,
            "bass": bass, "key": key}


if __name__ == "__main__":
    import sys
    for p in sys.argv[1:]:
        L = lanes(p)
        print(f"{p}: steps={L['steps']} key={L['key']} "
              f"kick={sum(L['kick'])} snare={sum(L['snare'])} hat={sum(L['hat'])} "
              f"bass={sum(1 for b in L['bass'] if b)}")
