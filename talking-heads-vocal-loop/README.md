# Talking Heads Vocal Loop

Status: `CONCEPT / NEW PROJECT`

An experimental farm of physically isolated robotic talking heads. Each head
learns to control its own airflow, artificial glottis, and vocal tract by
listening to itself through a microphone. Heads train independently, while a
shared validation layer distributes only improvements that reproduce safely.

This project is separate from Hebrew Ant Farm. Ant Farm learns acoustic units
and meaning from recorded voice; Talking Heads learns physical vocal production.
They may interface later through a versioned audio contract.

## First objective

Build one low-pressure head that can repeatedly produce a stable open vowel
similar to `/a/` ("ah"), measure it, and improve it through a bounded closed
feedback loop.

Acceptance requires physical microphone recordings, actuator telemetry, changed
controller parameters, and improvement on held-out target recordings. Synthetic
audio or a loudspeaker is not acceptance.

## Scale direction

1. One instrumented head in one acoustic chamber.
2. Three heads with intentionally different membranes and vocal tracts.
3. Ten or more isolated heads learning concurrently.
4. A Queen validator and Tribal Fireplace knowledge exchange.

See [ARCHITECTURE.md](ARCHITECTURE.md) and [SAFETY.md](SAFETY.md).
