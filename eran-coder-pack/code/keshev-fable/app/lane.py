"""lane.py — the ONE thread that decodes. The audio thread only hands over ids.

Laws (INSIGHTS §1.11; keshev-fable README "one thread per concern"):
- SYNCHRONOUS single lane: live records and the 60 s drain pass through the
  SAME queue, so a decode and a drain can never overlap — "parallel decode
  lanes are how the same audio types twice" now has no second lane to use.
- The audio callback (100 ms blocks) must never wait on the network. Until
  2026-08-20 router.process_one ran inside it: ~350 ms decode + ~175 ms
  LANG_FLIP + owner-gate per utterance, every one of them a hole in the
  NEXT utterance's first frames. submit() is a queue put and returns.
- A raising record is reported through on_error and the lane lives on
  (router.process_one_safe already fences; this is the belt to its braces).
- stop() is clean and idempotent; nothing here opens a device or a file.
"""
from __future__ import annotations

import queue
import threading
from typing import Callable, Protocol


class _RouterLike(Protocol):
    def process_one_safe(self, rec_id: str) -> str: ...
    def drain(self, max_records: int = 50) -> dict[str, int]: ...


_DRAIN = object()
_STOP = object()


class Lane:
    def __init__(self, router: _RouterLike,
                 on_outcome: Callable[[str, str], None] | None = None,
                 on_error: Callable[[str, str], None] | None = None) -> None:
        self.router = router
        self.on_outcome = on_outcome or (lambda rid, st: None)
        self.on_error = on_error or (lambda rid, err: None)
        self._q: queue.Queue = queue.Queue()
        self._thread: threading.Thread | None = None
        self._idle = threading.Event()
        self._idle.set()

    # ------------------------------------------------------------ control --
    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="lane", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        t = self._thread
        if t is None:
            return
        self._q.put(_STOP)
        t.join(timeout)
        self._thread = None

    @property
    def alive(self) -> bool:
        t = self._thread
        return t is not None and t.is_alive()

    # -------------------------------------------------------------- input --
    def submit(self, rec_id: str) -> None:
        """Audio-thread side: O(1), never blocks, never raises."""
        self._idle.clear()
        self._q.put(rec_id)

    def request_drain(self) -> None:
        self._idle.clear()
        self._q.put(_DRAIN)

    def depth(self) -> int:
        return self._q.qsize()

    def wait_idle(self, timeout: float | None = None) -> bool:
        return self._idle.wait(timeout)

    # --------------------------------------------------------------- loop --
    def _run(self) -> None:
        while True:
            item = self._q.get()
            try:
                if item is _STOP:
                    return
                if item is _DRAIN:
                    try:
                        self.router.drain()
                    except Exception as e:  # noqa: BLE001 — the lane must live
                        self.on_error("<drain>", f"{type(e).__name__}: {e}"[:300])
                    continue
                rec_id = str(item)
                try:
                    state = self.router.process_one_safe(rec_id)
                except Exception as e:  # noqa: BLE001 — the lane must live
                    self.on_error(rec_id, f"{type(e).__name__}: {e}"[:300])
                    continue
                try:
                    self.on_outcome(rec_id, state)
                except Exception as e:  # noqa: BLE001 — a UI callback cannot kill the lane
                    self.on_error(rec_id, f"on_outcome {type(e).__name__}: {e}"[:300])
            finally:
                if self._q.empty():
                    self._idle.set()
