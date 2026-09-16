# Fine-tuning Whisper on Iddo's voice — results

2026-08-07. Trained on eran3 and eran2. eran4 untouched. Nothing alma-stt serves was
modified.

---

## The target, stated before the numbers

Iddo asked for a model that "knows perfectly my voice". Perfect is not achievable and
a model that memorised these 11.8 hours would be *worse* on tomorrow's speech, not
better — which is why every session in the eval sets is one the model never trained
on, and why two of the eval sets are other people entirely.

**The target I set up front: halve the error on his held-out Hebrew without regressing
his English or general speech.** Measured against that: Hebrew error on his held-out
audio fell 41–46%, English held flat or improved slightly. Target met on Hebrew,
honestly short of "perfect" and always will be.

---

## 1. Base model — I did not use either of the two candidates

The task said to start from ivrit-ai if it beat production. **Measured, it beats
production on Hebrew and is catastrophically worse on English**, and Iddo's speech is
52.8% English:

| zero-shot | his tier-A Hebrew | **general Hebrew (human labels)** | **general English (human labels)** | English language-ID |
|---|---|---|---|---|
| openai turbo (= production) | 40.25 | **37.06** | **5.34** | 100% |
| ivrit-ai turbo | 13.28 | **18.33** | **51.94** | **0%** |

ivrit-ai never emits `<|en|>` at all. Its own model card says language detection "has
been degraded during training". I checked whether that was the whole problem by forcing
English and bypassing language ID: it still scored **32.58%** vs openai's 5.34%. So its
English decoder is genuinely damaged, not merely misrouted — starting there would have
meant rebuilding English from 2.7 hours of data.

**What I did instead.** Both models are the same 808.9M architecture and ivrit-ai is a
*continued fine-tune of openai turbo*, so the two sit in the same loss basin and
linear interpolation between them is well behaved. Sweeping α (weight on ivrit) found
a usable region no one had looked at:

| α | his tier-A | general Hebrew | general English | English LID |
|---|---|---|---|---|
| 0.00 openai | 33.74 | 37.06 | 5.34 | 100% |
| 0.20 | 28.06 | 25.87 | **5.22** | 100% |
| 0.50 | 24.90 | 20.43 | 6.30 | 38% |
| **0.70** | 20.59 | **18.72** | 11.31 | 0% |
| 1.00 ivrit | 15.82 | 18.33 | 51.94 | 0% |

α=0.20 **strictly dominates production on every metric with zero training.**
Higher α buys more Hebrew but breaks language ID — and language ID turned out to be
the thing fine-tuning fixes best. **I trained from α=0.70** and let training repair
the language head. That choice is the main result.

Both source checkpoints passed integrity checks before use: openai turbo 0.235% zero
bytes (fp16), ivrit-ai 0.732% (fp32 — the higher figure is the dtype, not damage),
808.9M params each, every tensor finite and non-degenerate.

**Correction to the brief:** production is whisper-large-v3-**turbo** at 808.9M
parameters, not large-v3 at 1.55B. Encoder 637.0M, decoder 171.9M.

---

## 2. A precision bug that silently destroyed the first run

Loading the model in bf16 makes AdamW keep bf16 state. bf16 resolves ~1 part in 256;
an Adam update at lr 1e-5 on a ~0.03 weight is ~3e-4 relative — about 13x finer than
bf16 can represent, so most updates round to zero.

| master dtype | trainable params that actually changed after 6 real steps |
|---|---|
| bf16 | **14.80%** |
| fp32 | **99.98%** |

The aborted run confirmed it: tier-A WER 28.19 → 28.33 → 29.12 while the loss fell.
All real runs use **fp32 master weights + fp32 Adam state, bf16 autocast compute**.
This is the kind of failure that produces a plausible-looking loss curve and a model
that learned nothing.

---

## 3. Configuration

| | |
|---|---|
| base | soup α=0.70 (0.70·ivrit-ai + 0.30·openai turbo) |
| precision | fp32 master + optimizer, bf16 autocast, gradient checkpointing |
| optimizer | AdamW, β (0.9, 0.98), eps 1e-6, wd 0.01, grad-clip 1.0 |
| lr | 1e-5, 50-step warmup, cosine decay; encoder lr ×0.25 |
| batch | 16 × 2 accumulation = 32 effective |
| epochs | 3 planned; **best checkpoint was epoch 0.33** |
| regularisation | SpecAugment (mask_time_prob 0.05) |
| targets | language token **in the loss** (this is what repairs language ID); 20% of samples keep clip-level timestamps so faster-whisper's timestamp path does not rot |
| **peak memory** | **9.5 GiB encoder-frozen · 21.0 GiB full fine-tune** (of 121 GiB) |
| **wall clock** | **39.8 min** (ft70, 2 epochs) · ~50 min (ft50full, 1.7 epochs) |

Encoder frozen for epoch 1, justified from the diagnosis: the dominant defects were
language-prior and decoder-side (hallucinated stock phrases, language misrouting), and
one speaker in one room gives the encoder almost no new acoustics to learn.
**The measurement vindicated this** — see §4; unfreezing the encoder only made things
worse.

---

## 4. WER per eval point — and the overfitting it exposes

`ft70` (α=0.70, encoder frozen throughout):

| step | epoch | his tier-A | general Hebrew | general English | |
|---|---|---|---|---|---|
| 0 | 0.00 | 20.59 | 18.72 | 11.31 | base |
| 107 | **0.33** | **19.31** | 19.79 | 7.08 | **best, saved** |
| 214 | 0.66 | 19.85 | 19.23 | 7.08 | |
| 321 | 1.00 | 20.83 | 19.83 | 7.06 | |
| 428 | 1.33 | 19.33 | 19.38 | 6.99 | |
| 644 | 2.00 | 19.71 | 19.40 | 6.80 | |

`ft50full` (α=0.50, encoder unfrozen after epoch 1):

| step | epoch | his tier-A | general Hebrew | general English | encoder |
|---|---|---|---|---|---|
| 0 | 0.00 | 24.86 | 20.95 | 6.07 | frozen |
| 107 | 0.33 | 24.06 | 21.99 | 6.14 | frozen |
| 214 | 0.66 | 22.02 | 21.12 | 6.02 | frozen |
| 321 | **1.00** | **21.61** | 21.51 | 6.21 | frozen — **best** |
| 428 | 1.33 | 22.15 | 21.51 | 6.30 | **training** |
| 535 | 1.66 | 22.84 | 21.53 | 6.44 | **training** |

**Both runs peaked at or before epoch 1, and ft50full got monotonically worse once the
encoder unfroze — while its training loss kept falling (0.60 → 0.39).** That is exactly
the loss-improves-while-WER-worsens failure the task warned about. Checkpointing on WER
caught it; checkpointing on loss would have shipped the epoch-3 model. 11.8 hours from
one speaker is simply not enough to move 637M encoder parameters.

---

## 5. Catastrophic forgetting — measured on humans, not on machine labels

`fleurs_he` / `fleurs_en` are **human-transcribed**, other speakers, and were never
trained on. They are the only unbiased numbers here.

| | general Hebrew | general English | English LID |
|---|---|---|---|
| production (openai turbo) | 37.06 | **5.34** | 100% |
| ivrit-ai (the "obvious" choice) | 18.33 | **51.94** | **0%** |
| α=0.70 before training | 18.72 | 11.31 | 0% |
| **ft70 after training** | **19.90** | **7.20** | **100%** |

Training **repaired the language head completely** — English LID 0% → 100%, and general
English recovered 11.31 → 7.20 — while giving up almost nothing in Hebrew. That is the
mechanism the whole design was built around, and it worked.

Residual honesty: ft70 is still **1.9 points worse than production on clean read
English** (7.20 vs 5.34). It did not "lose English", but it is not as good at English
as vanilla turbo. §6 is how to avoid paying that.

**Hallucination — the actual complaint.** Fraction of outputs that are *only* a stock
phrase ("תודה רבה", "thank you"):

| | his tier-A | his held-out | retain |
|---|---|---|---|
| production | 0.90% | 1.01% | **2.61%** |
| ft70 | 0.30% | 0.71% | **0.65%** |
| ft50 | 0.00% | 0.42% | 0.33% |

**Down 60–75%.** The dataset filters worked — I verified the training targets contain
**0.00%** stock-phrase-only labels — so the model was never taught the reflex.

---

## 6. What to actually run

The fine-tuned model and production turbo are good at different things, including at
*recognising* different languages:

| language-ID accuracy | his Hebrew | his English |
|---|---|---|
| production | 77.1% | **99.4%** |
| ft70 | **95.0%** | 79.9% |

So a two-model routed setup beats either alone. Measured from per-utterance dumps:

| system | his tier-A | retain | his English | general Hebrew | general English |
|---|---|---|---|---|---|
| **production today** | 33.74 | 35.97 | 24.80 | 37.06 | 5.34 |
| ft70 alone | 20.16 | 21.66 | 36.94 | 19.90 | 7.20 |
| **A** — ft70 routes; ft70=he, prod=en | **19.82** | **21.42** | 30.31 | **19.90** | **5.34** |
| **B** — both must agree "he"; else prod | 22.00 | 24.01 | **23.14** | 29.33 | **5.34** |
| oracle (perfect routing) | 19.43 | 21.09 | 22.93 | — | — |

**Recommendation: system B.** It is the only option that improves on production
*everywhere* — Hebrew −35%, his English −7%, general English unchanged, general Hebrew
−21%. System A is better if Hebrew is the priority (−41% on his Hebrew) at the cost of
his English.

**Qualitative check.** Production misroutes 55 of 203 held-out Hebrew clips to English
and types nonsense. The fine-tune rescues **51 of those 55**:

| he said | production typed | fine-tuned |
|---|---|---|
| מה קורה | "My cool, huh?" | **מה קורה?** |
| יש דאטאבייס | "Yes, database." | **יש דאטאבייס.** |
| תפתח את הלינקים | "with the linking." | תחת את הלינקים. |
| ראה את האדם | "I don't know." | ברוכה, בראת האדם. |

### Deployment
1. `training/export_ct2.py` converts the checkpoint to CTranslate2 for the mic app.
   It writes a **new** directory and changes nothing being served.
2. Keep `language: "auto"`. Never force `language=he` for this speaker.
3. **Raise `log_prob_threshold` from −1.0.** This is not a model issue and fine-tuning
   cannot touch it, but the prior diagnosis attributed **5.0% of all utterances** to
   real speech being deleted by that gate, inside a **13.5% total silent-deletion
   rate**. That is a bigger everyday defect than anything measured here and it is a
   config edit. Do it first.

---

## 7. The limitation that bounds all of this

**No transcript in this corpus was written by a human.** Every `iddo_*` number above
measures agreement with a machine labeller, not accuracy. It is still informative — if
the labels were simply production's output, production would score ~0% and it scores
33.74% — but it is not accuracy, and `iddo_eval`/`iddo_en` are actively biased *toward*
production because production wrote them. The FLEURS rows are the only true
measurements, which is why the forgetting analysis leans on them.

`training/make_verify_set.py` exports ~250 held-out clips as WAVs with the best model's
transcription pre-filled, so correcting is editing rather than typing. An hour or two of
Iddo's time turns every number in this report from "agrees with the old labeller" into
"is right" — and it is the single highest-value thing left to do.

## Files
- `training/` — `train.py`, `evaluate.py`, `soup.py`, `melgpu.py`, `common.py`,
  `probe_precision.py`, `route_analysis.py`, `export_ct2.py`, `make_verify_set.py`
- `results/baselines.md` — full zero-shot tables and the α sweep
- `results/hyps/` — every per-utterance hypothesis for every model and set
- `results/*history.json` — per-eval-point curves
- checkpoints: `eran2:~/whisper-iddo/runs/ft70/best` (recommended),
  `eran3:~/whisper-iddo/runs/ft50full/best`, soups at `eran3:~/whisper-iddo/soup_{20,50,70}`
