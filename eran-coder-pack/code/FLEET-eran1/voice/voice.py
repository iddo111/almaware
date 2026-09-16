# -*- coding: utf-8 -*-
"""voice.py -- the name eran_life.py imports. A SHIM, on purpose.

RETIRED 2026-08-24. What used to be in this file is now voice_splicer_v0.py:
an echo-babble SPLICER that concatenated snippets of other people's recordings.
It was honest about being that, and it was never ERAN's voice.

WHY THIS FILE STILL EXISTS INSTEAD OF JUST BEING DELETED. eran_life.py line 355
does a bare `import voice` inside the beat loop, and line 356 calls
voice.babble(brain, ears). The living organism has had that module cached in
sys.modules since beat 1, so renaming the file on disk cannot touch the running
process -- but the next time the life loop is started, `import voice` would fail,
be swallowed by the except at line 360, and babble would quietly stop forever
with one honest-looking log line. Retiring a file by breaking a caller is not
retiring it, it is a broken window with a nice comment on it.

So: the contract eran_life.py depends on is preserved EXACTLY. babble() below is
the same function, unchanged, still writing the same wav and the same sidecar to
songs/outbox/. Nothing about the living organism's behaviour changes today.

WHAT REPLACES IT, when Iddo says so. The real mouth now exists on this machine,
next to this file:

    mouth34.py   the vocal tract -- 34 areas -> a waveform, his own tube
    earlink.py   ERAN's own frozen 192-d cochlea + Iddo's real recordings
    gym.py       (1+1) hill climbing: aim, speak, hear yourself, correct
    render.py    one named parameter set -> one wav + one honest number

Switching the life loop's babble from the splicer to the tract is a change to
what the LIVING child does every 13.6 seconds. It is not a refactor and it is
not mine to make. It happens when Iddo says it happens.
"""
from voice_splicer_v0 import babble, GAP_S, SCAN_CAP     # noqa: F401

__all__ = ["babble", "GAP_S", "SCAN_CAP"]
