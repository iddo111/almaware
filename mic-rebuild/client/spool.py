"""KESHEV spool — K8 (PHASE2-DESIGN.md section 2 spool.py row, sections
4.1/4.4; PHASE1-INQUIRY.md scars 16/17, criterion 4).

THE mechanism (design structural move #2): the spool directory is the ring
buffer, the spill AND the recovery, in one:

  WRITE-AHEAD   every segment is written to disk (WAV + JSON sidecar, both
                fsynced) BEFORE any queue record exists. A crash between
                write and enqueue therefore loses nothing: the file has no
                terminal outcome in the journal, so recovery finds it.
  EVICT-OLDEST  a full queue evicts the OLDEST record from memory ONLY —
                the file stays on disk and rides the recovery lane
                (scar 17: divert, don't drop; SPILLED is a logged event).
  FRESH/STALE   `is_stale` is the ONE gate (design sec 4.1): fresh segments
                go to the live path; stale backlog is decoded but diverted
                to recovered.txt, NEVER the live typer (scar 16 — typing
                minutes-old text into whatever has focus is the RC-3 class).
  JOURNAL + GC  outcomes append to journal.jsonl (closed vocabulary); a
                spool file is deleted only after a TERMINAL outcome is
                journaled AND the 1h retention has elapsed (design sec 4.4).

Sidecar-commit discipline: the WAV is written first, the sidecar second;
recovery keys on the sidecar, so a crash mid-write leaves at most an
incomplete WAV that no record ever points to — never a truncated segment
presented as whole.

No audio device, no network, no model — pure files. Stdlib + nothing.
(json.dumps only — json.dump is configstore's, lint gate G3.)
"""
from __future__ import annotations

import json
import os
import threading
import wave
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from time import time as _time
from typing import Any, Callable

# ---------------------------------------------------------------- constants
# Code under git, not config keys (design sec 5).

SPOOL_CAPACITY = 50           # design sec 2: deque(50)
RETENTION_S_DEFAULT = 3600    # design sec 4.4: terminal outcome + 1h retention
SAMPLE_RATE = 16000
SAMPLE_WIDTH = 2              # s16le
CHANNELS = 1

# Terminal outcomes end a segment's lifecycle (design sec 4.4); only they
# make a file GC-eligible. SPILLED is journaled but NOT terminal — a spilled
# segment is still owed to Iddo via the recovery lane.
TERMINAL_OUTCOMES: frozenset[str] = frozenset({
    "TYPED", "RECOVERED", "GUARD_DROP", "EMPTY", "DUP_DISCARD", "PARKED",
})
OUTCOME_VOCABULARY: frozenset[str] = TERMINAL_OUTCOMES | frozenset({"SPILLED"})


class UnknownOutcomeError(ValueError):
    """Outcome not in the closed vocabulary — free-text outcomes cannot exist."""


# ------------------------------------------------------------------ records


@dataclass
class SpoolRecord:
    """One write-ahead segment. The in-memory queue holds these; the disk
    holds the truth they point at."""
    id: str
    wav_path: Path
    sidecar_path: Path
    t_start: float          # epoch seconds, segment open
    t_end: float            # epoch seconds, segment close (staleness anchor)
    duration_ms: int
    rms_raw: float = 0.0    # pre-gain rms (what the room actually sounded like)
    gain: float = 1.0       # auto-gain applied to the stored audio

    def read_pcm(self) -> bytes:
        """The stored PCM s16le mono 16k, exactly as written ahead."""
        with wave.open(str(self.wav_path), "rb") as w:
            return w.readframes(w.getnframes())


def is_stale(rec: SpoolRecord, stale_sec: float, now: float) -> bool:
    """The ONE fresh/stale gate (design sec 4.1). Stale segments are decoded
    but routed to recovered.txt — never typed into live focus (scar 16)."""
    return (now - rec.t_end) > stale_sec


class RecoveredTranscript:
    """Append-only recovered.txt writer (scar 16's second destination).
    Open-append-close per line: a crash never holds the file hostage and
    every accepted line is already on disk."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, seg_id: str, text: str, age_s: float) -> None:
        ts = datetime.now().astimezone().isoformat(timespec="seconds")
        line = f"{ts} [{seg_id} +{age_s:.0f}s] {text}\n"
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(line)
            fh.flush()
            os.fsync(fh.fileno())


# -------------------------------------------------------------------- spool


class Spool:
    """Write-ahead directory spool + bounded in-memory deque.

    Thread contract: the segmenter thread calls write_ahead/enqueue, the
    router thread calls pop/journal_outcome/gc — one lock + condition covers
    the queue; file operations are id-scoped and never contended by design
    (one writer per id, the router touches an id only after popping it).
    """

    def __init__(self,
                 spool_dir: str | Path,
                 capacity: int = SPOOL_CAPACITY,
                 retention_s: float = RETENTION_S_DEFAULT,
                 now_fn: Callable[[], float] = _time,
                 on_event: Callable[..., Any] | None = None) -> None:
        self.spool_dir = Path(spool_dir)
        self.spool_dir.mkdir(parents=True, exist_ok=True)
        self.capacity = int(capacity)
        self.retention_s = float(retention_s)
        self.journal_path = self.spool_dir / "journal.jsonl"
        self._now = now_fn
        self._on_event = on_event or (lambda evt, **kw: None)
        self._cond = threading.Condition()
        self._dq: deque[SpoolRecord] = deque()
        self.spilled_count = 0  # visible counter (scar 18 companion)
        # Terminal-outcome index CACHE (2026-08-18, the 15-second-stall
        # scar): _terminal_index() used to re-read and re-parse the WHOLE
        # journal from disk on every call, and sweep() calls gc() once per
        # sidecar — O(files x journal-lines) inside the ROUTER thread.
        # Measured on the live pile: 522 sidecars x 49 ms/scan = 25.6 s
        # with the router blocked, once a minute (SWEEP_INTERVAL_S), which
        # is exactly the 13-26 s SEG->DECODE spikes in events.jsonl. The
        # journal file on disk stays the durable truth; this dict only
        # mirrors it: seeded from disk at most once per process, then kept
        # current by journal_outcome() itself. journal_disk_scans is the
        # visible proof counter — tests pin it to 1.
        self._terminal_cache: dict[str, float] | None = None
        self.journal_disk_scans = 0

    # ------------------------------------------------------------ events

    def emit(self, evt: str, **fields: Any) -> None:
        """Forward an event to the wired sink (K3 telemetry speaks the same
        closed vocabulary — SPILLED / STALE_DIVERT / SEG / GATED …)."""
        self._on_event(evt, **fields)

    # ------------------------------------------------------- write-ahead

    def write_ahead(self, pcm_s16: bytes, *, seg_id: str, t_start: float,
                    t_end: float, duration_ms: int, rms_raw: float,
                    gain: float) -> SpoolRecord:
        """Put the segment on DISK. Never enqueues — that is the caller's
        second, separate step (the crash window between the two is exactly
        what the K8 kill test proves harmless)."""
        wav_path = self.spool_dir / f"{seg_id}.wav"
        sidecar_path = self.spool_dir / f"{seg_id}.json"
        # 1) audio first…
        with open(wav_path, "wb") as fh:
            w = wave.open(fh, "wb")
            w.setnchannels(CHANNELS)
            w.setsampwidth(SAMPLE_WIDTH)
            w.setframerate(SAMPLE_RATE)
            w.writeframes(pcm_s16)
            w.close()
            fh.flush()
            os.fsync(fh.fileno())
        # 2) …sidecar second: it is the commit record recovery keys on.
        meta = {
            "id": seg_id, "t_start": float(t_start), "t_end": float(t_end),
            "duration_ms": int(duration_ms), "rms_raw": float(rms_raw),
            "gain": float(gain), "n_bytes": len(pcm_s16), "rate": SAMPLE_RATE,
        }
        with open(sidecar_path, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(meta, ensure_ascii=False))
            fh.flush()
            os.fsync(fh.fileno())
        return SpoolRecord(
            id=seg_id, wav_path=wav_path, sidecar_path=sidecar_path,
            t_start=float(t_start), t_end=float(t_end),
            duration_ms=int(duration_ms), rms_raw=float(rms_raw),
            gain=float(gain),
        )

    # ------------------------------------------------------------- queue

    def enqueue(self, rec: SpoolRecord) -> SpoolRecord | None:
        """Add to the bounded queue. On full: evict the OLDEST record from
        memory ONLY — its file stays (scar 17), the eviction is journaled
        and emitted as SPILLED. Returns the evicted record, if any."""
        evicted: SpoolRecord | None = None
        with self._cond:
            if len(self._dq) >= self.capacity:
                evicted = self._dq.popleft()
            self._dq.append(rec)
            self._cond.notify()
        if evicted is not None:
            self.spilled_count += 1
            self.journal_outcome(evicted.id, "SPILLED")
            self.emit("SPILLED", id=evicted.id, spool_n=self.qsize())
        return evicted

    def pop(self, timeout: float = 0.5) -> SpoolRecord | None:
        """Oldest record, or None after `timeout` — the router's idle tick
        (design sec 4.1: None -> recovery-drain / probe housekeeping)."""
        with self._cond:
            if not self._dq and timeout and timeout > 0:
                self._cond.wait_for(lambda: bool(self._dq), timeout=timeout)
            if not self._dq:
                return None
            return self._dq.popleft()

    def qsize(self) -> int:
        with self._cond:
            return len(self._dq)

    # ----------------------------------------------------------- journal

    def journal_outcome(self, seg_id: str, outcome: str) -> None:
        """Append one outcome line. Closed vocabulary — an unknown outcome
        is a TypeError-class bug at the call site, never a new state."""
        if outcome not in OUTCOME_VOCABULARY:
            raise UnknownOutcomeError(
                f"outcome {outcome!r} is not in the closed vocabulary "
                f"{sorted(OUTCOME_VOCABULARY)}")
        now = self._now()
        try:
            iso = (datetime.fromtimestamp(now).astimezone()
                   .isoformat(timespec="milliseconds"))
        except (OSError, OverflowError, ValueError):
            # Windows localtime cannot render tiny/synthetic epochs; ts stays
            # the arithmetic truth, the human field says so honestly.
            iso = f"epoch:{now:g}"
        line = json.dumps({
            "ts": now,
            "iso": iso,
            "id": seg_id,
            "outcome": outcome,
        }, ensure_ascii=False) + "\n"
        # single O_APPEND write: concurrent lines never interleave
        fd = os.open(self.journal_path,
                     os.O_APPEND | os.O_CREAT | os.O_WRONLY
                     | getattr(os, "O_BINARY", 0))
        try:
            os.write(fd, line.encode("utf-8"))
            os.fsync(fd)
        finally:
            os.close(fd)
        # Keep the cache current — the line is already durable on disk, so
        # the cache can never claim an outcome the journal does not hold.
        # (An unseeded cache needs no update: the seeding scan will read the
        # line we just wrote.)
        if outcome in TERMINAL_OUTCOMES and self._terminal_cache is not None:
            self._terminal_cache[seg_id] = now

    def _terminal_index(self) -> dict[str, float]:
        """{id: ts of latest TERMINAL outcome}. Served from the in-memory
        cache; the disk journal is parsed at most ONCE per process (see the
        cache comment in __init__ — re-parsing per call was the 25.6 s
        router stall). Callers treat the mapping as read-only."""
        if self._terminal_cache is not None:
            return self._terminal_cache
        self.journal_disk_scans += 1
        index: dict[str, float] = {}
        if not self.journal_path.is_file():
            self._terminal_cache = index
            return index
        for raw in self.journal_path.read_text(encoding="utf-8").splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                entry = json.loads(raw)
            except json.JSONDecodeError:
                # a torn tail line (crash mid-append) is expected exactly once
                # at the end; it is unreadable, so it cannot mark anything
                # terminal — the segment stays recoverable (fail-open for
                # recovery, fail-closed for deletion).
                continue
            if entry.get("outcome") in TERMINAL_OUTCOMES:
                index[str(entry.get("id"))] = float(entry.get("ts", 0.0))
        self._terminal_cache = index
        return index

    # ---------------------------------------------------------- recovery

    def _record_from_sidecar(self, sidecar_path: Path) -> SpoolRecord | None:
        try:
            meta = json.loads(sidecar_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None  # incomplete commit record: the WAV was never whole
        wav_path = self.spool_dir / f"{meta['id']}.wav"
        if not wav_path.is_file():
            return None
        return SpoolRecord(
            id=str(meta["id"]), wav_path=wav_path, sidecar_path=sidecar_path,
            t_start=float(meta["t_start"]), t_end=float(meta["t_end"]),
            duration_ms=int(meta["duration_ms"]),
            rms_raw=float(meta.get("rms_raw", 0.0)),
            gain=float(meta.get("gain", 1.0)),
        )

    def orphans(self) -> list[SpoolRecord]:
        """Every on-disk segment with NO terminal outcome and NO in-memory
        record — the recovery lane (crash survivors + spilled evictions),
        oldest first. This is what `maybe_drain_recovery` decodes into
        recovered.txt (design sec 4.1)."""
        terminal = self._terminal_index()
        with self._cond:
            queued_ids = {r.id for r in self._dq}
        out: list[SpoolRecord] = []
        for sidecar in sorted(self.spool_dir.glob("*.json")):
            rec = self._record_from_sidecar(sidecar)
            if rec is None or rec.id in terminal or rec.id in queued_ids:
                continue
            out.append(rec)
        out.sort(key=lambda r: (r.t_end, r.id))
        return out

    # ---------------------------------------------------------------- GC

    def gc(self, seg_id: str) -> bool:
        """Delete a segment's files — ONLY if a terminal outcome is journaled
        AND retention has elapsed since it (design sec 4.4). Returns True if
        deleted. Refusal is the safe default, never an error."""
        terminal = self._terminal_index()
        ts = terminal.get(seg_id)
        if ts is None:
            return False
        if self._now() < ts + self.retention_s:
            return False
        (self.spool_dir / f"{seg_id}.wav").unlink(missing_ok=True)
        (self.spool_dir / f"{seg_id}.json").unlink(missing_ok=True)
        return True

    def sweep(self) -> list[str]:
        """GC every eligible segment; returns the ids removed. Cheap enough
        for the router's idle tick."""
        removed: list[str] = []
        for sidecar in sorted(self.spool_dir.glob("*.json")):
            seg_id = sidecar.stem
            if self.gc(seg_id):
                removed.append(seg_id)
        return removed
