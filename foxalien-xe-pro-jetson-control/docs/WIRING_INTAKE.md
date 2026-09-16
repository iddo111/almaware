# Wiring intake — required before hardware mode

Status: **BLOCKED**

The failed original board does not make the surviving connectors self-describing.
Do not guess a pinout and do not continuity-test energized equipment.

## First response

1. Disconnect AC/mains power.
2. Unplug the spindle/router power source.
3. Disconnect the motor power supply.
4. Photograph before removing any remaining wire.
5. Label every cable at both ends.
6. Do not connect a motor, encoder, limit switch, or spindle wire to Jetson GPIO.

## Evidence to collect

Take sharp, well-lit photographs with labels readable:

- Damaged board: front, back, every connector, part numbers, and burn location.
- Power-supply labels: input/output voltage, current, polarity, and connector.
- Each of the four motor labels and every motor/encoder connector.
- Any separate closed-loop driver: front, terminals, DIP switches, and label.
- 400 W spindle motor label and spindle controller/relay label.
- X, Y, and Z limit switches and connector labels.
- Probe, E-stop, offline-controller, and USB connectors.
- A wide photograph showing cable routing before disassembly.

Record:

| Item | Required value |
|---|---|
| Replacement controller make/model | Unknown |
| Firmware and version | Must be GRBL v1.1-compatible for this app |
| Logic output level | Unknown; must match driver inputs |
| Motor driver make/model | Unknown |
| Motor phase voltage/current | Unknown |
| Encoder voltage/interface | Unknown |
| Limit switch type and voltage | Unknown |
| Spindle supply voltage/current | Unknown |
| Spindle control input | Unknown |
| E-stop contact rating | Unknown |

## Controller requirements

The replacement controller must provide:

- A real-time motion processor; Jetson Linux is not the step generator.
- USB serial GRBL v1.1 at 115200 baud.
- At least X, Y, Z, and a duplicated/slaved axis if the machine wiring requires it.
- STEP/DIR/ENABLE outputs electrically compatible with the closed-loop drivers.
- Inputs for all homing/limit switches and probe.
- Hardware soft limits and homing support.
- An isolated spindle enable/speed interface rated for the actual spindle
  controller, not the motor load itself.
- A documented E-stop chain that removes hazardous power.

## Stop criteria

Stop and do not energize if any connector pin, voltage, current rating, common
reference, motor phase, encoder interface, or spindle interface is unknown.
