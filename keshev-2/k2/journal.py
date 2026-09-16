"""KESHEV 2 honest journal — ONE JSONL ledger, CLOSED event vocabulary.

Inherited from KESHEV A's telemetry design (D:\\CLAUDE\\mic-rebuild
client/telemetry.py) by ruling D-001 in DECISIONS.md: A's vocabulary is
kept VERBATIM and extended with the K2 block below, so A's watchdog and
morning-check tooling can read a K2 journal unchanged.

The laws this module enforces (each paid for in A):

  scar 18   Every silent path leaves a line. Emitting is cheap and the
            vocabulary covers every drop class BY NAME — free-text event
            names cannot exist (UnknownEventError).
  scar 20   Full ISO dates with timezone in every line; SESSION_BEGIN/END
            markers carrying a session id; per-minute heartbeat with a
            FIXED field set (keyword-only, so a missing field is a
            TypeError at the call site, not a hole in the ledger).
  privacy   Transcript text and window titles are UNREPRESENTABLE: a
            text= / title= / transcript= field raises TelemetryFieldError.
            Lengths, logprobs, EXE names only.
  species#4 REQUIRED_FIELDS makes scored events carry their score and
            RIVAL_ALIVE carry the detector that fired ("via") — the
            journal proves WHICH guard acted, not just that something did.

One sink only (K2 simplification over A's two): state\\events.jsonl,
appended with a single O_APPEND os.write per line so concurrent lines
never interleave. Human-readable grep works fine on JSONL; a second
key=value sink bought A nothing but drift risk.

stdlib only. No audio, no devices, no network — pure files.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping

# ------------------------------------------------------------------ errors


class UnknownEventError(TypeError):
    """Event name is not in the closed vocabulary (and not DEVICE_*)."""


class TelemetryFieldError(TypeError):
    """Forbidden or missing field on an event (privacy / required-field law)."""


# -------------------------------------------------------------- vocabulary
# KESHEV A's vocabulary VERBATIM (ruling D-001). Adding an event is a code
# change under git, never a runtime string.

A_VOCABULARY: frozenset[str] = frozenset({
    "SESSION_BEGIN", "SESSION_END", "STATE", "SEG", "GATED", "EMPTY",
    "DECODE", "TYPED", "DIVERTED", "SPILLED", "STALE_DIVERT",
    "GUARD_DROP", "LANG_DROP", "DUP_DISCARD", "TYPE_FAIL_PARKED",
    "FOCUS_BLOCK", "OWNER_REJ", "GATE_UNAVAILABLE",
    "PRESENCE_REJ", "ARM_ON", "ARM_OFF", "ARM_REJ",
    "DEMOTE", "PROMOTE", "PLANNED_DEMOTION", "PIN_FLAKY", "UNPIN",
    "DEAF", "DEAF_DROP", "VRAM_DEGRADE", "LOCAL_UNAVAILABLE",
    "WORKER_KILL", "WORKER_RESPAWN", "BREAKER_TRIP", "UIPI_SELFTEST",
    "CONFIG_HALT", "DRILL_BEGIN", "DRILL_END",
    "ACCEPTANCE_BEGIN", "ACCEPTANCE_END", "HEARTBEAT",
})

# The K2 extension block (ruling D-001). Each name exists because K2 has a
# guard A did not:
#   RIVAL_ALIVE / RIVAL_CLEAR  the A-interlock verdict (D-002) — K2 refuses
#                              to run capture while KESHEV A holds the mic.
#   CONFIG_STALE               a config write happened while a live process
#                              runs the OLD value (no-hot-reload contract,
#                              D-005) — the gap is journalled, never silent.
#   SCRIPT_RETRY               the language law's measured answer to a
#                              wrong-script decode (D-004): one re-decode
#                              with the opposite hint, recorded by name.
#   HOTKEY_BOUND / HOTKEY_BIND_FAIL  the arm hotkey's registration verdict
#                              (guard species #5: a key that binds for real
#                              or refuses loudly — never a parser with no
#                              RegisterHotKey behind it). D-008.
K2_VOCABULARY: frozenset[str] = frozenset({
    "RIVAL_ALIVE", "RIVAL_CLEAR", "CONFIG_STALE", "SCRIPT_RETRY",
    "HOTKEY_BOUND", "HOTKEY_BIND_FAIL",
})

EVENT_VOCABULARY: frozenset[str] = A_VOCABULARY | K2_VOCABULARY

# The one sanctioned open family (DEVICE_OPEN, DEVICE_LOST, DEVICE_RECHECK…).
_DEVICE_PREFIX = "DEVICE_"

# Events that MUST carry specific fields. A's two, plus K2's rule that an
# interlock verdict names its detector — "the verdict must reach the
# decision" (guard species #4) begins with the verdict being attributable.
REQUIRED_FIELDS: Mapping[str, tuple[str, ...]] = {
    "WORKER_KILL": ("vram_before", "vram_after"),
    "OWNER_REJ": ("score", "theta", "mode", "len_ms"),
    "RIVAL_ALIVE": ("via",),
    "SCRIPT_RETRY": ("hint_from", "hint_to"),
}

# Privacy: these field names are unrepresentable (transcript text never in
# telemetry; EXE names only, never window titles).
_FORBIDDEN_FIELDS = frozenset({"text", "title", "transcript"})

# Heartbeat field set — kept identical to A so A's watchdog can read us.
HEARTBEAT_FIELDS: tuple[str, ...] = (
    "q", "spool_n", "spool_mb", "eng", "state", "p50", "p95",
    "rss_mb", "worker_rss_mb", "worker_vram_mb", "drop_frames",
)


def _now_iso() -> str:
    """Full ISO date, milliseconds, LOCAL timezone offset (scar 20)."""
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def _validate(evt: str, fields: dict[str, Any]) -> None:
    if evt not in EVENT_VOCABULARY:
        if not (evt.startswith(_DEVICE_PREFIX) and len(evt) > len(_DEVICE_PREFIX)):
            raise UnknownEventError(
                f"event {evt!r} is not in the closed vocabulary and is not "
                f"a DEVICE_* event")
    bad = _FORBIDDEN_FIELDS & fields.keys()
    if bad:
        raise TelemetryFieldError(
            f"forbidden field(s) {sorted(bad)} on {evt}: transcript text and "
            f"window titles are unrepresentable in the journal")
    missing = [f for f in REQUIRED_FIELDS.get(evt, ()) if f not in fields]
    if missing:
        raise TelemetryFieldError(f"{evt} requires field(s) {missing}")
    for key in fields:
        if not key.isidentifier():
            raise TelemetryFieldError(f"field name {key!r} is not an identifier")


class Journal:
    """The one emitter. One instance per client process.

    Thread-safe: `event()` may be called from any thread. Ledger lines are
    written with a single O_APPEND os.write, so concurrent lines never
    interleave. Validation happens BEFORE anything is written.
    """

    def __init__(self, state_dir: str | Path, session_id: str) -> None:
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.session_id = session_id
        self.ledger_path = self.state_dir / "events.jsonl"
        self._lock = threading.Lock()
        self._fd = os.open(
            self.ledger_path,
            os.O_APPEND | os.O_CREAT | os.O_WRONLY | getattr(os, "O_BINARY", 0),
        )
        self._closed = False

    # ----------------------------------------------------------- public API

    def event(self, evt: str, **fields: Any) -> None:
        """Emit one event. Raises TypeError on vocabulary or field
        violations BEFORE the write (a bad event never half-lands)."""
        _validate(evt, fields)
        entry: dict[str, Any] = {
            "ts": _now_iso(), "sid": self.session_id, "evt": evt}
        entry.update(fields)
        line = (json.dumps(entry, ensure_ascii=False) + "\n").encode("utf-8")
        with self._lock:
            if self._closed:
                raise RuntimeError("Journal is closed")
            os.write(self._fd, line)

    def session_begin(self, **fields: Any) -> None:
        self.event("SESSION_BEGIN", **fields)

    def session_end(self, **fields: Any) -> None:
        self.event("SESSION_END", **fields)

    def heartbeat(
        self, *, q: int, spool_n: int, spool_mb: float, eng: str, state: str,
        p50: int, p95: int, rss_mb: int, worker_rss_mb: int,
        worker_vram_mb: int, drop_frames: int,
    ) -> None:
        """The per-minute pulse. Keyword-only: a missing field is a
        TypeError at the call site, not a hole in the ledger."""
        self.event(
            "HEARTBEAT", q=q, spool_n=spool_n, spool_mb=spool_mb, eng=eng,
            state=state, p50=p50, p95=p95, rss_mb=rss_mb,
            worker_rss_mb=worker_rss_mb, worker_vram_mb=worker_vram_mb,
            drop_frames=drop_frames,
        )

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            os.close(self._fd)


def emitter(journal: Journal) -> Callable[..., None]:
    """The emit-callable seam other modules take (presence, interlock,
    typer). Passing the bound method directly is fine too; this exists so
    tests can wrap it, and so production wiring is greppable."""
    return journal.event
