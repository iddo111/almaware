"""supervisor.py — the in-process health verdict. Watchdog-v2 law from birth.

Laws inherited (ADDENDUM #1 — paid for LAST NIGHT, three healthy-mic
restarts; INSIGHTS §5):
- Health = TEXT IN HIS WINDOW, not process-alive, not segments-captured.
- A silent room with heartbeats is QUIET, not DEAF. Silence is not a fault.
- A refusal-by-design (GATED / GUARD_DROP / PRESENCE_REJ) is the app
  WORKING — decodes-without-typing is only a fault when NO gate explains it,
  and even then it is MUTE_SOFT: a visible alarm, never a restart (a restart
  is itself a 60 s break).
- A fault must PERSIST before anyone acts (the 1 s startup IDLE_NO_MIC
  restarted a mic one second from healthy).
- The supervisor emits HEARTBEAT every beat with the three numbers
  (seg/decode/typed) so no dashboard can read "healthy" and miss a dead
  middle.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Protocol


class _JournalLike(Protocol):
    def event(self, name: str, **fields: object) -> dict: ...


# verdicts
HEALTHY = "HEALTHY"
STARTING = "STARTING"
QUIET = "QUIET"            # heartbeats, no audio — a sleeping house
NO_MIC = "NO_MIC"          # structural idle, no authorized USB mic
MUTE = "MUTE"              # segs flow, decodes zero, nothing explains it
MUTE_SOFT = "MUTE_SOFT"    # decodes flow, types zero, no gate explains it
STALLED = "STALLED"        # the pipeline thread stopped beating

FAULTS = (MUTE, MUTE_SOFT, STALLED)


@dataclass
class Window:
    """Rolling counters for one verdict window."""
    seg: int = 0
    decode: int = 0
    typed: int = 0
    gated: int = 0            # every gate refusal, any vocabulary
    parked: int = 0
    started_at: float = field(default_factory=time.monotonic)


class Supervisor:
    """Counts what the pipeline reports; judges by the v2 verdict law.

    The pipeline calls note_*() as things happen; a beat thread calls
    verdict() + heartbeat() every beat_s. No thread lives here — the caller
    owns scheduling (testability; the assembly wires the timer).
    """

    STARTUP_GRACE_S = 180.0        # worker-warmup lesson, generalized
    FAULT_PERSIST_S = 120.0        # a fault must survive two beats to be real

    def __init__(self, journal: _JournalLike, mic_present_fn=lambda: True,
                 window_s: float = 600.0) -> None:
        self.journal = journal
        self.mic_present_fn = mic_present_fn
        self.window_s = window_s
        self.win = Window()
        self._born = time.monotonic()
        self._fault_since: float | None = None
        self._last_beat = time.monotonic()

    # ------------------------------------------------------------- notes --
    def note_seg(self) -> None:
        self.win.seg += 1

    def note_decode(self) -> None:
        self.win.decode += 1

    def note_typed(self) -> None:
        self.win.typed += 1

    def note_gated(self) -> None:
        self.win.gated += 1

    def note_parked(self) -> None:
        self.win.parked += 1

    def roll(self) -> None:
        """Start a fresh window (caller does this every window_s)."""
        self.win = Window()

    # ----------------------------------------------------------- verdict --
    def _raw_verdict(self, now: float) -> tuple[str, str]:
        age = now - self._born
        w = self.win
        if not self.mic_present_fn():
            return NO_MIC, "no authorized USB mic — idle is correct"
        if age < self.STARTUP_GRACE_S and w.seg == 0:
            return STARTING, f"{int(age)}s old, quiet journal is a loading app"
        if w.seg == 0:
            # silence with a living beat is a sleeping house
            return QUIET, "zero segments — silence is not a fault"
        if w.decode == 0 and w.parked == 0 and w.seg >= 3:
            return MUTE, f"{w.seg} segs, zero decodes, zero parks — dead middle"
        if (w.decode >= 8 and w.typed == 0 and w.gated == 0
                and w.parked == 0):
            return MUTE_SOFT, (f"{w.decode} decodes, nothing typed, no gate "
                               "explains it — alarm only, never restart")
        return HEALTHY, f"seg={w.seg} decode={w.decode} typed={w.typed}"

    def verdict(self, now: float | None = None) -> tuple[str, str]:
        """The persistence law: a fault verdict must survive FAULT_PERSIST_S
        before it is reported as a fault; until then it reports the previous
        benign shape (STARTING/QUIET stand in)."""
        t = time.monotonic() if now is None else now
        v, detail = self._raw_verdict(t)
        if v in FAULTS:
            if self._fault_since is None:
                self._fault_since = t
                return QUIET, f"suspect {v} — waiting for persistence: {detail}"
            if t - self._fault_since < self.FAULT_PERSIST_S:
                return QUIET, f"suspect {v} — {int(t - self._fault_since)}s: {detail}"
            return v, detail
        self._fault_since = None
        return v, detail

    # --------------------------------------------------------- heartbeat --
    def heartbeat(self, now: float | None = None) -> dict:
        v, detail = self.verdict(now)
        w = self.win
        rec = self.journal.event(
            "HEARTBEAT", verdict=v, seg=w.seg, decode=w.decode,
            typed=w.typed, gated=w.gated, parked=w.parked, detail=detail)
        self._last_beat = time.monotonic() if now is None else now
        if v in FAULTS:
            self.journal.event("ALARM", verdict=v, detail=detail)
        return rec
