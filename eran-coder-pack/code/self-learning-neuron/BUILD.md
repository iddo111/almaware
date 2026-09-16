# BUILD — Sunflower Neuron v2 (the weight learns itself, no computer)

This is the bench guide. Read [`PRINCIPLE.md`](PRINCIPLE.md) first for *why* the physics
works. Here we build it, in stages, with realistic values and honest gremlins.

> **The rule, restated at the workbench:** the copper film (or the silver filament) changes
> its **own** value from the currents that pass through it. Everything else — op-amps,
> caps, LEDs, an optional Arduino — only *presents inputs, shapes error, and shows results.*
> **Nothing digital ever computes the weight update.**

The name: it's the **v2** of the "Sunflower Neuron." v1 (Arduino/`sunflower-neuron`) had a
microcontroller doing the delta-rule math in software — honest and educational, but the
*learning was digital.* **v2 moves the learning into the metal.** It is harder, finickier,
and slower — and it is the real thing.

---

## 0. Two builds, pick your path

| | **Path A — Memistor + analog delta rule** (RECOMMENDED) | **Path B — Ag₂S Hebbian synapse** (purist upgrade) |
|---|---|---|
| Weight element | copper plated on graphite (Widrow memistor) | silver filament in Ag₂S (atomic switch) |
| Learning | **supervised** — you wire in a target `d`; error → plating current | **unsupervised** — overlapping pre/post spikes; no teacher |
| Why start here | forgiving wet chemistry; big visible copper film; all-op-amp error loop | truest "fire together wire together", but stochastic & drifty |
| Difficulty | medium | high |

**Build Path A first.** It proves the whole loop with parts that behave. Path B is the
"no teacher at all" trophy once A works.

---

## 1. STAGE 0 — prove the physics: ONE weight that visibly self-adjusts

**Goal:** watch a *single* memistor's resistance move **because an error current pushed it**,
and **stop** when the error is nulled. No neuron yet. No learning loop yet. Just: *does the
weight change its own value under an error current, and hold?* If Stage 0 fails, nothing
downstream can work — so we prove the metal first.

### 1.1 Build the memistor cell (Path A)
```
  BOM (one cell):
    - Graphite rod / mechanical-pencil lead 0.5–0.9 mm, ~4–6 cm     (the "weight")
    - Copper wire or rod, bare, thicker                             (anode = control)
    - Copper-sulfate bath: CuSO4·5H2O in distilled water,
      + a small splash of sulfuric acid (battery acid)             (electrolyte)
    - Small glass test tube / jar                                  (vessel)
    - 2 insulated wires soldered to the TWO ENDS of the graphite    (signal terminals)
```
Solder a wire to **each end** of the graphite lead (epoxy/hot-glue the solder joints so
electrolyte can't creep up and dissolve them). The resistance **end-to-end of the lead** is
the weight `R_w` (conductance `G = 1/R_w`). Suspend the lead in the bath; suspend the copper
rod in the same bath **not touching** the lead. Bring all three wires out of the jar.

```
        ┌── signal end A ───────────────┐
        │        (graphite lead)        │  R_w measured A↔B = the WEIGHT
   [A]══╪═══════════════════════════════╪══[B] signal end B
        │   ~~~~ CuSO4 + H2SO4 bath ~~~~ │
        │        [ copper rod ]  ◄───────┼── [C] control/plating terminal
        └───────────────────────────────┘
```

### 1.2 The Stage-0 self-adjust demo (analog, no MCU math)
We drive the plating terminal with a current **proportional to an error**, where the error
is "how far is `R_w` from a target resistance `R_set`." When `R_w` reaches `R_set`, the error
is zero, the plating current stops, and the film **holds.** That is the delta rule for a
single weight, done entirely in analog.

```
                        +Vs
                         │
        R_set ──►[ pot ]─┤                      ┌─ this whole block is the
   (target knob)         │                      │  "error → plating current"
                        ─┴─ set voltage Vset    │  transconductance driver.
                         │                      │  NO CPU. op-amps only.
   AC READ of R_w:       │                      │
   small AC (~1 kHz) ──►[graphite A]            │
     through R_w ──►[graphite B]──►[precision   │
                                    rectifier]──┴─► Vw  (a DC voltage = the weight)
                                                     │
                     ε = Vset − Vw  ─────[op-amp diff]┘
                                    │
                                    ▼
             ε ──►[ transconductance stage: op-amp + BJT ]──► I_plate ──► [control rod C]
                                    │
        (ε>0 → plate copper → R_w ↓ → Vw rises → ε shrinks → I_plate → 0 → HOLD)
        (ε<0 → strip copper → R_w ↑ → Vw falls → ε shrinks → I_plate → 0 → HOLD)
```

**What you should SEE:**
- Turn the target pot. The op-amp drives a plating current; over ~seconds the copper film on
  the graphite **visibly thickens or thins**, `R_w` walks toward `R_set`, and the plating
  current **tapers to near zero** as it arrives. Park an LED (via a series resistor) across
  the plating drive so you can *watch the error current* fade as the weight converges.
- **Cut power, wait, re-read `R_w`.** It should still be near `R_set` (weeks of retention in
  Widrow's engineered cells; expect faster drift on a desk jar). That non-volatility is the
  "memory" in memistor.

**Why this is honest self-learning at n=1:** the *material* changed its own conductance, the
*material's* conductance nulled the error, and the loop *settled by physics.* An op-amp
shaped the error, but no processor computed "plate 0.42 mg of copper." The plating **is** the
integral (Faraday), and the film **is** the memory.

### 1.3 Stage-0 for Path B (Ag₂S — the purist alternative)
```
  BOM (one Ag2S cell):
    - Silver leaf / silver wire                                    (active electrode)
    - Sulfur source: flowers of sulfur (vapor) OR Na2S/polysulfide  (to make Ag2S)
    - Inert counter-electrode: graphite or platinum wire           (other terminal)
    - Tiny gap / thin Ag2S layer between them
```
Blacken the silver to **Ag₂S** (sulfur vapor in a warm jar, or a dip in sodium-sulfide
solution). Face it with the inert electrode across a **very small gap**. Now:
- Apply a small **positive** bias to the silver → Ag⁺ ions drift, a silver bridge grows →
  **conductance ↑ (SET / potentiation)**.
- Reverse, or simply **wait** → the thin bridge dissolves → **conductance ↓ (RESET /
  forgetting)**.
- **Stage-0 proof for B:** pulse it repeatedly and watch conductance *climb and hold* (LTP);
  pulse it once and watch it *decay* over seconds (STP → forgetting). That STP→LTP transition
  with pulse *repetition* — with **no error wire at all** — is the Ohno/Aono result and the
  proof that B learns by itself.

---

## 2. STAGE 1 — a 2–3 input neuron that self-learns a target

Now we make a whole neuron: several inputs, several self-updating weights, one summing node,
one threshold, and an **analog error-feedback loop** that trains all the weights at once —
the analog ADALINE. **Still no MCU in the learning path.**

### 2.1 Topology (Path A, the recommended build)
```
 x1 ──[memistor w1 (+/- pair)]─┐
 x2 ──[memistor w2 (+/- pair)]─┤
 x3 ──[memistor w3 (+/- pair)]─┼──►(Σ node: currents ADD by Kirchhoff)──► y ──►[thresh]──► ±1 out
 +1 ──[memistor b  (bias)   ]─┘                                          │
                                                                         │
   d (desired) ─────────────────────────►(−)────────► ε = d − y ─────────┘
                                                          │
            for each input i:  ε ⊗ xᵢ  ──►[transconductance]──► plating current into wᵢ's control rod
                                                          │
                        (each weight self-plates toward the value that lowers ε; ε→0 ⇒ plating→0 ⇒ HOLD)
```

- **Multiply for free:** each input voltage `xᵢ` drives current through its memistor
  conductance `wᵢ`. Current = `wᵢ · xᵢ`. That *is* the weighted term — Ohm's law did the
  multiply.
- **Sum for free:** all those currents meet on one wire. Kirchhoff's current law adds them:
  `y = Σ wᵢ·xᵢ`. No adder chip.
- **Signed weights:** each `wᵢ` is a **balanced pair** of memistors read differentially
  (`G⁺ − G⁻`), so weights can go negative (see PRINCIPLE §2.4).
- **The update (the learning):** the error `ε = d − y`, *gated by each input* `xᵢ`, becomes
  the **plating current** for weight `i`. Correlated `xᵢ` and `ε` of the same sign → copper
  plates → `wᵢ` moves to shrink `ε`. When `ε → 0`, every plating current → 0, and **all
  weights hold.** This is Widrow–Hoff LMS executed as electrochemistry.

### 2.2 The "gate ε by xᵢ" block — where the delta rule lives
The delta rule needs the **product** `xᵢ · ε` to drive weight `i`. In pure analog you have
two honest choices:

- **Manhattan / sign rule (simplest, most robust — START HERE):** use only the **sign** of
  `ε`, gated by whether `xᵢ` is active. i.e. "if this input was on and we were too low, plate
  a fixed small current; if too high, strip." A comparator (`sign of ε`) + an analog switch
  (gated by `xᵢ`) feeding a fixed-current source into the control rod. Ignores gradient
  magnitude — costs some accuracy — but it is the most buildable and is a real, published
  in-array rule (Prezioso 2015).
- **True analog product (`xᵢ · ε`):** an analog multiplier (AD633) or an OTA (LM13700 used as
  a transconductance multiplier) computes `xᵢ · ε`; feed its output through a resistor into
  the control rod so the cell integrates it. More faithful LMS, more offset/nonlinearity to
  fight.

> Either way the **multiply-and-decide** is analog; the **integrate-and-store** is the metal.
> No CPU touches `Δw`.

### 2.3 The post-neuron threshold (reuse PROTONEURON)
For the `±1` output you need a threshold. Two options, both analog:
- **Op-amp comparator** (TL072/LM311): `y` vs. 0 → clean ±1. Simplest for ADALINE.
- **Relaxation-oscillator integrate-and-fire** from the sibling **PROTONEURON** project (cap =
  membrane, relay/comparator = threshold, bulb = visible spike). Use this if you want the
  neuron to *spike* rather than just output a level — and it's the natural post-neuron for the
  Path-B Hebbian/STDP synapse, whose back-spike drives the weight update.

### 2.4 What to train it on (a target it can actually reach)
Pick a **linearly-separable** 2-input function so a single ADALINE *can* solve it:
- **AND / OR / NAND** logic (drive `x1,x2 ∈ {−1,+1}`, set `d` to the truth-table answer).
- A simple **analog regression** (`y ≈ a·x1 + b·x2`), `d` = the target line.

Cycle through the input patterns (by hand with pots, or with two slow oscillators / an
optional MCU that *only presents patterns*). Watch the weights plate toward the solution and
the error LED dim as it converges. **XOR will NOT work on one neuron** — it isn't linearly
separable; that needs MADALINE (multiple units), which is a Stage-2 stretch, not this build.

### 2.5 Where the OPTIONAL MCU may appear in Stage 1 (I/O ONLY)
```
 ALLOWED (I/O side):                       FORBIDDEN (learning side):
  • step through input patterns x1..xn       ✗ read x and ε, compute Δw = η·x·ε
  • drive the target voltage d               ✗ write a weight via a DAC/plating pulse
  • ADC-read y and each weight's G, plot     ✗ implement the delta rule in firmware
  • blink a "converged" LED, log a CSV       ✗ decide when to stop learning
```
**Litmus test (from PRINCIPLE §5):** with the analog `x`/`d` sources free-running, *unplug
the MCU.* If the weights keep converging, it's real in-materia learning. If learning freezes,
the MCU was cheating. **Design Stage 1 so you can pass this test** — the cleanest way is to
drive `x` and `d` from pots/oscillators so there is no MCU in the loop to remove.

---

## 3. FULL BILL OF MATERIALS

### 3.1 The in-materia weights (the heart)
| Ref | Part | Value / spec | Note |
|-----|------|--------------|------|
| MEM (A) | Graphite rod / pencil lead | 0.5–0.9 mm, 4–6 cm | one per weight (two per **signed** weight) |
| ANODE (A) | Copper rod/wire, bare | thicker than the lead | plating/control terminal |
| BATH (A) | CuSO₄·5H₂O + distilled water | ~saturated, blue | the electrolyte |
| ACID (A) | Sulfuric acid (battery acid) | a **small splash** | boosts conductivity/smoothness — **handle with care** |
| CELL (A) | Test tube / small jar + lid | one per weight | seal to slow evaporation |
| AG (B) | Silver leaf / silver wire | — | active electrode (Path B) |
| S (B) | Flowers of sulfur / Na₂S | — | to form Ag₂S |
| CE (B) | Graphite or Pt inert electrode | — | counter-electrode (Path B) |

### 3.2 The analog learning loop (per neuron)
| Ref | Part | Value / spec | Role |
|-----|------|--------------|------|
| U1 | Op-amp, FET-input | TL072 / TL074 / LMC6482 | summing node buffer, subtractor, comparator |
| U2 | Analog multiplier **or** OTA | AD633 (×1–2) **or** LM13700 | `xᵢ·ε` product (skip if using sign/Manhattan rule) |
| Q1 | NPN transistor | 2N2222 / BC547 | transconductance: turns error-voltage into plating current |
| Rsense | Sense/limit resistor | 100 Ω–1 kΩ | sets & LIMITS plating current (anti-runaway) |
| Rw-read | AC read network | ~1 kΩ + small AC source | non-destructive read of `R_w` (no net DC!) |
| D-rect | Precision rectifier diodes | 1N4148 ×2 | turn the AC read into `Vw` (a DC "weight voltage") |
| Chold | (if capacitor-weight variant) | 1 µF film, low-leak | *only* for the all-electronic control build |
| RV | Pots | 10 k linear | target `d`, learning-rate `η`, input `x` sources |
| LED | Error/plating indicators | any + 1 kΩ | **watch the error current fade as it learns** |
| PSU | Supply | ±9…±12 V bench | op-amps + plating rail |
| SW | Analog switch (Manhattan rule) | CD4066 / DG419 | gate the fixed plating current by `xᵢ` |

### 3.3 Optional post-neuron (spiking) — from PROTONEURON
Reuse that project's cap-membrane + relay/comparator threshold + 12 V bulb if you want a
*spiking* output and, for Path B, a back-spike to drive STDP.

### 3.4 Optional MCU (I/O ONLY — never learning)
| Arduino/Pico | present patterns, drive `d`, ADC-read `y` & `G`, blink LEDs, log CSV | **must survive the unplug test** |

---

## 4. STAGED BUILD CHECKLIST

- [ ] **Stage 0a** — build ONE memistor cell; solder both ends; suspend in bath.
- [ ] **Stage 0b** — measure `R_w` vs. plated charge; make a rough **G-vs-coulombs calibration**
      curve (it will be nonlinear — that's expected, PRINCIPLE §6).
- [ ] **Stage 0c** — wire the AC read + precision rectifier → `Vw`. Confirm **reading does not
      drift the weight** (no net DC).
- [ ] **Stage 0d** — close the single-weight error loop (target pot → ε → plating). **Watch the
      film converge to `R_set` and hold.** ← *physics proven.*
- [ ] **Stage 0e (optional)** — build the Ag₂S cell; show STP-decay vs. LTP-hold with pulse
      repetition (Path B proof, no teacher).
- [ ] **Stage 1a** — build 2 signed weights + summing node + comparator; verify `y = Σ wᵢxᵢ`
      by hand-setting weights.
- [ ] **Stage 1b** — add the error subtractor `ε = d − y` and the `xᵢ`-gated plating drivers
      (start with the **sign/Manhattan** rule).
- [ ] **Stage 1c** — train **AND/OR**; cycle patterns; watch weights plate to the solution and
      the error LED dim.
- [ ] **Stage 1d** — run the **unplug-the-MCU litmus test**. Learning must continue.
- [ ] **Stage 2 (stretch)** — 3rd input; try analog regression; note that XOR needs MADALINE.

---

## 5. SAFETY

- **Acid & electrolyte:** sulfuric acid burns — gloves, goggles, work on a tray, ventilate,
  add **acid to water never water to acid**, keep away from the electronics, wash hands. CuSO₄
  is toxic if ingested; label the jar; keep from kids/pets/food.
- **Off-gassing:** at plating extremes you get traces of H₂ (cathode) / O₂ (anode); Path B can
  liberate trace H₂S from sulfides — **ventilate**, keep currents modest, don't seal a gassing
  cell hard.
- **Current limiting:** always keep `Rsense` in the plating path (100 Ω–1 kΩ). It sets a *few
  mA* max — enough to plate in seconds, low enough to avoid dendrites/gassing/**runaway**.
- **Electronics:** double-check op-amp supply polarity and electrolytic-cap polarity. Flyback
  diode on any relay coil / motor if you use the PROTONEURON post-neuron.
- **Wet + mains:** never near mains. Bench supply / batteries only.

---

## 6. HONEST CAVEATS (read before you're disappointed)

This is **harder, finickier, and slower** than the Arduino v1. Expect all of this:

1. **Nonlinear, hysteretic weights.** `G` vs. charge is not a clean line; SET ≠ RESET.
   Calibrate, don't calculate. Your convergence will be lumpy.
2. **Drift & self-aging.** Desk-jar cells drift faster than Widrow's engineered ones; films
   oxidize/redissolve; **evaporation changes bath concentration → changes everything.** Seal
   the cell; expect to re-zero.
3. **Runaway plating.** Copper-on-copper plates easier than bare graphite → the biggest weight
   can hog current. `Rsense` + modest `η` fight this; watch for it.
4. **Dendrites, whiskers, gas bubbles.** Non-uniform copper can bridge/short or flake; bubbles
   disturb the film. Low current, clean bath, patience.
5. **Reading disturbs writing.** Any net DC in the signal path *is* plating. AC read is
   **mandatory**, not a nicety.
6. **Variability (esp. Path B).** Ag₂S/Cu filaments nucleate stochastically → thresholds jitter
   cell-to-cell; two "identical" synapses learn differently.
7. **Retention vs. plasticity.** The volatility that makes nice STP *is* forgetting; durable
   LTP costs more write energy. You can't max both in one simple cell.
8. **Analog offsets = an error floor.** Multiplier/op-amp offsets integrate onto the weight and
   leave a residual error you can't train away. Null offsets; accept a floor.
9. **Slow.** Seconds per meaningful weight change. A demo, not a datacenter.
10. **Part-count explodes.** Every weight = its own cell + driver. Great for *a neuron*; this
    is precisely why the 1960s memistor lost to silicon VLSI. We are rebuilding history's
    beautiful dead-end **on purpose**, to prove learning can be physical.

**The payoff:** when the Stage-0 film converges to your target and *holds with the power off*,
you are looking at a number that a piece of copper taught itself. No CPU computed it. That is
the whole point. **Logic & science, not sorcery.**

---

## 7. Recommended first move
Build **Stage 0d** (Path A single-weight self-adjust). It's a rainy-afternoon build, it's the
cheapest way to *see* in-materia learning, and it de-risks everything above it. Once a single
copper film reliably walks to a target and holds, Stage 1 is "the same thing, three times, on
one summing wire."
