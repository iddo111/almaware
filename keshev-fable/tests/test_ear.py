"""ear tests — synthetic voice blocks in, spooled WAV utterances out."""
from __future__ import annotations

import io
import pathlib
import struct
import sys
import unittest
import wave

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.ear import Ear, pcm_to_wav  # noqa: E402
from app.segmenter import Segmenter  # noqa: E402

RATE = 16000
BLOCK_MS = 100
SAMPLES = RATE * BLOCK_MS // 1000


def block(amplitude: int) -> bytes:
    """One 100 ms int16 block at a constant amplitude (rms = a/32768)."""
    return struct.pack(f"<{SAMPLES}h", *([amplitude] * SAMPLES))


LOUD = block(3000)      # rms ≈ 0.0916 — well above the 0.008 gate
QUIET = block(30)       # rms ≈ 0.0009 — below the gate


class _MemSpool:
    def __init__(self):
        self.admitted: list[tuple[str, bytes, dict]] = []

    def admit(self, rec_id, wav_bytes, meta):
        self.admitted.append((rec_id, wav_bytes, meta))
        return None, None


class EarTests(unittest.TestCase):
    def setUp(self):
        self.spool = _MemSpool()
        self.closed: list[str] = []
        self.ear = Ear(self.spool, "testsess",
                       on_segment=lambda rid, seg: self.closed.append(rid),
                       segmenter=Segmenter(min_ms=280, hang_ms=420))

    def speak(self, loud_blocks: int, quiet_blocks: int) -> None:
        for _ in range(loud_blocks):
            self.ear.feed_block(LOUD)
        for _ in range(quiet_blocks):
            self.ear.feed_block(QUIET)

    def test_utterance_reaches_the_spool_as_valid_wav(self):
        self.speak(8, 6)                      # 800 ms speech + 600 ms silence
        self.assertEqual(len(self.spool.admitted), 1)
        rec_id, wav_bytes, meta = self.spool.admitted[0]
        self.assertEqual(rec_id, "testsess-000001")
        with wave.open(io.BytesIO(wav_bytes)) as w:
            self.assertEqual(w.getframerate(), RATE)
            self.assertEqual(w.getnchannels(), 1)
            self.assertGreaterEqual(w.getnframes() / RATE, 0.7)
        self.assertEqual(self.closed, ["testsess-000001"])
        self.assertGreaterEqual(meta["ms"], 700)

    def test_silence_spools_nothing(self):
        self.speak(0, 50)
        self.assertEqual(self.spool.admitted, [])

    def test_blip_spools_nothing(self):
        self.speak(1, 6)                      # 100 ms blip
        self.assertEqual(self.spool.admitted, [])

    def test_two_utterances_two_records(self):
        self.speak(8, 6)
        self.speak(8, 6)
        self.assertEqual([r[0] for r in self.spool.admitted],
                         ["testsess-000001", "testsess-000002"])

    def test_broken_block_is_silence_not_a_crash(self):
        self.ear.feed_block(b"\x01")          # odd-length garbage
        self.ear.feed_block(b"")
        self.speak(8, 6)
        self.assertEqual(len(self.spool.admitted), 1)

    def test_pcm_to_wav_round_trips(self):
        wav = pcm_to_wav(LOUD)
        with wave.open(io.BytesIO(wav)) as w:
            self.assertEqual(w.getnframes(), SAMPLES)


if __name__ == "__main__":
    unittest.main()
