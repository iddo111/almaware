> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

# CODER (eran3) — 3 things that are Iddo's call, not mine
# קודר (eran3) — 3 דברים שהם החלטה של עידו, לא שלי

**2026-09-06, claude-cli-REV-coder.** Code revision of the coder model
(`eran3:~/coder-train`, Qwen3.5-4B-Base continued pretraining).
14 defects found. **11 are fixed as patches** (diff + proof, in
`_deliverables\code-revision\eran3-patches\`, **nothing applied on eran3** —
`coder-train.service` PID 1594129 was never touched, restarted, or signalled).
**These 3 are not mine to decide.**

**2026-09-06, claude-cli-REV-coder.** רוויזיית קוד למודל הקודר.
נמצאו 14 ליקויים. **11 תוקנו כטלאים** (דיף + הוכחה) — **שום דבר לא הופעל על eran3**,
התהליך החי לא נגע. **שלושת אלה מחכים למילה שלך.**

---

## 1. CODER-03 — what happens at step 1600? (~430 hours from now)
## 1. CODER-03 — מה קורה בצעד 1600? (בעוד ~430 שעות)

**The situation.** `max-steps` is 1600. The run is at step 71 as I write this,
1000 s per step, ETA 425 h. At step 1600 `train.py` writes status `finished` and
exits 0. The unit says `Restart=on-failure`, so systemd correctly leaves it
stopped — but its own header says **"PERMANENT. Iddo 2026-09-05 23:58: every
training run never stops."** Those two sentences cannot both be true.

**What I fixed without asking:** the watchdog no longer restart-loops a finished
run (it used to reload the 47 GB checkpoint, run `range(1600, 1600)` = zero
steps, exit, and be restarted again until the crash-loop cap escalated a
*completed* run to BROKEN). It now reports `VERIFIED: run complete, awaiting a
human decision`.

**What I did not decide** — three different answers, all defensible:

| option | what it means | cost |
|---|---|---|
| **second cycle** | new cosine over the same 756 M tokens (epoch 2) | another ~430 h, diminishing returns unknown |
| **new food** | build a bigger/different corpus first | changes what the coder is fed → your word by law |
| **stop and export** | 1600 steps is the run; export, score, serve | needs someone to consume the model (see #3 below) |

**מה שצריך ממך:** מה קורה בצעד 1600 — סיבוב שני על אותו אוכל, אוכל חדש, או עצירה
וייצוא. **בלי תשובה, בעוד 430 שעות הריצה פשוט תיעצר ותשב.**

---

## 2. CODER-13 — 98 GB of abandoned run state, on a disk that is 84% full
## 2. CODER-13 — 98 ג'יגה של שאריות ריצה נטושה, על דיסק ב-84%

Measured on eran3 today: `/` is 3.6 T, 2.9 T used, **561 G free, 84%**.

| path | size | what it is | my recommendation |
|---|---|---|---|
| `~/coder-train/ckpt/step_00001017` | 47 GB | the OLD batch-8 run's last step — **the provenance of `init_weights_step1017.pt`, which seeded the live run** | **KEEP** |
| `~/coder-train/init_weights_step1017.pt` | 16.8 GB | the extracted fp32 masters the live run started from | **KEEP** |
| `~/coder-train/ckpt/step_00001000` | 47 GB | one step before it, from the same abandoned run | delete? |
| `~/coder-train/ckpt-keep/step_00000800` | 48 GB | older still, same run | delete? |

**≈ 95 GB recoverable.** Deleting training artefacts is not a janitor's decision
and I will not do it on a hunch — the abandoned run is the only record of *why*
the hyperparameters were changed on 09-05.

**What I already patched (no permission needed):** `--ckpt-dir` no longer has a
silent default. It used to fall back to `<out>/ckpt` — that abandoned run — so
`train.py --resume auto` with any config lacking a `ckpt-dir` key (and
`train.config.json.bak-mb1ga8` is exactly such a config) would have quietly
resumed the *dead* run at step 1017 with block 8 and reported it as normal.

**מה שצריך ממך:** למחוק את שני הצ'קפוינטים הנטושים (~95 ג'יגה) או לא.

---

## 3. CODER-14 — the unit and the watchdog disagree about a human stop
## 3. CODER-14 — היחידה והשומר חלוקים על "עצירה אנושית"

Two files, on the same box, encoding opposite policies:

- **`coder-train.service`** says: *"train.py exits 0 in exactly two cases: the
  pass COMPLETED, or a human stopped it. **Neither should be restarted.**"* — and
  enforces it with `Restart=on-failure`.
- **`watchdog.py:719`** restarts **any** not-alive unit as long as
  `~/coder-train/ENABLED` exists. So `systemctl --user stop coder-train` is
  undone within 5 minutes.

This is not theoretical: the 09-05 pause for the big models had to stop
`coder-watchdog.timer` by hand as part of the procedure
(`PAUSED-BY-BIGMODELS.txt` records it).

Under your standing order — *"every training run never stops"* — the watchdog's
behaviour may be exactly what you want. But then **the unit's comment is a lie**,
and the next person to read it will believe it. One of the two has to change:

- **(a)** the watchdog honours `status: stopped` + exit 0 as "a human stopped it,
  leave it alone" → the pause switch becomes `rm ENABLED` (or a PAUSE file), and
  the timer never needs touching again; **or**
- **(b)** the unit becomes `Restart=always` with `RestartPreventExitStatus=1 3 5 6`
  and the comment is rewritten to say the watchdog owns the restart policy.

I lean to **(a)** — it gives you one obvious pause switch and stops the timer from
being a hidden second authority — but this is a policy question about your
machine, so it is yours.

**מה שצריך ממך:** איזו מהשתיים. (אני נוטה ל-(א): מתג עצירה אחד ברור.)

---

## Also worth your eye (not a decision, an observation)

The loss **rose** during this session: step 53 = 1.06829 (11:58) → step 71 =
1.44677 (17:04). Per-step sd on this run is 0.085, so that is a real move, not
noise. It may be nothing — the run is 71 steps into 1600 and warm-started from
another run's weights — but the patched watchdog will now say so with an error
bar instead of flipping between "increasing" and clean on noise. **Nothing was
changed in response to it. I am only telling you it happened.**

*הפסד האימון עלה מ-1.07 ל-1.45 במהלך היום. לא נגעתי בכלום בגלל זה — רק מדווח.*

---

## What DOES have an answer now (11 patched defects, none applied)

`D:\CLAUDE\_deliverables\code-revision\eran3-patches\` — diffs, proofs, and the
apply instructions. Every proof **fails against the code on eran3 today** and
**passes against the patched code**. Headline: the watchdog counted one real
restart twice and could burn its whole crash-loop budget on two real events; a
NaN would have restarted forever every 60 s; a SIGTERM on a save step wrote the
same 47 GB checkpoint twice; **and nothing anywhere ever loads the trained
weights — the held-out set has not been scored since the base model, twelve
hours before training began.** That last one is the real hole, and `eval_ckpt.py`
in the patch set is the thing that closes it.
