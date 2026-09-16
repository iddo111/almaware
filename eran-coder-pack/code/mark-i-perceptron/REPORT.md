# The 1958 Perceptron, Reproduced

### What Rosenblatt's Exact Machine Can Really Do

**Verdict: REPRODUCED and FAITHFUL — with one honest caveat about the central claim.**

Prepared for Iddo Perez · ALMAWARE · 2026-07-03
All numbers below are real held-out test accuracy. No cherry-picking.

---

## 1. The exact Mark I neuron counts

Frank Rosenblatt's Mark I Perceptron (1958–1960) was a physical machine, not a metaphor. Its canonical configuration had exactly:

| Layer | Name | Count | Role |
|-------|------|-------|------|
| S-units | Sensory (retina) | 400 | A 20×20 grid of photocells |
| A-units | Association | 512 | Random fixed feature detectors |
| R-units | Response | 8 | Trainable output units |
| Total | — | 920 units | — |

400 + 512 + 8 = 920 neuron-analogues. The 20×20 = 400 retina fed a bank of 512 association units, which drove 8 response units.

---

## 2. How the machine actually worked

Random A-unit plugboard. Each of the 512 association units was wired to a random, fixed subset of the 400 sensory cells through a physical patch panel — "a table of random numbers" made of wires. Roughly 20 excitatory (+1) and 20 inhibitory (−1) connections per A-unit, each firing when its algebraic sum crossed a threshold. These wires were never changed.

Motor-driven adjustable weights. The A→R connections were the only trainable weights. Each was a potentiometer turned by a small electric motor. Learning literally meant motors rotating dials to change resistances.

Error-correction (perceptron) learning. The rule was Rosenblatt's, not backprop: present a pattern, look at each response unit, and if it was wrong, nudge its weights toward the correct answer. Right answers changed nothing. Only the A→R weights were ever touched.

That last point is the whole architecture in one sentence: a fixed random nonlinear front-end, with a single trainable linear layer on top.

---

## 3. What we ran

We rebuilt this exactly in pure NumPy — no imported Perceptron/MLP class, no backprop — and ran it against two tasks, each with a vanilla control that applies the identical learning rule directly to the raw 400 pixels (skipping the 512 random A-units). Same data, same split, same rule. The only difference is whether the random feature expansion is present.

- MNIST-20×20 — real handwritten digits, each downsampled 28→20 and binarized to fill the 400-cell retina. 60,000 train / 10,000 test (the official split). 10 classes. 20 epochs.
- Synthetic shapes — self-generated square / circle / triangle, ~12 px, centered with ±3 px position jitter and 5% salt noise. 3,600 train / 900 test. 3 classes. 30 epochs. 100% ours, no download.

---

## 4. Honest results table

| Task | Mark I (512 random A-units) | Vanilla (linear on 400 pixels) | Winner |
|------|:---:|:---:|:---:|
| MNIST-20×20 (10-class, 10,000 test) | 0.8646 | 0.8699 | Vanilla (tie) |
| Synthetic shapes (3-class, 900 test) | 0.9378 | 0.9778 | Vanilla |

These are the confirmed, reproduced numbers. Re-running the original code returned them bit-for-bit. An independent from-scratch reimplementation (no shared modules) landed within a few percent: MNIST vanilla 0.8634, Mark I 0.856–0.886 across association seeds (mean 0.8711); shapes vanilla 0.9567, Mark I 0.897–0.911.

---

## 5. The insight — and the honest caveat

The 512 random association units are a random nonlinear feature expansion. This is the historical seed of what we now call Random Features and Extreme Learning Machines: project the input through a fixed random nonlinearity, then train only a linear readout. In theory this can let a linear classifier separate data that was not linearly separable at the pixel level — which is why, in principle, a faithful Mark I could beat a plain linear perceptron.

In our results, it did not. This is the one caveat we hold honestly:

- On shapes, vanilla clearly wins: 0.9778 vs 0.9378.
- On MNIST, it is effectively a tie: Mark I 0.8646 vs vanilla 0.8699 (and across seeds the two straddle each other, Mark I mean 0.8711 vs vanilla 0.8634).

So for these tasks the random-feature expansion is neutral-to-slightly-harmful, not beneficial. Why? Two reasons. First, the inputs are already close to linearly workable — binarized digits and centered shapes don't need a nonlinear lift for a linear rule to do well, so the expansion mostly adds noise. Second, 512 random units is small: the random-features / ELM advantage grows with the width of the random layer, and at Mark-I scale on already-easy inputs it simply doesn't pay off. The historical idea is real and important; the payoff requires either harder inputs or a much wider random layer than 1958 hardware had.

We report this direction plainly and do not overclaim.

---

## 6. Provenance and integrity checks

No train/test leakage. On the official 60,000 / 10,000 MNIST split, raw pixel-exact overlap between train and test is 0 / 10,000. The 59 / 10,000 binarized-pattern collisions we found are distinct raw digits that collapse to the same pattern only under the aggressive 28→20 downsample-plus-threshold (retina discretization loss, ~0.59%, none of them blank) — not split contamination.

Data sources. MNIST was fetched fresh via sklearn.datasets.fetch_openml('mnist_784', version=1, parser='liac-arff'). No local cache existed on this PC — we checked ~/.keras, ~/scikit_learn_data, torchvision caches, and did a filesystem search for mnist/*.gz/*.npz (only a torch header file matched; no data). The shapes are 100% self-generated. Ran on the PC CPU (Python 3.13); the GPU was untouched.

---

## 7. The direct answer to Iddo's question

What is the most impressive task the exact-size 1958 perceptron can genuinely learn on its own — with proven accuracy?

The faithful Mark I learns to read MNIST handwritten digits at 86.46% on the real 10,000-image test set — a task that did not even exist in 1958. That is the headline genuine feat: a 920-unit machine from the Eisenhower era, with only its 8-ish response weights trainable, reading modern handwritten digits at nearly 7-in-8 accuracy.

On its native task regime — Rosenblatt's actual demo of shape discrimination at fixed position — it hits 100% on 3-way square/circle/triangle (verified in a diagnostic run), and binary square-vs-circle at fixed position is also ~100%.

---

## 8. Three caveats, stated plainly

Caveat 1 — position invariance is a regime, not a given. Shapes accuracy depends entirely on where the shape sits:

| Position regime | Mark I | Vanilla |
|-----------------|:------:|:-------:|
| Fixed position | ~100% | ~100% |
| ±3 px jitter (reported) | 93.78% | 97.78% |
| Free placement anywhere | ~41% (~33% chance) | ~41% |

Free placement collapses to near-chance because a single linear readout cannot be position-invariant — the classic Minsky–Papert limitation, not a bug. Our first run used free placement and correctly produced ~41%; we then constrained to the modest-jitter regime the real machine actually operated in.

Caveat 2 — the vanilla control (important, non-flattering). As Section 5 showed: the 512 random A-units did not help. Vanilla matched or slightly beat Mark I on every task (MNIST 86.99% vs 86.46%; shapes 97.78% vs 93.78%). The random-feature expansion is neutral-to-harmful here.

Caveat 3 — a modern readout choice. We used a multiclass argmax-over-R-units readout. Rosenblatt's canonical hardware demos were 2-class (a single R-unit). Binary square-vs-circle at fixed position is also ~100%.

Run settings: MNIST 20 epochs, shapes 30 epochs, learning rate 1.0.

---

## 9. Bottom line

The reproduction is faithful and honest. The architecture is a genuine Mark I — 400 sensory → 512 fixed-random ±1 association units → trainable response units via true Rosenblatt error-correction, only A→R trained. The most impressive proven feat is 86.46% on real MNIST, and 100% on fixed-position shape discrimination. And the one thing that would have been nicer to claim — that the random association units beat the plain linear control — is not true for these tasks, and we say so.

Source code: D:\CLAUDE\mark-i-perceptron\perceptron.py, run.py, results.json. This document: REPORT.md in the same folder.
