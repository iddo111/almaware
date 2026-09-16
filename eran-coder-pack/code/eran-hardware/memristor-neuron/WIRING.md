# WIRING — POT + CAP self-training neuron

Maps 1:1 to `firmware.ino` and the schematic in `build.html`. MCU = Arduino Nano (or RP2040).

## Power
- 5 V rail → op-amps (TL072/LM358 V+), SG90 servo (RED), MCP41010 VDD, MCU 5V.
- GND common to **everything** (op-amps, servo BROWN, both MCP41010 VSS, MCU GND). Single ground.
- Decouple each op-amp and each MCP41010 with 100 nF across its supply pins.

## Neuron core (analog — computes y in hardware)
| From | To | Purpose |
|---|---|---|
| x1 source | U1 summing input via **Cw1** (servo variable cap) | weight-1 branch |
| x2 source | U1 summing input via **Rw2** (MCP41010 wiper→resistor) | weight-2 branch |
| bias pot wiper | U1 summing input via Rb | bias branch |
| U1 out | U2 (integrator/buffer) → U3 (comparator) | sum → activation |
| U3 out | diode D1 → **MCU D2 (PIN_Y)** | neuron fired? (0/1) |

## MCU ↔ actuators (the tunable weights)
| MCU pin | Net | Device | Meaning |
|---|---|---|---|
| A0 | PIN_X1 | input 1 sense | x1 (−1..+1) |
| A1 | PIN_X2 | input 2 sense | x2 (−1..+1) |
| D2 | PIN_Y | ← U3 comparator out | y (neuron output) |
| D3 | PIN_TGT | target/label switch (pull-up) | hold = train, open = infer |
| D9 | PIN_SERVO | → SG90 signal (ORANGE) | **w1 = Cw1** (variable capacitor angle) |
| D10 | CS_W2 | → MCP41010 #1 CS | **w2 = Rw2** |
| D8 | CS_B | → MCP41010 #2 CS | **bias** |
| D11 (MOSI) | SDI | → both MCP41010 SI | SPI data |
| D13 (SCK) | SCK | → both MCP41010 SCK | SPI clock |

SPI is shared; the two pots are selected by their separate CS lines (D10, D8).

## Variable capacitor Cw1 (the "CAP")
- SG90 horn couples to the rotor of an interleaved-plate air variable cap (or two Al-foil rolls).
- Rotation 0–180° ↔ overlap area ↔ C ≈ 5–120 pF ↔ weight w1 ∈ [−WMAX,+WMAX].
- Cw1 sits in U1's input/feedback branch so its capacitance scales that input's gain.

## Graphite+magnet variant (optional, replaces/augments Rw2)
- Graphite rod in Al sleeve = the resistive element; NdFeB ring magnet sets contact/position.
- Magnet in a copper tube gives eddy-current damping (history-dependent → memristor-like).
- Drive coil (from DRV8833) moves the magnet; same integer-step update as the digital pot.

## VANILLA control bench
- Swap Cw1+Rw2 for **two MCP41010** (both weights digital) driven by the same loop.
- Compare convergence to the servo-cap version → this is what `sim.py` scores (hardware vs vanilla).

## Bring-up order (per build.html §4)
1. Power rails + grounds, decoupling caps. Verify 5 V, 0 V ripple.
2. Op-amp summing/comparator alone; inject known x, confirm U3 toggles at the right threshold.
3. Attach servo (Cw1) + pots; run `firmware.ino`; open PIN_TGT switch → inference only.
4. Hold PIN_TGT with a known label; watch a1/t2/tb move and y track the target → **learning**.
5. Confirm final weights land in the ratio `sim.py` predicts (w1:w2:b ≈ +2.1 : −1.4 : +0.5).
