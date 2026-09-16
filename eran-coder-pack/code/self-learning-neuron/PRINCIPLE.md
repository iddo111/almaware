# PRINCIPLE — Learning that happens *inside the material*

**The one rule that governs this whole project (Iddo's rule):**

> The **weight itself** must physically change its own value from the signals that pass
> through it. The neuron learns **in the analog domain**. A microcontroller may — at
> most — present inputs, blink LEDs, and log numbers. **It must NEVER compute the weight
> update.** The moment a CPU calculates `Δw` and writes it back, this is no longer a
> self-learning neuron; it is a digital neuron wearing an analog costume.

This document explains *why* that is physically possible, and it grounds the design in
two real, historically-proven mechanisms:

1. **Widrow & Hoff's electroplating "memistor" (Stanford, 1960)** — a weight stored as
   the *thickness of copper plated on a graphite rod*, updated by an *error current*.
2. **The two-terminal memristor / atomic-switch synapse** (Jo 2010; Ohno/Aono 2011;
   Prezioso 2015/2018) — a weight stored as the *conductance of a metal filament*,
   updated by *overlapping pre/post voltage spikes* (Hebbian / STDP).

Both are ways of putting the number we call a "weight" into a lump of matter, and then
letting **the matter update the number by itself** under ordinary electrical laws.

---

## 1. What "the weight is physical" actually means

In a software neuron a weight is a float in RAM: `w = 0.37`. To change it, a processor
reads inputs, computes `Δw`, and writes `w += Δw`. Three separate digital acts.

In an **in-materia** neuron the weight is a *state of a material*:

| Mechanism | The weight physically IS… | You read it as… | It changes when… |
|-----------|---------------------------|-----------------|------------------|
| **Memistor (Widrow)** | thickness of copper plated on graphite | conductance `G = 1/R` between the rod's two ends | a plating current flows in the 3rd (control) wire |
| **Memristor / atomic switch** | length/thickness of a metal filament in a solid electrolyte | conductance `G` across the two terminals | the voltage across it exceeds a switching threshold |

The profound part: **reading, multiplying, and updating are no longer three digital acts —
they are the same piece of matter obeying physics.** Kirchhoff's laws do the summation
for free; Faraday's law does the integration for free; the material's own switching
threshold makes the "should I learn now?" decision for free.

---

## 2. Grounding A — Widrow's memistor and the delta rule *in the metal*

### 2.1 The device
A **memistor** ("**mem**ory + res**istor**") is a three-terminal electrochemical cell:

- A thin **graphite rod** (a mechanical-pencil lead works) sits in an **acid-copper
  plating bath**: copper sulfate `CuSO₄` + a splash of sulfuric acid.
- The **two ends of the rod** are the *signal* terminals. The resistance measured
  end-to-end is **the weight**.
- A **copper rod/anode** in the same bath is the *third, control* terminal.

Pass a DC plating current from the copper anode to the graphite (graphite = cathode) and
**copper metal electroplates onto the rod**: `Cu²⁺ + 2e⁻ → Cu⁰`. A thicker copper film =
a fatter conductive path along the rod = **lower resistance / higher conductance / bigger
weight**. Reverse the current and copper **strips back off**: resistance rises, weight
shrinks.

> **weight (conductance) ∝ thickness of copper plated on the graphite.**

### 2.2 Why it *remembers* and *integrates* — Faraday's law
The mass of copper deposited is set by the **time-integral of the control current** —
the total charge pushed through the plating terminal:

```
m_Cu = (Q · M) / (n · F),     Q = ∫ I_plate dt
       M = 63.5 g/mol   (copper molar mass)
       n = 2            (electrons per Cu²⁺)
       F = 96 485 C/mol (Faraday constant)
```

So **≈ 1 coulomb deposits ≈ 0.33 mg of copper.** The cell is a **coulomb-counter that
remembers**: its conductance is the running integral of everything you've ever plated
minus everything you've stripped. That "conductance = ∫ current" behaviour is exactly why,
a decade later, people linked the memistor to Chua's 1971 *memristor* idea. (They are not
the same device: the memistor is 3-terminal and needs power to write; but the
integral-of-current memory is shared.)

Widrow's real cells: swing **~100 Ω → ~1 Ω**, full range in **~10 s** at **a few mA**,
**thousands of continuously-variable analog levels**, and — crucially — **non-destructive
AC readout**: you sense the resistance with AC so *no net charge* flows, so reading does
**not** erase the weight. Trained neurons held their weights for **weeks**.

### 2.3 The learning law — Widrow–Hoff LMS / the delta rule
ADALINE (*ADAptive LInear NEuron*) adapts on the analog sum **before** the threshold,
minimizing squared error. Its update is real-time stochastic gradient descent:

```
wᵢ ← wᵢ + η · (d − y) · xᵢ
```

- `y` = the analog weighted sum (formed by currents adding on a wire — Kirchhoff),
- `d` = the desired/target output,
- `ε = (d − y)` = the **error** (one analog subtraction),
- `xᵢ` = the i-th input.

**The beauty is that every term is a physical quantity and the update happens by itself:**

```
   error ε ──(gated by input xᵢ)──► becomes a PLATING CURRENT into weight i
                                             │
                                             ▼
   plating current ──(Faraday integrates it)──► becomes stored COPPER THICKNESS
                                             │
                                             ▼
   copper thickness ──(Ohm/Kirchhoff)──► becomes the CONDUCTANCE that lowers ε
```

The loop **settles**: when `ε → 0` there is **no net plating current**, so the weight
**stops moving and holds**. That is gradient descent implemented as electrochemistry — no
CPU, no clock, no stored program. The physics performs the integration and the memory.

### 2.4 Signed weights
Copper thickness only goes one way (conductance ≥ 0). To get **negative** weights,
Widrow used a **balanced pair** of memistors per weight and took the **difference** of
their conductances (`G⁺ − G⁻`). We copy that: one op-amp reads the pair differentially, so
a weight can be positive or negative even though each cell can only plate.

---

## 3. Grounding B — the two-terminal memristor doing Hebbian / STDP

This is the *purest* in-materia case: **no error wire, no teacher, no multiplier** — the
device updates itself from the *coincidence* of two neurons firing.

### 3.1 The correlation gate is the switching threshold
A memristor's conductance changes **only when the voltage across it exceeds a threshold**
`V_th`. Drive the **top** electrode with the pre-neuron's spike and the **bottom**
electrode with the post-neuron's spike. By Kirchhoff the device sees the **difference**:

```
V_across(t) = V_pre(t) − V_post(t)
```

Make each spike *sub-threshold* on its own (say peak +0.3 V, threshold +0.4 V):

- Pre fires alone → 0.3 V < V_th → **nothing.**
- Post fires alone → 0.3 V < V_th → **nothing.**
- Pre **and** post overlap → the waveforms subtract and the momentary difference climbs
  **past V_th** → **the filament grows, conductance ↑.**

That is a physical AND-gate for "fire together": an update happens *only* on coincidence,
because only then does `|V_pre − V_post|` clear the material's own threshold. Demonstrated
on an Ag/a-Si filament synapse by **Jo et al., Nano Letters 2010**.

### 3.2 The *timing sign* (STDP, not just Hebb)
Shape each spike as **a sharp narrow positive lobe followed by a long, slowly-decaying
negative tail**. Because the device sees `V_pre − V_post`:

- **Pre-before-post** (`Δt > 0`): pre's sharp positive lobe lands during post's long
  negative tail → difference strongly **positive** → clears SET threshold →
  **potentiation** (G ↑).
- **Post-before-pre** (`Δt < 0`): geometry reverses → difference strongly **negative** →
  clears RESET threshold → **depression** (G ↓).
- **Far apart:** lobes never overlap → sub-threshold → **no change.**

The magnitude falls off with separation, reproducing the exponential STDP window. The deep
result from the literature (**Serrano-Gotarredona et al., Frontiers in Neuroscience 7:2,
2013**): **the shape of the spike literally programs the shape of the STDP curve.** Same
passive device, different waveform → symmetric, asymmetric, or anti-Hebbian learning.
**Prezioso et al., Nature Communications 2018** showed a memristor network *learning
coincidence detection* with updates done purely by overlapping waveforms — zero digital
weight update.

### 3.3 The atomic-switch case (our DIY path: Ag₂S)
In an **Ag₂S atomic switch** you don't even need shaped spikes — the *filament dynamics
themselves are the learning rule*. **Ohno/Hasegawa/Terabe/Gimzewski/Aono, Nature Materials
10:591 (2011)**: a single Ag₂S junction shows **short-term plasticity that spontaneously
decays** when stimulated rarely (the thin Ag bridge dissolves — "forgetting"), but
**transitions to retained long-term potentiation** under frequent stimulation (the bridge
thickens into a stable contact). Rehearsal turns short-term memory into long-term memory,
governed entirely by input timing/repetition and the device's own ion kinetics. **In-materia
memory with zero controller.** This is directly buildable from Iddo's silver-leaf → Ag₂S
idea (blacken silver with sulfur to make the Ag₂S solid electrolyte, face it with an inert
graphite/Pt counter-electrode across a small gap).

---

## 4. The two grounding mechanisms side by side

| | **A — Memistor (Widrow)** | **B — Memristor / Ag₂S** |
|---|---|---|
| Terminals | 3 (2 signal + 1 plating) | 2 |
| Weight is… | copper thickness → conductance | filament conductance |
| Update driven by… | an **error current** (supervised, delta rule) | **spike coincidence** (unsupervised, Hebb/STDP) |
| Needs a teacher? | **Yes** — you wire in `d` (target) | **No** — learns from correlation alone |
| Integrates via | Faraday's law (charge → mass) | ion drift + switching threshold |
| Read without erasing | AC sense (no net charge) | small/brief sub-threshold read |
| Historical proof | ADALINE, Memistor Corp. | Jo 2010, Ohno 2011, Prezioso 2015/18 |
| DIY difficulty | medium (wet chemistry, but forgiving) | high (filaments are stochastic) |

**Design choice for this project:** we lead with **A (the memistor + analog delta rule)**
as the recommended, most-buildable *supervised* self-learner, because the whole loop is
made of forgiving, off-the-shelf analog parts and the weight is a big visible copper film
you can literally watch thicken. We keep **B (Ag₂S Hebbian synapse)** as the *purist,
teacher-free* upgrade — the truly-unsupervised "fire together, wire together" cell — and
we are honest that B is finickier.

Either way, **the microcontroller never computes `Δw`.** In A, the error is an analog
voltage turned into a plating current by a transconductance stage; in B, there is no error
at all — just two overlapping spikes. The learning is in the metal.

---

## 5. Where the (optional) microcontroller is allowed to live

Draw a hard line. The MCU is on the **I/O side of the glass wall**, never the **learning
side**:

```
        ┌─────────────── ANALOG / IN-MATERIA (the neuron) ───────────────┐
inputs  │  x1,x2 ──►[memistor weights]──►Σ (Kirchhoff)──►y──►[threshold]  │  output
teacher │  d ──►(−)──► ε = d−y ──►[transconductance]──► plating currents  │
        │                                   │                             │
        │                                   ▼                             │
        │                       COPPER PLATES/STRIPS = weight updates     │
        └────────────────────────────────────────────────────────────────┘
                    ▲                    ▲                     │
                    │ present x,d        │ (nothing)           ▼ read G, y (ADC)
        ┌───────────┴────────────────────┴─────────────────────────────────┐
        │  OPTIONAL MCU — I/O ONLY:  drive input voltages, drive target d,  │
        │  read/plot y and each weight's conductance, blink LEDs, log CSV.  │
        │  IT NEVER COMPUTES Δw. IT NEVER WRITES A WEIGHT.                   │
        └───────────────────────────────────────────────────────────────────┘
```

**Litmus test.** If you unplug the MCU mid-training and the neuron *keeps converging* as
long as the analog `x` and `d` sources keep running, it is a real self-learning neuron. If
unplugging the MCU freezes learning, the MCU was secretly doing the math — and you've
violated the rule. **Design so you can pass this test.** (Stage-1 uses pots/oscillators
for `x` and `d` so there is literally no MCU in the loop to remove.)

---

## 6. Honest physics caveats (both mechanisms)

These are not footnotes; they are why silicon eventually won.

- **Conductance is a nonlinear, hysteretic function of charge.** Bare graphite plates
  differently from copper-on-copper; a filament SETs differently than it RESETs. Expect to
  **calibrate `G` vs. coulombs**, not calculate it. Potentiation and depression are
  asymmetric.
- **Variability / stochasticity.** Filaments nucleate at random weak spots → SET/RESET
  thresholds jitter cycle-to-cycle and cell-to-cell. Your "correlation-gate threshold" is
  not a fixed number. DIY Ag₂S and Cu cells are the worst offenders.
- **Retention vs. plasticity trade-off.** The same volatility that gives nice short-term
  plasticity *is* forgetting: thin Ag₂S filaments dissolve in seconds-to-minutes. Durable
  weights cost more write energy — you cannot maximise both in one simple cell.
- **Reading disturbs writing.** Any net DC through a memistor's signal path is itself
  plating current. **AC sense (Widrow) or brief low-current probing is mandatory**, not
  optional.
- **Runaway plating (positive feedback).** Copper deposits on copper more easily than it
  extends bare graphite, so the strongest weight can grab a disproportionate share —
  a pathology you must current-limit against.
- **Wet-chemistry housekeeping.** Evaporation shifts bath concentration; contamination and
  temperature move the operating point; dendrites/whiskers can bridge and short; gassing
  (H₂/O₂) at the extremes wastes charge. Seal and stabilise the cell.
- **Slow, and part-count explodes.** Seconds per meaningful weight change; every weight
  needs its own cell + drive. Fine for a *neuron*; the reason a *chip* went to silicon.

**Bottom line:** the physics genuinely performs the delta rule / Hebbian update with no
CPU — *that part is real and historically demonstrated.* What is hard is doing it
**reliably and repeatably at scale.** A hand-made cell will show you both the magic and the
messiness in the same afternoon. That is exactly the honest bargain of in-materia
learning. **Logic & science, not sorcery.**

---

## Sources
- Widrow & Hoff (1960), *An Adaptive "Adaline" Neuron Using Chemical "Memistors"*, Stanford tech report.
- Widrow (1990), *30 Years of Adaptive Neural Networks*, Proc. IEEE.
- Jo et al. (2010), *Nanoscale Memristor Device as Synapse in Neuromorphic Systems*, Nano Lett.
- Ohno, Hasegawa, Terabe, Gimzewski, Aono (2011), *Short-term plasticity and long-term potentiation mimicked in single inorganic synapses*, Nature Materials 10:591.
- Serrano-Gotarredona et al. (2013), *STDP and STDP variations with memristors*, Frontiers in Neuroscience 7:2.
- Zamarreño-Ramos et al. (2011), *On STDP, Memristive Devices, and a Self-Learning Visual Cortex*, Frontiers in Neuroscience 5:26.
- Prezioso et al. (2015), *Training and operation of an integrated neuromorphic network based on metal-oxide memristors*, Nature 521:61.
- Prezioso et al. (2018), *Spike-timing-dependent plasticity learning of coincidence detection with passively integrated memristive circuits*, Nature Communications.
- Wikipedia: *Memistor*, *ADALINE*, *Physical neural network*.
