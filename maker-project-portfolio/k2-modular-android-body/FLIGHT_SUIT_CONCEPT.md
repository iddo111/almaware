# Valkyrie Flight Suit / Folding Personal Air Vehicle

## Status

`ACTIVE RESEARCH / SIMULATION-FIRST / HUMAN FLIGHT BLOCKED`

This document adds the user’s folding flight-suit idea to the canonical
exoskeleton-to-android project. It is a concept and verification roadmap, not a
claim that a wearable aircraft is feasible, safe, legal, or ready to build.

## User concept baseline

- The exoskeleton folds into a vehicle the wearer can carry as part of the
  body platform.
- Strong lift modules fold into the back, arms, and legs.
- Deployed modules turn the platform into a flying exoskeleton or personal air
  taxi intended to cross terrain and traffic.
- The same modular body may support snake, alligator, telescoping-locust,
  bird-like, climbing-monkey, rescue, and android configurations.
- In the rescue idea, the platform approaches from behind, supports a wounded
  person in a controlled embrace, secures limb-to-limb interfaces, and removes
  the person.

These are desired capabilities, not verified requirements or authorized
physical tests.

## Architectural rule

The wearer’s arms, legs, spine, and joints cannot be primary aircraft load
paths.

The aerial system must therefore be treated as a folding vehicle frame that
interfaces with the exoskeleton:

- A rigid back/pelvis/torso structure carries lift, landing, battery, and
  emergency loads.
- Fold-out pods remain mechanically locked and electrically isolated while
  stowed.
- Limb modules may change geometry or provide bounded control authority only
  after simulation and uncrewed testing qualify them.
- Rotating machinery needs physical guarding and an exclusion envelope in
  every reachable body configuration.
- Ground-exoskeleton control and flight control remain independent safety
  domains; one cannot silently activate the other.
- Loss of the exoskeleton controller must not cause deployment, thrust, or an
  unsafe transition.

## Transformation modes

1. **Safe/stowed** — all aerial energy isolated and every module mechanically
   locked.
2. **Ground exoskeleton** — validated ground mobility only; flight functions
   remain unavailable.
3. **Inert deployment** — folding geometry demonstrated without propulsive
   energy.
4. **Uncrewed aerial test article** — a rigid dummy frame exercises lift and
   control away from people.
5. **Folding vehicle** — the uncrewed article proves repeatable stow/deploy,
   landing, transport, and inspection.
6. **Rescue mockup** — ground-only weighted-dummy support and release; no
   powered lift.
7. **Crewed research** — blocked until all independent engineering,
   regulatory, medical, facility, and aviation approvals exist.

Every transition must be explicit, observable, reversible where physically
possible, and rejected when locks, sensors, controllers, or state estimates
disagree.

## Personal air-taxi boundary

“Get over traffic” is a mission idea, not an operating assumption. Urban
flight adds public-risk constraints that a successful hover test cannot answer:

- protected takeoff and landing areas;
- safe routes that avoid crowds, roads, buildings, wires, and rotor wash;
- weather and visibility limits;
- noise, privacy, insurance, licensing, maintenance, and airspace integration;
- a credible safe outcome after power, sensor, actuator, or communication
  loss;
- inspection and dispatch rules that prevent flight with a hidden folding,
  structural, battery, or control fault.

No public-road or public-airspace trial is part of this project.

## Rescue boundary

The rear-hug casualty concept begins as a ground-only evacuation harness on a
weighted medical dummy. It must not constrict breathing, neck, circulation, or
an injured limb, and it needs rapid release by both the operator and a helper.

Flight adds rotor strike, downwash, debris, noise, thermal, fall, and trauma
risks. Casualty flight remains blocked until a separately qualified evacuation
system, medical protocol, uncrewed mass-dummy program, and aviation acceptance
all pass. A stable hover with a dead weight would not prove safe patient
carriage.

## Verification ladder

### F0 — requirements and budgets

- Freeze mission profiles and separate ground, rescue, and aerial use cases.
- Produce mass, centre-of-mass, energy, thermal, structural-load, control, and
  safe-landing budgets with stated uncertainty.
- Define the worst credible single failures and required safe responses.
- Document applicable aviation, product, workplace, medical, and public-space
  constraints with qualified reviewers.

### F1 — digital twin

- Simulate folding kinematics, collision envelopes, structural loads, thermal
  behavior, control authority, sensor disagreement, and failure transitions.
- Reject any layout that can direct rotating machinery or deployment force
  into the wearer.
- Demonstrate a safe simulated outcome after each defined single failure.

### F2 — inert full-scale mockup

- Build only non-propulsive folding geometry.
- Verify locks, reachability, egress, pinch clearance, fit, inspection access,
  and emergency removal on a rigid dummy.
- Keep the wearer out of any structure that can trap or load the body.

### F3 — contained subscale vehicle

- Use an uncrewed, remotely isolated article in an appropriate contained test
  facility.
- Validate control and transition logic without copying the human-worn form
  into a live propulsive test.
- Stop after any unexplained motion, control disagreement, loss of telemetry,
  containment issue, or thermal event.

### F4 — uncrewed rigid full-scale article

- Requires independent structural, electrical, battery, controls, fire, and
  aviation review.
- Demonstrate repeatable inspection, stow/deploy, takeoff, controlled landing,
  abort, and worst-case failure handling away from people.
- Human carriage remains blocked even after F4 passes.

### F5 — crewed consideration

This is not an automatic next step. It requires a new authorization and a
qualified aviation program with approved facility, pilots/operators, medical
and rescue coverage, regulatory permission, and independently accepted
hardware. The current project supplies none of those approvals.

## Current authorized deliverables

- mission and requirement matrix;
- concept sketches and non-propulsive folding envelopes;
- digital-twin state machine;
- hazard log and fault tree;
- mass/energy/thermal budget templates;
- uncrewed test and evidence format;
- interfaces that keep the ground exoskeleton independent from the aerial
  branch.

## Hard exclusions

- No human-worn powered lift or powered rotor test.
- No free flight, outdoor flight, operation above roads/crowds, or public
  airspace.
- No motor, propeller, battery-pack, flight-controller, or wiring selection
  presented as safe for human carriage.
- No casualty lift, soldier extraction, or medical-use claim.
- No autonomous launch, pursuit, weapon, surveillance, or combat function.
- No bypass of aviation, workplace, medical, electrical, or site safety
  requirements.

## Devil’s advocate

A rotor on every limb sounds redundant but can multiply failure points,
deployment collisions, wiring faults, joint torque, debris exposure, control
coupling, and maintenance burden. Folding mechanisms reduce transport volume
while adding hidden structural and locking failures. A wearable shape also
places energy storage and rotating machinery beside the body, where a fault
has little separation.

The concept survives only if evidence shows that modularity improves fault
containment and safe landing more than it increases coupled failure. If the
safer result is a separable rigid vehicle rather than a wearable suit, the
architecture must follow the evidence.

## Kill criteria

Stop or redesign the aerial branch after any:

- uncontrolled deployment, thrust, or mode transition;
- rotating-hardware exposure inside a body or bystander envelope;
- structural crack, lock migration, unexpected flex, or load-path ambiguity;
- battery fault, thermal runaway precursor, smoke, or fire;
- controller disagreement without immediate safe isolation;
- simulated or physical failure without a credible controlled-landing outcome;
- trapped-wearer, blocked egress, circulation, breathing, neck, or joint risk;
- need to overfly people, roads, or buildings to make the mission practical;
- regulatory or qualified-review finding that invalidates the operating
  concept.

Preserve evidence after a stop. Do not retry by increasing thrust, energy,
speed, authority, or scale.
