# HANDOUT — Perplexity: "Building the Talking Head" — the DIY build film

Assigned by Iddo 2026-08-09. Owner: **Perplexity** (research + shot-ready references).
Output lands in `D:\CLAUDE\eran-movie\`. Coordinate via RAMCHAT (post as perplexity).
This is a SEPARATE deliverable from the 15-min Eran movie — a focused **build film**:
how Iddo physically builds the Talking Head (הראש המדבר) with his own hands, DIY,
part by part — molds, casting, folds, assembly — **with audio and video**.

## HONESTY LAW (unbreakable)

The Talking Head is **PLANNED — nothing is built yet**. Spec:
`D:\CLAUDE\voice-ant-farm\docs\TALKING_HEAD_ANT_ARCHITECTURE.md`.
The film is a **build guide** — "here is how it gets built" — not "here is what we built".
Every visual must be labeled: reference footage = cite the source on screen;
renders/animations = labeled as renders. No fake milestones, no fake workshop shots
pretending to be ours. When Iddo actually builds, real footage replaces references.

## What the machine is (60-second version for your research focus)

A low-pressure, low-voltage bench instrument that makes a real "AH" the way a human
throat does — NOT a speaker playing a file:

1. **Breath** — quiet variable-speed blower → compliant plenum (air reservoir),
   pressure + flow sensors, mechanical relief valve. Human analog: lungs.
2. **Phonation valve (the folds)** — two symmetric thin **silicone membranes** with a
   small repeatable pre-gap, tension + adduction adjustable. Airflow makes them
   **self-oscillate** (hundreds of Hz). The actuator only sets tension — like tuning
   a guitar, not strumming it. Human analog: vocal folds.
3. **Vocal tract** — modular pharynx/oral tube, open jaw, lip aperture, movable
   tongue/formant insert. Resonances turn the buzz into a vowel. Human analog: throat+mouth.

Safety envelope (must appear in the film): low pressure only, no compressor, no gas
canister, MCU-owned hard limits, **never connected to a person**.

Available tools on site: Creality **K2 Plus** 3D printer (molds + rigid parts),
Arduino/ESP32-class MCUs, standard maker bench. Iddo is in Israel — prefer materials
he can actually buy (local or AliExpress/Amazon-to-IL).

## Your research tasks (the meat)

For EACH item: find 2-3 authoritative sources AND at least one good **video** reference
(YouTube/Vimeo/paper supplementary). Prefer footage we may legally excerpt or imitate;
note the license.

1. **Synthetic vocal folds — the science.** Physical vocal-fold models in speech
   research: Titze/Thomson-style silicone folds (the "M5" geometry family), self-
   oscillating membrane models, syrinx/larynx robots (e.g., Waseda talking robots,
   Osaka anthropomorphic vocal tracts). What geometry and Shore hardness do labs use?
   What subglottal pressure starts phonation (typical ~0.5–2 kPa)?
2. **Mold-making from a 3D print.** Two-part mold design for casting silicone:
   print settings for smooth mold cavities, sealing/vapor-smoothing PLA/PETG molds,
   draft angles, keys/registration, pour spouts and vents. Video of a full
   print-mold → cast → demold cycle.
3. **Silicone casting for thin membranes.** Ecoflex 00-30 vs Dragon Skin 10 vs
   cheaper RTV-2: which for 1–3 mm fold membranes? Mixing, degassing without a vacuum
   chamber (and with a cheap one), cure times, release agents, layering thickness
   control. Failure modes: bubbles, tears, uneven thickness.
4. **The fold cartridge.** How labs mount fold pairs so tension and pre-gap are
   repeatable: clamping frames, adjustable medial gap, symmetric left/right coupling.
   What DIY hardware replicates it (printed frame + screws + springs)?
5. **Quiet air source.** Blower choice: centrifugal 5–12 V PWM blowers vs aquarium
   pumps vs CPAP blowers (used CPAP = excellent quiet pressure source — verify safety
   and availability). Plenum design to remove pulsation; intake silencing.
6. **Tract + tongue.** Printable vocal-tract geometries (MRI-derived vowel tracts are
   published); simplest adjustable one-tube tract with a sliding constriction that
   sweeps F1/F2 believably. Existing printable STL projects if any.
7. **Sensing + first calibration.** Cheap differential pressure sensors (MPXV series),
   flow estimation, and the "AH ladder": leak check → static pressure → first
   self-oscillation → pitch control via tension → vowel shaping. What does each stage
   sound like (find audio/video of lab models phonating)?
8. **Film craft.** Best-practice references for build-documentary filming: macro shots
   of casting, time-lapse of curing, before/after audio A/B. How top makers
   (Stuff Made Here / Wintergatan-style) structure a build episode so it lands.

## Deliverable back from you (files, not chat)

Write into `D:\CLAUDE\eran-movie\`:

1. **`RESEARCH-talking-head-build.md`** — findings per task above, each claim with
   source link + license note for any footage we'd excerpt.
2. **`SHOTLIST-talking-head-build.md`** — scene-by-scene for a 6–10 min build film:
   - scene goal (e.g., "cast the folds"),
   - visual (reference clip link OR render prompt, labeled which),
   - narration line (Hebrew primary, English subtitle),
   - real audio to capture when the build happens (blower hiss, first buzz, first AH),
   - music cue (Darwish psytrance score exists; mark intensity 1–5).
3. **`BOM-talking-head.md`** — full parts list with quantities, est. prices,
   IL-available links. Group by block (breath / folds / tract / sensing / safety).
   Flag the 3 items with longest shipping first.

Definition of done: all three files exist, every scene has at least one concrete
visual reference or labeled render prompt, every BOM line has a live link, and a
RAMCHAT post announces completion. Audio+video = the film must specify BOTH tracks
for every scene (what we see, what we hear).

— claude-cli-FABLE, on Iddo's direct order.
