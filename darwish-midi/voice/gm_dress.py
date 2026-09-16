"""gm_dress.py -- put the model's MIDI through REAL instruments.

Iddo, 2026-08-23 09:20, after hearing the psy_synth render:
  "זה לא מחובר לכלי מידי נורמליים, זה לא מחובר לפקים ולקצב נורמלי,
   זה לא מחובר לסינטי נורמלי ... אז קודם תחבר את זה נורמלי."

WHAT WAS WRONG. Two separate things, and only one of them was the synth:

  1. voice/psy_synth.py is hand-written oscillators. Its own docstring says
     "No sample packs or soundfonts are used here." Nothing on this PC had a
     real instrument in it -- no DAW, no VST, not one soundfont.

  2. The MIDI the bridge emits is format 0, one track, and carries NO PROGRAM
     CHANGE AT ALL (measured: 4149 note-ons on ch9, 3810 on ch0, zero 0xCn
     events). Any real synth therefore plays the bassline as Acoustic Grand
     Piano. That alone would ruin a perfect render.

WHAT THIS DOES. It does not touch the model and does not re-derive the token
mapping -- the bridge already puts drums on ch9 and the pitched voice on ch0,
correctly. This is a MIDI dresser: it re-emits the same events as a format-1
file with instruments assigned, and it splits the single pitched stream into
the two registers psy_synth was faking in DSP:

  ch9  drums   -> program 25, the TR-808 kit in FluidR3 (a real kit, not a sine)
  ch0  bass    -> program 38 Synth Bass 1, one octave DOWN, full velocity
  ch1  lead    -> program 87 Lead 8 (bass+lead), one octave UP, accented only
  ch2  pad     -> program 89 Pad 2 (warm), the bar root, held

The lead is still derived from the bass, because v0's vocabulary has exactly
ONE pitched voice -- 3 drum bits + 12 bass degrees, 108 tokens total. A real
lead needs a richer token language and a retrain on eran4; that is the other
half of the job and no renderer can substitute for it. This file is honest
about being the loudspeaker, not the composer.

Usage:
    python gm_dress.py <in.mid> [out_stem]
"""
import os
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
VENDOR = os.path.normpath(os.path.join(HERE, "..", "vendor"))
FLUIDSYNTH = os.path.join(VENDOR, "fluidsynth",
                          "fluidsynth-v2.6.0-win10-x64-cpp11", "bin", "fluidsynth.exe")
SOUNDFONT = os.path.join(VENDOR, "FluidR3_GM.sf2")

DRUM_CH, BASS_CH, LEAD_CH, PAD_CH = 9, 0, 1, 2
PROG_DRUMKIT = 25      # FluidR3 bank 128: 25 = TR-808 kit
PROG_BASS = 38         # Synth Bass 1
PROG_LEAD = 87         # Lead 8 (bass + lead)
PROG_PAD = 89          # Pad 2 (warm)

ACCENT_VELOCITY = 100  # a lead note only fires on an accent; below this it stays silent
LEAD_MIN_VEL = 70


# ---------------------------------------------------------------- read

def read_varlen(b, i):
    v = 0
    while True:
        c = b[i]
        i += 1
        v = (v << 7) | (c & 0x7F)
        if not c & 0x80:
            return v, i


def parse_midi(path):
    """-> (division, tempo_us, [(abs_tick, status, data_bytes)]) for channel events only."""
    d = open(path, "rb").read()
    if d[:4] != b"MThd":
        raise ValueError("not a MIDI file: %s" % path)
    _fmt, ntrk, division = struct.unpack(">HHH", d[8:14])
    events, tempo_us = [], 500000
    i = 14
    for _ in range(ntrk):
        if d[i:i + 4] != b"MTrk":
            break
        ln = struct.unpack(">I", d[i + 4:i + 8])[0]
        body = d[i + 8:i + 8 + ln]
        i += 8 + ln
        j, t, running = 0, 0, None
        while j < len(body):
            delta, j = read_varlen(body, j)
            t += delta
            if j >= len(body):
                break
            b0 = body[j]
            if b0 == 0xFF:                                  # meta
                mtype = body[j + 1]
                j += 2
                ln2, j = read_varlen(body, j)
                if mtype == 0x51 and ln2 == 3:
                    tempo_us = (body[j] << 16) | (body[j + 1] << 8) | body[j + 2]
                j += ln2
                continue
            if b0 in (0xF0, 0xF7):                          # sysex
                j += 1
                ln2, j = read_varlen(body, j)
                j += ln2
                continue
            if b0 & 0x80:
                running = b0
                j += 1
            st = running
            if st is None:
                break
            hi = st & 0xF0
            n = 1 if hi in (0xC0, 0xD0) else 2
            events.append((t, st, body[j:j + n]))
            j += n
    events.sort(key=lambda e: e[0])
    return division, tempo_us, events


# ---------------------------------------------------------------- write

def varlen(v):
    out = bytearray([v & 0x7F])
    v >>= 7
    while v:
        out.insert(0, (v & 0x7F) | 0x80)
        v >>= 7
    return bytes(out)


def build_track(abs_events):
    """abs_events: [(tick, bytes)] -> an MTrk chunk with correct deltas."""
    abs_events = sorted(abs_events, key=lambda e: e[0])
    out, prev = bytearray(), 0
    for tick, raw in abs_events:
        out += varlen(tick - prev) + raw
        prev = tick
    out += b"\x00\xFF\x2F\x00"
    return b"MTrk" + struct.pack(">I", len(out)) + bytes(out)


# ---------------------------------------------------------------- dress

def dress(in_mid, out_mid):
    division, tempo_us, events = parse_midi(in_mid)

    drums, bass, lead, pad = [], [], [], []

    drums.append((0, bytes([0xC0 | DRUM_CH, PROG_DRUMKIT])))
    bass.append((0, bytes([0xC0 | BASS_CH, PROG_BASS])))
    lead.append((0, bytes([0xC0 | LEAD_CH, PROG_LEAD])))
    pad.append((0, bytes([0xC0 | PAD_CH, PROG_PAD])))

    # a resonant filter sweep on the lead makes it read as an acid line rather
    # than a flat sawtooth: CC74 = brightness, CC71 = resonance
    lead.append((0, bytes([0xB0 | LEAD_CH, 71, 100])))

    bar_ticks = division * 4
    pad_open = {}          # bar index -> root pitch, so the pad changes once per bar
    last_bass_pitch = None
    n_lead = 0

    for tick, st, data in events:
        hi, ch = st & 0xF0, st & 0x0F
        if hi not in (0x80, 0x90):
            continue
        pitch = data[0]
        vel = data[1] if len(data) > 1 else 0
        on = (hi == 0x90 and vel > 0)

        if ch == DRUM_CH:
            drums.append((tick, bytes([st, pitch, vel])))
            continue

        if ch != 0:
            continue

        # --- bass: same line, an octave down, where the psy weight belongs
        bp = max(0, pitch - 12)
        bass.append((tick, bytes([(0x90 if on else 0x80) | BASS_CH, bp, vel if on else 0])))

        # --- lead: the same line an octave up, but only on accents, so it is a
        #     phrase and not a doubling of every bass note
        if on and vel >= ACCENT_VELOCITY:
            lp = min(127, pitch + 12)
            lead.append((tick, bytes([0x90 | LEAD_CH, lp, max(LEAD_MIN_VEL, vel - 10)])))
            lead.append((tick + division // 2, bytes([0x80 | LEAD_CH, lp, 0])))
            # sweep the filter with the phrase
            lead.append((tick, bytes([0xB0 | LEAD_CH, 74, 40 + (n_lead * 7) % 80])))
            n_lead += 1
        if on:
            last_bass_pitch = pitch

        # --- pad: one held root per bar, the harmonic floor psy_synth had none of
        bar = tick // bar_ticks
        if on and bar not in pad_open and last_bass_pitch is not None:
            root = max(0, last_bass_pitch - 24)
            pad.append((bar * bar_ticks, bytes([0x90 | PAD_CH, root, 52])))
            pad.append(((bar + 1) * bar_ticks - 2, bytes([0x80 | PAD_CH, root, 0])))
            pad_open[bar] = root

    tempo_track = build_track([
        (0, b"\xFF\x51\x03" + struct.pack(">I", tempo_us)[1:]),
    ])
    chunks = [tempo_track, build_track(drums), build_track(bass),
              build_track(lead), build_track(pad)]
    head = b"MThd" + struct.pack(">IHHH", 6, 1, len(chunks), division)
    open(out_mid, "wb").write(head + b"".join(chunks))

    bpm = 60_000_000.0 / tempo_us
    print("dressed -> %s" % out_mid)
    print("  %.1f BPM, division %d, %d bars" %
          (bpm, division, (max(e[0] for e in events) // bar_ticks) + 1))
    print("  drums %d ev (TR-808 kit) | bass %d ev (Synth Bass 1, -1 oct) | "
          "lead %d ev (Lead 8, +1 oct, accents only) | pad %d ev (Pad 2 warm)"
          % (len(drums), len(bass), len(lead), len(pad)))
    return out_mid


def render(mid, wav, gain=0.7):
    if not os.path.isfile(FLUIDSYNTH):
        raise SystemExit("fluidsynth missing: %s" % FLUIDSYNTH)
    if not os.path.isfile(SOUNDFONT):
        raise SystemExit("soundfont missing: %s" % SOUNDFONT)
    cmd = [FLUIDSYNTH, "-ni", "-F", wav, "-r", "44100", "-g", str(gain),
           "-o", "synth.reverb.active=1", "-o", "synth.chorus.active=0",
           SOUNDFONT, mid]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not os.path.isfile(wav):
        raise SystemExit("fluidsynth failed (%d):\n%s\n%s" % (r.returncode, r.stdout, r.stderr))
    print("rendered -> %s  (%.1f MB)" % (wav, os.path.getsize(wav) / 1e6))
    return wav


if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else None
    if not src:
        raise SystemExit("usage: gm_dress.py <in.mid> [out_stem]")
    stem = sys.argv[2] if len(sys.argv) > 2 else os.path.splitext(src)[0] + "-GM"
    render(dress(src, stem + ".mid"), stem + ".wav")
