# Sunflower Neuron v2 — the weight learns itself, no computer

**A single artificial neuron whose *weight is a piece of matter that changes its own value*
from the signals passing through it.** No microcontroller computes the update. The learning
happens in the analog domain — in copper plated on graphite, or in a silver filament in Ag₂S.
100% ours, built on the bench.

> **Iddo's rule (the whole point):** the weight itself must physically change from the signals
> through it. An MCU may present inputs, blink LEDs, and log — but it must **NEVER** compute the
> weight update. If a CPU calculates `Δw`, this is a digital neuron in disguise. v2 is not that.

---

## v1 → v2: what changed

- **v1 (`sunflower-neuron`, Arduino):** honest and educational, but the delta-rule math ran in
  *software*. The weight was a number in RAM. **The learning was digital.**
- **v2 (this project):** the weight is a **material state** — copper film thickness (conductance)
  or a silver filament — and it **updates itself** by physics. Error becomes a *plating current*;
  plating *integrates* into copper; copper *is* the memory that lowers the error. **The learning
  is in the metal.**

This is the real thing Bernard Widrow was chasing in 1960 with his electroplating **"memistor,"**
and the same physics behind modern two-terminal **memristor** synapses doing Hebbian/STDP.

---

## Two paths (see [`BUILD.md`](BUILD.md))

| Path | Weight is… | Learns by… | Teacher? | Difficulty |
|------|-----------|-----------|----------|------------|
| **A — Memistor + analog delta rule** *(recommended)* | copper on graphite | error → plating current (Widrow–Hoff LMS) | yes (you wire in a target) | medium |
| **B — Ag₂S Hebbian synapse** *(purist upgrade)* | silver filament | overlapping pre/post spikes (STDP) | **no** | high |

**Start with A.** It's forgiving, the copper film is big and visible, and the error loop is all
op-amps. **B** is the truly-teacher-free "fire together, wire together" trophy — and it's finicky.

---

## Files

| File | What it is |
|------|-----------|
| [`PRINCIPLE.md`](PRINCIPLE.md) | *Why* in-materia learning works. Widrow's memistor (Faraday's law → conductance = ∫current), the memristor Hebbian/STDP gate, signed weights, where the MCU is allowed to live, and honest physics limits. |
| [`BUILD.md`](BUILD.md) | The bench guide: ASCII schematics, how the weight self-updates, full BOM (Iddo's parts), the **staged build**, safety, and honest caveats. |

---

## The staged path (honest, de-risked)

- **Stage 0 — prove the physics (n=1).** ONE memistor weight that **visibly self-adjusts** to a
  target under an error current, then **holds with the power off.** No neuron, no loop yet — just
  proof that copper can teach itself a number. *(Path B variant: show STP-decay vs. LTP-hold with
  pulse repetition — learning with no teacher.)*
- **Stage 1 — a 2–3 input neuron that self-learns a target.** Signed memistor weights, a summing
  wire (Kirchhoff adds for free), a threshold, and an **analog error-feedback loop** that trains
  all weights at once (analog ADALINE). Train it on **AND/OR** or a simple regression. Note where
  an optional MCU may sit — **I/O ONLY, never learning** — and the **unplug-the-MCU litmus test**
  that proves it.
- **Stage 2 (stretch).** 3rd input, analog regression; XOR needs multiple units (MADALINE).

---

## The honest bargain

This is **harder, finickier, and slower** than the Arduino version. Weights are nonlinear and
drifty, reading can disturb writing (AC read is mandatory), plating can run away, and part-count
explodes with size — which is exactly why silicon eventually beat the memistor. **We rebuild
history's beautiful dead-end on purpose,** to prove that "learning" can be a physical, chemical
act with no digital computer in the loop.

The payoff: a number a piece of copper taught itself, held in metal, with the power off.

*Logic & science, not sorcery.*

---

## Sources
Widrow & Hoff (1960) *An Adaptive "Adaline" Neuron Using Chemical "Memistors"* · Ohno/Aono (2011,
Nature Materials) Ag₂S STP→LTP · Jo et al. (2010, Nano Lett.) memristor synapse · Prezioso et al.
(2015 Nature, 2018 Nat. Commun.) in-situ memristor learning · Serrano-Gotarredona et al. (2013)
STDP with memristors. Full list in `PRINCIPLE.md`.
