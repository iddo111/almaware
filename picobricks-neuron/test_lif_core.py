import unittest

from lif_core import LIFNeuron, normalize_ldr


class NormalizeLdrTests(unittest.TestCase):
    def test_clamps_and_maps_observed_range(self):
        self.assertEqual(normalize_ldr(50, 100, 500), 0.0)
        self.assertEqual(normalize_ldr(600, 100, 500), 1.0)
        self.assertAlmostEqual(normalize_ldr(300, 100, 500), 0.5)

    def test_inversion_is_explicit(self):
        self.assertAlmostEqual(normalize_ldr(200, 100, 500, invert=True), 0.75)

    def test_degenerate_calibration_fails_closed(self):
        self.assertEqual(normalize_ldr(100, 100, 100), 0.0)


class LIFNeuronTests(unittest.TestCase):
    def test_subthreshold_input_never_fires(self):
        neuron = LIFNeuron()
        spikes = [neuron.step(0.25, 20) for _ in range(500)]
        self.assertFalse(any(spikes))
        self.assertLess(neuron.voltage, neuron.threshold)

    def test_sustained_light_produces_real_spikes(self):
        neuron = LIFNeuron()
        spike_times = []
        for tick in range(300):
            if neuron.step(0.95, 20):
                spike_times.append(tick * 20)
        self.assertGreaterEqual(len(spike_times), 3)
        self.assertEqual(neuron.spike_count, len(spike_times))

    def test_refractory_period_blocks_immediate_refire(self):
        neuron = LIFNeuron(refractory_ms=400)
        while not neuron.step(1.0, 20):
            pass
        self.assertTrue(neuron.refractory_left_ms > 0)
        self.assertFalse(any(neuron.step(1.0, 20) for _ in range(19)))

    def test_voltage_leaks_after_stimulus_is_removed(self):
        neuron = LIFNeuron(threshold=2.0)
        for _ in range(30):
            neuron.step(1.0, 20)
        charged = neuron.voltage
        for _ in range(30):
            neuron.step(0.0, 20)
        self.assertGreater(charged, neuron.voltage)
        self.assertGreaterEqual(neuron.voltage, 0.0)

    def test_temporal_integration_is_not_an_if_statement(self):
        neuron = LIFNeuron(threshold=0.55, refractory_ms=200)
        # One short flash is insufficient.
        for _ in range(8):
            self.assertFalse(neuron.step(0.95, 20))
        # Closely spaced flashes add to the remaining membrane potential.
        fired = False
        for _ in range(6):
            neuron.step(0.0, 20)
        for _ in range(30):
            fired = neuron.step(0.95, 20) or fired
        self.assertTrue(fired)

    def test_invalid_parameters_are_rejected(self):
        with self.assertRaises(ValueError):
            LIFNeuron(tau_ms=0)
        with self.assertRaises(ValueError):
            LIFNeuron(threshold=0.1, reset_voltage=0.2)
        with self.assertRaises(ValueError):
            LIFNeuron().step(0.5, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
