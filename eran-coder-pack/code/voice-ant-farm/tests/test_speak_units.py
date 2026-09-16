import unittest

import numpy as np

from speak_units import hold


def fake_checkpoint(rate: int = 16000, frame: int = 400) -> dict:
    t = np.arange(frame) / rate
    exemplar = np.rint(0.4 * np.sin(2 * np.pi * 200 * t) * 32768).astype(np.int64)
    return {
        "exemplar_rate": rate,
        "exemplar_frame_samples": frame,
        "exemplar_hop_samples": frame // 4,
        "exemplars_pcm16": [exemplar.tolist()],
        "units": 1,
        "checkpoint_sha256": "fake",
    }


class HoldTest(unittest.TestCase):
    def test_soft_by_default_faded_and_normalised(self):
        ck = fake_checkpoint()
        y = hold(0, 0.3, ck)
        self.assertEqual(len(y), int(0.3 * ck["exemplar_rate"]))
        self.assertLess(abs(float(y[0])), 1e-3)
        self.assertLess(abs(float(y[-1])), 1e-3)
        self.assertAlmostEqual(float(np.abs(y).max()), 0.85, places=2)

    def test_raw_keeps_original_rendering(self):
        ck = fake_checkpoint()
        y = hold(0, 0.3, ck, raw=True)
        # the raw path starts mid-exemplar with no fade-in and no 0.85 peak
        self.assertNotAlmostEqual(float(np.abs(y).max()), 0.85, places=2)


if __name__ == "__main__":
    unittest.main()
