# ער"ן v2 — לומד מהקול (Eran learns from SOUND)

*"תינוק לא יודע לקרוא אותיות, הוא שומע צליל." — A baby doesn't read letters, it hears sound.*

Eran v2 is the **audio** Eran: a from-scratch, age-zero brain that learns by
predicting the **next moment of sound** in Iddo's heard world — then babbles sound
back, so you can literally **listen to it learn**.

## The heard world — NOT "contamination"
> *"אם הוא שומע מה שאני שומע, ערן, זה לא זיהום סביבתי. זה מה שאני רוצה, שיגדל כמו תינוק."*
> *"If Eran hears what I hear — that is NOT environmental contamination. That is
> what I want: that he grows like a baby."* — Iddo, 2026-06-18

`data.py` feeds Eran **everything** in his sound collection — his own voice **and**
the world around it (other people, music, the room, calls). No speaker-gating, no
denoising, no dropping "noisy" clips. A baby hears its whole world. The only thing
refused is non-heard / synthetic / book data — Eran learns from **real heard sound**.

## The pipeline (modular legos — same brain as Eran v1, swap the body)
```
 samples/*.wav  ──▶  cochlea.py        ──▶  audio tokens  ──▶  model.py (ERAN GPT)
 (his heard world)   EnCodec 24kHz          150 tok/s,           from-zero, age-zero
                     = the EAR             vocab 2048           predicts next sound
                                                                      │
 babble_latest.wav ◀──  cochlea.decode  ◀──  generate  ◀───────────┘
 (listen to it grow)     = the VOICE
```
- **cochlea.py** — Meta's **EnCodec** (via `transformers`, pure-torch, **no
  torchaudio** → the Hebrew mic's GPU torch is never touched). Runs on **CPU** so
  the mic always wins the GPU. The ear is frozen; ALL learning is in `model.py`.
- **model.py** — the *identical* nanoGPT lego as `eran-live` (only vocab/block
  differ) → trivial to upscale / migrate to ADA later.
- **data.py** — encodes all wavs once → `tokens_cache.npy`; folds in new
  recordings incrementally (the 24/7 collection keeps feeding him).
- **train.py** — continuous, VRAM-capped, GPU-throttled, checkpoints + resumes
  forever. Mic always wins.
- **listen.py** — turns the latest checkpoint into a real **babble .wav**.
- **supervisor.py** — keeps it alive + refreshes a babble every 5 min.

## Run
```
python -s data.py          # one-time: encode the heard world -> tokens_cache.npy
python -s supervisor.py     # train forever + babble every 5 min  (pythonw for autostart)
python -s listen.py         # hear the latest babble  ->  babble_latest.wav
```
`-s` is REQUIRED (Python312 cu121 torch, not the shadowing user-site CPU torch).

## Honest expectation
Age-zero babble from one person's heard world starts as **formless noise**; as the
loss/perplexity drop it grows **vocal texture, rhythm, breath** — a baby babbling
toward speech. It will NOT speak words from this alone — that is the long road
(more sound + the deeper soul-stack layers). This is the *ear + voice + age-zero
brain*, real and listenable today.

## Team review → v2.1 roadmap (Claude + Grok + Gemini)
Captured from the multi-AI review of this design. Folded in as the next iteration —
v2.0 (this build) ships first, then:
- **Parallel codebook heads + 1-step delay** (instead of flattening the 2 RVQ
  codebooks). Flattening doubles the sequence (effective 300 Hz) and eats the tiny
  model's short attention; predicting the 2 codebooks in parallel with a 1-frame
  delay keeps 2× the real context. **Biggest expected quality win.**
- **Experience-replay buffer** for anti-forgetting: a FIFO of older heard segments,
  ~10% mixed into every batch, so never-ending training doesn't drift to "current
  room silence." (Eran's own version of reconsolidation + a stable anchor.)
- **Vocal curriculum — WITHOUT gating the data.** The team suggested VAD-filtering
  to voice only ("ambient is poison"). We **reject the filtering** — Iddo's
  directive is explicit: *he hears everything I hear, that's the baby's world, not
  contamination.* The honest reconciliation: keep ALL sound in the stream, but
  early on **bias sampling** toward vocal-rich segments (a baby hears everything yet
  innately attends to the caregiver's voice), then broaden. Nothing is ever
  discarded.
- **Growing brain:** team verdict = skip at 3M params (Adam-reset / routing
  overhead not worth it); revisit only at a much larger scale.

## Future ear upgrade
`cochlea.py` is a clean swap-point. A richer ear (Descript-DAC, SoundStream, or a
codec **trained from Eran's own sound**) drops in here behind the same
`encode/decode` signatures — ideally in an isolated venv so it never disturbs the
mic. The model/trainer don't change.
