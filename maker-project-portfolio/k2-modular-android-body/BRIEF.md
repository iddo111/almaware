# Modular Exoskeleton to Android Body

## Intent

Build one modular embodiment platform that begins as a human-worn exoskeleton
and later becomes the physical basis of the android robot.

The wearer provides demonstrations of movement and real-world interaction while
the platform records synchronized joint, load, balance, vision, audio, and
control data. Those demonstrations may support imitation learning and shared
control; they do not by themselves prove that the robot can move or act
autonomously.

## Modular progression

### Stage 0 — non-human test rig

Establish the load-bearing skeleton, module interfaces, joint axes, hard stops,
quick release, sensors, control limits, and emergency stop on a bench rig or
weighted dummy. Printed shells are covers, not primary human-load structures.

### Stage 1 — waist to below the knees

Build the pelvis/waist, hip, thigh, knee, and short upper-shin modules. The
acceptance target is aligned, bounded motion on the non-human rig. A worn test
is a later safety-gated milestone, not the first experiment.

### Stage 2 — full lower body

Extend the same interfaces through the shins, ankles, and feet. Validate
standing and gait mechanics first with overhead fall protection and a
non-human load. Do not use unbounded powered walking around people.

### Stage 3 — full-body exoskeleton

Add torso, shoulders, arms, hands, head/sensor carrier, and whole-body control
without replacing the validated lower-body interfaces.

### Stage 4 — independent android

Transfer the modular structure, sensors, control policy, and validated
demonstration data to the robot configuration. Independent movement is a new
acceptance program; it is not assumed from successful worn operation.

## Optional aerial branch — Valkyrie Flight Suit

Add a separately gated folding flight module that can transform the full-body
platform into a compact personal aerial vehicle. The concept baseline places
folding lift modules across the back and limbs, but the wearer’s joints must
not become aircraft load paths. A credible design would route primary lift and
landing loads through a rigid back, pelvis, and torso flight frame; limb
modules remain stowed, guarded, and structurally isolated unless analysis and
uncrewed testing qualify a specific function.

This branch does not replace the ground roadmap and is not part of the current
authorized build. It begins with mass/energy/control simulation, an inert
folding mockup, and uncrewed test articles. Human lift, free flight, outdoor
operation, traffic overflight, casualty carriage, and public-airspace use are
blocked pending a separate aviation-grade acceptance and regulatory program.

See `FLIGHT_SUIT_CONCEPT.md` for the concept, transformation modes, rescue
boundary, test ladder, and kill criteria.

## Embodiment-learning purpose

- Learn human joint timing, balance corrections, contact transitions, and
  task motion from synchronized demonstrations.
- Associate speech and environmental context with the motion and interaction
  occurring at that time.
- Progress from recording, to advisory/shared control, to bounded robot trials.
- Keep every autonomous capability behind a separate deterministic test and
  physical safety gate.

## Fabrication boundary

Design modules around the K2 Plus 350 mm print envelope. Split larger parts at
intentional structural seams with locating features and serviceable fasteners.
Use printed parts for geometry, housings, fit checks, and sacrificial elements
unless testing qualifies a specific part for a defined load.

## Immediate triage

1. Freeze the Stage 1 body dimensions and joint-axis locations.
2. Define the mechanical interface shared by every later leg module.
3. Build one unpowered hip-to-below-knee bench leg with angle sensing and hard
   stops.
4. Measure alignment, range, backlash, binding, fastener retention, and
   emergency-release time.
5. Advance only after the recorded Stage 1 acceptance gate passes.

## Exclusions

No autonomous humanoid operation, human lifting, untethered powered walking,
walking near other people, high-torque actuation, powered lift, propulsive
rotor testing, or human flight in the first build.

## Devil's advocate

A wearable robot can injure the wearer through joint misalignment, pinch
points, runaway motion, falls, heat, or a failed release even at modest power.
Do not let an attractive shell or a successful single motion stand in for load,
fault, and repeatability evidence.

## Stop conditions

Stop immediately after unexpected motion, joint-axis migration, structural
cracking, binding, excessive backlash, a failed hard stop or release, sensor
disagreement, overheating, loss of control, or any pain or pressure on a
wearer. Preserve the logs and failed part; do not retry by increasing power.
