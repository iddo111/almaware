"""parent.py — the father's channel. Taps pay saved song traces at ACh 1.5, x10.

Silence is neutral, never negative. A tap hours later still pays exactly the
pathways that sang that song (the trace was saved to disk).

REVISION 2026-09-06 (DW-11): payment used to end with
os.rename(taps-<date>.jsonl, taps-<date>.jsonl.paid). tap_server.py appends to
that same daily path all day from another process, so (a) a tap written between
the read loop and the rename was renamed away and never paid, and (b) a second
payout on the same day renamed a fresh file ONTO the existing .paid, and POSIX
rename silently destroyed the earlier record. Payment is now by CURSOR: the
number of lines already paid is kept in a sidecar and the tap file is never
renamed, never moved, never lost.
"""
import json
import os

import genome


def _cursor_path(path):
    return path + ".cursor"


def _read_cursor(path):
    """Lines of `path` already paid. Honours the old .paid marker as 'all paid'."""
    try:
        with open(_cursor_path(path), "r", encoding="utf-8") as f:
            return int(json.load(f).get("lines", 0))
    except (OSError, ValueError, TypeError):
        return 0


def _write_cursor(path, lines):
    tmp = _cursor_path(path) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"lines": int(lines)}, f)
    os.replace(tmp, _cursor_path(path))


def pay_taps(brain, chem, inbox_dir, outbox_dir, log=print):
    """Read tap jsonl files from inbox, pay each against its song's trace."""
    if not os.path.isdir(inbox_dir):
        return 0
    paid_total = 0
    for fname in sorted(os.listdir(inbox_dir)):
        if not fname.endswith(".jsonl"):
            continue
        path = os.path.join(inbox_dir, fname)
        if os.path.exists(path + ".paid"):
            continue                       # legacy marker: that whole file is done
        start = _read_cursor(path)
        seen = 0
        try:
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()      # snapshot; appends after this are next time
        except OSError as e:
            log(f"[parent] cannot read {fname}: {e}")
            continue
        for raw in lines[start:]:
            seen += 1
            line = raw.strip()
            if not line:
                continue
            try:
                tap = json.loads(line)
            except ValueError:
                continue
            song_id, v = tap.get("song_id"), float(tap.get("tap", 0))
            if not song_id or v == 0:
                continue
            trace_path = os.path.join(outbox_dir, song_id + ".trace.json")
            if not os.path.exists(trace_path):
                log(f"[parent] no trace for {song_id}")
                continue
            with open(trace_path, "r", encoding="utf-8") as tf:
                trace = json.load(tf)["trace"]
            old_ach = chem.ach
            chem.mode(genome.ACH_PARENT)          # full attention to אבא
            paid, missing = brain.pay_trace(
                trace, v * genome.V_TAP, genome.ETA_PARENT, chem)
            chem.valence(v)                        # praise lifts the mood
            chem.mode(old_ach)
            frac = paid / max(1, paid + missing)
            log(f"[parent] tap {v:+.0f} on {song_id}: paid {paid} synapses "
                f"({frac:.0%} of trace survived)")
            paid_total += paid
        if seen:
            _write_cursor(path, start + seen)
    return paid_total
