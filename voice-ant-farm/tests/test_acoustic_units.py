import tempfile
import unittest
import wave
import json
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from acoustic_units import (
    CHECKPOINT_FORMAT, checkpoint_digest, dataset, encode, error, evaluate,
    features, fit_codebook, load_checkpoint, load_wav, reconstruct, train,
    train_ant, write_json_atomic, write_wav_atomic,
)


def write_tone(path: Path, hz: float, seconds: float = 0.6, rate: int = 16000):
    t = np.arange(int(rate * seconds)) / rate
    samples = (0.25 * np.sin(2 * np.pi * hz * t) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes(samples.tobytes())


class AcousticUnitsTest(unittest.TestCase):
    def test_waveform_features_and_learned_units(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "tone.wav"; write_tone(p, 440)
            audio = load_wav(p); x, hop = features(audio)
            centers = fit_codebook(x, 4, seed=7)
            self.assertGreater(len(x), 10)
            self.assertEqual(encode(x, centers).shape[0], len(x))
            self.assertGreater(hop, 0)
            self.assertLessEqual(error(x, centers), error(x, np.repeat(x.mean(0, keepdims=True), 4, 0)))

    def test_dataset_hash_deduplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); write_tone(root / "a.wav", 300)
            (root / "b.wav").write_bytes((root / "a.wav").read_bytes())
            _, hashes = dataset(root)
            self.assertEqual(len(hashes), 1)

    def test_checkpoint_is_sealed_and_independently_evaluated(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            train_dir, heldout_dir, evaluation_dir = root / "train", root / "heldout", root / "evaluation"
            train_dir.mkdir(); heldout_dir.mkdir(); evaluation_dir.mkdir()
            write_tone(train_dir / "a.wav", 300)
            write_tone(train_dir / "b.wav", 450)
            write_tone(heldout_dir / "c.wav", 320)
            write_tone(heldout_dir / "d.wav", 470)
            write_tone(evaluation_dir / "e.wav", 340)
            write_tone(evaluation_dir / "f.wav", 490)
            with redirect_stdout(StringIO()):
                train(SimpleNamespace(
                    train=str(train_dir), heldout=str(heldout_dir), state=str(root / "state"),
                    ant="ant-a", units=4, seed=7,
                ))
            checkpoint_path = root / "state" / "ant-a" / "current.json"
            checkpoint = load_checkpoint(checkpoint_path)
            self.assertEqual(checkpoint["architecture"], "waveform-acoustic-vector-quantizer-with-exemplars")
            self.assertEqual(checkpoint["format_version"], CHECKPOINT_FORMAT)
            self.assertEqual(len(checkpoint["exemplars_pcm16"]), 4)
            output = StringIO()
            with redirect_stdout(output):
                evaluate(SimpleNamespace(checkpoint=str(checkpoint_path), heldout=str(evaluation_dir)))
            result = json.loads(output.getvalue())
            self.assertGreater(result["evaluation_frame_count"], 0)
            self.assertTrue(result["improved"])

            source = load_wav(evaluation_dir / "e.wav")
            reconstructed, unit_ids = reconstruct(source, checkpoint)
            self.assertGreater(len(unit_ids), 10)
            self.assertGreater(float(np.max(np.abs(reconstructed))), 0.01)
            output_wav = root / "reconstructed.wav"
            output_hash = write_wav_atomic(output_wav, reconstructed, checkpoint["exemplar_rate"])
            self.assertEqual(load_wav(output_wav).sha256, output_hash)

            tampered = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            tampered["seed"] = 999
            checkpoint_path.write_text(json.dumps(tampered), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                load_checkpoint(checkpoint_path)

    def test_evaluation_rejects_training_audio_overlap(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            train_dir, heldout_dir = root / "train", root / "heldout"
            train_dir.mkdir(); heldout_dir.mkdir()
            write_tone(train_dir / "a.wav", 300)
            write_tone(train_dir / "b.wav", 450)
            write_tone(heldout_dir / "c.wav", 320)
            write_tone(heldout_dir / "d.wav", 470)
            with redirect_stdout(StringIO()):
                train(SimpleNamespace(
                    train=str(train_dir), heldout=str(heldout_dir), state=str(root / "state"),
                    ant="ant-a", units=4, seed=7,
                ))
            checkpoint_path = root / "state" / "ant-a" / "current.json"
            with self.assertRaisesRegex(ValueError, "overlaps"):
                evaluate(SimpleNamespace(checkpoint=str(checkpoint_path), heldout=str(train_dir)))
            with self.assertRaisesRegex(ValueError, "overlaps"):
                evaluate(SimpleNamespace(checkpoint=str(checkpoint_path), heldout=str(heldout_dir)))

    def test_verified_legacy_raw_hash_checkpoint_migrates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            train_dir, heldout_dir = root / "train", root / "heldout"
            train_dir.mkdir(); heldout_dir.mkdir()
            write_tone(train_dir / "a.wav", 300)
            write_tone(train_dir / "b.wav", 450)
            write_tone(heldout_dir / "c.wav", 320)
            write_tone(heldout_dir / "d.wav", 470)
            state = root / "state"
            first, _ = train_ant(
                train_dir, heldout_dir, state, "ant-a", 4, 7,
                {"sample_rates": [16000]},
            )
            legacy = dict(first)
            legacy["format_version"] = 2
            for key in (
                "audio_hash_kind", "feature_spec", "experiment_namespace",
                "corpus_provenance",
            ):
                legacy.pop(key, None)
            legacy["train_audio_hashes"] = sorted(
                load_wav(path).sha256 for path in train_dir.glob("*.wav")
            )
            legacy["heldout_audio_hashes"] = sorted(
                load_wav(path).sha256 for path in heldout_dir.glob("*.wav")
            )
            legacy["checkpoint_sha256"] = checkpoint_digest(legacy)
            current_path = state / "ant-a" / "current.json"
            write_json_atomic(current_path, legacy)

            upgraded, _ = train_ant(
                train_dir, heldout_dir, state, "ant-a", 4, 7,
                {"sample_rates": [16000]},
            )
            self.assertTrue(upgraded["promotion_eligible"])
            self.assertEqual(
                upgraded["promotion_basis"],
                "capability-upgrade-from-verified-legacy-audio-hashes",
            )
            self.assertEqual(load_checkpoint(current_path)["format_version"], CHECKPOINT_FORMAT)


class RenderSoftTest(unittest.TestCase):
    RATE = 16000

    def _tone(self, hz: float, seconds: float = 0.5, amp: float = 0.5) -> np.ndarray:
        t = np.arange(int(self.RATE * seconds)) / self.RATE
        return (amp * np.sin(2 * np.pi * hz * t)).astype(np.float32)

    def test_removes_energy_above_cutoff_keeps_it_below(self):
        # Peak normalisation is part of the rendering, so absolute levels
        # prove nothing; the filter's promise is relative — in a mixed tone
        # the high band dies while the low band survives.
        from acoustic_units import render_soft
        x = self._tone(440) + self._tone(6000)
        y = render_soft(x, self.RATE)

        def high_band_fraction(sig: np.ndarray) -> float:
            power = np.abs(np.fft.rfft(sig)) ** 2
            freqs = np.fft.rfftfreq(len(sig), 1.0 / self.RATE)
            return float(power[freqs >= 5000].sum() / power.sum())

        self.assertGreater(high_band_fraction(x), 0.4)
        self.assertLess(high_band_fraction(y), 0.01)

    def test_fades_edges_normalises_peak_keeps_length(self):
        from acoustic_units import render_soft
        x = self._tone(440)
        y = render_soft(x, self.RATE)
        self.assertEqual(len(y), len(x))
        self.assertLess(abs(float(y[0])), 1e-3)
        self.assertLess(abs(float(y[-1])), 1e-3)
        self.assertAlmostEqual(float(np.abs(y).max()), 0.85, places=2)

    def test_silence_stays_silent_without_nans(self):
        from acoustic_units import render_soft
        y = render_soft(np.zeros(self.RATE, dtype=np.float32), self.RATE)
        self.assertTrue(np.all(np.isfinite(y)))
        self.assertEqual(float(np.abs(y).max()), 0.0)


if __name__ == "__main__":
    unittest.main()
