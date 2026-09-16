"""Hardware-independent sensory-neuron dynamics.

This module deliberately uses only the Python standard library features also
available in MicroPython.  It can therefore be imported unchanged by both the
Pico and the deterministic host-side tests.
"""

import math


ADC_MAX = 65535.0


def clamp(value, low=0.0, high=1.0):
    """Return a finite value bounded to ``low..high``."""
    value = float(value)
    if value != value:  # NaN, without depending on math.isfinite in MicroPython.
        return low
    if value < low:
        return low
    if value > high:
        return high
    return value


def bounded_dt(dt_s, maximum_s):
    """Sanitize elapsed time and discard unsafe scheduler-sized jumps."""
    dt_s = float(dt_s)
    if dt_s != dt_s or dt_s <= 0.0:
        return 0.0
    if dt_s > maximum_s:
        return maximum_s
    return dt_s


def normalize_ldr(raw_value, observed_min, observed_max, invert=False):
    """Normalize a calibrated LDR reading to ``0..1``.

    This is the fixed-range API from the first host model.  It remains useful
    for explicit two-point calibration, while :class:`AdaptiveLDR` below is the
    preferred ambient-tracking path on the device.  A missing/degenerate range
    fails closed to zero stimulus.
    """
    observed_min = float(observed_min)
    observed_max = float(observed_max)
    if observed_max <= observed_min:
        return 0.0
    normalized = clamp(
        (float(raw_value) - observed_min) / (observed_max - observed_min)
    )
    return 1.0 - normalized if invert else normalized


class AdaptiveLDR:
    """Convert a 16-bit LDR reading into positive ambient-light contrast.

    The slowly moving baseline makes the sensor respond to a light increase
    rather than to an arbitrary raw ADC number.  A brighter-than-baseline step
    is normalized to 0..1.  The baseline moves more slowly while stimulated,
    creating biological-style sensory adaptation without hiding a short event.
    """

    def __init__(
        self,
        active_high=True,
        baseline_tau_s=8.0,
        stimulated_tau_s=24.0,
        contrast_span=0.20,
        deadband=0.008,
        max_dt_s=0.05,
    ):
        if baseline_tau_s <= 0.0 or stimulated_tau_s <= 0.0:
            raise ValueError("baseline time constants must be positive")
        if contrast_span <= 0.0:
            raise ValueError("contrast_span must be positive")
        self.active_high = bool(active_high)
        self.baseline_tau_s = float(baseline_tau_s)
        self.stimulated_tau_s = float(stimulated_tau_s)
        self.contrast_span = float(contrast_span)
        self.deadband = clamp(deadband, 0.0, 0.5)
        self.max_dt_s = float(max_dt_s)
        self.baseline = None
        self.level = 0.0
        self.stimulus = 0.0

    def reset(self):
        self.baseline = None
        self.level = 0.0
        self.stimulus = 0.0

    def update(self, raw_u16, dt_s):
        raw = clamp(raw_u16, 0.0, ADC_MAX) / ADC_MAX
        self.level = raw if self.active_high else 1.0 - raw

        if self.baseline is None:
            self.baseline = self.level
            self.stimulus = 0.0
            return self.stimulus

        dt_s = bounded_dt(dt_s, self.max_dt_s)
        positive_contrast = self.level - self.baseline
        tau_s = (
            self.stimulated_tau_s
            if positive_contrast > self.deadband
            else self.baseline_tau_s
        )
        if dt_s > 0.0:
            alpha = 1.0 - math.exp(-dt_s / tau_s)
            self.baseline += alpha * (self.level - self.baseline)
            self.baseline = clamp(self.baseline)

        contrast = self.level - self.baseline - self.deadband
        self.stimulus = clamp(contrast / self.contrast_span)
        return self.stimulus


class LeakyIntegrateAndFire:
    """A bounded leaky integrate-and-fire neuron with refractory/adaptation.

    ``input_gain * stimulus`` is the membrane's steady-state value.  The exact
    exponential leak update is stable across small variations in loop timing.
    One call can emit at most one spike; long scheduler gaps are capped.
    """

    def __init__(
        self,
        tau_m_s=0.24,
        input_gain=1.20,
        threshold=0.62,
        reset_value=0.0,
        refractory_s=0.12,
        adaptation_increment=0.075,
        adaptation_tau_s=2.0,
        adaptation_cap=0.32,
        max_dt_s=0.05,
    ):
        if tau_m_s <= 0.0 or adaptation_tau_s <= 0.0:
            raise ValueError("neuron time constants must be positive")
        if input_gain <= 0.0 or threshold <= 0.0:
            raise ValueError("input gain and threshold must be positive")
        if refractory_s < 0.0 or adaptation_increment < 0.0:
            raise ValueError("refractory/adaptation values cannot be negative")
        self.tau_m_s = float(tau_m_s)
        self.input_gain = float(input_gain)
        self.threshold = float(threshold)
        self.reset_value = clamp(reset_value, 0.0, threshold)
        self.refractory_s = float(refractory_s)
        self.adaptation_increment = float(adaptation_increment)
        self.adaptation_tau_s = float(adaptation_tau_s)
        self.adaptation_cap = max(0.0, float(adaptation_cap))
        self.max_dt_s = float(max_dt_s)
        self.membrane = self.reset_value
        self.adaptation = 0.0
        self.refractory_remaining_s = 0.0
        self.spike_count = 0

    @property
    def effective_threshold(self):
        return self.threshold + self.adaptation

    def reset(self):
        self.membrane = self.reset_value
        self.adaptation = 0.0
        self.refractory_remaining_s = 0.0
        self.spike_count = 0

    def step(self, stimulus, dt_s):
        stimulus = clamp(stimulus)
        dt_s = bounded_dt(dt_s, self.max_dt_s)
        if dt_s <= 0.0:
            return False

        self.adaptation *= math.exp(-dt_s / self.adaptation_tau_s)

        if self.refractory_remaining_s > 0.0:
            self.refractory_remaining_s = max(
                0.0, self.refractory_remaining_s - dt_s
            )
            self.membrane = self.reset_value
            return False

        steady_state = self.input_gain * stimulus
        leak_factor = math.exp(-dt_s / self.tau_m_s)
        self.membrane = steady_state + (
            self.membrane - steady_state
        ) * leak_factor
        self.membrane = max(self.reset_value, self.membrane)

        if self.membrane < self.effective_threshold:
            return False

        self.membrane = self.reset_value
        self.adaptation = min(
            self.adaptation_cap,
            self.adaptation + self.adaptation_increment,
        )
        self.refractory_remaining_s = self.refractory_s
        self.spike_count += 1
        return True


class LIFNeuron(LeakyIntegrateAndFire):
    """Backward-compatible millisecond API over the current LIF engine.

    The original host tests used ``LIFNeuron.step(stimulus, dt_ms)`` and the
    names ``voltage`` and ``refractory_left_ms``.  This adapter preserves those
    units and names without duplicating the dynamics.  Legacy behavior had no
    adaptive threshold, so adaptation is disabled for this wrapper; new code
    should instantiate :class:`LeakyIntegrateAndFire` directly.
    """

    def __init__(
        self,
        tau_ms=300.0,
        input_gain=1.20,
        threshold=0.62,
        reset_voltage=0.0,
        refractory_ms=120.0,
        max_dt_ms=50.0,
    ):
        if tau_ms <= 0.0:
            raise ValueError("tau_ms must be positive")
        if threshold <= 0.0:
            raise ValueError("threshold must be positive")
        if reset_voltage < 0.0 or reset_voltage >= threshold:
            raise ValueError("reset_voltage must be in [0, threshold)")
        if refractory_ms < 0.0:
            raise ValueError("refractory_ms cannot be negative")
        if max_dt_ms <= 0.0:
            raise ValueError("max_dt_ms must be positive")

        self.tau_ms = float(tau_ms)
        self.reset_voltage = float(reset_voltage)
        self.refractory_ms = float(refractory_ms)
        self.max_dt_ms = float(max_dt_ms)
        super().__init__(
            tau_m_s=self.tau_ms / 1000.0,
            input_gain=input_gain,
            threshold=threshold,
            reset_value=self.reset_voltage,
            refractory_s=self.refractory_ms / 1000.0,
            adaptation_increment=0.0,
            adaptation_cap=0.0,
            max_dt_s=self.max_dt_ms / 1000.0,
        )

    @property
    def voltage(self):
        return self.membrane

    @voltage.setter
    def voltage(self, value):
        self.membrane = max(self.reset_value, float(value))

    @property
    def refractory_left_ms(self):
        return self.refractory_remaining_s * 1000.0

    def step(self, stimulus, dt_ms):
        if dt_ms <= 0.0:
            raise ValueError("dt_ms must be positive")
        return super().step(stimulus, float(dt_ms) / 1000.0)
