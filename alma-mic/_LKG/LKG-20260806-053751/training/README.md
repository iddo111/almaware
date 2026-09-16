> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

# ALMA-MIC — real weight training that cannot degrade
# אימון משקולות אמיתי שלא יכול להידרדר

**Full fine-tuning of the whole model. Not LoRA.** Iddo asked for real weights, and
that is what this trains: every parameter of `whisper-large-v3-turbo` (809 M), updated
on his own voice.

The hard requirement is not "make it learn". It is **"make it impossible to get worse."**
Everything below exists to serve that second sentence.

---

## The honest problem, stated first

Every transcript in `voice_corpus/` was written by the model we are about to train.
That makes this **self-training**, and self-training has a well-documented failure mode:
it does not teach a model new things, it amplifies what the model already believes —
including the things it believes wrongly.

We did not take that on faith. We measured it. Here are real pairs from the corpus,
label on top, the same audio re-decoded underneath:

```
label : איזה נקניק כזה של שוונצה ג'ייסה מודרפאקרס
redec : זה נקניקה זה של שוונצר שייזה מותה פאקאקאקאקאקאקאקאקאקאקאקא

label : דויטשן, דויטשן, דונטרלס!
redec : דודשן, דודשן, דודשן, דודשן, דודשן, דודשן, דודשן.

label : בל
redec : ל ל ל ל ל ל ל ל
```

**That is the actual failure mode.** The model does not lose to Iddo's accent — it falls
into a repetition loop on hard audio and never climbs out. Labels like those are sitting
in the corpus right now. Train on them and you are explicitly teaching the model that
looping is the right answer to difficult speech. It would get *more* likely, not less.
No clever optimiser and no eval gate downstream can repair a target that bad.

So the first and most important component here is not the trainer. It is the filter.

Measured agreement between the stored labels and a fresh beam-5 re-decode of the same
audio: **WER 0.49**. Between labels and a beam-1 re-decode: **WER 0.62**. Those numbers
are not a verdict on the model's quality — much of the gap is `אפס חמש ארבע` vs `0 5 4`,
the same words written differently. They are a verdict on **the labels as ground truth:
they are too noisy to be one.**

---

## What is built and what it does

| file | runs on | what it is |
|---|---|---|
| `analyze_corpus.py` | PC (stdlib) | quality report; defines what "junk" means, once |
| `prepare_dataset.py` | PC (stdlib) | frozen train / eval_voice / eval_retain splits |
| `evaluate.py` | PC or DGX (CT2) | WER + CER on a frozen split — the exam |
| `relabel_teacher.py` | DGX | *next* — stronger teacher rewrites the targets |
| `train_full.py` | DGX | *next* — full-weight fine-tune with an anti-forgetting anchor |
| `promote.py` | DGX | *next* — the gate. The only thing that can change the deployed model |

### The filters (`analyze_corpus.py`)

Of 9,439 captured utterances, **524 are rejected**:

| reason | n |
|---|---|
| stock phrase over short audio (`תודה`, `Thank you.` over silence) | 424 |
| **repetition collapse** (word loops, character loops, vocabulary collapse) | 52 |
| no letters in the transcript | 22 |
| impossible speech rate (>28 chars/s) | 20 |
| audio under 0.35 s | 4 |

Leaving **8,915 utterances / ~7.3 h** of usable speech from one speaker. That is a
genuinely good speaker-adaptation set.

### The splits (`prepare_dataset.py`)

```
train.jsonl        7,515 utts   5.98 h
eval_voice.jsonl     683 utts   0.58 h   HELD OUT — does it hear Iddo better?
eval_retain.jsonl    356 utts   0.27 h   HELD OUT — the OLDEST sessions. Did it forget?
```

Assignment is by **SHA-256 of the filename**, not by a random seed, and it is written to
`dataset/split_lock.json` and reused forever. A file that has ever been in an eval split
can never enter training — not in this run, not in any future run. Without that,
"never degrades" is a slogan: you would be comparing two models on two different exams
and calling the difference progress.

`eval_retain` is the forgetting check. A model that gets brilliant at last week's
microphone and forgets last month's has degraded, even though its headline number went up.

---

## How "never degrades" is actually enforced

Three independent layers. Any one of them failing still leaves the other two.

**1. At the data.** Poisoned targets are removed before training, not corrected after.
Duplicate transcripts are capped at 3 copies — 75 copies of `תודה רבה, תודה רבה.` do not
teach 75× more, they just tilt the model toward saying it.

**2. At the optimiser.** Full fine-tuning of 809 M parameters on 6 hours of audio will
overfit if you let it. So: low LR (1e-5), warmup, cosine decay, few epochs, EMA weights,
early stop — plus an **L2-SP anchor**, a penalty on `‖θ − θ_base‖²` that makes drifting
far from the starting weights expensive. The model is allowed to adapt; it is not allowed
to wander off.

**3. At the gate — this is the guarantee.** `promote.py` is the *only* thing permitted to
change the model the app loads. A challenger replaces the champion **only if all** of:

- `WER(challenger, eval_voice)` < `WER(champion, eval_voice)` by more than the noise floor
  (bootstrap confidence interval over utterances — not a single point estimate)
- `WER(challenger, eval_retain)` is **not worse** than the champion's
- no increase in repetition-collapse rate on either split
- the CT2-converted artifact reproduces the same WER as the pre-conversion model
  (conversion is a real place to silently lose quality)

Otherwise the challenger is **discarded** and the champion stays. Every champion is kept;
rollback is a file move. The deployed model therefore forms a monotone chain — it can only
ever move in one direction, because the only door it can walk through is one-way.

---

## The part that is NOT solved yet, said plainly 🟡

**Self-training alone cannot make this model better at words it currently gets wrong.**
The gate above guarantees no *regression against its own labels*. It does not, and cannot,
prove genuine improvement — because the exam is marked by the same model that sits it.

Two ways out, in order of value:

1. **A stronger teacher relabels the corpus** (`relabel_teacher.py`, on the DGX). Run
   `whisper-large-v3` (the full model, beam 5, temperature 0) over every utterance. Where
   the teacher and the current model agree, the label is trustworthy. Where they disagree,
   the teacher's label is the training target. That is real knowledge distillation from a
   stronger model into a faster one — genuine gains, not circular ones.
2. **Iddo corrects a gold set.** Even 200 hand-checked utterances would make the gate
   trustworthy in a way no amount of machine labelling can. This is the single
   highest-value hour anyone could spend on this project.

Until one of those exists, this system is an excellent **regression guard** and an honest
**speaker-adaptation** pipeline. Calling it more than that would be overselling it.

---

## Where it runs

**No torch on the PC — training or inference.** Full fine-tuning runs on the DGX fleet.
`eran4` is the voice node by fleet policy but was unreachable at build time, so training
targets **eran2** (GB10, torch 2.13 + CUDA, 121 GB). The PC only ever runs CTranslate2,
which is not torch, which is how the app already works.

```bash
python training/analyze_corpus.py          # is the fuel clean?
python training/prepare_dataset.py         # freeze the splits
python training/evaluate.py --tag champion # baseline. Do this before anything else.
```
