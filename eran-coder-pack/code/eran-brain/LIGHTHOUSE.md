# 🔦 ALMA-LIGHTHOUSE — Eran's body sense, built from four Vive base stations
> 🪟 **BROKEN WINDOWS LAW:** if it's not working, fix it IMMEDIATELY. Test the REAL output — a pose stream you can plot — never a proxy.

**Iddo's idea, 2026-08-21 17:15:** *"לחבר את הקונטרולרים של הוייב לידיים... יש לי ארבע לייטהאוזס של וייב... זה אינפרא-אדום עם בלוטות'."*

He is right on the physics, and the consequence is bigger than VR.

## The insight

A Vive base station is not a display accessory. It is a **room-scale optical metrology system**: two orthogonal infrared laser planes sweeping at 60 Hz plus a sync flash, and Bluetooth only for management (channel, power, sleep). Anything carrying photodiodes computes its own 6-DoF pose from the sweep timings. Sub-millimetre position, sub-degree rotation, ~250 Hz, no cameras, no markers to occlude, no drift.

**So: the lighthouses are a SENSOR, not a screen.** That single reframe removes every blocker we hit earlier today:

| The VR blocker | Why it disappears |
|---|---|
| SteamVR is x86-only, eran1 is aarch64 | **libsurvive** is an open-source lighthouse tracker in C — no Steam, no proprietary runtime, builds with cmake on ARM64 Linux |
| eran1 has no display outputs | Irrelevant. Tracking needs USB and math, not a monitor |
| A headset is needed | No. Trackers/controllers each carry photodiodes; the headset is just another tracked object |

## Why this matters for Eran

His standing law is **"no body ships open-loop"** — every joint reports angle, velocity, load. Encoders on every joint are expensive and fiddly. Four lighthouses give **absolute pose of every tracked segment, in one room frame, for free** — the ground truth that every cheap servo lacks.

Three uses, in order of how soon they pay:

1. **Demonstration (this week's cheap win).** A controller strapped to Iddo's hand writes a real motion trajectory: reaching, drawing a letter, waving. That is a *teacher signal* for a motor cortex, recorded from a human body, not simulated. Imitation learning with real data.
2. **Proprioception for the first real body.** A tracker on the toy car, later on each limb of the arm/Golem: the robot learns the mapping from what it commands to where it actually ends up — the closed feedback loop, with truth.
3. **The room becomes the world frame.** The apartment lab, the letter board, the printer, the car: all in one coordinate system that both the simulator and the real body share. That is what makes sim-to-real honest instead of hopeful.

**Four base stations is not a spare — it is a full room with no occlusion shadows** (2 is the normal setup; 4 covers a large volume and survives a body blocking a sweep).

## The build

**Host: eran1.** It is where Eran lives, it is Linux, and it needs the data. No display required. The PC stays free.

### Phase 0 — inventory (blocked on Iddo, 2 minutes)
Nothing Vive is connected to this PC right now (checked 17:15: no Vive/Valve/Watchman USB devices, no Steam, no SteamVR). Needed to proceed:
- the 4 base stations (version 1.0 or 2.0 — 1.0 have a channel switch b/c/A, 2.0 are set over Bluetooth)
- at least one **tracked object**: a controller, or better a **Vive Tracker** (the puck — made exactly for strapping to a limb or an object)
- at least one **USB radio dongle** per tracked object (without a headset there is no radio hub; each puck needs its dongle)

### Phase 1 — the pose stream (half a day once hardware is in)
- Build `libsurvive` on eran1 (cmake, C, ARM64-clean), calibrate the room once, verify it holds a static point to <1 mm over a minute.
- `body/lighthouse.py` — read poses, publish them on the **same ALMA contract Eran's senses already use** (knot/thread/strand/spark/beat), one stream per tracked object.
- Acceptance: `results/LIGHTHOUSE-001.json` with measured static jitter, tracked volume, dropout rate, and a plotted trajectory of one hand wave.

### Phase 2 — the teacher (days)
- `record_demo.py`: Iddo moves, the room records; each demonstration is stored as an ALMA motion strand with provenance.
- First lesson: draw **א** in the air. It is the letter board, the handwriting cortex, and the motor cortex in one gesture.
- Acceptance: the model, given the start pose, predicts the rest of the trajectory better than a straight-line baseline. Numbers in a file.

### Phase 3 — the body closes the loop (with the CNC car)
- A puck on the car. Command → measured pose → error → learning. The consequence *is* the label (Iddo's "לימוד מעוגן חוויה").

## Honest limits
- **libsurvive is not SteamVR.** It is good, it is used in research, and it will need a calibration afternoon. Budget frustration.
- Base station 2.0 firmware over Bluetooth is documented but fussy; 1.0 with the channel switch is easier.
- A controller strapped to a hand tracks the *controller*, not the wrist joint — the offset must be measured once, not guessed.
- This does not need, and should not wait for, a headset. If a headset ever renders anything, it renders on the PC.

## What is NOT the plan
Not a VR game. Not SteamVR. Not a headset on a DGX. The lighthouses join this project as **Eran's sense of where his body is** — and, first, as the way his father can show him how to move.
