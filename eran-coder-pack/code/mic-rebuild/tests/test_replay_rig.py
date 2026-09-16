"""K0 acceptance tests for the replay-rig skeleton (tools/replay/rig.py).

K0 acceptance row: "Rig harness loads the corpus manifest."
Also proven here: the stage chain runs real PCM end-to-end (synthetic WAV,
no audio device involved — Sacred Audio holds in tests too).
"""
from __future__ import annotations

import json
import math
import struct
import sys
import tempfile
import unittest
import wave
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools" / "replay"))
import rig  # noqa: E402


def write_wav(path: Path, seconds: float = 0.5, rate: int = 16000, freq: float = 220.0):
    n = int(seconds * rate)
    frames = b"".join(
        struct.pack("<h", int(12000 * math.sin(2 * math.pi * freq * i / rate)))
        for i in range(n)
    )
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(frames)
    return n * 2  # bytes


class ManifestLoads(unittest.TestCase):
    def test_repo_manifest_loads_and_validates(self):
        data, clips = rig.load_manifest()
        self.assertEqual(data["version"], 1)
        self.assertGreaterEqual(len(clips), 10)
        cats = {c.category for c in clips}
        for required in ("silence", "noise", "faint", "he", "en", "code_switch", "laughter", "failing"):
            self.assertIn(required, cats)
        # the three known failing clips from the inquiry are present by id
        ids = {c.id for c in clips}
        for fid in ("failing-wifi", "failing-flying-corals", "failing-talking-english"):
            self.assertIn(fid, ids)

    def test_malformed_manifest_halts_loudly(self):
        cases = [
            '{"version": 2, "corpus": [{"id":"a","category":"he","file":"x.wav","expect":{}}]}',
            '{"version": 1, "corpus": []}',
            '{"version": 1, "corpus": [{"id":"a","category":"he","file":"x.wav"}]}',
            '{"version": 1, "corpus": [{"id":"a","category":"NOPE","file":"x.wav","expect":{}}]}',
            '{"version": 1, "corpus": [{"id":"a","category":"he","file":"x.wav","expect":{}},'
            '{"id":"a","category":"en","file":"y.wav","expect":{}}]}',
            "not json at all",
        ]
        for src in cases:
            with tempfile.TemporaryDirectory() as td:
                p = Path(td) / "manifest.json"
                p.write_text(src, encoding="utf-8")
                with self.assertRaises(rig.ManifestError, msg=src):
                    rig.load_manifest(p)


class RigRuns(unittest.TestCase):
    def test_null_chain_processes_synthetic_wav(self):
        with tempfile.TemporaryDirectory() as td:
            wav = Path(td) / "he-clean-1.wav"
            n_bytes = write_wav(wav, seconds=0.5)
            manifest = {
                "version": 1, "sample_rate": 16000,
                "corpus": [{"id": "he-clean-1", "category": "he",
                            "file": wav.name, "lang": "he", "expect": {"transcribed": True}}],
            }
            mp = Path(td) / "manifest.json"
            mp.write_text(json.dumps(manifest), encoding="utf-8")

            data, clips = rig.load_manifest(mp)
            self.assertTrue(clips[0].present)
            r = rig.ReplayRig([rig.NullDecoder()]).run_clip(clips[0])
            self.assertEqual(r.clip_id, "he-clean-1")
            self.assertEqual(r.n_pcm_bytes, n_bytes)
            self.assertEqual(r.duration_ms, 500)
            self.assertEqual(len(r.stage_trace), 1)
            self.assertEqual(r.stage_trace[0][0], "null-decoder")

    def test_wrong_rate_is_a_loud_error(self):
        with tempfile.TemporaryDirectory() as td:
            wav = Path(td) / "bad.wav"
            write_wav(wav, seconds=0.2, rate=44100)
            clip = rig.Clip(id="bad", category="he", path=wav, lang="he", expect={})
            with self.assertRaises(ValueError):
                rig.ReplayRig([rig.NullDecoder()]).run_clip(clip)

    def test_missing_clips_reported_not_hidden(self):
        _, clips = rig.load_manifest()
        # at K0 the WAVs may be absent; presence must be a computed fact, not a crash
        for c in clips:
            self.assertIsInstance(c.present, bool)


if __name__ == "__main__":
    unittest.main(verbosity=2)
