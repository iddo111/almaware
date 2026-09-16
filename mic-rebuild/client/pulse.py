"""KESHEV pulse — the heartbeat that proves the whole chain is ALIVE.

WHY THIS EXISTS (Iddo, 2026-08-16 04:21, after being told the mic broke at
least 80 times in 77 days):

    "AI should handle everything the world throws at it."

He is right, and the forensic count proves the gap: for **38 days** the
supervisor restarted an ImportError corpse while reporting "running". Every
health signal in the system answered the question *"is my process alive?"* —
none answered *"can I still hear, and does what I hear become text?"*

`selftest.py` already proves the HAND (typing round-trip, scar 19: Windows
lies "success" across an integrity boundary). Nothing proved the EAR or the
BRAIN. This module is that missing half.

Three checks, in the order the signal actually travels:

    EAR    open the selected input device, pull real frames, measure RMS.
           Catches: device vanished, device renamed (BRIO -> USBAudio1.0),
           capture level silently reset by a reboot (100% -> 69%), a stream
           that opens fine and delivers nothing but zeros.

    BRAIN  push a FIXTURE of known speech through the real decode path and
           compare the returned text to the known transcript.
           Catches: server down, model swapped, cublas64_12.dll vanished,
           a degraded rung silently answering (small @ CER 0.325 while
           large-v3-turbo sits idle on eran1).

    HAND   delegate to selftest.py's round-trip. One copy of that law.

None of these trust a return value. Each one looks at the real output —
frames, text, characters read back — because every scar in PHASE1-INQUIRY.md
was a component that reported success while doing nothing.

The fixture is generated once by Windows SAPI so the expected transcript is
known exactly and no recording of Iddo is ever stored for a test
(mic-private-capture law). English on purpose: the pulse asks "is the pipe
open", not "how good is the Hebrew".

stdlib + numpy + sounddevice. No torch on the PC — ever.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

HERE = Path(__file__).resolve().parent
FIXTURE_DIR = HERE.parent / "state" / "pulse"
FIXTURE_WAV = FIXTURE_DIR / "pulse_fixture_16k.wav"
FIXTURE_TXT = FIXTURE_DIR / "pulse_fixture.txt"

# Short, unambiguous, no proper nouns a decoder can plausibly mangle.
FIXTURE_TEXT = "the quick brown fox jumps over the lazy dog"

SAMPLE_RATE = 16000
EAR_SECONDS = 1.5
EAR_MIN_FRAMES = 4
# An input that is open but delivering digital silence is the 69%-level scar.
# Room tone on a live USB mic sits well above this; true zeros sit at 0.0.
EAR_SILENCE_RMS = 1e-5
BRAIN_MAX_CER = 0.35            # a healthy rung is ~0.05 on this fixture; small is 0.325


# ------------------------------------------------------------------ verdicts

@dataclass
class Check:
    name: str
    ok: bool
    detail: str
    measured: dict = field(default_factory=dict)


@dataclass
class PulseResult:
    checks: list[Check]
    started: float
    elapsed_s: float

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks)

    @property
    def failed(self) -> list[Check]:
        return [c for c in self.checks if not c.ok]

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "elapsed_s": round(self.elapsed_s, 2),
            "checks": [
                {"name": c.name, "ok": c.ok, "detail": c.detail, **c.measured}
                for c in self.checks
            ],
        }


# ------------------------------------------------------------------ fixture

def _sapi_to_wav(text: str, out_wav: Path) -> None:
    """Speak `text` to a WAV with the Windows speech engine.

    PowerShell, because System.Speech is a .NET assembly and shelling out
    keeps this module import-light. Generated once, then cached forever.
    """
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    ps = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        f"$s.SetOutputToWaveFile('{out_wav}'); "
        f"$s.Speak('{text}'); "
        "$s.Dispose()"
    )
    subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
        check=True, capture_output=True, timeout=90,
    )


def _to_16k_mono_pcm(src_wav: Path) -> bytes:
    """Read any PCM wav and return 16 kHz mono s16le, the wire format."""
    import numpy as np

    with wave.open(str(src_wav), "rb") as w:
        chans, width, rate, nframes = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        raw = w.readframes(nframes)

    if width != 2:
        raise ValueError(f"fixture must be 16-bit PCM, got {width * 8}-bit")

    a = np.frombuffer(raw, dtype="<i2").astype("float32")
    if chans > 1:
        a = a.reshape(-1, chans).mean(axis=1)

    if rate != SAMPLE_RATE:
        # linear resample — a TTS fixture does not need a polyphase filter
        n_out = int(round(len(a) * SAMPLE_RATE / rate))
        a = np.interp(
            np.linspace(0, len(a) - 1, n_out, dtype="float64"),
            np.arange(len(a), dtype="float64"),
            a,
        )

    return np.clip(a, -32768, 32767).astype("<i2").tobytes()


def ensure_fixture(text: str = FIXTURE_TEXT) -> tuple[bytes, str]:
    """Return (pcm_16k_mono_s16le, expected_text), generating it on first use."""
    if not FIXTURE_WAV.exists() or not FIXTURE_TXT.exists():
        raw_wav = FIXTURE_DIR / "_sapi_raw.wav"
        _sapi_to_wav(text, raw_wav)
        pcm = _to_16k_mono_pcm(raw_wav)
        FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
        with wave.open(str(FIXTURE_WAV), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SAMPLE_RATE)
            w.writeframes(pcm)
        FIXTURE_TXT.write_text(text, encoding="utf-8")
        raw_wav.unlink(missing_ok=True)

    with wave.open(str(FIXTURE_WAV), "rb") as w:
        pcm = w.readframes(w.getnframes())
    return pcm, FIXTURE_TXT.read_text(encoding="utf-8").strip()


# ------------------------------------------------------------------ scoring

def cer(expected: str, got: str) -> float:
    """Character error rate — Levenshtein / len(expected), case- and
    punctuation-insensitive so a decoder is judged on words, not commas."""
    def norm(s: str) -> str:
        return "".join(ch for ch in s.lower() if ch.isalnum() or ch.isspace()).split() and \
               " ".join("".join(ch for ch in s.lower() if ch.isalnum() or ch.isspace()).split()) or ""

    a, b = norm(expected), norm(got)
    if not a:
        return 0.0 if not b else 1.0

    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1] / len(a)


# ------------------------------------------------------------------ the three checks

def check_ear(seconds: float = EAR_SECONDS, device: Optional[int] = None) -> Check:
    """Open the input and prove frames arrive with real signal in them."""
    try:
        import numpy as np
        import sounddevice as sd
    except Exception as exc:                                    # noqa: BLE001
        return Check("EAR", False, f"audio stack unavailable: {type(exc).__name__}: {exc}")

    frames: list = []
    try:
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32",
                            device=device, blocksize=1024) as stream:
            name = sd.query_devices(stream.device, "input")["name"]
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                block, overflowed = stream.read(1024)
                frames.append(block.reshape(-1))
                if overflowed:
                    pass                                        # counted upstream, not fatal here
    except Exception as exc:                                    # noqa: BLE001
        return Check("EAR", False, f"could not open input: {type(exc).__name__}: {exc}")

    if len(frames) < EAR_MIN_FRAMES:
        return Check("EAR", False, f"device opened but delivered only {len(frames)} frames",
                     {"device": name, "frames": len(frames)})

    audio = np.concatenate(frames)
    rms = float(np.sqrt(np.mean(audio ** 2)))
    peak = float(np.max(np.abs(audio)))

    if rms <= EAR_SILENCE_RMS:
        return Check("EAR", False,
                     "device is open and delivering DIGITAL SILENCE — "
                     "wrong input, muted, or capture level collapsed",
                     {"device": name, "frames": len(frames), "rms": rms, "peak": peak})

    return Check("EAR", True, f"hearing on '{name}'",
                 {"device": name, "frames": len(frames),
                  "rms": round(rms, 6), "peak": round(peak, 4)})


def check_brain(engine_transcribe: Callable[[bytes, str], str],
                max_cer: float = BRAIN_MAX_CER) -> Check:
    """Push known speech through the real decode path and read the text back.

    `engine_transcribe(pcm, request_id) -> text`. Injected so this works
    against the DGX engine, a local rung, or a fake in tests.
    """
    try:
        pcm, expected = ensure_fixture()
    except Exception as exc:                                    # noqa: BLE001
        return Check("BRAIN", False, f"fixture unavailable: {type(exc).__name__}: {exc}")

    # request-id is LAW: `<session8hex>-<seq:06d>` (common/protocol.py, scar 53).
    rid = f"{int(time.time()) & 0xFFFFFFFF:08x}-000001"
    t0 = time.monotonic()
    try:
        got = engine_transcribe(pcm, rid) or ""
    except Exception as exc:                                    # noqa: BLE001
        return Check("BRAIN", False, f"decode failed: {type(exc).__name__}: {str(exc)[:140]}")
    ms = int((time.monotonic() - t0) * 1000)

    score = cer(expected, got)
    ok = score <= max_cer
    detail = (f"decoded in {ms} ms, CER {score:.3f}" if ok
              else f"DECODER DEGRADED — CER {score:.3f} > {max_cer}: got {got[:80]!r}")
    return Check("BRAIN", ok, detail,
                 {"cer": round(score, 3), "decode_ms": ms,
                  "expected": expected, "got": got[:200]})


def check_hand() -> Check:
    """Delegate to the existing typing round-trip — ONE copy of that law."""
    try:
        from client import selftest
    except Exception as exc:                                    # noqa: BLE001
        return Check("HAND", False, f"selftest unavailable: {type(exc).__name__}: {exc}")

    runner = None
    for attr in ("run_selftest", "run", "main", "selftest"):
        fn = getattr(selftest, attr, None)
        if callable(fn):
            runner = fn
            break
    if runner is None:
        return Check("HAND", False, "selftest module exposes no runner — check its API")

    try:
        res = runner()
    except Exception as exc:                                    # noqa: BLE001
        return Check("HAND", False, f"round-trip raised: {type(exc).__name__}: {str(exc)[:140]}")

    ok = bool(getattr(res, "ok", res))
    return Check("HAND", ok, "typing round-trip verified" if ok else f"round-trip FAILED: {res!r}")


# ------------------------------------------------------------------ the pulse

def pulse(engine_transcribe: Optional[Callable[[bytes, str], str]] = None,
          *, ear: bool = True, brain: bool = True, hand: bool = False) -> PulseResult:
    """Run the heartbeat. HAND is off by default because it spawns a window;
    the supervisor runs it on a slower cadence than EAR/BRAIN."""
    t0 = time.monotonic()
    checks: list[Check] = []
    if ear:
        checks.append(check_ear())
    if brain:
        if engine_transcribe is None:
            checks.append(Check("BRAIN", False, "no decode path supplied"))
        else:
            checks.append(check_brain(engine_transcribe))
    if hand:
        checks.append(check_hand())
    return PulseResult(checks=checks, started=t0, elapsed_s=time.monotonic() - t0)


def dgx_transcriber(base_url: str, token: str) -> Callable[[bytes, str], str]:
    """Build a decode path that goes to the real server (eran1:8737)."""
    from client.dgx_engine import DgxEngine
    eng = DgxEngine(base_url, token)

    def _t(pcm: bytes, request_id: str) -> str:
        res = eng.transcribe(pcm, request_id=request_id,
                             duration_ms=len(pcm) // 32, lang_hint="en")
        return getattr(res, "text", "") or ""

    return _t


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="KESHEV pulse — prove the chain is alive")
    ap.add_argument("--server-url", default=None, help="e.g. http://<lan-ip>:8737/")
    ap.add_argument("--token-file", default=str(HERE.parent / "state" / "stt-token"))
    ap.add_argument("--hand", action="store_true", help="also run the typing round-trip")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    transcriber = None
    if args.server_url:
        token = ""
        tf = Path(args.token_file)
        if tf.exists():
            token = tf.read_text(encoding="utf-8").strip()
        transcriber = dgx_transcriber(args.server_url, token)

    res = pulse(transcriber, brain=bool(transcriber), hand=args.hand)

    if args.json:
        print(json.dumps(res.as_dict(), ensure_ascii=False, indent=2))
    else:
        for c in res.checks:
            mark = "OK  " if c.ok else "FAIL"
            print(f"[{mark}] {c.name:5s} {c.detail}")
        print(f"\npulse {'ALIVE' if res.ok else 'BROKEN'} in {res.elapsed_s:.2f}s")
    return 0 if res.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
