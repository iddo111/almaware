# PicoBricks LDR sensory neuron

This is a real board program plus a deterministic host model for a
light-sensitive leaky integrate-and-fire (LIF) neuron. It is deliberately a new,
isolated package: it does not change the existing Arduino neuron builds.

## What is verified, and what is not

The official PicoBricks Raspberry Pi Pico/Pico W examples confirm this pin map:

| Function | GPIO | Used here |
|---|---:|---|
| LDR analog input | GP27 / ADC1 | yes |
| piezo buzzer | GP20 / PWM | yes |
| addressable RGB LED | GP6 | optional |
| servo headers | GP21 and GP22 | optional, GP22 selected |
| OLED I2C0 SDA/SCL | GP4 / GP5 | optional |

Official references:

- https://picobricks.com/blogs/robotic-stem-projects/two-axis-robot-arm
- https://docs.picobricks.com/tr/latest/projeler/night%20and%20day.html
- https://github.com/Robotistan/PicoBricks-for-RPico

The code uses **GP22 for the servo**. On RP2040, GP20 and GP21 are the two
channels of the same PWM slice, so GP21 cannot reliably run a 50 Hz servo while
GP20 generates an 880 Hz tone. GP22 is on a separate slice.

The software and pin mapping are source-checked and host-tested. They have **not
been flashed to or electrically verified on the attached kit**. Confirm the
actual product is the Raspberry Pi Pico/Pico W PicoBricks board, not the
different micro:bit product, and check the silk labels before any later upload.

## Neuron behavior

`lif_core.py` contains both hardware-independent stages:

1. `AdaptiveLDR` maps the 16-bit ADC value to a bounded `0..1` positive contrast
   against a slowly adapting ambient baseline. Set `LDR_ACTIVE_HIGH = False` in
   `main.py` if this physical board's ADC falls as light rises.
2. `LeakyIntegrateAndFire` applies exact exponential membrane leak, integrates
   the normalized input, fires at threshold, resets the membrane, enforces a
   120 ms refractory period, and raises a decaying adaptive threshold after a
   spike.

For compatibility with the package's first deterministic test harness,
`lif_core.py` also exports `normalize_ldr(...)` and a millisecond-based
`LIFNeuron`. The wrapper uses the same exponential-leak implementation with
legacy property names and adaptation disabled; new device code uses
`AdaptiveLDR` and `LeakyIntegrateAndFire` directly.

Each spike starts a short low-duty piezo tone. RGB represents input/membrane
state, and the OLED shows readings and rate. The optional servo makes only a
bounded 90 to 105 degree twitch and slews one degree every 20 ms. Servo output is
disabled by default until it can be tested with the horn and linkage removed.

`main.py` contains no long `sleep` or `delay` calls. Sensor, sound, servo, RGB,
OLED, and serial reporting are independent timestamped state machines. The only
sleep is a 1 ms cooperative idle yield. A two-second nonblocking ambient
calibration suppresses startup spikes.

## Host verification (safe; does not touch USB or hardware)

From this directory, with the Python already installed on the PC:

```powershell
python -m py_compile lif_core.py main.py simulate.py tests\test_lif_core.py
python -m unittest discover -s tests -v
python simulate.py
```

The tests require only Python's standard library. They verify polarity and
bounded normalization, slow baseline adaptation, no subthreshold firing,
stronger-input rate response, refractory spacing, spike-frequency adaptation,
safe handling of long loop gaps, determinism, and the ambient/bright/recovery
scenario.

## Later board bring-up acceptance criteria

Do these only after explicit permission to write the Pico:

1. With `ENABLE_SERVO = False`, keep normal room light steady during the two
   second calibration. Serial `stim` remains in `0..1` and there are no ambient
   spikes during a five-second quiet check.
2. A flashlight increase produces `stim > 0`, several audible/visible spikes,
   and no two spike timestamps closer than 120 ms. Removing the flashlight
   makes spiking stop as the membrane leaks down.
3. OLED and RGB continue updating while sound pulses occur; no output freezes
   LDR sampling for more than one 10 ms control interval.
4. Only with the servo horn/linkage removed, set `ENABLE_SERVO = True`. Confirm
   the signal is on GP22 and motion stays between 75 and 105 degrees. Then power
   down before attaching any mechanism and establish mechanism-specific limits.
5. A servo should use an adequately rated supply with a common ground; do not
   infer power safety from a successful software test.
