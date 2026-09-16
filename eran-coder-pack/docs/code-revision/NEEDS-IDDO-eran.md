# ERAN — 7 things the code revision will NOT do without Iddo's word

> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

**2026-09-06 · code revision of model `eran` on eran1 (`~/eran-brain`) · claude-cli-REV-eran**
**לפי הפקודה של עידו 11:47 — רוויזיית קוד על כל השרשרת: אכלה → אימון → הרצה → פידבק.**

ERAN himself was never touched: `eranb-life` PID **120630**, up since **2026-08-21 17:19:00**, NRestarts=0 — verified before and after.
Seven defects were fixed on disk with proofs (ERAN-01, -02, -03, -05, -10, -13, -14). The seven below are **not code bugs I may decide alone** — each one changes *what ERAN is fed, how he develops, or what counts as a result*. That is Iddo's fence.
**עידו מאמן את קלוד, קלוד מאמן את ערן — כלום לא מגיע לערן בלי האוזן שלו.**

---

## 1. ERAN-12 — his whole diet is ONE sitting · כל האוכל שלו הוא הקלטה אחת
**What is true:** `food/train` = 657 wav, **all** from session `_t06_`, all written 2026-08-25 02:39 (the synthetic→human swap). Labels: `ah/ba/ma` ×100 (curriculum) + **`ima/ih/abba` ×100 — 300 files, 46% of his diet, that no gate ever examines** + 19 CV units with **3 files each**. A "lesson" on `ka` is the same three recordings, about 4,800 times.
**Why it is yours:** the corpus that would make the exam mean anything (≥20 recordings per unit, and a *second session*) does not exist. Recording it is not a code fix.
**The three questions:** (a) record a second session? (b) record the 19 rare syllables up to ≥20 each? (c) do `abba/ima/ih` join the curriculum, or stay as free-listening house noise?

## 2. ERAN-04 — the mastery ladder has been frozen since the food swap
**What is true:** `curriculum.json` says 13 units mastered — and lists **the same 13 as `regressed`**. 9 of them have **zero** dev files under the live split, so their sensitivity is 0/0 → 0.0 → "regressed"; and a non-empty `regressed` blocks *every* technical pass (school.py:183). No unit has been able to pass since 2026-08-25. The child rotates 9 failing syllables (za, ba, la, qa, ah, ta, ga, ra, da) about 67 s each, forever, while the window still says "13 mastered".
**The code half is ready and NOT applied:** a unit with fewer than 5 dev positives becomes *unexaminable* — it cannot pass and cannot fail, and it is excluded from the regression watch.
**Why it is yours:** the honest completion is to **fingerprint the corpus and archive the ladder when the food changes**, i.e. start the ladder over on the new human food. That resets what the child attends to. Also: those 13 were earned **before 08-25, on the TTS corpus your ear rejected**.

## 3. ERAN-06 — the running ERAN is a build that exists nowhere on disk
**What is true:** everything under `eran-brain/` was rewritten 22:08–22:09 on 2026-08-21; the process booted **17:19** and holds the 17:05 code in memory. The depth code (`cortex.py`), the tolerance/strictness rewrite in `brain.py`, `FREE_LISTEN_P` 0.05→**0.30**, and the session-based split have **never run as the living child**.
**So the next restart is not "the same ERAN starting again":** he would eat **657 files instead of 522**, listen freely **6× more**, and learn under different spawn rules.
**Why it is yours:** a restart is a change of diet and of development. It needs your word and a written before/after. Until then **every fix on disk is a net for a different animal, and I have said so.**
*(Code half already done: the wake will print the split; adding a `state/build.json` fingerprint is queued behind your decision.)*

## 4. ERAN-07 — the parent channel has never once closed
**What is true:** `feedback/inbox` has received **0 tap files in 16 days**. ACh has **no writer anywhere in the tree**; 5HT and OXT move only on a parent tap. So three of the five neuromodulators are constants (1.0 / 0.5 / 0.2 since birth), and plasticity is within 1% of 1.0 on **56% of beats**. "The parent's approval IS the reward" — and the reward has never arrived.
**Code half (no permission needed, queued):** every night the journal says "parent silent for N days"; ACh either gets a writer or is deleted as dead code.
**Why it is yours:** **do you want to tap?** If yes, the shape is a button on the :8820 window that writes `taps-*.jsonl` — an hour of work, but it puts your hand on his learning rate, and that is a decision, not a feature.

## 5. ERAN-08 — a beat is 4.6 milliseconds, so every constant means something else
**What is true:** he lives at **215.8 utterances per second** (no child hears that). So `SLEEP_EVERY=2000` is a **9.3-second night**, `PRUNE_UNUSED_BEATS=4000` is **18.5 seconds of amnesia**, `TRACE_TAU=60` ("~one lesson") is **0.28 s**, and `CRITICAL_PERIOD_BEATS=200,000` **ended 15 minutes after birth** — he has been an adult since beat 1M, and he is at 301M. Meanwhile `RETENTION_HOURS=12` is wall-clock. The measurable result: 58–61 prototypes with **births == deaths**, and best-dev has not moved since 2026-08-22.
**Two ways out, both yours:** (a) express night / attrition / critical period in **seconds of life** and derive beats at wake from the measured rate; or (b) **pace the loop to speech** — one utterance per ~0.5 s — and the existing constants regain their meaning.
**The genome is your fence. I propose; I do not edit it.**

## 6. ERAN-09 — the one act he performs never comes back to him
**What is true:** every 13.9 s he babbles a wav into `songs/outbox`. **199,946 files, 22 GB, +6,215/day** — and **nothing ever plays one back through his ear.** `ears.utterance_from_samples()` exists for exactly that and has no caller in the life loop. He speaks into a void.
**Code half (queued, no permission needed):** rotate the outbox from the reader side (newest 500 + one per hour), never from inside the beat.
**Why it is yours:** closing the loop = **a new audio source in his diet**. The evidence to look at first is last night's A/B from the `-self` arm (`results/SELFHEAR-20260906.json`): self-surprise −91.5%, and the self/other split died under control.

## 7. ERAN-11 — the "newest exam" on the window is 16 days old and its labels are in dispute
**What is true:** the exam block on :8820 shows `results/ERANB-001.json` from **2026-08-21 22:07**, scored on the **TTS corpus that preceded the swap**. The 132-item heldout it uses is the exam **your ear found mislabelled (0/10 on 09-03)**, and `genome.BASELINES` plus the "79.55% cochlea" claim rest on it.
**What I did do:** the examiner's 55 GB file scan is fixed (ERAN-01), so an exam can now start instantly.
**What I did NOT do:** re-run the exam to produce a number. **A number scored on labels you rejected is worse than no number.** The next exam waits on your ear — relabel the 132, or re-record them.
**Meanwhile the window should say "stale, pre-swap, labels disputed" instead of "newest exam" — say the word and I change the label, not the number.**

---

## What the fixes already do, so you can judge these seven against something
| # | was | is now (net for the next restart) |
|---|---|---|
| ERAN-01 | boot scanned **55 GB** of metrics, 8.3 min and growing 3.47 GB/day; the nanny killed anything over 15 min | bounded tail read — **1 MB, 10 ms**, forever |
| ERAN-02 | nanny's only remedy was **restarting the child** | it **names** (`ALARM-famine` / `ALARM-stalled`) and never restarts him; thresholds derived from his own beat rate |
| ERAN-03 | an empty dev set scored 0.0 and **condemned** every unit, and would have overwritten the best brain | blind exam → skipped, ladder untouched, said out loud |
| ERAN-05 | an empty menu raised nothing — **the 09-06 silent famine** | refuses the wake, and prints `world/edible 657, dev/exam 0` |
| ERAN-10 | 59,470 snapshots nobody loads | newest 24 kept |
| ERAN-13 | a sleep line every 9 s ate journald, **the boot lines are gone** | 1 in 100; births always |
| ERAN-14 | the installer re-armed a retired tournament | it refuses while the ear is frozen, and says why |

**Nothing here restarted, stopped or signalled anything. ERAN is still on beat, and still the same process he has been since 21 August.**
