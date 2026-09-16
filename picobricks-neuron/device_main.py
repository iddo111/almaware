"""Fail-closed MicroPython runtime for the PicoBricks sensory neuron.

Official PicoBricks Raspberry Pi Pico/Pico W connections used here:
  LDR GP27, buzzer GP20, WS2812 GP6, servo header GP21,
  OLED I2C0 SDA GP4 / SCL GP5.

This file does not flash or probe the board.  Copying/running it is a separate,
explicit hardware step.  Optional peripherals disable themselves on failure.
"""

from machine import ADC, I2C, PWM, Pin
import math
import time

import lif_core


LDR_PIN = 27
BUZZER_PIN = 20
RGB_PIN = 6
SERVO_PIN = 21
OLED_SDA_PIN = 4
OLED_SCL_PIN = 5

LDR_ACTIVE_HIGH = True
ENABLE_BUZZER = True
ENABLE_RGB = True
ENABLE_OLED = True
ENABLE_SERVO = False

CONTROL_PERIOD_MS = 10
CALIBRATION_MS = 2000
STATUS_PERIOD_MS = 500
OLED_PERIOD_MS = 250
RGB_PERIOD_MS = 50


def _clamp(value, low=0.0, high=1.0):
    value = float(value)
    if value != value:
        return low
    if value < low:
        return low
    if value > high:
        return high
    return value


class CoreAdapter:
    """Use either supported lif_core API without hiding its model semantics."""

    def __init__(self):
        if hasattr(lif_core, "AdaptiveLDR") and hasattr(
            lif_core, "LeakyIntegrateAndFire"
        ):
            self.style = "adaptive"
            self.normalizer = lif_core.AdaptiveLDR(
                active_high=LDR_ACTIVE_HIGH
            )
            self.neuron = lif_core.LeakyIntegrateAndFire()
            self.local_baseline = None
        elif hasattr(lif_core, "LIFNeuron") and hasattr(
            lif_core, "normalize_ldr"
        ):
            # Compatibility with the earlier fixed-range core.  Device-side
            # baseline tracking supplies ambient adaptation, while the core's
            # normalize_ldr function retains its explicit clamp/invert logic.
            self.style = "fixed-range"
            self.normalizer = None
            self.neuron = lif_core.LIFNeuron()
            self.local_baseline = None
        else:
            raise ImportError("unsupported lif_core API")

        self.stimulus = 0.0
        self.baseline = 0.0

    def update_ldr(self, raw_u16, dt_ms):
        if self.style == "adaptive":
            self.stimulus = self.normalizer.update(
                raw_u16, max(0.0, dt_ms) / 1000.0
            )
            self.baseline = self.normalizer.baseline or 0.0
            return self.stimulus

        directed = float(raw_u16)
        if not LDR_ACTIVE_HIGH:
            directed = 65535.0 - directed
        if self.local_baseline is None:
            self.local_baseline = directed
            self.stimulus = 0.0
            self.baseline = directed / 65535.0
            return self.stimulus

        positive = directed - self.local_baseline
        tau_ms = 24000.0 if positive > 524.0 else 8000.0
        safe_dt_ms = min(50.0, max(0.0, float(dt_ms)))
        alpha = 1.0 - math.exp(-safe_dt_ms / tau_ms)
        self.local_baseline += alpha * (directed - self.local_baseline)
        low = self.local_baseline + 524.0
        high = low + 13107.0
        self.stimulus = lif_core.normalize_ldr(directed, low, high)
        self.baseline = self.local_baseline / 65535.0
        return self.stimulus

    def step(self, dt_ms):
        if self.style == "adaptive":
            return self.neuron.step(
                self.stimulus, max(0.0, dt_ms) / 1000.0
            )
        # The earlier core expects milliseconds and rejects zero.  Cap a USB or
        # debugger-sized scheduler gap so it cannot create an artificial spike.
        safe_dt_ms = min(50, max(1, int(dt_ms)))
        return self.neuron.step(self.stimulus, safe_dt_ms)

    @property
    def membrane(self):
        if hasattr(self.neuron, "membrane"):
            return self.neuron.membrane
        return self.neuron.voltage

    @property
    def threshold(self):
        if hasattr(self.neuron, "effective_threshold"):
            return self.neuron.effective_threshold
        return self.neuron.threshold

    @property
    def spike_count(self):
        return self.neuron.spike_count


class Buzzer:
    """Short nonblocking piezo pulse; remains off if initialization fails."""

    def __init__(self, enabled):
        self.pwm = None
        self.stop_at_ms = None
        if not enabled:
            return
        try:
            self.pwm = PWM(Pin(BUZZER_PIN))
            self.pwm.freq(880)
            self.pwm.duty_u16(0)
        except Exception as error:
            self._disable("buzzer init", error)

    def _disable(self, label, error):
        if self.pwm is not None:
            try:
                self.pwm.duty_u16(0)
                self.pwm.deinit()
            except Exception:
                pass
        self.pwm = None
        self.stop_at_ms = None
        print("# {} disabled: {}".format(label, error))

    def trigger(self, now_ms):
        if self.pwm is None:
            return
        try:
            self.pwm.freq(880)
            self.pwm.duty_u16(2500)
            self.stop_at_ms = time.ticks_add(now_ms, 32)
        except Exception as error:
            self._disable("buzzer", error)

    def service(self, now_ms):
        if self.pwm is None or self.stop_at_ms is None:
            return
        if time.ticks_diff(now_ms, self.stop_at_ms) >= 0:
            try:
                self.pwm.duty_u16(0)
                self.stop_at_ms = None
            except Exception as error:
                self._disable("buzzer", error)

    def close(self):
        if self.pwm is not None:
            try:
                self.pwm.duty_u16(0)
                self.pwm.deinit()
            except Exception:
                pass
        self.pwm = None


class Servo:
    """Optional bounded, slew-limited servo output on official header GP21."""

    REST_DEG = 90.0
    SPIKE_DEG = 102.0
    MIN_DEG = 78.0
    MAX_DEG = 102.0
    STEP_DEG = 1.0
    STEP_PERIOD_MS = 20

    def __init__(self, enabled, buzzer_enabled, now_ms):
        self.pwm = None
        self.angle = self.REST_DEG
        self.target = self.REST_DEG
        self.release_at_ms = now_ms
        self.next_step_ms = now_ms
        if not enabled:
            return

        # GP20 is PWM2A and GP21 is PWM2B.  Both channels must share one
        # frequency on RP2040, so 880 Hz sound and a 50 Hz servo cannot coexist.
        if buzzer_enabled and SERVO_PIN == 21:
            print(
                "# servo disabled: GP20 buzzer and GP21 servo share PWM2; "
                "disable buzzer or move the servo signal to the GP22 header"
            )
            return
        try:
            self.pwm = PWM(Pin(SERVO_PIN))
            self.pwm.freq(50)
            self._write_angle(self.angle)
        except Exception as error:
            self._disable(error)

    def _disable(self, error):
        if self.pwm is not None:
            try:
                self.pwm.deinit()
            except Exception:
                pass
        self.pwm = None
        print("# servo disabled: {}".format(error))

    def _write_angle(self, angle):
        angle = _clamp(angle, self.MIN_DEG, self.MAX_DEG)
        # Conservative center-only pulse range: about 1.43..1.57 ms.
        pulse_us = 1000.0 + angle * (1000.0 / 180.0)
        self.pwm.duty_u16(int(pulse_us * 65535.0 / 20000.0))

    def trigger(self, now_ms):
        if self.pwm is None:
            return
        self.target = self.SPIKE_DEG
        self.release_at_ms = time.ticks_add(now_ms, 90)

    def service(self, now_ms):
        if self.pwm is None:
            return
        try:
            if time.ticks_diff(now_ms, self.release_at_ms) >= 0:
                self.target = self.REST_DEG
            if time.ticks_diff(now_ms, self.next_step_ms) < 0:
                return
            self.next_step_ms = time.ticks_add(
                now_ms, self.STEP_PERIOD_MS
            )
            delta = self.target - self.angle
            if abs(delta) < 0.001:
                return
            delta = _clamp(delta, -self.STEP_DEG, self.STEP_DEG)
            self.angle = _clamp(
                self.angle + delta, self.MIN_DEG, self.MAX_DEG
            )
            self._write_angle(self.angle)
        except Exception as error:
            self._disable(error)

    def close(self):
        if self.pwm is not None:
            try:
                self.pwm.deinit()
            except Exception:
                pass
        self.pwm = None


class RGB:
    """Optional one-pixel adapter with standard and PicoBricks drivers."""

    def __init__(self, enabled):
        self.device = None
        self.kind = None
        if not enabled:
            return
        try:
            from neopixel import NeoPixel

            self.device = NeoPixel(Pin(RGB_PIN), 1)
            self.kind = "neopixel"
        except Exception:
            try:
                from picobricks import WS2812

                self.device = WS2812(RGB_PIN, brightness=0.08)
                self.kind = "picobricks"
            except Exception as error:
                print("# RGB disabled: {}".format(error))
                self.device = None
        self.set((0, 0, 0))

    def _disable(self, error):
        self.device = None
        self.kind = None
        print("# RGB disabled: {}".format(error))

    def set(self, color):
        if self.device is None:
            return
        color = tuple(int(_clamp(item, 0, 255)) for item in color)
        try:
            if self.kind == "neopixel":
                self.device[0] = color
                self.device.write()
            else:
                self.device.pixels_fill(color)
                self.device.pixels_show()
        except Exception as error:
            self._disable(error)

    def show_state(self, stimulus, membrane_fraction, spiking):
        if spiking:
            self.set((55, 8, 0))
        else:
            self.set(
                (
                    0,
                    int(45 * _clamp(stimulus)),
                    int(45 * _clamp(membrane_fraction)),
                )
            )

    def close(self):
        self.set((0, 0, 0))
        self.device = None


class OLED:
    """Optional SSD1306 adapter; any bus/driver error disables only the OLED."""

    def __init__(self, enabled):
        self.device = None
        if not enabled:
            return
        driver = None
        try:
            from picobricks import SSD1306_I2C

            driver = SSD1306_I2C
        except Exception:
            try:
                from ssd1306 import SSD1306_I2C

                driver = SSD1306_I2C
            except Exception as error:
                print("# OLED disabled: {}".format(error))
                return
        try:
            bus = I2C(
                0,
                sda=Pin(OLED_SDA_PIN),
                scl=Pin(OLED_SCL_PIN),
                freq=400000,
            )
            self.device = driver(128, 64, bus)
        except Exception as error:
            print("# OLED disabled: {}".format(error))
            self.device = None

    def show(self, raw, core, rate_hz, calibrating):
        if self.device is None:
            return
        try:
            self.device.fill(0)
            self.device.text("LDR LIF NEURON", 0, 0)
            if calibrating:
                self.device.text("CALIBRATING...", 0, 18)
            else:
                self.device.text("raw {:5d}".format(raw), 0, 16)
                self.device.text("stim {:.2f}".format(core.stimulus), 0, 28)
                self.device.text(
                    "V {:.2f}/{:.2f}".format(
                        core.membrane, core.threshold
                    ),
                    0,
                    40,
                )
                self.device.text("rate {:.1f}Hz".format(rate_hz), 0, 52)
            self.device.show()
        except Exception as error:
            print("# OLED disabled: {}".format(error))
            self.device = None

    def close(self):
        if self.device is not None:
            try:
                self.device.fill(0)
                self.device.show()
            except Exception:
                pass
        self.device = None


class PicoBricksNeuronApp:
    def __init__(self):
        now_ms = time.ticks_ms()
        self.ldr = ADC(LDR_PIN)
        self.core = CoreAdapter()
        self.buzzer = Buzzer(ENABLE_BUZZER)
        self.servo = Servo(ENABLE_SERVO, self.buzzer.pwm is not None, now_ms)
        self.rgb = RGB(ENABLE_RGB)
        self.oled = OLED(ENABLE_OLED)
        self.started_ms = now_ms
        self.last_control_ms = now_ms
        self.next_control_ms = time.ticks_add(now_ms, CONTROL_PERIOD_MS)
        self.next_status_ms = now_ms
        self.next_oled_ms = now_ms
        self.next_rgb_ms = now_ms
        self.raw = self.ldr.read_u16()
        self.spike_times_ms = []
        self.last_spike_ms = None

    def calibrating(self, now_ms):
        return time.ticks_diff(now_ms, self.started_ms) < CALIBRATION_MS

    def rate_hz(self, now_ms):
        while (
            self.spike_times_ms
            and time.ticks_diff(now_ms, self.spike_times_ms[0]) > 2000
        ):
            self.spike_times_ms.pop(0)
        return len(self.spike_times_ms) / 2.0

    def control_step(self, now_ms):
        dt_ms = max(0, time.ticks_diff(now_ms, self.last_control_ms))
        self.last_control_ms = now_ms
        self.raw = self.ldr.read_u16()
        self.core.update_ldr(self.raw, dt_ms)
        if self.calibrating(now_ms):
            return
        if self.core.step(dt_ms):
            self.spike_times_ms.append(now_ms)
            self.last_spike_ms = now_ms
            self.buzzer.trigger(now_ms)
            self.servo.trigger(now_ms)
            print("spike_ms={} count={}".format(
                now_ms, self.core.spike_count
            ))

    def service(self, now_ms):
        self.buzzer.service(now_ms)
        self.servo.service(now_ms)
        rate_hz = self.rate_hz(now_ms)

        if time.ticks_diff(now_ms, self.next_rgb_ms) >= 0:
            self.next_rgb_ms = time.ticks_add(now_ms, RGB_PERIOD_MS)
            membrane_fraction = self.core.membrane / max(
                0.001, self.core.threshold
            )
            spiking = (
                self.last_spike_ms is not None
                and time.ticks_diff(now_ms, self.last_spike_ms) < 45
            )
            self.rgb.show_state(
                self.core.stimulus, membrane_fraction, spiking
            )

        if time.ticks_diff(now_ms, self.next_oled_ms) >= 0:
            self.next_oled_ms = time.ticks_add(now_ms, OLED_PERIOD_MS)
            self.oled.show(
                self.raw, self.core, rate_hz, self.calibrating(now_ms)
            )

        if time.ticks_diff(now_ms, self.next_status_ms) >= 0:
            self.next_status_ms = time.ticks_add(now_ms, STATUS_PERIOD_MS)
            print(
                "raw={} base={:.3f} stim={:.3f} V={:.3f} "
                "threshold={:.3f} rate_hz={:.1f}{}".format(
                    self.raw,
                    self.core.baseline,
                    self.core.stimulus,
                    self.core.membrane,
                    self.core.threshold,
                    rate_hz,
                    " CALIBRATING" if self.calibrating(now_ms) else "",
                )
            )

    def run(self):
        print("# PicoBricks LDR LIF neuron; core={}".format(self.core.style))
        print("# Servo default={} pin=GP{}".format(
            ENABLE_SERVO, SERVO_PIN
        ))
        while True:
            now_ms = time.ticks_ms()
            if time.ticks_diff(now_ms, self.next_control_ms) >= 0:
                self.control_step(now_ms)
                self.next_control_ms = time.ticks_add(
                    self.next_control_ms, CONTROL_PERIOD_MS
                )
                if time.ticks_diff(now_ms, self.next_control_ms) > 50:
                    self.next_control_ms = time.ticks_add(
                        now_ms, CONTROL_PERIOD_MS
                    )
            self.service(now_ms)
            time.sleep_ms(1)  # Cooperative idle yield, not an output delay.

    def close(self):
        for peripheral in (self.buzzer, self.servo, self.rgb, self.oled):
            try:
                peripheral.close()
            except Exception:
                pass


def main():
    app = PicoBricksNeuronApp()
    try:
        app.run()
    finally:
        app.close()


if __name__ == "__main__":
    main()
