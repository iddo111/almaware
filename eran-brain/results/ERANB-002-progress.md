# ERAN — Perceptron Mark II v0.1 · first day, honest numbers
> BROKEN WINDOWS LAW: test the REAL output, never a proxy.

2026-08-21, all on the fixed 132-item heldout, 22 classes, chance 4.545%.
Published baselines: duration-floor 5.30% | random-real-frames 46.21% | raw speech-span 53.79% | raw+loudest60 (1-NN) 68.94%

| time | what changed | heldout top1 |
|---|---|---|
| 15:50 | first life (log-band pooling ear) | 13.64% |
| 16:00 | cepstrum ear (drop c0) | 23.48% |
| 16:46 | frozen cochlea ear + critical period | 23.48% (still walled by exposure) |
| 16:55 | the house is never silent (free listening over ALL sounds) | **58.33%** |
| 17:22 | tuning-curve floor + warmup floor (two real bugs) | **62.88%** |

PASS: beats chance, beats duration floor, beats random-real-frames (46.21%), beats raw speech-span (53.79%).
FAIL: the 68.94% bar (which is a 1-NN number, not a centroid one).
Ear ceiling measured with no learning at all: 79.55%.

Bugs found and fixed today (each cost real accuracy):
1. `drives.wake_refresh()` never reset the stall clock -> the child slept every ~4 beats for two hours.
2. Novelty as a spawn-RATE target ran away (more prototypes -> better matches -> higher bar -> more prototypes): 856 blobs in four minutes.
3. A young prototype accepted ANY sound, including an opposite one (warmup floor now 0.0).
4. A prototype fed identical copies had sd=0, so its own sound fell a hair below its own mean and it cloned itself (min tuning width now 0.02).
5. Free listening was restricted to already-taught sounds, so the child had heard 3 of 22 after 733,000 beats -- a hard 13.64% ceiling on every exam.

The ear is FROZEN (Iddo's law, 2026-08-21): anatomy is fixed at birth, the brain learns to use it. The nightly tournament may measure but may not crown.
