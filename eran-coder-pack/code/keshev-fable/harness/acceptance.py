"""KESHEV-FABLE acceptance — measured rows against A's baseline (INSIGHTS §7).

Read-only: never opens an audio device (ONE-MIC LAW). Decode round-trips use
A's synthetic canary WAVs (System.Speech phrases — no privacy content) through
THIS repo's own SttClient against the real eran1:8737.

Run:  python harness/acceptance.py
"""
from __future__ import annotations

import pathlib
import statistics
import wave
import sys
import time

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from app.stt import SttClient  # noqa: E402

A_REPO = pathlib.Path(r"D:\CLAUDE\mic-rebuild")
CANARY_DIR = A_REPO / "tools" / "replay" / "wavs" / "canary"
TOKEN = A_REPO / "state" / "stt-token"
BASE_URL = "http://<lan-ip>:8737"

# canary reference words — the REAL phrases from tools/privacy_canaries.py
# (rare 8+-letter words, unique per phrase; a hit is proof of a real decode)
EXPECT = {
    "canary1": ("quixotic", "zeppelin", "marmalade"),
    "canary2": ("porcupine", "saxophone", "dirigible"),
    "canary3": ("chrysanthemum", "tambourine"),
    "canary4": ("telescope", "turquoise", "armadillo"),
    "canary5": ("crocodile", "pistachio", "cupcakes"),
}


def main() -> int:
    wavs = sorted(CANARY_DIR.glob("*.wav"))
    if not wavs:
        print(f"NO CANARIES at {CANARY_DIR} — cannot measure")
        return 1
    client = SttClient(BASE_URL, TOKEN, timeout_s=15)
    if not client.health():
        print("eran1:8737 health FAILED — no measurement today")
        return 1

    times: list[float] = []
    hits = 0
    words_total = 0
    for i, wav in enumerate(wavs):
        with wave.open(str(wav)) as w:
            assert (w.getframerate(), w.getnchannels(),
                    w.getsampwidth()) == (16000, 1, 2), wav.name
            pcm = w.readframes(w.getnframes())
        t0 = time.perf_counter()
        rid = f"acce9701-{100000 + i:06d}"      # protocol: ^[0-9a-f]{8}-[0-9]{6,}$
        res = client.decode(rid, pcm)
        dt = (time.perf_counter() - t0) * 1000
        if not res.ok:
            print(f"{wav.name}: FAILED ({res.reason})")
            continue
        times.append(dt)
        got = res.text.casefold()
        expected = EXPECT.get(wav.stem, ())
        for w in expected:
            words_total += 1
            if w in got:
                hits += 1
        print(f"{wav.name}: {dt:.0f}ms  lang={res.lang}  text={res.text[:60]!r}")

    if not times:
        print("ZERO successful decodes — row is FAILED, not skipped")
        return 1
    p50 = statistics.median(times)
    print("-" * 60)
    print(f"MEASURED: n={len(times)} p50={p50:.0f}ms "
          f"words={hits}/{words_total or '?'}")
    print("A baseline (INSIGHTS §7): 407ms round-trip; K2 measured 235-242ms")
    return 0


if __name__ == "__main__":
    sys.exit(main())
