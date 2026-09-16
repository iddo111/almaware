"""PicoBricks LDR -> leaky integrate-and-fire sensory neuron.

Copy this file and lif_core.py to a Raspberry Pi Pico/Pico W only after checking
the board's silk labels.  No flashing or hardware write is performed by the
host-side test suite.
"""

from machine import ADC, I2C, PWM, Pin
import time

from lif_core import AdaptiveLDR, LeakyIntegrateAndFire, clamp


# Confirmed PicoBricks Raspberry Pi Pico/Pico W pin map.
LDR_PIN = 27
BUZZER_PIN = 20
RGB_PIN = 6
OLED_SDA_PIN = 4
OLED_SCL_PIN = 5

# PicoBricks exposes servo outputs on GP21 and GP22.  GP20 and GP21 share an
# RP2040 PWM slice, so using the buzzer on GP20 and a servo on GP21 would force
# both channels to one frequency.  GP22 avoids that conflict.
SERVO_PIN = 22

LDR_ACTIVE_HIGH = True
ENABLE_BUZZER = True
ENABLE_RGB = True
ENABLE_OLED = True
ENABLE_SERVO = False  # Enable only after testing with the horn/linkage removed.

CONTROL_PERIOD_MS = 10
CALIBRATION_MS = 2000
STATUS_PERIOD_MS = 500
DISPLAY_PERIOD_MS = 250
RGB_PERIOD_MS = 50


class BuzzerOutput:
    def __init__(self, enabled):
        self.pwm = PWM(Pin(BUZZER_PIN)) if enabled else None
        self.stop_at_ms = None
        if self.pwm is not None:
            self.pwm.freq(880)
            self.pwm.duty_u16(0)

    def trigger(self, now_ms, duration_ms=32):
        if self.pwm is None:
            return
        self.pwm.freq(880)
        self.pwm.duty_u16(2500)  # Low piezo duty; audible but intentionally bounded.
        self.stop_at_ms = time.ticks_add(now_ms, duration_ms)

    def update(self, now_ms):
        if self.pwm is None or self.stop_at_ms is None:
            return
        if time.ticks_diff(now_ms, self.stop_at_ms) >= 0:
            self.pwm.duty_u16(0)
            self.stop_at_ms = None

    def close(self):
        if self.pwm is not None:
            self.pwm.duty_u16(0)
            self.pwm.deinit()


class SafeServoOutput:
    REST_DEG = 90.0
    SPIKE_DEG = 105.0
    MIN_DEG = 75.0
    MAX_DEG = 105.0
    STEP_DEG = 1.0
    STEP_PERIOD_MS = 20

    def __init__(self, enabled, now_ms):
        self.pwm = PWM(Pin(SERVO_PIN)) if enabled else None
        self.angle = self.REST_DEG
        self.target = self.REST_DEG
        self.release_at_ms = now_ms
        self.next_step_ms = now_ms
        if self.pwm is not None:
            self.pwm.freq(50)
            self._write_angle(self.angle)

    def _write_angle(self, angle):
        if self.pwm is None:
            return
        angle = clamp(angle, self.MIN_DEG, self.MAX_DEG)
        # Narrow, conservative 1.0..2.0 ms mapping; configured range uses only
        # about 1.42..1.58 ms around center.
        pulse_us = 1000.0 + (angle / 180.0) * 1000.0
        duty = int((pulse_us / 20000.0) * 65535.0)
        self.pwm.duty_u16(duty)

    def trigger(self, now_ms):
        if self.pwm is None:
            return
        self.target = self.SPIKE_DEG
        self.release_at_ms = time.ticks_add(now_ms, 90)

    def update(self, now_ms):
        if self.pwm is None:
            return
        if time.ticks_diff(now_ms, self.release_at_ms) >= 0:
            self.target = self.REST_DEG
        if time.ticks_diff(now_ms, self.next_step_ms) < 0:
            return
        self.next_step_ms = time.ticks_add(now_ms, self.STEP_PERIOD_MS)
        delta = self.target - self.angle
        if abs(delta) < 0.001:
            return
        if delta > self.STEP_DEG:
            delta = self.STEP_DEG
        elif delta < -self.STEP_DEG:
            delta = -self.STEP_DEG
        self.angle = clamp(self.angle + delta, self.MIN_DEG, self.MAX_DEG)
        self._write_angle(self.angle)

    def close(self):
        if self.pwm is not None:
            self.target = self.REST_DEG
            self.angle = self.REST_DEG
            self._write_angle(self.REST_DEG)
            self.pwm.deinit()


class RGBOutput:
    def __init__(self, enabled):
        self.kind = None
        self.device = None
        if not enabled:
            return
        try:
            from neopixel import NeoPixel

            self.device = NeoPixel(Pin(RGB_PIN), 1)
            self.kind = "neopixel"
        except (ImportError, OSError):
            try:
                from picobricks import WS2812

                self.device = WS2812(RGB_PIN, brightness=0.08)
                self.kind = "picobricks"
            except (ImportError, OSError):
                self.device = None
        self.set((0, 0, 0))

    def set(self, color):
        if self.device is None:
            return
        color = tuple(int(clamp(channel, 0, 255)) for channel in color)
        if self.kind == "neopixel":
            self.device[0] = color
            self.device.write()
        else:
            self.device.pixels_fill(color)
            self.device.pixels_show()

    def show_state(self, stimulus, membrane_fraction, spiking):
        if spiking:
            self.set((55, 8, 0))
            return
        green = int(45 * clamp(stimulus))
        blue = int(45 * clamp(membrane_fraction))
        self.set((0, green, blue))

    def close(self):
        self.set((0, 0, 0))


class OLEDOutput:
    def __init__(self, enabled):
        self.device = None
        if not enabled:
            return
        driver = None
        try:
            from picobricks import SSD1306_I2C

            driver = SSD1306_I2C
        except ImportError:
            try:
                from ssd1306 import SSD1306_I2C

                driver = SSD1306_I2C
            except ImportError:
                return
        try:
            bus = I2C(
                0,
                sda=Pin(OLED_SDA_PIN),
                scl=Pin(OLED_SCL_PIN),
                freq=400000,
            )
            self.device = driver(128, 64, bus)
        except OSError:
            self.device = None

    def show(self, raw, stimulus, membrane, threshold, rate_hz, calibrating):
        if self.device is None:
            return
        self.device.fill(0)
        self.device.text("LDR LIF NEURON", 0, 0)
        if calibrating:
            self.device.text("CALIBRATING...", 0, 16)
        else:
            self.device.text("raw {:5d}".format(raw), 0, 16)
            self.device.text("stim {:.2f}".format(stimulus), 0, 28)
            self.device.text("V {:.2f}/{:.2f}".format(membrane, threshold), 0, 40)
            self.device.text("rate {:.1f} Hz".format(rate_hz), 0, 52)
        self.device.show()

    def close(self):
        if self.device is not None:
            self.device.fill(0)
            self.device.show()


class PicoBricksNeuron:
    def __init__(self):
        now_ms = time.ticks_ms()
        self.ldr = ADC(LDR_PIN)
        self.normalizer = AdaptiveLDR(active_high=LDR_ACTIVE_HIGH)
        self.neuron = LeakyIntegrateAndFire()
        self.buzzer = BuzzerOutput(ENABLE_BUZZER)
        self.servo = SafeServoOutput(ENABLE_SERVO, now_ms)
        self.rgb = RGBOutput(ENABLE_RGB)
        self.oled = OLEDOutput(ENABLE_OLED)
        self.started_ms = now_ms
        self.last_control_ms = now_ms
        self.next_control_ms = time.ticks_add(now_ms, CONTROL_PERIOD_MS)
        self.next_status_ms = now_ms
        self.next_display_ms = now_ms
        self.next_rgb_ms = now_ms
        self.spike_times_ms = []
        self.raw = self.ldr.read_u16()
        self.stimulus = 0.0
        self.last_spike_ms = None

    def _calibrating(self, now_ms):
        return time.ticks_diff(now_ms, self.started_ms) < CALIBRATION_MS

    def _record_spike(self, now_ms):
        self.spike_times_ms.append(now_ms)
        self.last_spike_ms = now_ms
        self.buzzer.trigger(now_ms)
        self.servo.trigger(now_ms)

    def _rate_hz(self, now_ms):
        while (
            self.spike_times_ms
            and time.ticks_diff(now_ms, self.spike_times_ms[0]) > 2000
        ):
            self.spike_times_ms.pop(0)
        return len(self.spike_times_ms) / 2.0

    def _control_step(self, now_ms):
        elapsed_ms = time.ticks_diff(now_ms, self.last_control_ms)
        self.last_control_ms = now_ms
        dt_s = max(0.0, elapsed_ms / 1000.0)
        self.raw = self.ldr.read_u16()
        self.stimulus = self.normalizer.update(self.raw, dt_s)

        if self._calibrating(now_ms):
            self.neuron.reset()
            return

        if self.neuron.step(self.stimulus, dt_s):
            self._record_spike(now_ms)

    def _update_outputs(self, now_ms):
        self.buzzer.update(now_ms)
        self.servo.update(now_ms)
        rate_hz = self._rate_hz(now_ms)
        calibrating = self._calibrating(now_ms)

        if time.ticks_diff(now_ms, self.next_rgb_ms) >= 0:
            self.next_rgb_ms = time.ticks_add(now_ms, RGB_PERIOD_MS)
            threshold = max(0.001, self.neuron.effective_threshold)
            membrane_fraction = self.neuron.membrane / threshold
            spiking = (
                self.last_spike_ms is not None
                and time.ticks_diff(now_ms, self.last_spike_ms) < 45
            )
            self.rgb.show_state(self.stimulus, membrane_fraction, spiking)

        if time.ticks_diff(now_ms, self.next_display_ms) >= 0:
            self.next_display_ms = time.ticks_add(now_ms, DISPLAY_PERIOD_MS)
            self.oled.show(
                self.raw,
                self.stimulus,
                self.neuron.membrane,
                self.neuron.effective_threshold,
                rate_hz,
                calibrating,
            )

        if time.ticks_diff(now_ms, self.next_status_ms) >= 0:
            self.next_status_ms = time.ticks_add(now_ms, STATUS_PERIOD_MS)
            print(
                "raw={} baseline={:.3f} stim={:.3f} V={:.3f} "
                "threshold={:.3f} rate_hz={:.1f}{}".format(
                    self.raw,
                    self.normalizer.baseline or 0.0,
                    self.stimulus,
                    self.neuron.membrane,
                    self.neuron.effective_threshold,
                    rate_hz,
                    " CALIBRATING" if calibrating else "",
                )
            )

    def run(self):
        print("# PicoBricks LDR sensory neuron; no blocking output delays")
        print("# Servo is {} on GP{}".format(
            "ENABLED" if ENABLE_SERVO else "DISABLED", SERVO_PIN
        ))
        while True:
            now_ms = time.ticks_ms()
            if time.ticks_diff(now_ms, self.next_control_ms) >= 0:
                self._control_step(now_ms)
                self.next_control_ms = time.ticks_add(
                    self.next_control_ms, CONTROL_PERIOD_MS
                )
                # If a debugger/USB stall put us far behind, resume from now.
                if time.ticks_diff(now_ms, self.next_control_ms) > 50:
                    self.next_control_ms = time.ticks_add(
                        now_ms, CONTROL_PERIOD_MS
                    )
            self._update_outputs(now_ms)
            time.sleep_ms(1)  # Cooperative idle yield, not a behavioral delay.

    def close(self):
        self.buzzer.close()
        self.servo.close()
        self.rgb.close()
        self.oled.close()


controller = PicoBricksNeuron()
try:
    controller.run()
finally:
    controller.close()

