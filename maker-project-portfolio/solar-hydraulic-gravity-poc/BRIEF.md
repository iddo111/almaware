# Terrace Solar-Hydraulic Gravity Battery — Miniature POC

## Goal

Demonstrate the complete energy chain: solar input -> controlled pump/lift -> mechanically latched mass -> controlled descent -> electrical measurement.

## Safe scale boundary

Start with a fully enclosed **1 kg or lower** mass and a low lift height. Do not use a one-ton mass, an overhead load, an unguarded pulley, or an unreviewed terrace anchor. Nobody may stand beneath, beside, or within the path of the moving mass.

## Architecture

```text
small solar panel -> charge controller / energy meter -> low-pressure pump
  -> contained hydraulic cylinder -> mechanical latch -> guarded mass carriage
  -> controlled descent -> small generator -> load + measurement
```

The latch—not hydraulic pressure—holds stored energy. The system must fail to a mechanically safe, non-dropping state on power loss.

## What to measure

- Solar energy consumed during lift.
- Potential energy stored: `m × g × height`.
- Electrical energy recovered on descent.
- Round-trip efficiency and leakage/self-discharge over time.

## Devil's advocate

At terrace scale the stored energy is tiny: 1 kg lifted 2 m stores only about 20 J (about 0.005 Wh) before losses. This is a learning demonstrator, not practical household storage. Hydraulics add leaks, seals, pressure hazards, and maintenance; a guided winch or lead-screw version may be safer for the first experiment.

## Stop conditions

Any leakage, uncontrolled movement, carriage binding, cracking, temperature rise, electrical fault, or uncertainty about the balcony/terrace structure stops the project pending qualified review.
