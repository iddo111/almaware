"""alma-mic / audio.py — microphone capture.

ALMAWARE-pure: every line ours. We use ONLY the OS-audio access primitive
(sounddevice = a thin PortAudio binding, the standard way to reach the OS mic —
NOT an external app/project/collage). All capture logic below is our own.

Single responsibility:
  1. enumerate input devices (with host API)
  2. pick a LIVE one — host-API-aware (WASAPI/DirectSound deliver real signal;
     MME is often SILENT for USB mics — the old app's gotcha), and probe real signal
  3. stream clean 16 kHz mono float32 frames with an explicit, leak-free lifecycle
"""
from __future__ import annotations
import queue
import time

try:
    import sounddevice as sd
    import numpy as np
except ImportError as e:  # honest, actionable
    raise SystemExit(
        "alma-mic needs the OS-audio primitive + numpy:\n"
        "    pip install sounddevice numpy\n"
        f"(import failed: {e})"
    )

SAMPLE_RATE = 16_000
CHANNELS = 1
LIVE_RMS_FLOOR = 0.0008  # below this over a probe = effectively dead/silent device
# Host APIs that actually deliver signal for USB mics; MME is frequently silent.
# Order = preference: WASAPI & DirectSound open reliably in shared mode; WDM-KS is
# finicky (often exclusive-only) so it's the last resort.
_GOOD_APIS = ["wasapi", "directsound", "wdm-ks"]
_NOT_DEVICES = ["mapper", "primary sound"]


from dataclasses import dataclass


@dataclass(frozen=True)
class Device:
    index: int
    name: str
    hostapi: str = ""


def list_input_devices() -> list[Device]:
    """All devices that can actually capture audio, tagged with their host API."""
    apis = sd.query_hostapis()
    out: list[Device] = []
    for i, d in enumerate(sd.query_devices()):
        if d.get("max_input_channels", 0) > 0:
            api = apis[d["hostapi"]]["name"] if d.get("hostapi") is not None else ""
            out.append(Device(i, str(d["name"]), str(api)))
    return out


def find_device(name_substr: str) -> Device | None:
    """First input device whose name contains `name_substr` (case-insensitive).
    Used when the user explicitly PICKS a mic in settings — we honor the choice
    even if it's quiet right now (a chosen mic isn't probe-gated)."""
    s = name_substr.lower().strip()
    if not s:
        return None
    # prefer a good host API among matches (avoid the silent-MME copy)
    matches = [d for d in list_input_devices() if s in d.name.lower()]
    matches.sort(key=lambda d: 0 if any(a in d.hostapi.lower() for a in _GOOD_APIS) else 1)
    return matches[0] if matches else None


def _native_rate(index: int) -> int:
    """The device's own default sample rate (what WASAPI shared-mode will accept)."""
    try:
        info = sd.query_devices(index)
        return int(info.get("default_samplerate") or 48_000)
    except Exception:
        return 48_000


def _native_channels(index: int) -> int:
    """The device's max input channels (some mics refuse a forced mono open)."""
    try:
        return max(1, int(sd.query_devices(index).get("max_input_channels") or 1))
    except Exception:
        return 1


def probe_rms(index: int, seconds: float = 0.5) -> float:
    """Open a device briefly and measure RMS — proves it delivers REAL signal.
    Returns -1.0 if it can't even be opened. We try 16 kHz first, then the device's
    native rate, because WASAPI shared-mode mics (e.g. BRIO) reject a forced 16 kHz."""
    for rate in (SAMPLE_RATE, _native_rate(index)):
        try:
            rec = sd.rec(int(seconds * rate), samplerate=rate,
                         channels=CHANNELS, dtype="float32", device=index)
            sd.wait()
            return float(np.sqrt(np.mean(np.square(rec))))
        except Exception:
            continue
    return -1.0


def same_mic_indices(dev: Device) -> list[int]:
    """All device indices for the SAME physical mic as `dev`, across host APIs,
    ordered: the chosen one first, then other good APIs (DirectSound/WDM-KS/MME).
    Used as a fallback chain — if WASAPI transiently refuses to start, try another
    API for the very same microphone before giving up."""
    same = [d for d in list_input_devices() if d.name.lower() == dev.name.lower()]

    def rank(d: Device) -> tuple[int, int]:
        primary = 0 if d.index == dev.index else 1
        al = d.hostapi.lower()
        api = next((i for i, a in enumerate(_GOOD_APIS) if a in al), len(_GOOD_APIS))
        return (primary, api)

    same.sort(key=rank)
    seen, out = set(), []
    for d in same:
        if d.index not in seen:
            seen.add(d.index)
            out.append(d.index)
    return out or [dev.index]


# Devices that capture SYSTEM AUDIO rather than a voice. These stay hard-blocked
# whatever the config says - transcribing your own speakers is never wanted.
_LOOPBACK = ("stereo mix", "what u hear", "loopback", "wave out",
             "virtual", "audiorelay")


def pick_device(prefer: list[str] | None = None,
                avoid: list[str] | None = None) -> Device | None:
    """Choose a mic that ACTUALLY PASSES AUDIO. Signal beats names, always.

    `avoid` used to be a hard filter applied BEFORE probing, which twice left
    this app with no microphone at all: once it rejected the only USB mic on the
    machine, then it rejected the only working Bluetooth headset. A name is a
    preference, never a veto.

    Order of business:
      1. hard-block only true loopback devices (they record the speakers)
      2. try the non-avoided devices, best host API first - first LIVE one wins
      3. if none of those are live, try the avoided ones anyway
      4. if nothing proves live (silent room), fall back to the best-ranked
    """
    prefer = [p.lower() for p in (prefer or [])]
    avoid = [a.lower() for a in (avoid or [])]

    real = [d for d in list_input_devices()
            if not any(nd in d.name.lower() for nd in _NOT_DEVICES)
            and not any(lb in d.name.lower() for lb in _LOOPBACK)]

    def name_rank(d: Device) -> int:
        nl = d.name.lower()
        for i, p in enumerate(prefer):
            if p in nl:
                return i
        return len(prefer)

    def api_rank(d: Device) -> int:
        al = d.hostapi.lower()
        for i, a in enumerate(_GOOD_APIS):
            if a in al:
                return i
        return len(_GOOD_APIS)

    def is_avoided(d: Device) -> bool:
        nl = d.name.lower()
        return any(a in nl for a in avoid)

    preferred = sorted([d for d in real if not is_avoided(d)],
                       key=lambda d: (name_rank(d), api_rank(d)))
    demoted = sorted([d for d in real if is_avoided(d)],
                     key=lambda d: (name_rank(d), api_rank(d)))

    for group in (preferred, demoted):
        for d in group:
            try:
                if probe_rms(d.index) >= LIVE_RMS_FLOOR:
                    return d
            except Exception:
                continue

    return (preferred or demoted or [None])[0]


def _design_lowpass(cutoff_hz: float, fs: int, numtaps: int = 101) -> np.ndarray:
    """Our own windowed-sinc FIR low-pass (Hamming window). Linear phase, unity DC."""
    wc = min(0.99, cutoff_hz / (fs / 2.0))          # cutoff as fraction of Nyquist
    n = np.arange(numtaps) - (numtaps - 1) / 2.0
    h = wc * np.sinc(wc * n) * np.hamming(numtaps)
    h /= h.sum()
    return h.astype(np.float32)


class _Resampler:
    """Streaming resampler (our own, pure numpy). Mono float32, continuous phase
    across callback boundaries (no clicks at seams). When DOWN-sampling it first runs
    an anti-alias low-pass FIR — without it, energy above 8 kHz folds back into the
    speech band as noise and makes Whisper hallucinate. Pass-through when in==out."""

    def __init__(self, in_rate: int, out_rate: int):
        self.in_rate = in_rate
        self.out_rate = out_rate
        self._step = in_rate / out_rate          # input samples advanced per output sample
        self._buf = np.empty(0, dtype=np.float32)  # unconsumed (filtered) input tail
        self._pos = 0.0                            # fractional read position within _buf
        # anti-alias FIR (only meaningful when downsampling), with carry state
        self._fir = (_design_lowpass(0.45 * out_rate, in_rate)
                     if in_rate > out_rate else None)
        self._fir_state = (np.zeros(len(self._fir) - 1, dtype=np.float32)
                           if self._fir is not None else None)

    def _antialias(self, x: np.ndarray) -> np.ndarray:
        buf = np.concatenate([self._fir_state, x])
        y = np.convolve(buf, self._fir, mode="valid")   # exactly len(x) samples out
        self._fir_state = buf[-(len(self._fir) - 1):]
        return y.astype(np.float32, copy=False)

    def process(self, x: np.ndarray) -> np.ndarray:
        if self.in_rate == self.out_rate:
            return np.ascontiguousarray(x, dtype=np.float32)
        x = np.asarray(x, dtype=np.float32)
        if self._fir is not None:
            x = self._antialias(x)
        self._buf = np.concatenate([self._buf, x])
        n = len(self._buf)
        if n < 2:
            return np.empty(0, dtype=np.float32)
        # outputs we can produce while the right interpolation neighbour exists (idx+1 <= n-1)
        k_max = int(np.floor((n - 1 - self._pos) / self._step)) + 1
        if k_max <= 0:
            return np.empty(0, dtype=np.float32)
        idx = self._pos + self._step * np.arange(k_max)
        i0 = np.floor(idx).astype(np.int64)
        frac = (idx - i0).astype(np.float32)
        out = self._buf[i0] * (1.0 - frac) + self._buf[i0 + 1] * frac
        last = self._pos + self._step * k_max
        consume = int(np.floor(last))
        self._buf = self._buf[consume:]
        self._pos = last - consume
        return out.astype(np.float32, copy=False)


class AudioCapture:
    """Streaming capture with an explicit lifecycle (context manager).
    We copy out of the driver buffer immediately and always close the stream —
    no leaked handles, bounded queue → no growing buffers (the leak that killed the old app).

    Opens at a sample rate the device actually accepts (WASAPI shared-mode mics like the
    BRIO reject a forced 16 kHz), then resamples to 16 kHz mono in-callback so the rest of
    the pipeline always sees uniform 16 kHz, `block_ms`-sized frames regardless of hardware."""

    def __init__(self, device_index: int, block_ms: int = 30,
                 fallbacks: list[int] | None = None, tries_per_device: int = 3):
        self.device_index = device_index
        self.block_ms = block_ms
        self.block = int(SAMPLE_RATE * block_ms / 1000)   # output frame size @16k (480 @30ms)
        # device chain: the chosen index first, then any same-mic fallbacks (other host APIs)
        self._chain = [device_index] + [i for i in (fallbacks or []) if i != device_index]
        self._tries = max(1, tries_per_device)
        self._q: "queue.Queue[np.ndarray]" = queue.Queue(maxsize=200)
        self._stream = None
        self.active_index = device_index   # which index actually opened (may differ after fallback)
        self._cap_rate = SAMPLE_RATE
        self._cap_channels = CHANNELS       # channels we actually open (downmixed to mono)
        self._res: _Resampler | None = None
        self._stage = np.empty(0, dtype=np.float32)       # resampled 16k samples awaiting framing

    @staticmethod
    def _pick_format(index: int) -> tuple[int, int]:
        """First (rate, channels) the device truly accepts — adapts to ANY mic the user
        picks: 16 kHz mono if supported, else native rate, else stereo (downmixed later).
        Whatever the hardware wants, we open it and convert to 16 kHz mono ourselves."""
        nr, nch = _native_rate(index), _native_channels(index)
        for rate in (SAMPLE_RATE, nr, 48_000, 44_100):
            for ch in (1, nch):
                if ch < 1:
                    continue
                try:
                    sd.check_input_settings(device=index, channels=ch,
                                            samplerate=rate, dtype="float32")
                    return rate, ch
                except Exception:
                    continue
        return nr, nch

    def _cb(self, indata, frames, t, status):  # noqa: ARG002
        # downmix to mono (mean of channels) — works for mono, stereo, or any channel count
        mono = indata[:, 0] if indata.shape[1] == 1 else indata.mean(axis=1)
        y = self._res.process(mono)
        if not len(y):
            return
        self._stage = np.concatenate([self._stage, y])
        while len(self._stage) >= self.block:
            frame, self._stage = self._stage[:self.block], self._stage[self.block:]
            try:
                self._q.put_nowait(frame.copy())
            except queue.Full:
                pass  # never grow without bound

    def _open_one(self, index: int) -> bool:
        """Try to open+start a stream on one device index, with a few retries for the
        transient WASAPI 'Unanticipated host error' (device momentarily busy). True on success."""
        cap_rate, cap_channels = self._pick_format(index)
        cap_block = int(cap_rate * self.block_ms / 1000)
        for attempt in range(self._tries):
            try:
                self._res = _Resampler(cap_rate, SAMPLE_RATE)
                self._stage = np.empty(0, dtype=np.float32)
                self._stream = sd.InputStream(
                    samplerate=cap_rate, channels=cap_channels, dtype="float32",
                    blocksize=cap_block, device=index, callback=self._cb)
                self._stream.start()
                self.active_index = index
                self._cap_rate = cap_rate
                self._cap_channels = cap_channels
                return True
            except Exception:
                if self._stream is not None:
                    try:
                        self._stream.close()
                    except Exception:
                        pass
                    self._stream = None
                if attempt < self._tries - 1:
                    time.sleep(0.4)   # let the driver release the device
        return False

    def __enter__(self) -> "AudioCapture":
        last = None
        for index in self._chain:
            if self._open_one(index):
                return self
        # exhausted the whole chain — open once more to surface the real error
        cap_rate, cap_channels = self._pick_format(self._chain[0])
        self._res = _Resampler(cap_rate, SAMPLE_RATE)
        self._cap_rate = cap_rate
        self._cap_channels = cap_channels
        cap_block = int(cap_rate * self.block_ms / 1000)
        self._stream = sd.InputStream(
            samplerate=cap_rate, channels=cap_channels, dtype="float32",
            blocksize=cap_block, device=self._chain[0], callback=self._cb)
        self._stream.start()
        self.active_index = self._chain[0]
        return self

    def frames(self):
        while True:
            yield self._q.get()

    def read(self, timeout: float = 0.1):
        """Get one frame, or None if none arrived within `timeout`.
        Lets a caller loop while staying responsive to a stop signal (the GUI uses this)."""
        try:
            return self._q.get(timeout=timeout)
        except queue.Empty:
            return None

    def __exit__(self, *exc) -> bool:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        try:
            while True:
                self._q.get_nowait()
        except queue.Empty:
            pass
        return False
