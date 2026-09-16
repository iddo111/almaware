# Custom Glasses Frame — Reference-Driven Prototype

## Goal

Create a custom frame concept from supplied reference photos, a 3D scan/model if available, and the existing lens dimensions. The first output is a fit/appearance prototype, not a prescription-ready or safety-certified frame.

## Send these references

1. Front, left, right, top, and underside photos of the current glasses on a flat surface, with a ruler in frame.
2. Close photos of the hinge, bridge, lens groove/rim, temple ends, and any markings.
3. Lens measurements if known: lens width, lens height, bridge width, temple length, and lens edge thickness.
4. A straight-on face photo only if you want facial fit/aesthetic evaluation; do not include identity documents or private metadata.
5. Any 3D scan, photogrammetry model, STL/OBJ, or manufacturer drawing.
6. Desired changes: stronger, lighter, wider/narrower, different colour, nose comfort, cable routing, camera/LED mount, etc.

## Workflow

- Preserve the submitted reference as the baseline.
- Extract measured dimensions and list every inferred dimension as `UNKNOWN` until confirmed.
- Produce a reversible mock-up first: lensless or with dummy lenses.
- Use rounded edges and a conservative rim/bridge; validate temple pressure and nose contact before final material choice.
- Keep lenses, hinges, and any prescription geometry as separate interfaces; do not force-fit lenses into an unvalidated print.

## Material boundary

PLA is suitable only for visual fitting. PETG, ASA, nylon, or TPU inserts may be evaluated after a skin-contact, heat, flex, and hinge-cycle test. Printed frames may not meet optical, impact, allergy, or durability requirements for everyday prescription wear.

## Devil's advocate

Glasses are dimensional: a frame that looks right can pinch, slip, distort lenses, or fail at the hinge. Photo-derived scale is error-prone. The app must never decorate or redesign the frame without a separate, explicit change request.
