# Hardware commissioning acceptance

All items require observed evidence. A checked software box is not evidence.

## Power-off inspection

- [ ] Original board and all machine power are disconnected.
- [ ] No damaged insulation, loose strands, carbonized board material, or
      conductive debris remains.
- [ ] Protective earth continuity is verified by a competent person.
- [ ] Motor, encoder, limit, probe, and spindle conductors are identified.
- [ ] Replacement controller and driver manuals match the exact models installed.

## Independent protection

- [ ] Physical E-stop removes motor power.
- [ ] Physical E-stop removes spindle power.
- [ ] E-stop works when Jetson is frozen or disconnected.
- [ ] E-stop contacts and contactor are rated for the actual loads.
- [ ] Spindle remains physically unplugged during motion commissioning.

## Controller configuration

- [ ] Correct motor current and microstep settings are documented.
- [ ] Axis direction is verified one axis at a time.
- [ ] Limit inputs change state correctly before homing.
- [ ] Homing direction and pull-off distance are verified.
- [ ] GRBL hard limits are enabled and tested at low speed.
- [ ] GRBL soft limits match the measured usable envelope.
- [ ] Power interruption does not unexpectedly start motion or spindle.

## Staged acceptance

1. Controller powered with drivers and spindle disconnected.
2. USB serial identity and GRBL version captured.
3. Limit switches verified by status reports.
4. One driver and motor connected at low current.
5. 0.1 mm jog at 100 mm/min in both directions.
6. Repeat independently for every axis.
7. Low-speed homing with one hand at the physical E-stop.
8. Air-cut a validated linear test job with spindle physically disconnected.
9. Only then design and verify the isolated spindle-control circuit.

## Application acceptance

- [ ] Simulation tests pass.
- [ ] Hardware mode refuses to start without its enable phrase.
- [ ] Disconnecting USB changes the UI to disconnected/error state.
- [ ] Feed hold stops planned motion.
- [ ] Physical E-stop stops motion independently.
- [ ] G-code containing `M3`, `M4`, `M7`, `M8`, or `S` is rejected.
- [ ] Out-of-envelope test program is rejected.
