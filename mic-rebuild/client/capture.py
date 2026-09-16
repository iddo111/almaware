"""KESHEV capture layer — K7 (PHASE2-DESIGN.md section 2 capture.py spec;
PHASE1-INQUIRY.md section 2, scars 24/25/45, criterion 22).

  scar 24       format negotiation 16k mono -> native -> 48k/44.1k; downmix
                to mono; resample to 16k in-callback (client/resample.py).
  scar 25       silent-but-open devices trigger PERIODIC re-resolve — the
                69% capture-level reset after a Windows reboot deafened the
                RMS gate with zero errors, 136 device-loss events in one log.
  scar 45       ABOVE_NORMAL priority for the capture thread only, NEVER
                realtime; asserted at RUNTIME, not assumed (criterion 22).
  design sec 2  copy-out in the callback; bounded 200-frame queue with
                drop-on-full + a VISIBLE counter (heartbeat `drop_frames`).

This module never opens a device and never imports sounddevice: the stream
owner (app.py, wired at integration) opens the device chosen by the K6
device law (client/devices.py) and feeds raw callback buffers into
`CapturePipeline.on_audio`. Everything here is therefore testable against
synthetic streams — no real device, ever, before the K5-gated live phase.
There is no audio-output code path (scar 22; lint gate G6).
"""
from __future__ import annotations

import queue
import sys
import threading
from typing import Any, Callable

import numpy as np

from client.devices import RMS_LIVENESS_FLOOR
from client.resample import TARGET_RATE, StreamingResampler

# ---------------------------------------------------------------- constants
# All knobs are code under git — none of these is a config key (design sec 5).

CAPTURE_QUEUE_FRAMES = 200        # design sec 2: bounded 200-frame queue
BLOCK_MS = 30                     # frame size handed downstream (480 @ 16k)
SILENT_OPEN_WINDOW_S = 30.0       # scar 25: re-resolve after this much dead air
SILENT_RMS_FLOOR = RMS_LIVENESS_FLOOR   # one source of truth with the device law

# scar 45: ABOVE_NORMAL only. Realtime/time-critical is deliberately
# UNREPRESENTED in this module — there is no constant to reach for.
THREAD_PRIORITY_ABOVE_NORMAL = 1


class FormatNegotiationError(Exception):
    """No (rate, channels) combination was accepted — loud, never a hopeful
    open with an unvalidated format (scar 6 ethos)."""


class PriorityAssertError(Exception):
    """The capture thread is not at ABOVE_NORMAL (scar 45 / criterion 22)."""


# ---------------------------------------------------------------- priority (scar 45)

_K32 = None


def _kernel32():
    """Typed kernel32 handle (lazy). Explicit argtypes/restype: the
    GetCurrentThread pseudo-handle is a full-width HANDLE — the ctypes
    default c_int mangles it on 64-bit and SetThreadPriority fails."""
    global _K32
    if _K32 is None:
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.GetCurrentThread.restype = wintypes.HANDLE
        k32.SetThreadPriority.argtypes = (wintypes.HANDLE, ctypes.c_int)
        k32.SetThreadPriority.restype = wintypes.BOOL
        k32.GetThreadPriority.argtypes = (wintypes.HANDLE,)
        k32.GetThreadPriority.restype = ctypes.c_int
        _K32 = k32
    return _K32


def _win_get_priority() -> int:
    k32 = _kernel32()
    return int(k32.GetThreadPriority(k32.GetCurrentThread()))


def _win_set_above_normal() -> None:
    import ctypes
    k32 = _kernel32()
    if not k32.SetThreadPriority(k32.GetCurrentThread(),
                                 THREAD_PRIORITY_ABOVE_NORMAL):
        raise PriorityAssertError(
            f"SetThreadPriority(ABOVE_NORMAL) failed, "
            f"winerror={ctypes.get_last_error()}")


def set_capture_thread_priority() -> int:
    """Raise the CURRENT thread to ABOVE_NORMAL (never higher — scar 45)
    and return the read-back value. Call from the capture thread itself."""
    if sys.platform != "win32":  # pragma: no cover — KESHEV is a Windows client
        raise PriorityAssertError("thread priority is Windows-only")
    _win_set_above_normal()
    return _win_get_priority()


def assert_capture_thread_priority(
        get_priority: Callable[[], int] | None = None) -> int:
    """Criterion 22: assert at RUNTIME that the current thread is at exactly
    ABOVE_NORMAL — not normal (starved under co-tenant bursts) and never
    realtime (scar 45). Returns the verified value."""
    actual = (get_priority or _win_get_priority)()
    if actual != THREAD_PRIORITY_ABOVE_NORMAL:
        raise PriorityAssertError(
            f"capture thread priority is {actual}, required ABOVE_NORMAL "
            f"({THREAD_PRIORITY_ABOVE_NORMAL}) exactly — never normal, "
            f"never realtime (scar 45)")
    return actual


# ---------------------------------------------------------------- negotiation (scar 24)

def negotiate_format(check_fn: Callable[[int, int], None],
                     *,
                     native_rate: int,
                     native_channels: int,
                     target_rate: int = TARGET_RATE) -> tuple[int, int]:
    """First (rate, channels) the device truly accepts, in scar-24 order:
    16k -> native -> 48k -> 44.1k, mono before native channel count.

    `check_fn(rate, channels)` raises if the combination is refused (live:
    sounddevice.check_input_settings, injected by the stream owner; tests:
    a fake). All-refused is a loud FormatNegotiationError, never a hopeful
    open."""
    tried: list[tuple[int, int]] = []
    failures: list[str] = []
    for rate in dict.fromkeys((target_rate, int(native_rate), 48_000, 44_100)):
        for ch in dict.fromkeys((1, max(1, int(native_channels)))):
            combo = (rate, ch)
            if combo in tried:
                continue
            tried.append(combo)
            try:
                check_fn(rate, ch)
                return combo
            except Exception as e:
                failures.append(f"{rate}Hz/{ch}ch: {e}")
    raise FormatNegotiationError(
        "device accepted NO negotiated format (scar 24 order "
        "16k->native->48k->44.1k): " + "; ".join(failures))


# ---------------------------------------------------------------- bounded queue

class BoundedFrameQueue:
    """Bounded frame queue: drop-on-full with a VISIBLE counter (design
    sec 2). Dropping is a counted, heartbeat-surfaced event — never growth,
    never a silent `except: pass` (the old app's leak class)."""

    def __init__(self, maxsize: int = CAPTURE_QUEUE_FRAMES):
        self.maxsize = maxsize
        self._q: "queue.Queue[np.ndarray]" = queue.Queue(maxsize=maxsize)
        self._lock = threading.Lock()
        self.accepted = 0
        self.dropped = 0

    def put(self, frame: np.ndarray) -> bool:
        """True if enqueued; False if dropped (counter incremented)."""
        try:
            self._q.put_nowait(frame)
        except queue.Full:
            with self._lock:
                self.dropped += 1
            return False
        with self._lock:
            self.accepted += 1
        return True

    def get(self, timeout: float | None = 0.1) -> np.ndarray | None:
        """One frame, or None within `timeout` — keeps callers responsive
        to stop signals."""
        try:
            if timeout is None or timeout <= 0:
                return self._q.get_nowait()
            return self._q.get(timeout=timeout)
        except queue.Empty:
            return None

    def qsize(self) -> int:
        return self._q.qsize()


# ---------------------------------------------------------------- silent-open (scar 25)

class SilentOpenWatch:
    """Detects a silent-but-open device (scar 25) and asks for a re-resolve
    PERIODICALLY while the silence persists.

    Duration is counted from the audio itself (samples / rate), which is
    deterministic and needs no clock: a stream that is delivering callbacks
    full of dead air is exactly the failure this scar records (capture level
    reset to 69%, wrong endpoint grabbed). A stream that stops delivering
    callbacks entirely is the wedge case, watched elsewhere (design sec 7,
    capture-callback recency)."""

    def __init__(self, rate: int,
                 floor: float = SILENT_RMS_FLOOR,
                 window_s: float = SILENT_OPEN_WINDOW_S):
        self.rate = int(rate)
        self.floor = float(floor)
        self.window_s = float(window_s)
        self._silent_samples = 0
        # Most recent RMS seen by feed(), for the window's level bar. None
        # until the first callback — never 0.0, which would draw a confident
        # "silent" before any audio has arrived at all.
        self.last_level: float | None = None

    @property
    def silent_s(self) -> float:
        return self._silent_samples / self.rate

    def feed(self, mono: np.ndarray) -> bool:
        """Feed one mono chunk at the capture rate. Returns True when a full
        window of continuous silence has accumulated — the re-resolve
        trigger. The accumulator then resets so a STILL-silent device fires
        again one window later (periodic, per scar 25)."""
        if len(mono) == 0:
            return False
        level = float(np.sqrt(np.mean(np.square(mono.astype(np.float64)))))
        # Iddo, 2026-08-15: "should have the soundbar". The level is already
        # computed here every callback for the silence test — publishing it
        # costs one assignment and gives the window something HONEST to draw.
        # It is the same number the silence watch judges on, so a moving bar
        # and a silent-reopen can never tell him two different stories.
        self.last_level = level
        if level >= self.floor:
            self._silent_samples = 0
            return False
        self._silent_samples += len(mono)
        if self.silent_s >= self.window_s:
            self._silent_samples = 0
            return True
        return False


# ---------------------------------------------------------------- pipeline

class CapturePipeline:
    """The in-callback body: copy-out -> downmix -> resample(16k) -> frame ->
    bounded enqueue. Owns the runtime counters criterion 22 reads.

    The stream owner calls `on_audio(indata, status)` from the capture
    thread; the segmenter drains `read()`. Priority is set+asserted on the
    FIRST callback — i.e. on the real capture thread, at runtime. A priority
    failure is visible (counter + DEVICE_PRIORITY_FAIL event) but never
    stops capture: audio flow outranks scheduling comfort."""

    def __init__(self,
                 cap_rate: int,
                 cap_channels: int,
                 out_rate: int = TARGET_RATE,
                 block_ms: int = BLOCK_MS,
                 queue_maxsize: int = CAPTURE_QUEUE_FRAMES,
                 set_priority_fn: Callable[[], int] | None = None,
                 on_event: Callable[..., Any] | None = None):
        self.cap_rate = int(cap_rate)
        self.cap_channels = int(cap_channels)
        self.out_rate = int(out_rate)
        self.block = int(out_rate * block_ms / 1000)          # 480 @ 16k/30ms
        self.queue = BoundedFrameQueue(maxsize=queue_maxsize)
        self.resampler = StreamingResampler(self.cap_rate, self.out_rate)
        self.silence_watch = SilentOpenWatch(rate=self.cap_rate)
        self._stage = np.empty(0, dtype=np.float32)           # 16k awaiting framing
        self._set_priority = set_priority_fn or set_capture_thread_priority
        self._on_event = on_event or (lambda evt, **kw: None)
        self._priority_done = False
        # -------- the visible counters (criterion 22 reads THESE)
        self.callbacks = 0
        self.overflow_count = 0
        self.priority_failures = 0
        self.thread_priority: int | None = None

    # ---- counters snapshot for the 60s heartbeat (design sec 8)
    def snapshot(self) -> dict[str, int]:
        return {"q": self.queue.qsize(),
                "drop_frames": self.queue.dropped,
                "overflow": self.overflow_count,
                "callbacks": self.callbacks}

    @property
    def frames_dropped(self) -> int:
        return self.queue.dropped

    @property
    def frames_enqueued(self) -> int:
        return self.queue.accepted

    def read(self, timeout: float | None = 0.1) -> np.ndarray | None:
        return self.queue.get(timeout=timeout)

    # ---- the callback body (runs on the capture thread)
    def on_audio(self, indata: np.ndarray, status: Any = None) -> None:
        self.callbacks += 1

        if not self._priority_done:                    # scar 45, at runtime,
            self._priority_done = True                 # on the REAL thread
            try:
                self.thread_priority = self._set_priority()
            except Exception as e:
                self.priority_failures += 1            # visible, never fatal
                self._on_event("DEVICE_PRIORITY_FAIL", error=str(e))

        if status is not None and getattr(status, "input_overflow", False):
            self.overflow_count += 1                   # criterion 22 counter

        # copy-out IMMEDIATELY (design sec 2): the driver owns `indata`
        # after we return; downmix to mono (mean works for any channel count)
        data = np.asarray(indata, dtype=np.float32)
        if data.ndim == 1:
            mono = data.copy()
        elif data.shape[1] == 1:
            mono = data[:, 0].copy()
        else:
            mono = data.mean(axis=1, dtype=np.float64).astype(np.float32)

        # scar 25: silent-but-open watch, on the raw capture-rate audio
        if self.silence_watch.feed(mono):
            self._on_event("DEVICE_SILENT_REOPEN",
                           silent_s=self.silence_watch.window_s,
                           rate=self.cap_rate)

        y = self.resampler.process(mono)
        if not len(y):
            return
        self._stage = np.concatenate([self._stage, y])
        while len(self._stage) >= self.block:
            frame, self._stage = self._stage[:self.block], self._stage[self.block:]
            self.queue.put(np.ascontiguousarray(frame))   # drop-on-full counted
