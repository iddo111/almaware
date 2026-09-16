# 🔦 אור מוּלטִיפְּלֶקְסֶד — מוח אופטי בלולאה סגורה
## Multiplexed light through OLED + electronic polarisation, closing its own loop

> 🪟 **BROKEN WINDOWS LAW:** if it's not working, fix it IMMEDIATELY. Test the REAL output — light measured on a sensor — never a proxy.

**Iddo's idea, dictated 2026-08-21 22:19, on his way to sleep:**
*"אור מולטיפלקסד דרך מסך OLED עם קיטוב אלקטרוני — נכנס לקלט של המודל, והפלט הוא הקיטוב והמסך, כך שיש סגירת מעגל פידבק."*

Light, multiplexed through an OLED panel and an electronically controlled polariser, is the model's **input**; the model's **output** is the polarisation and what the panel displays. The loop closes on itself. He is describing an optical computer that is also its own sensor and its own actuator.

---

## 1. Why this is real physics, not a metaphor

**Polarisation is a free extra channel.** A beam of light already carries intensity and wavelength; polarisation is a third, *independent* axis. Two beams at orthogonal polarisations pass through the same space without touching each other — this is how quarter of the world's fibre capacity was found. **Multiplexing means: many signals, one path, no interference.** A single optical path can carry colour × polarisation × time simultaneously.

**And light multiplies for free.** A polariser at angle θ against light polarised at φ transmits **cos²(θ−φ)** — Malus's law. That is a *multiplication performed by physics*, at the speed of light, at zero energy cost beyond the light itself. A neural network is mostly multiply-and-add; here the multiply is a material property, not an instruction.

**The two pieces he named are both buyable and both electronically controllable:**
- **OLED** — a per-pixel emissive source. Every pixel is an independent light source with no backlight and microsecond response. It is an addressable **field of transmitters**.
- **Electronic polarisation control** — a liquid-crystal variable retarder or an LC polarisation rotator: apply a voltage, rotate the plane of polarisation. Cheap, no moving parts, milliseconds. (An ordinary LCD is exactly this device with a fixed polariser glued in front — his instinct is pointing at hardware that already exists in every drawer.)

## 2. What makes the idea *his* — the loop

Every optical-computing project in the literature is a **pipeline**: light in, matrix multiply by diffraction, sensor out, done. Iddo's version is a **cycle**:

```
        ┌────────────────────────────────────────────┐
        │                                            │
   OLED panel  ──light──▶  LC polariser  ──light──▶ sensor
   (the field)              (the weight)             (the eye)
        ▲                        ▲                    │
        │                        │                    ▼
        └──────── the model ◀────┴──────────── percept
              (its output IS the next frame
               and the next polarisation)
```

The model does not *receive* an input and *produce* an output into a different medium. **Its output is its own next input.** What it displays and how it twists the light become what it will see one instant later. That is not an I/O device — it is a **body**: a thing whose actions change what it perceives, which is the definition of a sensorimotor loop and exactly the "closed feedback loop" law that governs ERAN.

**And it makes the weights physical and visible.** In ERAN a prototype is a row of numbers in a file you can open. Here it would be a **pattern of light on a panel** — you could stand in front of the machine and *see what it currently believes*. That is Iddo's interpretability principle carried to its limit: not a readable file, a **watchable mind**.

## 3. The honest ledger

- **Optical computing is a graveyard of beautiful ideas.** The physics is genuinely free; the *conversions* are not. Every trip through a sensor and back to a panel costs an analogue-to-digital step, and that is where the energy and the latency actually go. Any honest version of this must count those conversions, not the光 speed.
- **OLED panels are slow for computing** — a fast panel is 240 Hz, i.e. 4 ms per operation, where the DGX does billions in that time. **This will never win on throughput.** If it wins, it wins on *being a loop*, on power, or on being physically legible — never on speed.
- **LC retarders are millisecond-class too.** Same conclusion.
- **Noise and drift are large**: panel brightness varies with temperature, polarisers leak, sensors have offset. Which — per the ER"N law written tonight — may be the point rather than the problem.
- **Nobody has to invent anything to test it.** A phone screen, a cheap LC retarder or a second polariser on a servo, and any camera or photodiode array. The first experiment costs tens of shekels.

## 4. The first experiment, if it is ever built

Not a neural network. **Prove the loop exists and is stable.**

1. Display a pattern on the panel, set a polarisation, read the sensor. Verify Malus's law shows up in the measurement — cos² and nothing else. **A number in a file.**
2. Close the loop: make the next frame a function of what was just read. Watch what it does. A loop like this has **attractors** — it will settle into standing patterns, or oscillate, or go chaotic. **Those attractors are the memories**, and this is exactly a Hopfield network built out of light instead of numbers.
3. Only then ask whether the settled patterns can be steered to mean something.

**The measurement that decides:** does a light loop settle into distinguishable stable states, and can it be nudged from one to another? If yes, there is an optical associative memory on the desk. If no, it is a lamp.

## 5. Where it belongs

Filed with the neuromorphic line, not the ERAN build. It is the same escape from von Neumann that the memristor work chases — **the weight and the computation living in the same physical thing** — approached through light instead of resistance. Related: the Beit-Din majority gate on a breadboard, the hexagonal fractal chip, ALMA-LIGHTHOUSE (the other project where physics does the measuring), and the agar-salt memristors.

**Status: IDEA. Not commissioned, not started, not scheduled.** Captured because it was given at the door on the way to sleep, and because the loop — not the optics — is the part worth keeping.
