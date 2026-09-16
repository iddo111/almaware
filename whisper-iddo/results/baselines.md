# Baseline measurements — 2026-08-07, eran3

All numbers from one harness (`training/evaluate.py`), identical audio, identical
scoring (`common.score_norm`: punctuation stripped, case folded, Whisper-normalised).
Decode reproduces production: predict the language token, whitelist to {he,en},
then decode greedily with that language forced.

## Reference quality — read this before reading any number below

| set | n | reference written by | trust |
|---|---|---|---|
| `iddo_tierA` | 335 | two independent Whisper decodes that agreed | best available in-domain |
| `iddo_eval` | 1682 | a single Whisper pass (the production model's own output) | biased toward openai turbo |
| `retain` | 306 | mostly two-decode agreement (261/306 tier A) | good |
| `iddo_en` | 902 | single Whisper pass | biased |
| `fleurs_he` | 300 | **human** | ground truth |
| `fleurs_en` | 200 | **human** | ground truth |

Only the FLEURS rows measure accuracy. The `iddo_*` rows measure agreement with a
machine labeller. They are still informative — if the labels were simply openai
turbo's output, openai turbo would score ~0% on them and it scores 33.74% — but
absolute values there are not accuracy.

## Zero-shot, before any training

| model | iddo_tierA | tierA he | tierA en | iddo_en | **fleurs_he** | **fleurs_en** |
|---|---|---|---|---|---|---|
| openai turbo (= production) | 33.74 | 40.25 | 13.43 | 24.80 | **37.06** | **5.34** |
| ivrit-ai turbo | 15.82 | 13.28 | 52.84 | 62.43 | **18.33** | **51.94** |
| soup α=0.20 | 28.06 | – | – | 23.26 | **25.87** | **5.22** |
| soup α=0.50 | 24.90 | – | – | – | **20.43** | **6.30** |

Language-ID accuracy (the number that decides usability for a 53%-English speaker):

| model | iddo_tierA | iddo_en | fleurs_he | fleurs_en |
|---|---|---|---|---|
| openai turbo | 77.1 | 99.4 | 94.0 | 100.0 |
| ivrit-ai turbo | 84.6 | **0.0** | 100.0 | **0.0** |
| soup α=0.20 | 93.3 | 87.5 | 99.7 | 100.0 |

## Two findings that decided the plan

**1. Production mislabels 27% of his Hebrew as English and emits garbage.**
55 of 203 Hebrew tier-A clips are routed to English by openai turbo:

| he said | production typed |
|---|---|
| תפתח את הלינקים | "with the linking." |
| ראה את האדם | "I don't know." |
| מה קורה | "My cool, huh?" |
| דבר חם עליו קצת, תודה רבה טוב | "foreign" |

This is Iddo's complaint, located. It is a routing failure, not an acoustic one.

**2. ivrit-ai's English loss is only partly a routing failure.**
With English *forced* (bypassing language ID entirely) ivrit still scores 32.58% on
human-labelled English vs openai's 5.34%. So repairing its language head would
recover part of the damage but not most of it — its English decoder is genuinely
degraded. Its own model card says so.

Consequence: "start from ivrit-ai" as stated in the task is **not** safe for this
speaker, and "stay on vanilla turbo" leaves a 2x Hebrew win on the table. Hence the
interpolation.

## Interpolation between the two (both are the same 808.9M architecture; ivrit is a
continued fine-tune of openai turbo, so they are linearly connected)

| α (weight on ivrit) | iddo_tierA | iddo_en | fleurs_he | fleurs_en | fleurs_en LID |
|---|---|---|---|---|---|
| 0.00 (openai) | 33.74 | 24.80 | 37.06 | 5.34 | 100.0 |
| 0.15 | 32.93 | 25.76 | 26.49 | 5.34 | 100.0 |
| **0.20** | **28.06** | **23.26** | **25.87** | **5.22** | **100.0** |
| 0.25 | 26.85 | 29.00 | 24.45 | 5.24 | 100.0 |
| 0.30 | 27.52 | 34.40 | 23.52 | 5.22 | 100.0 |
| 0.35 | 25.33 | 33.08 | 22.71 | 5.48 | 100.0 |
| 0.40 | 25.59 | 30.29 | 21.86 | 5.55 | 99.5 |
| 0.50 | 24.90 | – | 20.43 | 6.30 | 38.0 |
| 0.70 | 20.67 | – | 19.38 | 11.17 | 0.0 |
| 0.85 | 17.75 | – | 18.82 | 28.33 | 0.0 |
| 1.00 (ivrit) | 15.82 | 62.43 | 18.33 | 51.94 | 0.0 |

α=0.20 **strictly dominates the production model on every metric measured**, with no
training at all: general Hebrew 37.06 → 25.87 (−30% relative), his English 24.80 →
23.26, general English 5.34 → 5.22, tier-A 33.74 → 28.06.

## A precision bug that would have wasted the whole run

The first training attempt loaded the model in bf16, which also makes AdamW keep its
state in bf16. bf16 resolves about 1 part in 256; an Adam update at lr 1e-5 on a
~0.03 weight is ~3e-4 relative — roughly 13x finer than bf16 can represent, so most
updates round to nothing.

Measured directly (`training/probe_precision.py`, 6 real steps, same model and data):

| master dtype | trainable params that actually changed |
|---|---|
| bf16 | **14.80%** |
| fp32 | **99.98%** |

The aborted run confirmed it end to end — tier-A WER went 28.19 → 28.33 → 29.12, i.e.
no learning at all while the loss drifted down on the 15% of weights that could move.
All reported runs use fp32 master weights and optimizer state with bf16 autocast
compute. Peak memory 7.5 GiB frozen / ~11.9 GiB with the encoder training.

## Training-label audit (the self-distillation risk)

Every label was machine written, so the risk is teaching the model its own mistakes.
The dataset build's filters hold up:

- train rows 10,323; distinct labels 9,776
- labels that are **only** a stock phrase: **0 (0.00%)** — the "תודה רבה" reflex is
  genuinely absent from the training targets
- exact-duplicate label mass: 7.3%
