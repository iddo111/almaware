# -*- coding: utf-8 -*-
"""rhythm_lock.py -- beatbox rhythm-lock for DJ ALMIDO, blocker #2.

Takes onset TIMESTAMPS (float seconds, from any detector) and returns a
tempo lock -- or None when the input is not a steady beat. Never guesses.

This module opens NO audio device, NO microphone, NO socket: it is pure
data-in, command-out, like bridge/grammar.py, so it is unit-testable with
synthetic clicks. The future live listener (needs Iddo's confirm before it
is wired permanently to the audio chain) will feed it real onset times;
this file does not care where the timestamps came from.

Pipeline once live:
    beatbox onsets -> lock() -> {"cmd": "SET_TEMPO", "param": N}
        -> send.Sender -> DJ_ALMIDO (Ableton)

BPM range follows protocol.TEMPO_MIN/MAX_BPM (120-160): an estimate
outside the range returns None instead of being silently clamped --
the caller must decide, not the math.
"""
import os
import sys
from dataclasses import dataclass
from statistics import median

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import protocol

MIN_ONSETS = 6          # fewer than this is a fill, not a groove
MAX_SPREAD = 0.08       # median absolute deviation / median IOI above this = not steady
MIN_IOI_S = 0.25        # faster than 240 BPM is hits, not beats
MAX_IOI_S = 0.75        # slower than 80 BPM is drones, not beats


@dataclass
class LockResult:
    bpm: float          # estimated tempo, 120-160
    param: int          # protocol SET_TEMPO param (bpm_to_param)
    confidence: float   # 0..1, 1 = metronomic
    n_onsets: int       # how many timestamps went in
    phase: float        # 0..1, beat-phase of the last onset (for future drop-on-beat)


def lock(onsets) -> "LockResult | None":
    """Estimate tempo from onset timestamps (seconds, ascending).

    Returns LockResult on a steady beat, None on anything else:
    empty/few onsets, non-ascending input, IOIs outside beat range,
    jitter above MAX_SPREAD, or BPM outside 120-160.
    """
    try:
        ts = [float(t) for t in onsets]
    except (TypeError, ValueError):
        return None
    if len(ts) < MIN_ONSETS:
        return None
    if any(b <= a for a, b in zip(ts, ts[1:])):
        return None
    iois = [b - a for a, b in zip(ts, ts[1:])]
    if any(i < MIN_IOI_S or i > MAX_IOI_S for i in iois):
        return None
    med = median(iois)
    mad = median([abs(i - med) for i in iois])
    spread = mad / med
    if spread > MAX_SPREAD:
        return None
    bpm = 60.0 / med
    if not (protocol.TEMPO_MIN_BPM <= bpm <= protocol.TEMPO_MAX_BPM):
        return None
    period = 60.0 / bpm
    phase = (ts[-1] % period) / period
    bpm = round(bpm, 2)  # param derives from the reported value: output is self-consistent
    return LockResult(
        bpm=bpm,
        param=protocol.bpm_to_param(bpm),
        confidence=round(max(0.0, 1.0 - spread / MAX_SPREAD), 3),
        n_onsets=len(ts),
        phase=round(phase, 3),
    )


def to_command(res: LockResult) -> dict:
    """LockResult -> send.py-ready SET_TEMPO_EXACT with the exact float.

    Uses the JSON-side command (OPUS-djalmido's addition), not the 0-127
    wire format -- a locked 140.02 stays 140.02 instead of landing at
    140.157. res.param is kept for booth/dj_bridge consumers that only
    speak the integer format.
    """
    return {"cmd": "SET_TEMPO_EXACT", "bpm": res.bpm, "param": res.param}
