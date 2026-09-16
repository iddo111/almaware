# 🪟 Broken Windows Law — if it's not working, fix it NOW.

# TAPE-BRAIN — a mechanical neural computer whose weights are a punched film
**ALMAWARE · spec born 2026-08-19 01:07, from Iddo's line: "הסרט הוא עצמו שבלונה עם חורים שמכיל משקלים"**

## 0. The one sentence
**The trained model is a roll of punched film.** Water flows through the holes; how many holes
are open under each port *is* the weight. Swap the tape → swap the model. Nothing is stored
electronically, anywhere.

## 1. Why holes are COUNTED, never SIZED  (the key engineering call)
A weight set by one hole's diameter inherits the laser's kerf error: at d=0.3 mm that is **±33 %**
of the flow area, and if the channel is laminar (flow ∝ d⁴) it is far worse. So: every hole on the
tape is **identical (⌀0.6 mm, 2 mm pitch)**, and the weight is **how many of them are open** —
a patch of up to 16 holes per synapse (8×2, 16×4 mm). Counting is exact; the residual size error
averages down as 1/√N → **~4 %**. This is a Jacquard card, not an analog aperture.

- signed weights: the patch is split — top row → the neuron's **inlet** (excitatory),
  bottom row → its **drain** (inhibitory). w = (open_top − open_bottom)/16.
- resolution 4 bits ≈ 1/16. Enough: a chess eval net quantised to 4 bits still plays.

## 2. Measured sizes (computed, not guessed)
| model | synapses | tape (200 mm wide) | holes to cut |
|---|---|---|---|
| XOR 2-2-1 | 9 | 5 cm | 144 |
| tic-tac-toe 18-12-9 | 324 | **10 cm** | 5,184 |
| chess "intuition" 768-16-1 | 12,304 | **3.9 m** | 196,864 |
| chess 768-64-1 | 49,216 | 15.7 m | 787,456 |
**A chess brain is a four-metre roll of film.** Cut on the FoxAlien laser head; mylar/PET 0.15 mm.

## 3. Flow physics — why it sums linearly
Summation must be linear, so every channel is **laminar** (Hagen–Poiseuille, Q ∝ ΔP/R), never a
sharp orifice (Q ∝ √ΔP). Checked: ⌀0.6 mm at 0.05 m/s → **Re = 30**; ⌀2 mm at 0.2 m/s → Re = 400.
Comfortably laminar. Water viscosity drifts ~2 %/°C, but it scales **every** synapse equally, so the
weight *ratios* — the only thing a weighted sum cares about — are temperature-invariant.

## 4. Architecture: constant-head layers (this is what makes it cascade)
Water is **not** passed from layer to layer. Each layer has its own **constant-head supply tank**
(overflow-regulated, one pump per layer, MONIAC-style). A neuron's tank level lifts a **float**;
the float rod opens a valve on the **next layer's** supply. That gives:
- **gain ≥ 1** (a weak level can gate a strong flow) → signals don't decay down the depth,
- isolation between layers, and
- one pump per layer instead of one per neuron.

## 5. The neuron (already printed: `water_neuron.stl`)
inlets high → chamber = Σ → **spout at height θ = threshold (ReLU)** → drain at the floor = decay.
Two upgrades available:
- **carved cam** on the float rod = any activation you like — a **sigmoid is a filed curve**
  (exactly Phillips's cut perspex plates, 1949);
- **siphon instead of a spout** = all-or-nothing discharge that empties the tank = a real
  **integrate-and-fire spiking neuron**.

## 6. Tunable weights — three routes, ranked
1. **The tape (non-volatile, whole model at once).** Sliding the tape by one pitch shifts every
   patch → a **global gain knob** for a whole layer with a single actuator. Load time: seconds.
2. **CNC as the weight-loader (continuous, re-tunable).** Screw-type needle valve per synapse with
   a hex socket on top; the FoxAlien carries a hex bit; **the G-code IS the weight matrix**.
   Measured budget: 3 s/valve → 324 valves = **16 min**, 12,304 valves = **10.2 h** for a full load.
   This also enables real **in-situ training**: run forward → measure error → CNC re-tweaks the
   worst valves → repeat. Physical SGD.
3. **~30 servos, not 12,000.** Servos are wasted on individual synapses; put them where they buy
   the most: per-layer gain, per-neuron threshold (raise/lower the spout collar), and the tape feed.

## 7. Learning that is itself physical (the dream, honest status: unproven)
- **Erosion-Hebbian:** channels cut through a soft medium (wax, gypsum, packed sand). More flow →
  wider channel → more flow. That is Hebb's rule written in hydraulics, and it is how river networks
  and slime moulds already compute. Reset by re-casting the medium.
- **Deposition (anti-Hebbian):** saturated brine or gypsum narrows a channel with use = habituation.
- Both need an experiment before any claim: measure Δwidth vs litres passed.

## 8. Build ladder (WIP=1)
1. **XOR, 9 valves, one afternoon** — proves summation + threshold + a second layer.
2. **Tic-tac-toe, 324 synapses, 10 cm of tape, ~2 m² of wall** — plays perfectly, and the tape
   swap is demonstrable in front of a person.
3. Only then chess: 785 neurons, 3.9 m of tape, ~1 minute per move.

## 9. What it is FOR (say this honestly)
It will never beat silicon: one operation ≈ 0.7 s, ~10⁹× slower. Its value is that the model is a
**visible, holdable, mailable object** — a brain you can watch think, and hand to someone.
Related: [[project_physical_weights_ai]] · [[project_water_computer]] · [[project_shisha_brain]] ·
[[project_alma_memorial_street_corner]].
