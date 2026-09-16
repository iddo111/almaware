# NEEDS-IDDO — KESHEV-6 (the live mic's decoder), code revision 2026-09-06

> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it
> IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy
> (`health: ok` ≠ working). A broken window left unfixed invites decay.

**Nothing in this file was applied.** Eight defects were fixed on disk and
proved; these six were not, because each one either changes what a model is fed,
throws away his audio, or spends a box's night. *Iddo trains Claude, Claude
trains ERAN* — nothing reaches a model without his word.

**שמונה ליקויים תוקנו והוכחו. ששת אלה לא נגעתי בהם — כל אחד מהם או משנה מה שמאכילים
מודל, או מוחק את ההקלטות שלו, או מוציא לילה שלם של GPU. אתה מחליט.**

Nothing was restarted, stopped or signalled anywhere. `eranb-life` PID 120630
still shows `Fri Aug 21 17:19:00 2026`.

---

## The one-line version

| # | The question only you can answer | השאלה |
|---|---|---|
| K6-01 | The mic computes a "is this a voice or the room" number on every reply and **throws it away at the socket.** Plumbing it through is free. The gate numbers need your ear. | המיק מודד אם זה קול או רעש — וזורק את המספר |
| K6-02 | One number, `-0.40`, picked from **33 decodes**, now drops **74.5%** of everything you say. | סף שנקבע מ-33 דגימות חותך שלושה רבעים |
| K6-07 | **3.89 GB of your recorded voice** sits on this PC, growing 0.4 GB/day, with no label and nothing that ever deletes it. | 38,814 הקלטות שלך על הדיסק, בלי תווית ובלי מחיקה |
| K6-08 | eran4 trains a LoRA for 25 min every night **on zero new data**, and says "2305 new utterances" while doing it. | אימון לילי על אפס נתונים חדשים |
| K6-09 | …and even a winning result **could never reach the model that listens to you.** | ואפילו אם ינצח, הוא לא יכול להגיע למודל ששומע אותך |
| K6-10 | The thing that collected your corrections **died on 2026-09-02** and every check stayed green. | מי שאסף את התיקונים שלך מת ב-2 בספטמבר |

---

## K6-01 — the one signal built to tell your voice from the room, discarded

**File:** `D:\CLAUDE\keshev-next\app\decoder.py:159-165`

The server on eran1 computes `speech_ratio` and `no_speech_prob` on **every**
reply, and its own docstring says why: *"so the client's hallucination stop-list
can stop firing on loud speech and keep firing on silence."* The client keeps
`text` and `avg_logprob` and nothing else. `grep -rn speech_ratio
D:\CLAUDE\keshev-next` returns **0 matches**.

The signal is alive and informative — today on :8739, live traffic only:

| speech_ratio | segments |
|---|---|
| < 0.1 (room) | 1,908 |
| 0.1 – 0.3 | 893 |
| 0.3 – 0.6 | 1,144 |
| ≥ 0.6 (voice) | 1,166 |

And it disagrees with the gate that is actually used: **580 segments today
looked like speech (sr ≥ 0.5) and were dropped by the confidence floor; 12
looked like silence (sr < 0.1) and passed it.**

**What needs no permission and is ready to write:** return a dict from
`transcribe_hebrew_pcm` instead of a 4-tuple, and print `sr=` beside `lp=` on
every `[segment]` / `[confidence]` line. Then the next calibration has both axes
instead of one.

**What needs you:** the two-dimensional verdict itself — *relax the floor when
sr ≥ 0.5, tighten it when sr < 0.1*. Those numbers are a judgement about which
mistake costs you more, and only your ear can make it. See K6-02: it is the same
sitting.

---

## K6-02 — a threshold picked from 33 decodes now decides three quarters of your speech

**File:** `D:\CLAUDE\keshev-next\RUN-KESHEV6.cmd:137` —
`KESHEV_LOGPROB_FLOOR=-0.40`

The launcher's own note records that it came from **33 decodes of one session**
and that the measured margin to your real speech is **0.04**.

What it does now, from the last 3 MB of `trial.log`:

```
decode=ok                     1,247
[confidence] dropped          3,984      74.5% of everything decoded
  of those, in -0.50..-0.40     387      i.e. within 0.10 of the line
  full sentences among them     535
typed lines within 0.05 of it   299
```

The tail shows drops at `lp=-0.41`, `-0.48`, `-0.49` sitting next to a pass at
`-0.39`. That is not a threshold separating speech from noise; that is a coin
landing on an edge, 3,984 times.

**The sitting I am asking for (about 20 minutes):**

1. I pull **60 dropped segments** with `sr ≥ 0.5` and `lp ∈ [-1.0, -0.4)` and
   **20 that were typed**, from `keshev-next\segments` — they are already on
   disk, no new recording.
2. You listen **blind** (no scores shown, no order you can infer) and say for
   each one: *speech* / *not speech*.
3. The floor and the `sr` axis get derived from **your labels**, with the cost
   stated in both directions: how many of your sentences a given line loses, and
   how much room it lets in.

Until then the number stays exactly where it is. I am not moving a gate that
touches three quarters of your dictation on my own arithmetic.

---

## K6-07 — 3.89 GB of your voice on this PC, unlabelled, never deleted

**File:** `D:\CLAUDE\keshev-next\app\main.py:459` — `--debug-dump` **defaults to
True**, and `gui6.py:309` launches the engine with no flag, so production runs
with the debug dump on.

Measured today:

```
38,814 wav files      4,180,088,528 B   (3.89 GB)
oldest 2026-08-20 20:57      newest today 12:19
written today                4,626      (~0.4 GB/day)
retention                    none
label beside them            none
```

So it is simultaneously the worst of both: **it keeps your private audio
forever**, and it is **useless as a corpus**, because no verdict is written next
to any file — nothing says whether that segment was typed, dropped by the floor,
or thrown away by textguard.

Three ways out, and the choice is yours because it is your voice:

- **Turn it off.** `--no-debug-dump` in gui6's launch line. Nothing is kept.
- **Keep a window.** 7 days, then delete. Bounded, and enough to debug a bad day.
- **Make it worth keeping.** Write a sidecar `.json` beside each wav with the
  verdict, `lp` and `sr`. That is *also* what makes K6-02's listening sample
  possible without recording anything new.

They combine: a 7-day window **with** sidecars would answer K6-02 and stop the
growth. But whether your audio is kept at all is not my call to make.

---

## K6-08 — a nightly training run on zero new data, that says otherwise

**File:** `eran4:/home/eran4/lora-iddo/lora-nightly.sh:38` and `:67`
*(eran4 is DARWISH's box — read only, nothing was touched)*

Two independent faults that happen to cancel into a very confident lie:

1. **Line 38** counts `NEW_WAVS` as *every wav ever pushed* into
   `data/keshev_corpus`, which is never drained. So `MIN_NEW=200` can never skip
   again. The ledger has said `new_utterances` = 2260, **2305, 2305, 2305,
   2305** for five nights running, while `find data -newer promotion-ledger.jsonl`
   returns **0 files** and the newest file in that inbox is **2026-09-02 18:23**.
2. **Line 67** trains on `data/voice_corpus` (15,327 files, newest **2026-08-10**)
   plus `teacher_corpus.jsonl` (08-10), and **never reads that inbox at all** —
   `grep -n keshev_corpus train_lora_iddo.py` = **0 hits**.

So every night at 03:30 the box spends 25 minutes of GPU announcing *"training
on voice_corpus + 2305 new utterances"* while training on **zero** new
utterances, and is then rejected: **21 candidates since 08-19, 0 promotions**,
candidate WER 0.4354–0.4821 against a deployed 0.3805 that has been byte-identical
for five nights. The evaluation is **n=15 pairs** (there are 91 audio files and
66 transcripts in `cafe/`).

**The patch is written and NOT applied** (eran4 is not mine to write to) — it
would count only wavs newer than the last ledger timestamp, actually merge the
inbox into the training pool or say *"not included"* in the log, move consumed
files to `data/consumed/<date>`, and refuse to report a WER on n < 30.

**But the real question is K6-09, and it is yours:**

---

## K6-09 — even a winning candidate could never reach the model that listens to you

**File:** `eran4:/home/eran4/lora-iddo/lora-nightly.sh:107`

The promotion writes into **eran4's own** `keshev-stt` — which served **0
requests in 24 h**. Your microphone's primary is **eran1:8739** (the ivrit
model, which has no LoRA path at all) and its fallback is **eran1:8737**, whose
LoRA directory has been frozen since **2026-08-12**.

The only training loop in the whole KESHEV family is aiming at a server nobody
talks to, from data that stopped moving on 09-02.

**Your call, and it is a real fork:**

- **Retire it.** Stop the timer. DARWISH's box is at 116/120 GB and spends 25
  minutes of GPU a night on a guaranteed rejection.
- **Re-base it.** Point it at `ivrit-ai/whisper-large-v3-turbo` (the model that
  actually hears you), ship promotions to `eran1:/home/eran1/keshev6/models`,
  and gate promotion on segments **you have judged** rather than on a 15-pair
  café set.

I did not stop the timer. Stopping a nightly job is a decision about what this
fleet is for.

---

## K6-10 — the thing that collected your corrections died on 2026-09-02, quietly

**File:** `D:\CLAUDE\mic-rebuild\client\corpus.py`

The rule *"an utterance enters the corpus only if it was TYPED"* is good, and it
exists **only in the retired `mic-rebuild` client**. `keshev-next` — the live mic
since 09-05 — has no corpus writer at all (`grep corpus keshev-next/app/*.py`
finds only comments in `textguard.py`).

Meanwhile every check stayed green: the scheduled task `KESHEV-Corpus-Push` ran
**today at 03:00, result 0**, and moved nothing; `mic-rebuild/state/corpus` has
not changed since 09-03 03:00; eran4's inbox stops at 09-02 18:23; the ledger
sits at 2305.

This is the **same failure shape as ERAN's empty menu**: a pipeline whose input
went to zero, with no exception, no log line, and every green light still on.

**What I would write, on your word:** port the typed-only capture into
`keshev-next` (wav + accepted text, only for verdict `typed`, excluding the
reserved Café sessions), and make the push log a **FAIL** line when it moves 0
files for three nights running — so the next time this dies it says so.

**Nothing is fed to any model without your word**, so this stays unwritten until
you say yes. And it is tied to K6-07: a corpus writer and a labelled dump are
the same mechanism wearing two hats.

---

## Two smaller things, for the record

**A real canary for :8739.** The health check now asserts the *shape* of the
decoder's answer and takes `/health` to 503 on a stale canary — that is fixed and
proved. But the clip is still a synthetic sine chirp, so it can prove the decode
path runs and **cannot** prove the model heard correctly. `canary_clip` +
`canary_expect` in `server-6.json` is a working door: point it at a 1-second
Hebrew clip **your ear has ruled on** and the canary becomes a real one. I did
not pick a clip myself — inventing an expected token for an unjudged wav is
exactly how the mislabeled 132-item exam was built, and that already cost us a
week.

**`trial.log` rotation (the PC half of K6-14).** One 9.9 MB file, unrotated.
The patch is `_deliverables/code-revision/keshev6-proposed/gui6-trial-log-rotation.diff`
and it is **not applied** — `app/gui6.py` was being edited by another agent at
17:34 today while this revision ran, and a second hand in the live microphone's
window is the exact collision that breaks things. Whoever owns gui6.py right now
should apply it. This one is coordination, not a decision for you.
