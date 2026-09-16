# FoxAlien XE-PRO Jetson Recovery Console

Status: **SIMULATION VERIFIED / HARDWARE BLOCKED PENDING ELECTRICAL IDENTIFICATION**

This is a local, English-only Ubuntu control console for recovering a FoxAlien XE-PRO
after the original controller failed. The Jetson Nano runs the operator interface,
validates G-code, and streams GRBL commands over USB serial. It does **not** use
Jetson GPIO to generate motor pulses.

## Required architecture

```text
Jetson Nano
  local web console + G-code validation
          |
          | USB serial, GRBL v1.1, 115200 baud
          v
Third-party real-time motion controller
  limits / probe / STEP-DIR / spindle control
          |
          +--> closed-loop stepper drivers --> XE-PRO motors
          |
          +--> isolated spindle relay/controller --> 400 W spindle

Physical E-stop --> directly removes motion and spindle power
```

The official XE-PRO specification lists GRBL control, a 400 × 400 × 95 mm
working area, four closed-loop NEMA 23 motors, a 5000 mm/min maximum movement
speed, a 400 W spindle, and 1204 ball screws. That does **not** establish the
pinout or electrical requirements of the motors, encoders, spindle, limits, or
damaged board. Those must be identified before wiring.

## What works now

- Simulation transport with position, state, and job progress.
- GRBL v1.1 status parsing and 4 Hz status polling.
- Safe jog using `$J=G91 G21 ...`, capped at 10 mm and 1000 mm/min.
- Feed hold, resume, jog cancel, and guarded soft reset.
- Guarded homing, alarm unlock, and XYZ work-zero controls.
- Four built-in dry-motion examples: 1 mm axis check, 20 mm square, 30 mm
  diamond, and 40 x 20 mm gantry raster.
- Validated XY toolpath preview with path length and travel spans.
- G-code normalization and validation.
- Rejection of spindle/coolant commands, speed words, arcs, system commands,
  malformed lines, excessive feed, and jobs exceeding the configured envelope.
- One-line-at-a-time GRBL streaming with acknowledgement and error handling.
- Four mandatory operator acknowledgements before dry motion.
- Localhost-only server and no external JavaScript or font dependencies.
- Same-origin enforcement on all motion-changing HTTP requests.
- Local `/health` status endpoint.
- Ubuntu application-menu launcher.

## Explicit limits

- Spindle start is deliberately disabled, even if a configuration key is changed.
- Version 0.1 accepts linear `G0`/`G1` jobs only; `G2`/`G3` arcs are blocked.
- Software **Stop motion** sends GRBL feed hold. It is not an emergency stop.
- The offline envelope check verifies travel span, not fixture placement or work
  coordinate zero. The operator must still verify position and clearance.
- No wiring map is supplied until the replacement controller, motor-driver
  interfaces, spindle controller, and connector labels are identified.
- No unattended operation.

## Run on Windows or Jetson in simulation

Python 3.8 or newer is sufficient.

```powershell
cd D:\CLAUDE\foxalien-xe-pro-jetson-control
python -m foxalien_control.server --config config\machine.json
```

Open `http://127.0.0.1:8765`.

The server refuses non-loopback binding. For access from another computer, use
an authenticated SSH tunnel instead of exposing the motion API:

```bash
ssh -L 8765:127.0.0.1:8765 jetson-user@jetson-address
```

On Jetson:

```bash
cd /opt/foxalien-xe-pro-jetson-control
chmod +x scripts/install_jetson.sh
./scripts/install_jetson.sh
./scripts/launch_gui.sh
```

The installer creates **FoxAlien XE-PRO Console** in the Ubuntu application
menu. The launcher starts the localhost service when needed and opens Chromium
in app mode. Simulation is the default.

## Hardware activation sequence

Do not perform this sequence until [the wiring intake](docs/WIRING_INTAKE.md) and
[the acceptance checklist](docs/SAFETY_ACCEPTANCE.md) are complete.

1. Install and configure a dedicated GRBL v1.1-compatible motion controller.
2. Confirm its step/direction signal levels match the closed-loop drivers.
3. Wire and test a physical E-stop that removes motor and spindle power without
   relying on the Jetson, network, app, or controller firmware.
4. Disconnect or physically isolate spindle power.
5. Test one axis at a time at low current, 0.1 mm jog, and 100 mm/min.
6. Copy `config/machine.hardware.example.json` to a new hardware config.
7. Set the three physical safety booleans to `true` only after testing.
8. Start the process with the one-session enable phrase:

```bash
export FOXALIEN_HARDWARE_ENABLE=I_ACCEPT_PHYSICAL_RISK
python -m foxalien_control.server --config config/machine.hardware.json
```

Serial mode refuses to start unless all gates are present. Keep
`spindle_commands_enabled` false during commissioning.

## Test

```powershell
python -m unittest discover -s tests -v
```

## Sources

- [FoxAlien XE-PRO official product page](https://www.foxalien.com/products/cnc-router-machine-xe-pro?variant=43138100461705)
- [FoxAlien official manual and driver index](https://www.foxalien.com/blogs/news/foxalien-cnc-and-laser-machine-user-manual)
- [Official GRBL v1.1 interface](https://github.com/gnea/grbl/blob/master/doc/markdown/interface.md)
- [Official GRBL v1.1 commands](https://github.com/gnea/grbl/blob/master/doc/markdown/commands.md)
- [NVIDIA Jetson Nano 2GB developer kit guide](https://developer.nvidia.com/embedded/learn/jetson-nano-2gb-devkit-user-guide)
