# Cave Wall Brain — Simulator

Control-software half of `project_cave_wall_brain`: a live neural net whose
synaptic weights are shown as LED color/brightness on a physical wall
(the role Zack Akil's RGB Neural Net plays: Pi → WiFi → Arduino → LEDs).

Pure-Python stdlib, zero deps.

- `python cave_wall_brain.py` — live 24-bit ANSI animation of a net training XOR;
  amber = excitatory (+), cyan = inhibitory (−), brightness = |weight|.
- `python cave_wall_brain.py --html` — also writes `wall.html`, a Steampunk-Ada
  snapshot of the LED wall.
- Prints the JSON **broadcast packet** each frame would push to the Arduino LED
  driver (`{id, w, rgb}` per synapse) — the exact hardware handoff.

Verified: converges to loss ≈ 0.001, XOR solved, `wall.html` renders.
