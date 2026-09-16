"""capture.py — frames off the USB mic. Opens LAST, heals at the edge.

Laws inherited (INSIGHTS §1.5, §1.9; ONE-MIC LAW; ADDENDUM #2):
- The device is chosen by lawbook.choose_device — this module cannot even
  express "open a Bluetooth mic": it receives a name that already passed the
  law, and re-checks it anyway (defense in depth, one line).
- ONE-MIC INTERLOCK: refuse to start while a rival mic app is alive. The
  interlock asks a probe function (production: KESHEV A's kernel mutex,
  read-only OpenMutexW); this module fails CLOSED — no proof of a free mic,
  no capture.
- Self-healing at the edge: device errors reopen with capped backoff
  (1,2,4,8,…60s), journalled DEVICE_LOST/DEVICE_REOPEN. The pipeline never
  dies with the device; it goes IDLE and comes back.
- The audio backend is injected (production: the WASAPI adapter in main;
  tests: a fake). This file names no audio library at all — the ONE-MIC law
  is enforceable by grep, and a test greps it.
"""
from __future__ import annotations

from typing import Callable, Protocol

from .lawbook import is_forbidden


class _JournalLike(Protocol):
    def event(self, name: str, **fields: object) -> dict: ...


class RivalAliveError(RuntimeError):
    """A rival mic app holds the mic — ONE-MIC LAW, fail closed."""


class Capture:
    """Owns the open/reopen lifecycle. Frames flow to on_frame."""

    BACKOFF_S = (1, 2, 4, 8, 16, 32, 60)

    def __init__(self, journal: _JournalLike,
                 rival_alive_fn: Callable[[], bool | None],
                 open_stream_fn: Callable[[str], object],
                 close_stream_fn: Callable[[object], None]) -> None:
        self.journal = journal
        self.rival_alive_fn = rival_alive_fn
        self.open_stream_fn = open_stream_fn
        self.close_stream_fn = close_stream_fn
        self.stream: object | None = None
        self.device_name: str | None = None
        self._consec_failures = 0

    # ------------------------------------------------------------- start --
    def start(self, device_name: str | None) -> bool:
        """Open the stream. False = structural idle (no device / law refusal).
        Raises RivalAliveError when the mic is not provably free."""
        rival = self.rival_alive_fn()
        if rival is None or rival:
            # None = cannot prove the mic is free → CLOSED. The mic-switch
            # scar: a flip proceeded on an audit that admitted it couldn't
            # prove freedom. Never again.
            self.journal.event("STATE", state="RIVAL_ALIVE",
                               proof="none" if rival is None else "mutex")
            raise RivalAliveError("mic not provably free — ONE-MIC LAW")

        if device_name is None or is_forbidden(device_name):
            self.journal.event("IDLE_NO_MIC")
            return False

        self.stream = self.open_stream_fn(device_name)
        self.device_name = device_name
        self._consec_failures = 0
        self.journal.event("DEVICE_OPEN", dev=device_name)
        return True

    # -------------------------------------------------------------- heal --
    def on_device_error(self) -> float:
        """Journal the loss, close, return the backoff the caller sleeps
        before retrying start(). Never raises: healing is a loop, not a
        crash."""
        if self.stream is not None:
            try:
                self.close_stream_fn(self.stream)
            except Exception:  # noqa: BLE001 — a broken handle may not close
                pass
            self.stream = None
        self.journal.event("DEVICE_LOST", dev=self.device_name or "?")
        backoff = self.BACKOFF_S[min(self._consec_failures,
                                     len(self.BACKOFF_S) - 1)]
        self._consec_failures += 1
        return float(backoff)

    def reopened(self) -> None:
        self.journal.event("DEVICE_REOPEN", dev=self.device_name or "?",
                           after_failures=self._consec_failures)
        self._consec_failures = 0

    def stop(self) -> None:
        if self.stream is not None:
            try:
                self.close_stream_fn(self.stream)
            finally:
                self.stream = None
