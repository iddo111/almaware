"""Deterministic regression tests; no board, USB, or third-party packages."""

import math
import os
import sys
import unittest


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from lif_core import AdaptiveLDR, LeakyIntegrateAndFire  # noqa: E402


def constant_run(neuron, stimulus, seconds, dt_s=0.01):
    spike_times = []
    for index in range(int(round(seconds / dt_s))):
        if neuron.step(stimulus, dt_s):
            spike_times.append((index + 1) * dt_s)
    return spike_times


class AdaptiveLDRTests(unittest.TestCase):
    def test_initial_sample_is_zero_contrast_and_bounds_hold(self):
        sensor = AdaptiveLDR(active_high=True)
        self.assertEqual(sensor.update(10000, 0.01), 0.0)
        self.assertEqual(sensor.update(65535, 0.01), 1.0)
        self.assertGreaterEqual(sensor.update(-100, 0.01), 0.0)
        self.assertLessEqual(sensor.update(70000, 0.01), 1.0)

    def test_active_low_reverses_the_physical_direction(self):
        sensor = AdaptiveLDR(active_high=False)
        sensor.update(50000, 0.01)
        self.assertGreater(sensor.update(5000, 0.01), 0.9)

    def test_baseline_moves_slowly_toward_sustained_light(self):
        sensor = AdaptiveLDR(active_high=True)
        sensor.update(10000, 0.01)
        first = sensor.update(40000, 0.01)
        original_baseline = sensor.baseline
        for _ in range(3000):
            last = sensor.update(40000, 0.01)
        self.assertGreater(sensor.baseline, original_baseline)
        self.assertLess(last, first)
        self.assertGreaterEqual(last, 0.0)


class LeakyIntegrateAndFireTests(unittest.TestCase):
    def test_zero_and_subthreshold_inputs_do_not_spike(self):
        self.assertEqual(len(constant_run(LeakyIntegrateAndFire(), 0.0, 5.0)), 0)
        self.assertEqual(len(constant_run(LeakyIntegrateAndFire(), 0.35, 5.0)), 0)

    def test_bright_input_spikes_and_stronger_input_is_faster(self):
        medium = constant_run(LeakyIntegrateAndFire(), 0.60, 6.0)
        strong = constant_run(LeakyIntegrateAndFire(), 1.00, 6.0)
        self.assertGreaterEqual(len(medium), 2)
        self.assertGreater(len(strong), len(medium))

    def test_refractory_period_is_respected(self):
        neuron = LeakyIntegrateAndFire()
        times = constant_run(neuron, 1.0, 8.0, dt_s=0.005)
        self.assertGreater(len(times), 3)
        for left, right in zip(times, times[1:]):
            self.assertGreaterEqual(right - left + 1e-12, neuron.refractory_s)

    def test_adaptation_reduces_late_rate(self):
        neuron = LeakyIntegrateAndFire(
            adaptation_increment=0.10,
            adaptation_tau_s=4.0,
        )
        times = constant_run(neuron, 1.0, 10.0)
        early = len([t for t in times if t <= 3.0])
        late = len([t for t in times if 7.0 < t <= 10.0])
        self.assertGreater(early, late)

    def test_long_or_invalid_dt_is_safe_and_finite(self):
        neuron = LeakyIntegrateAndFire()
        emitted = int(neuron.step(1.0, 99.0))
        emitted += int(neuron.step(float("nan"), 0.01))
        emitted += int(neuron.step(1.0, -1.0))
        self.assertLessEqual(emitted, 1)
        self.assertTrue(math.isfinite(neuron.membrane))
        self.assertTrue(math.isfinite(neuron.adaptation))

    def test_same_inputs_produce_identical_spike_train(self):
        def trial():
            neuron = LeakyIntegrateAndFire()
            sequence = (0.0, 0.2, 0.55, 1.0, 0.7, 0.0) * 200
            return [
                index
                for index, stimulus in enumerate(sequence)
                if neuron.step(stimulus, 0.01)
            ]

        self.assertEqual(trial(), trial())


class IntegratedScenarioTests(unittest.TestCase):
    def test_ambient_bright_recovery_pattern(self):
        sensor = AdaptiveLDR(active_high=True)
        neuron = LeakyIntegrateAndFire()
        counts = []
        for raw, seconds in ((9000, 3.0), (52000, 5.0), (9000, 3.0)):
            count = 0
            for _ in range(int(seconds / 0.01)):
                if neuron.step(sensor.update(raw, 0.01), 0.01):
                    count += 1
            counts.append(count)
        self.assertEqual(counts[0], 0)
        self.assertGreaterEqual(counts[1], 3)
        self.assertEqual(counts[2], 0)


if __name__ == "__main__":
    unittest.main()

