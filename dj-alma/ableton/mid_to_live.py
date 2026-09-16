# -*- coding: utf-8 -*-
"""mid_to_live.py -- take a MIDI file Chai the Songbird actually composed and
put it into Ableton Live as REAL CLIPS ON REAL TRACKS, with the tempo and the
key set, so Iddo can mix it himself.

לזכרה של עלמה ז״ל ולזכרו של לָאוֹר ז״ל.

WHAT THIS IS FOR
----------------
`compose_and_send.py` (next to this file) asks the Darwish model for a fresh
section and writes it into Live. That is the "generate something new" path.
This file is the OTHER path, and it is the one that was missing: Chai is
already alive on eran4 composing a song every ~16 minutes, 200 of them sitting
in `~/darwish-midi/songs/outbox/`. Those are finished pieces. Until now there
was no way to get one of them onto Ableton's timeline -- the booth rendered
them straight to an .mp3 (finished audio, unmixable) and the Ableton arm could
only write freshly-generated model output. This closes that gap:

    a .mid Chai wrote  ->  parts split by MIDI channel  ->  one Ableton MIDI
    track per part, one clip each, tempo set from the file, key measured from
    the notes

WHAT IT DOES NOT DO -- the same discipline booth/compose.py states about itself
---------------------------------------------------------------------------
It does not compose, transpose, quantize, harmonize, re-voice or "fix" anything.
Every note that reaches Live is a note Chai wrote, at his pitch, at his time.
Specifically:

  * It does NOT split a monophonic line into "bass" and "lead" tracks by
    register. Chai's pitched channel is strictly monophonic (measured: max 1
    simultaneous note), and cutting one melodic line in half at MIDI 52 would
    invent a two-part arrangement he never played. That is available behind an
    explicit `--split-register` flag, off by default, and the flag documents
    that it is an editorial choice, not a transcription.
  * It does NOT invent a key. The key is MEASURED from the pitch-class content
    by Krumhansl-Schmuckler correlation and reported WITH its confidence. If
    the correlation is weak the key is reported as uncertain and, unless you
    pass --force-key, is not sent to Live at all.
  * It does NOT assume Live supports setting a key. Live 12.4.5's own LOM type
    table on this machine (_MxDCore/LomTypes.pyc) DOES contain `root_note`,
    `scale_name`, `scale_intervals` and `scale_mode` -- measured, one
    occurrence each -- but that table does not say which object owns them, and
    the attribute has moved between Live versions. So SET_SONG_SCALE is sent
    BEST-EFFORT: DJ_ALMIDO checks the Song object for the attributes and says
    plainly whether it found them. A failure there is reported, never
    swallowed -- the tempo and the notes still go in regardless.

DRY RUN
-------
`--dry-run` opens no socket and touches nothing. It prints the exact command
sequence it would send, with the real note counts, so the whole pipeline can be
checked with Ableton closed (which is how it was verified -- Live must not be
launched by a script; it claims the audio devices the moment it opens, and that
is Iddo's decision alone).

USAGE
-----
    python mid_to_live.py --dry-run chai-in/chai-20260912-020906.mid
    python mid_to_live.py chai-in/chai-20260912-020906.mid      # for real
"""
from __future__ import annotations

import argparse
import collections
import contextlib
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import send  # ./send.py -- the stdlib socket client, already has dry_run

try:
    import mido
except ImportError:  # pragma: no cover - environment problem, not a code path
    raise SystemExit(
        "mid_to_live.py needs `mido` to read a MIDI file. Install it with:\n"
        '    "C:\\Program Files\\Python312\\python.exe" -m pip install -r '
        "..\\requirements.txt"
    )

PITCH_CLASS_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# Krumhansl-Schmuckler key profiles (Krumhansl & Kessler 1982). Used ONLY to
# report a measured key with a confidence number -- never to alter a note.
KS_MAJOR = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
KS_MINOR = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]

# Below this correlation the key call is not trustworthy enough to push into
# Live. Chai's own files measure ~0.85, far above it; a chromatic or atonal
# source would land near 0 and correctly refuse.
KEY_CONFIDENCE_FLOOR = 0.60

DRUM_CHANNEL = 9  # General MIDI: channel 10, 0-based 9

# Channel -> part name. Mirrors booth/compose.py's own ROLE_CHANNEL
# ({"lead": 0, "bass": 1, "pad": 2}) so a file written by compose.write_midi
# lands on correctly-named tracks. Chai's raw output uses only 0 and 9.
CHANNEL_PART_NAME = {0: "Lead", 1: "Bass", 2: "Pad", DRUM_CHANNEL: "Drums"}

# booth/compose.py's own register line, reused unchanged, for --split-register.
SOLO_BASS_BELOW = 52

BEATS_PER_BAR = 4.0  # 4/4 throughout, the same assumption compose.py and
                     # psy_render make; Chai writes no time-signature meta.


class Note:
    __slots__ = ("channel", "pitch", "start_beats", "duration_beats", "velocity")

    def __init__(self, channel, pitch, start_beats, duration_beats, velocity):
        self.channel = channel
        self.pitch = pitch
        self.start_beats = start_beats
        self.duration_beats = duration_beats
        self.velocity = velocity

    def to_spec(self) -> dict:
        """The note-spec dict DJ_ALMIDO's WRITE_NOTES expects -- the same shape
        score_bridge.score_to_notes produces, so both paths speak one format."""
        return {
            "pitch": self.pitch,
            "start_time": self.start_beats,
            "duration": self.duration_beats,
            "velocity": self.velocity,
            "mute": 0,
        }


def read_notes(path: str):
    """Parse a MIDI file into (notes, bpm, ticks_per_beat).

    Times come out in BEATS, which is Live's clip-editing unit. Note-off is
    matched per (channel, pitch) FIFO; a note_on with velocity 0 counts as a
    note-off, which is how most writers (mido's own included) encode it.

    A note left hanging at end-of-file is closed at the last event rather than
    dropped -- dropping it would silently lose a sustained final note.
    """
    mf = mido.MidiFile(path)
    tpb = mf.ticks_per_beat
    bpm = None

    open_notes = collections.defaultdict(collections.deque)
    notes = []
    now_ticks = 0

    # merged_track flattens all tracks onto one timeline with absolute-ish
    # delta times already resolved per message, which is what we want: Chai
    # writes a type-0 file, but compose.write_midi could produce type 1.
    for msg in mido.merge_tracks(mf.tracks):
        now_ticks += msg.time
        if msg.type == "set_tempo" and bpm is None:
            # MIDI stores tempo as an INTEGER number of microseconds per
            # quarter note, so 140 BPM is not exactly representable and
            # tempo2bpm hands back 140.00014000014. Rounding to 3 decimals
            # recovers the tempo that was actually intended, and is still ~30x
            # finer than the 0.01 BPM Live itself displays. Not rounding here
            # would make SET_TEMPO_EXACT a lie: this whole command exists to
            # stop a fractional-BPM drift, so it must not introduce its own.
            bpm = round(mido.tempo2bpm(msg.tempo), 3)
        elif msg.type == "note_on" and msg.velocity > 0:
            open_notes[(msg.channel, msg.note)].append((now_ticks, msg.velocity))
        elif msg.type == "note_off" or (msg.type == "note_on" and msg.velocity == 0):
            key = (msg.channel, msg.note)
            if open_notes[key]:
                start_ticks, vel = open_notes[key].popleft()
                notes.append(Note(
                    channel=msg.channel,
                    pitch=msg.note,
                    start_beats=start_ticks / tpb,
                    duration_beats=max(1, now_ticks - start_ticks) / tpb,
                    velocity=vel,
                ))

    # Close anything still sounding at the end of the file.
    for (channel, pitch), pending in open_notes.items():
        while pending:
            start_ticks, vel = pending.popleft()
            notes.append(Note(channel, pitch,
                              start_ticks / tpb,
                              max(1, now_ticks - start_ticks) / tpb,
                              vel))

    notes.sort(key=lambda n: (n.start_beats, n.channel, n.pitch))
    return notes, bpm, tpb


def _correlation(a, b) -> float:
    mean_a = sum(a) / len(a)
    mean_b = sum(b) / len(b)
    num = sum((x - mean_a) * (y - mean_b) for x, y in zip(a, b))
    den_a = sum((x - mean_a) ** 2 for x in a) ** 0.5
    den_b = sum((y - mean_b) ** 2 for y in b) ** 0.5
    return num / (den_a * den_b) if den_a and den_b else 0.0


def detect_key(notes):
    """Measure the key from pitched (non-drum) notes.

    Returns (root_note, scale_name, confidence, runner_up_name) where
    root_note is 0-11 with C=0 -- the convention Live's own `root_note` uses --
    or (None, None, 0.0, None) if there are no pitched notes at all.

    Weighted by SOUNDING TIME, not note count: a whole-note tonic should count
    for more than a passing sixteenth, which is what the KS profiles were
    derived against.
    """
    histogram = [0.0] * 12
    for n in notes:
        if n.channel == DRUM_CHANNEL:
            continue
        histogram[n.pitch % 12] += n.duration_beats

    if sum(histogram) == 0:
        return None, None, 0.0, None

    scored = []
    for root in range(12):
        rotated = histogram[root:] + histogram[:root]
        scored.append((_correlation(rotated, KS_MAJOR), root, "Major"))
        scored.append((_correlation(rotated, KS_MINOR), root, "Minor"))
    scored.sort(reverse=True, key=lambda t: t[0])

    confidence, root, scale_name = scored[0]
    runner_up = f"{PITCH_CLASS_NAMES[scored[1][1]]} {scored[1][2]}"
    return root, scale_name, confidence, runner_up


def split_parts(notes, split_register: bool = False):
    """Group notes into named parts, one Ableton track each.

    Default rule: ONE PART PER MIDI CHANNEL. This is pure transcription -- the
    channels are the parts the composer wrote.

    --split-register additionally cuts a monophonic pitched channel at MIDI 52
    (booth/compose.py's SOLO_BASS_BELOW) into a Bass part and a Lead part. That
    is an EDITORIAL choice: it fabricates a two-part arrangement out of one
    line. Off by default, and the caller is told when it is on.
    """
    by_channel = collections.defaultdict(list)
    for n in notes:
        by_channel[n.channel].append(n)

    parts = []  # list of (part_name, [notes])
    for channel in sorted(by_channel):
        channel_notes = by_channel[channel]
        base_name = CHANNEL_PART_NAME.get(channel, f"Ch{channel}")

        if split_register and channel != DRUM_CHANNEL:
            low = [n for n in channel_notes if n.pitch < SOLO_BASS_BELOW]
            high = [n for n in channel_notes if n.pitch >= SOLO_BASS_BELOW]
            # Only actually split if BOTH halves have notes -- otherwise the
            # split would produce an empty track, which is noise in Live.
            if low and high:
                parts.append(("Bass", low))
                parts.append(("Lead", high))
                continue

        parts.append((base_name, channel_notes))
    return parts


def clip_length_beats(notes, whole_bars: bool = True) -> float:
    """Clip length = end of the last note, rounded UP to a whole bar.

    Rounding up matters: a clip that ends mid-bar loops off-grid, which would
    make the whole thing unusable for the one job it has (letting Iddo mix it).
    """
    if not notes:
        return BEATS_PER_BAR
    end = max(n.start_beats + n.duration_beats for n in notes)
    if not whole_bars:
        return end
    bars = int(end / BEATS_PER_BAR)
    if end > bars * BEATS_PER_BAR:
        bars += 1
    return max(1, bars) * BEATS_PER_BAR


def build_plan(path: str, split_register: bool = False, force_key: bool = False,
               clip_slot: int = 0, tempo_override: float | None = None) -> dict:
    """Everything that happens BEFORE any socket is opened. Pure function of
    the file on disk -- this is what --dry-run prints, and it is the same
    object send_plan() executes, so the dry run cannot drift from the real run.
    """
    notes, file_bpm, tpb = read_notes(path)
    bpm = tempo_override if tempo_override is not None else file_bpm

    root, scale_name, confidence, runner_up = detect_key(notes)
    key_trusted = confidence >= KEY_CONFIDENCE_FLOOR
    send_key = root is not None and (key_trusted or force_key)

    parts = split_parts(notes, split_register=split_register)
    stem = os.path.splitext(os.path.basename(path))[0]

    # ONE clip length for every part of the same song, not one per part.
    # Measured on Chai's own output: his lead runs to 224 beats (56 bars) and
    # his drums to 220 (55). Written at their individual lengths, the two clips
    # sit in the same Session scene looping at different periods and walk out
    # of phase with each other after the first pass -- which destroys the only
    # thing this importer is for. The longest part sets the bar count and the
    # shorter ones simply have empty bars at the end, which is what a DAW
    # expects. No note moves; only the loop brace changes.
    unified_length = max(clip_length_beats(ns) for _, ns in parts) if parts else BEATS_PER_BAR

    planned_parts = []
    for part_name, part_notes in parts:
        pitched = [n for n in part_notes if n.channel != DRUM_CHANNEL]
        planned_parts.append({
            "part_name": part_name,
            "track_name": f"ALMIDO {part_name}",
            "clip_name": f"{stem} {part_name}",
            "n_notes": len(part_notes),
            "channel": part_notes[0].channel if part_notes else None,
            "pitch_lo": min((n.pitch for n in part_notes), default=None),
            "pitch_hi": max((n.pitch for n in part_notes), default=None),
            "is_drums": bool(part_notes) and part_notes[0].channel == DRUM_CHANNEL,
            "max_simultaneous": max_simultaneous(pitched) if pitched else 0,
            "clip_length_beats": unified_length,
            "own_length_beats": clip_length_beats(part_notes),
            "notes": [n.to_spec() for n in part_notes],
        })

    return {
        "source_file": os.path.abspath(path),
        "ticks_per_beat": tpb,
        "file_bpm": file_bpm,
        "bpm": bpm,
        "tempo_overridden": tempo_override is not None,
        "n_notes_total": len(notes),
        "key_root": root,
        "key_root_name": PITCH_CLASS_NAMES[root] if root is not None else None,
        "key_scale": scale_name,
        "key_confidence": confidence,
        "key_runner_up": runner_up,
        "key_trusted": key_trusted,
        "key_will_be_sent": send_key,
        "split_register": split_register,
        "clip_slot": clip_slot,
        "parts": planned_parts,
    }


def max_simultaneous(notes) -> int:
    """Peak polyphony, by sweeping note starts and ends. Reported because it is
    the single number that says whether a part carries harmony at all -- Chai's
    pitched channel measures 1, i.e. strictly monophonic, and that is a real
    property of his vocabulary, not a bug in this importer."""
    events = []
    for n in notes:
        events.append((n.start_beats, 1))
        events.append((n.start_beats + n.duration_beats, -1))
    events.sort(key=lambda e: (e[0], e[1]))  # ends before starts at equal time
    peak = current = 0
    for _, delta in events:
        current += delta
        peak = max(peak, current)
    return peak


def print_plan(plan: dict, stream=sys.stdout):
    w = lambda s="": print(s, file=stream)
    w("=" * 72)
    w("DJ ALMIDO -- MIDI -> Ableton Live plan")
    w("=" * 72)
    w(f"source          : {plan['source_file']}")
    w(f"ticks per beat  : {plan['ticks_per_beat']}")
    bpm = plan["bpm"]
    if plan["tempo_overridden"]:
        w(f"tempo           : {bpm:.3f} BPM  (OVERRIDDEN; file says {plan['file_bpm']})")
    else:
        w(f"tempo           : {bpm:.3f} BPM  (read from the file)")

    if plan["key_root"] is None:
        w("key             : no pitched notes -- nothing to measure")
    else:
        verdict = "trusted" if plan["key_trusted"] else "UNCERTAIN"
        w(f"key (measured)  : {plan['key_root_name']} {plan['key_scale']}  "
          f"(confidence {plan['key_confidence']:.3f}, {verdict}; "
          f"runner-up {plan['key_runner_up']})")
        if not plan["key_will_be_sent"]:
            w("                  -> NOT sent to Live (below the "
              f"{KEY_CONFIDENCE_FLOOR} floor; pass --force-key to send anyway)")

    w(f"total notes     : {plan['n_notes_total']}")
    if plan["split_register"]:
        w("split-register  : ON -- a monophonic line is being cut at MIDI "
          f"{SOLO_BASS_BELOW} into Bass/Lead. This is an EDITORIAL choice.")
    w()
    w(f"{len(plan['parts'])} track(s) would be created:")
    w("-" * 72)
    for i, p in enumerate(plan["parts"]):
        kind = "drums" if p["is_drums"] else f"poly={p['max_simultaneous']}"
        w(f"  [{i}] track {p['track_name']!r}")
        w(f"      clip   {p['clip_name']!r} in slot {plan['clip_slot']}")
        w(f"      {p['n_notes']:>5} notes  ch{p['channel']}  "
          f"pitch {p['pitch_lo']}-{p['pitch_hi']}  {kind}")
        padded = ""
        if p["own_length_beats"] < p["clip_length_beats"]:
            padded = (f"  [padded from {p['own_length_beats'] / BEATS_PER_BAR:.0f}"
                      f" bars so every clip loops in phase]")
        w(f"      clip length {p['clip_length_beats']:.1f} beats "
          f"({p['clip_length_beats'] / BEATS_PER_BAR:.0f} bars){padded}")
    w("-" * 72)
    w()
    w("command sequence:")
    w("  PING")
    w(f"  SET_TEMPO_EXACT bpm={bpm:.3f}")
    if plan["key_will_be_sent"]:
        w(f"  SET_SONG_SCALE root_note={plan['key_root']} "
          f"({plan['key_root_name']}) scale_name={plan['key_scale']!r}  [best-effort]")
    for p in plan["parts"]:
        w(f"  CREATE_MIDI_TRACK name={p['track_name']!r}")
        w(f"  WRITE_NOTES  {p['n_notes']} notes -> that track, slot "
          f"{plan['clip_slot']}, length {p['clip_length_beats']:.1f} beats, "
          f"clip_name={p['clip_name']!r}")
    w("=" * 72)


def send_plan(plan: dict, host: str, port: int, dry_run: bool) -> int:
    """Execute the plan against DJ_ALMIDO. Returns a process exit code.

    Every reply is checked. A failed CREATE_MIDI_TRACK or WRITE_NOTES aborts
    with a non-zero exit rather than continuing and leaving a half-imported
    song in Live -- a half-import that reports success is exactly the kind of
    broken window this project's own rules forbid.
    """
    try:
        sender = send.Sender(host, port, dry_run=dry_run)
    except send.NotConnected as e:
        print(f"\nNOT SENT: {e}", file=sys.stderr)
        print("\nAbleton Live is not listening on "
              f"{host}:{port}. Run again with --dry-run to check the plan "
              "without Live, or open Live and select DJ_ALMIDO under "
              "Preferences -> Link, Tempo & MIDI -> Control Surface "
              "(see INSTALL.md).", file=sys.stderr)
        return 2

    # send.py echoes EVERY dry-run command to stderr, note list included --
    # about 100 KB of JSON for a real song, which buries the readable plan
    # print_plan just rendered. Silence only that echo; keep driving the real
    # Sender.dry_run code path, so the dry run cannot drift from the real run,
    # and leave this function's own error messages going to stderr as normal.
    raw_send = sender.send_command  # bound once, deliberately not a call site

    def _send(cmd, **fields):
        if dry_run:
            with contextlib.redirect_stderr(io.StringIO()):
                return raw_send(cmd, **fields)
        return raw_send(cmd, **fields)

    failures = 0
    with sender:
        reply = _send("PING")
        if not reply.get("ok"):
            print(f"PING failed: {reply}", file=sys.stderr)
            return 2
        if not dry_run:
            result = reply.get("result") or {}
            print(f"connected: Live has {result.get('n_tracks')} track(s), "
                  f"{result.get('n_scenes')} scene(s)")

        # -- tempo. SET_TEMPO_EXACT is this file's own addition; fall back to
        # the original 0-127 SET_TEMPO if an older DJ_ALMIDO is installed.
        reply = _send("SET_TEMPO_EXACT", bpm=plan["bpm"])
        if not reply.get("ok"):
            print(f"  SET_TEMPO_EXACT unavailable ({reply.get('error')}), "
                  "falling back to the quantized SET_TEMPO", file=sys.stderr)
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "dj_alma_protocol", r"D:\CLAUDE\dj-alma\bridge\protocol.py")
            protocol = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(protocol)
            param = protocol.bpm_to_param(plan["bpm"])
            reply = _send("SET_TEMPO", param=param)
            if not reply.get("ok"):
                print(f"  tempo NOT set: {reply.get('error')}", file=sys.stderr)
                failures += 1
            else:
                got = (reply.get("result") or {}).get("bpm")
                print(f"  tempo set to {got} BPM (quantized from "
                      f"{plan['bpm']:.3f} by the 0-127 wire format)")
        elif not dry_run:
            print(f"  tempo set to {(reply.get('result') or {}).get('bpm')} BPM")

        # -- key, best effort. root_note/scale_name DO exist in Live 12.4.5's
        # LOM type table, but nothing on disk says which object owns them, so
        # this is allowed to fail without failing the whole import -- and it
        # is REPORTED when it does, never swallowed.
        if plan["key_will_be_sent"]:
            reply = _send(
                "SET_SONG_SCALE",
                root_note=plan["key_root"],
                scale_name=plan["key_scale"],
            )
            if reply.get("ok"):
                if not dry_run:
                    print(f"  key set to {plan['key_root_name']} "
                          f"{plan['key_scale']}: {reply.get('result')}")
            else:
                print(f"  key NOT set (this Live may not expose it): "
                      f"{reply.get('error')}", file=sys.stderr)

        # -- the tracks and clips
        for p in plan["parts"]:
            reply = _send("CREATE_MIDI_TRACK", name=p["track_name"])
            if not reply.get("ok"):
                print(f"  CREATE_MIDI_TRACK {p['track_name']!r} FAILED: "
                      f"{reply.get('error')}", file=sys.stderr)
                return 1
            track_index = (reply.get("result") or {}).get("track_index", 0)

            reply = _send(
                "WRITE_NOTES",
                track_index=track_index,
                clip_slot_index=plan["clip_slot"],
                notes=p["notes"],
                clip_length_beats=p["clip_length_beats"],
                clip_name=p["clip_name"],
            )
            if not reply.get("ok"):
                print(f"  WRITE_NOTES into {p['track_name']!r} FAILED: "
                      f"{reply.get('error')}", file=sys.stderr)
                return 1
            if not dry_run:
                n = (reply.get("result") or {}).get("n_notes")
                print(f"  {p['track_name']}: wrote {n} notes into track "
                      f"{track_index}, slot {plan['clip_slot']}")

    if dry_run:
        print("\nDRY RUN -- no socket was opened, Ableton was not touched.")
    else:
        print(f"\nDone. {len(plan['parts'])} track(s) in Live. "
              "Nothing was played; press play yourself when you want to hear it.")
    return 1 if failures else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Put a MIDI file Chai composed into Ableton Live as real "
                    "clips on real tracks, tempo and key set.")
    ap.add_argument("midi_file", help="path to the .mid (e.g. chai-in/chai-20260912-020906.mid)")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the exact plan and open no socket at all")
    ap.add_argument("--split-register", action="store_true",
                    help="EDITORIAL: also cut a monophonic pitched channel at "
                         f"MIDI {SOLO_BASS_BELOW} into separate Bass and Lead tracks")
    ap.add_argument("--force-key", action="store_true",
                    help="send the measured key to Live even if its confidence "
                         f"is below {KEY_CONFIDENCE_FLOOR}")
    ap.add_argument("--tempo", type=float, default=None,
                    help="override the BPM instead of reading it from the file")
    ap.add_argument("--clip-slot", type=int, default=0,
                    help="Session View clip slot (row) to write into (default 0)")
    ap.add_argument("--host", default=send.HOST)
    ap.add_argument("--port", type=int, default=send.PORT)
    args = ap.parse_args(argv)

    if not os.path.exists(args.midi_file):
        print(f"no such file: {args.midi_file}", file=sys.stderr)
        return 2

    plan = build_plan(
        args.midi_file,
        split_register=args.split_register,
        force_key=args.force_key,
        clip_slot=args.clip_slot,
        tempo_override=args.tempo,
    )
    print_plan(plan)

    if not plan["parts"]:
        print("\nThis file contains no notes -- nothing to import.", file=sys.stderr)
        return 2

    return send_plan(plan, args.host, args.port, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
