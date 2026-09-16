# -*- coding: utf-8 -*-
"""Proof that the ONE-LINE SWITCH actually works, using the live client code.

Not a mock: this imports keshev-next's own `app/decoder.py` - the file the mic
calls - points KESHEV_STT_URL at :8738, and runs a real segment of Iddo's
speech through it. If this passes, `setx KESHEV_STT_URL ...` is the whole
change; if it fails, the report's switch instruction is a lie.

Reads only. Starts nothing, stops nothing, opens no audio device.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import wave
from pathlib import Path

KESHEV_NEXT = Path(r"D:/CLAUDE/keshev-next")
SEG = KESHEV_NEXT / "segments"
NEW = "http://127.0.0.1:8738/v1/transcribe"
OLD = "http://127.0.0.1:8737/v1/transcribe"
# a segment the live server already decoded correctly tonight
SAMPLE = "20260903-225146-431.wav"          # "אני הולך לישון."


def load_client_decoder():
    """Import keshev-next/app/decoder.py without importing the mic engine."""
    sys.path.insert(0, str(KESHEV_NEXT / "app"))
    spec = importlib.util.spec_from_file_location("keshev_decoder",
                                                  KESHEV_NEXT / "app" / "decoder.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def pcm(name: str) -> bytes:
    with wave.open(str(SEG / name)) as w:
        return w.readframes(w.getnframes())


def main() -> int:
    d = load_client_decoder()
    data = pcm(SAMPLE)
    fails = 0

    # the fallback would mask a broken :8738 by silently answering from eran1
    os.environ["KESHEV_STT_FALLBACK_URL"] = ""

    for label, url in (("OLD :8737", OLD), ("NEW :8738", NEW)):
        os.environ["KESHEV_STT_URL"] = url
        state = d.server_state()
        ok, text, lang, lp = d.transcribe_hebrew_pcm(data)
        print(f"{label}  health={state}  ok={ok} lang={lang} lp={lp:.2f}")
        print(f"          text={text!r}")
        if state != "READY":
            print(f"   FAIL {label}: /health did not say READY")
            fails += 1
        if not ok or not text.strip():
            print(f"   FAIL {label}: the client got no text out of real speech")
            fails += 1

    print("---", "SWITCH VERIFIED" if not fails else f"{fails} FAILURES")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
