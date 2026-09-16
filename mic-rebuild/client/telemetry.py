"""KESHEV telemetry — K3 (PHASE2-DESIGN.md section 8, scars 18/20).

Two synchronized sinks, one CLOSED event vocabulary:

  * Human log  state\\logs\\mic-YYYYMMDD.log — key=value lines with full ISO
    dates + timezone, 10MB x 14 rotated IN-PROCESS (scar 20: mic-child.log
    hit 10.1MB unrotated; days had to be inferred from midnight rollovers).
  * Machine ledger  state\\events.jsonl — the same events as JSON, one per
    line, ATOMIC append (single O_APPEND write per line). Drills, morning
    checks, gate measurements and the acceptance report read THIS.

Laws enforced here:

  scar 18   Every silent path leaves a line — so emitting must be cheap,
            never throw on IO trouble downstream of validation, and the
            vocabulary must cover every drop class by name.
  scar 20   Full dates in every line, per-minute heartbeat with the fixed
            field set, SESSION_BEGIN/END markers carrying a session id,
            rotation at a hard size cap.
  section 8 The vocabulary is CLOSED: an unknown event name raises
            TypeError (UnknownEventError). DEVICE_* is the one sanctioned
            prefix family. Free-text event names cannot exist.
  privacy   Transcript text and window titles are UNREPRESENTABLE: a
            text= / title= / transcript= field raises TypeError. Lengths,
            logprobs and EXE names only.

No third-party imports. No audio, no devices, no network — pure files.
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
# PHASE2-DESIGN.md section 8 — verbatim. Adding an event is a code change
# under git, never a runtime string.

EVENT_VOCABULARY: frozenset[str] = frozenset({
    "SESSION_BEGIN", "SESSION_END", "STATE", "SEG", "GATED", "EMPTY",
    "DECODE", "TYPED", "DIVERTED", "SPILLED", "STALE_DIVERT",
    "GUARD_DROP", "LANG_DROP", "DUP_DISCARD", "TYPE_FAIL_PARKED",
    "FOCUS_BLOCK", "OWNER_REJ", "GATE_UNAVAILABLE",
    # PRESENCE_REJ (2026-08-15) is NOT OWNER_REJ. OWNER_REJ belongs to the
    # voice-identity gate (criterion 18) and REQUIRED_FIELDS below makes it
    # carry score/theta/mode/len_ms — a scored decision about WHOSE voice it
    # is. The presence gate answers a different, smaller question with no
    # score at all: has a human touched this machine recently. Reusing
    # OWNER_REJ for it raised TelemetryFieldError the moment it fired, which
    # the unit tests missed because they inject a fake emitter and only the
    # end-to-end app tests caught.
    "PRESENCE_REJ",
    # The arm switch (2026-08-17, KESHEV B's surviving verdict — a DELIBERATE
    # consent act, distinct from both OWNER_REJ's voice score and
    # PRESENCE_REJ's idle clock; three gates, three questions, three names).
    "ARM_ON", "ARM_OFF", "ARM_REJ",
    # The hold-while-typing gate (2026-08-17 night: he typed "מיק", a voiced
    # "Hello." landed INSIDE it — "מיHello.ק"). The typer emits this when a
    # burst was HELD for a keyboard-quiet gap (action=held), when the wait
    # ran out and the text was parked instead (action=parked — never
    # dropped), and when auto-Enter was withheld because HE was typing
    # (action=enter_suppressed). wait_ms says how long the mic yielded.
    "TYPING_COLLISION",
    "DEMOTE", "PROMOTE", "PLANNED_DEMOTION", "PIN_FLAKY", "UNPIN",
    "DEAF", "DEAF_DROP", "VRAM_DEGRADE", "LOCAL_UNAVAILABLE",
    "WORKER_KILL", "WORKER_RESPAWN", "BREAKER_TRIP", "UIPI_SELFTEST",
    "CONFIG_HALT", "DRILL_BEGIN", "DRILL_END",
    "ACCEPTANCE_BEGIN", "ACCEPTANCE_END", "HEARTBEAT",
})

# The one sanctioned open family (DEVICE_OPEN, DEVICE_LOST, DEVICE_RECHECK…).
_DEVICE_PREFIX = "DEVICE_"

# Events that MUST carry specific fields (section 8 vocabulary annotations).
REQUIRED_FIELDS: Mapping[str, tuple[str, ...]] = {
    "WORKER_KILL": ("vram_before", "vram_after"),
    "OWNER_REJ": ("score", "theta", "mode", "len_ms"),
    "TYPING_COLLISION": ("action", "wait_ms"),
}

# Privacy: these field names are unrepresentable (section 8 — transcript
# text never in telemetry; EXE names only, never window titles).
_FORBIDDEN_FIELDS = frozenset({"text", "title", "transcript"})

# Heartbeat field set (section 8, verbatim example line).
HEARTBEAT_FIELDS: tuple[str, ...] = (
    "q", "spool_n", "spool_mb", "eng", "state", "p50", "p95",
    "rss_mb", "worker_rss_mb", "worker_vram_mb", "drop_frames",
)

_DEFAULT_MAX_BYTES = 10 * 1024 * 1024
_DEFAULT_BACKUPS = 14


def _now_iso() -> str:
    """Full ISO date, milliseconds, LOCAL timezone offset (scar 20)."""
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def _validate(evt: str, fields: dict[str, Any]) -> None:
    if evt not in EVENT_VOCABULARY:
        if not (evt.startswith(_DEVICE_PREFIX) and len(evt) > len(_DEVICE_PREFIX)):
            raise UnknownEventError(
                f"event {evt!r} is not in the closed vocabulary "
                f"(section 8) and is not a DEVICE_* event"
            )
    bad = _FORBIDDEN_FIELDS & fields.keys()
    if bad:
        raise TelemetryFieldError(
            f"forbidden field(s) {sorted(bad)} on {evt}: transcript text and "
            f"window titles are unrepresentable in telemetry (section 8)"
        )
    missing = [f for f in REQUIRED_FIELDS.get(evt, ()) if f not in fields]
    if missing:
        raise TelemetryFieldError(f"{evt} requires field(s) {missing}")
    for key in fields:
        if not key.isidentifier():
            raise TelemetryFieldError(f"field name {key!r} is not an identifier")


class Telemetry:
    """The two-sink emitter. One instance per client process.

    Thread-safe: `event()` may be called from any thread (capture callback,
    segmenter, router, tray). Ledger lines are written with a single
    O_APPEND os.write, so concurrent lines never interleave.
    """

    def __init__(
        self,
        state_dir: str | Path,
        session_id: str,
        max_bytes: int = _DEFAULT_MAX_BYTES,
        backups: int = _DEFAULT_BACKUPS,
    ) -> None:
        self.state_dir = Path(state_dir)
        self.session_id = session_id
        self.max_bytes = int(max_bytes)
        self.backups = int(backups)
        self.logs_dir = self.state_dir / "logs"
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.ledger_path = self.state_dir / "events.jsonl"
        self._lock = threading.Lock()
        self._ledger_fd = os.open(
            self.ledger_path,
            os.O_APPEND | os.O_CREAT | os.O_WRONLY | getattr(os, "O_BINARY", 0),
        )
        self._log_fh = None  # lazily opened; date-stamped
        self._log_date = ""
        self._hb_stop: threading.Event | None = None
        self._hb_thread: threading.Thread | None = None
        self._closed = False

    # ----------------------------------------------------------- public API

    def event(self, evt: str, level: str = "INFO", **fields: Any) -> None:
        """Emit one event to BOTH sinks. Raises TypeError on vocabulary or
        field violations BEFORE anything is written (sinks stay in step)."""
        _validate(evt, fields)
        ts = _now_iso()
        entry: dict[str, Any] = {"ts": ts, "sid": self.session_id, "evt": evt}
        entry.update(fields)
        ledger_line = json.dumps(entry, ensure_ascii=False) + "\n"
        kv = " ".join(f"{k}={self._fmt(v)}" for k, v in fields.items())
        human_line = f"{ts} {level} sid={self.session_id} evt={evt}"
        if kv:
            human_line += " " + kv
        human_line += "\n"
        with self._lock:
            if self._closed:
                raise RuntimeError("Telemetry is closed")
            os.write(self._ledger_fd, ledger_line.encode("utf-8"))
            self._write_human(human_line.encode("utf-8"))

    def session_begin(self, **fields: Any) -> None:
        self.event("SESSION_BEGIN", **fields)

    def session_end(self, **fields: Any) -> None:
        self.event("SESSION_END", **fields)

    def heartbeat(
        self, *, q: int, spool_n: int, spool_mb: float, eng: str, state: str,
        p50: int, p95: int, rss_mb: int, worker_rss_mb: int,
        worker_vram_mb: int, drop_frames: int,
    ) -> None:
        """The per-minute pulse (scar 20). Keyword-only: a missing field is
        a TypeError at the call site, not a hole in the ledger."""
        self.event(
            "HEARTBEAT", q=q, spool_n=spool_n, spool_mb=spool_mb, eng=eng,
            state=state, p50=p50, p95=p95, rss_mb=rss_mb,
            worker_rss_mb=worker_rss_mb, worker_vram_mb=worker_vram_mb,
            drop_frames=drop_frames,
        )

    def start_heartbeat(
        self, stats_fn: Callable[[], Mapping[str, Any]], interval_s: float = 60.0
    ) -> None:
        """Background per-minute heartbeat. stats_fn returns the full
        HEARTBEAT_FIELDS mapping; a broken stats_fn logs a STATE line
        rather than dying silently (scar 18: every silent path leaves a line)."""
        if self._hb_thread is not None:
            raise RuntimeError("heartbeat already running")
        self._hb_stop = threading.Event()

        def loop() -> None:
            assert self._hb_stop is not None
            while not self._hb_stop.is_set():
                try:
                    self.heartbeat(**dict(stats_fn()))
                except (TypeError, ValueError, KeyError) as exc:
                    self.event("STATE", level="ERROR", state="HEARTBEAT_FAIL",
                               err=type(exc).__name__)
                if self._hb_stop.wait(interval_s):
                    break

        self._hb_thread = threading.Thread(
            target=loop, name="keshev-heartbeat", daemon=True
        )
        self._hb_thread.start()

    def stop_heartbeat(self) -> None:
        if self._hb_stop is not None:
            self._hb_stop.set()
        if self._hb_thread is not None:
            self._hb_thread.join(timeout=5)
            self._hb_thread = None
            self._hb_stop = None

    def close(self) -> None:
        self.stop_heartbeat()
        with self._lock:
            if self._closed:
                return
            self._closed = True
            os.close(self._ledger_fd)
            if self._log_fh is not None:
                self._log_fh.close()
                self._log_fh = None

    # ------------------------------------------------------------ internals

    @staticmethod
    def _fmt(v: Any) -> str:
        if isinstance(v, float):
            return f"{v:g}"
        return str(v)

    def _current_log_path(self) -> Path:
        return self.logs_dir / f"mic-{self._log_date}.log"

    def _write_human(self, data: bytes) -> None:
        """Caller holds self._lock. Rotate by date and by size cap."""
        today = datetime.now().astimezone().strftime("%Y%m%d")
        if self._log_fh is None or self._log_date != today:
            if self._log_fh is not None:
                self._log_fh.close()
            self._log_date = today
            self._log_fh = open(self._current_log_path(), "ab")
        elif self._log_fh.tell() + len(data) > self.max_bytes:
            self._rotate()
        self._log_fh.write(data)
        self._log_fh.flush()

    def _rotate(self) -> None:
        """Size-cap rotation: current file gets the next numbered suffix,
        a fresh mic-<date>.log starts, and the oldest files beyond
        `backups` are deleted. Caller holds self._lock."""
        assert self._log_fh is not None
        self._log_fh.close()
        base = self._current_log_path()
        n = 1
        while (rolled := base.with_name(f"{base.name}.{n}")).exists():
            n += 1
        os.replace(base, rolled)
        self._log_fh = open(base, "ab")
        self._gc_logs()

    def _gc_logs(self) -> None:
        files = sorted(
            self.logs_dir.glob("mic-*.log*"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        current = self._current_log_path()
        keep = files[: self.backups]
        for old in files[self.backups:]:
            if old != current:
                old.unlink(missing_ok=True)
