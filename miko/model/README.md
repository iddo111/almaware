> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

# מיקו · MIKO — the model

**לזכרה של עלמה ז״ל.**

Started 2026-08-29 21:44 on Iddo's word: *"תתחיל לכתוב את המודל"* —
*"אני רוצה שיהיה לו כל הביולוגיה והקבלה והלוגיקה"* —
*"עם פידבק לופ סגור תמיד למידה עצמית — הוא הולך ומשתבח עם הזמן."*

This README states what the code **does**. It never states what it achieves.
Achievements live in numbers, below, each next to its control.

---

## The files

| file | what is in it |
|---|---|
| `alma.py` | the substrate — byte⊕letter⊕sound binding, multi-weight synapse, the dendritic bump, צמצום/homeostasis |
| `sefirot.py` | the kabbalah as structure — three columns as the court's seats, דעת as the coincidence gate, the ten channels, שבירת הכלים |
| `middot.py` | the logic curriculum — 13 middot, classical forms, fallacies; Hebrew and English |
| `logic.py` | קל וחומר with the דיו ceiling as a `min`; the held-out-BY-FORM split; the degenerate-form detector |
| `miko.py` | the model — question + page → ruling, score, dissent, ten channels. Plus `Vanilla`, the matched control |
| `loop.py` | אור חוזר — the closed feedback loop: JEPA, scars (pain/pleasure), Iddo's taps, curiosity, צמצום, תיקון |
| `bench.py` | the three metrics, stated before training |

---

## Numbers that exist (2026-08-29, CPU, this machine)

| what | result | control | verdict |
|---|---|---|---|
| dendritic bump solves XOR alone | **1.00** | vanilla unit 0.50 | ✔ reproduced |
| דיו ceiling holds (train + eval) | overshoot **0.0** | — | ✔ structural, exact |
| `LayerNorm(1)` output | **0.0 for every input** | — | ✔ scar found |
| corrupted seat — **saturated** | bloc **0.89** | mean 27.26 · median 1.37 | ✔ bloc best, 30× |
| corrupted seat — **zeroed** | bloc 0.77 | mean **0.61** · median 0.73 | ✘ mean won |
| corrupted seat — **inverted** | bloc 1.40 | mean **1.23** · median 1.36 | ✘ mean won |
| three-factor: tag with no signal | weight moves **0.0** | — | ✔ a tag alone does nothing |
| three-factor: one +1 scalar | weight moves 7.8e−4 | — | ✔ learns with no gradient |
| seat separation under training | columns 3.70 | plain 2.96 · bribe 31.5 | inconclusive — wrong metric |
| JEPA falls with no labels, 6 turns | 1.1149 → 0.9910 | — | ✔ the loop closes |
| pain/pleasure asymmetry, 30 days | pain −0.76→−0.56 | pleasure +0.54→+0.14 | ✔ as designed |

**The robustness headline, honestly: the court buys robustness only against a LOUD
corrupted seat — and there it is worth 30× — while a plain mean is slightly better
against a silenced or inverted one.** This independently reproduces the line already in
`ALMA-BIOLOGY.md` (*"bought robustness only against saturation"*), and it matters, because
the failure a search organ actually meets is the page that screams.

**And on the case where the court matters, the bloc ruling beats the median Iddo rejected
(0.89 vs 1.37).** His halakhic ruling — *"בית דין אמיתי עם הכרעה, לא חציון"* — and the
measurement point the same way.

## ⚖️ His rulings of 2026-08-29 21:30–21:41, obeyed in the code

| his words | what changed |
|---|---|
| *"בית דין אמיתי עם הכרעה, לא חציון"* | the ruling is **אחרי רבים להטות** — the majority of the agreeing bloc. Not a median. `ColumnTriad.rule` |
| *"אין תיקו בבית דין"* | **no תיקו anywhere.** MIKO rules every time and marks it במחלוקת. The band is deleted, not disabled |
| *"מישהו שאומר לו זה כך או כך, אבל בכל זאת הוא נוירומורפי ולומד לבד"* | the **three-factor rule**: local pre×post trace × ONE right/wrong scalar. No gradient. `loop.ThreeFactor` |
| *"אני רוצה שמיקו פשוט יהיה מנוע חכם שיביא דברים נכונים וטובים"* | numbers stay in `bench.py`; they are not the goal, they are the guard |

Still owed from that night, his own untested variant: **a court BETWEEN each pair of
layers** rather than inside the neuron.

---

## ⚠️ The scar found while building this — the real cause of the 48.2 %

`almido-search` was archived on 2026-08-20 because its logic model scored **48.2 % on
unseen forms, below a coin flip**, and that failure had been filed in memory as an
achievement.

Building `logic.py` on 2026-08-29, a live test of the recovered code showed why:

```
nn.LayerNorm(1)  normalises over a ONE-element axis  →  output is identically 0
```

The archived worm built **both** its GIST attention scorer and its logic verdict head as
`Triad(d, 1)`, and `Triad` ended with `nn.LayerNorm(d_out)`. So:

* the **verdict head emitted a constant** for every input — the model could not express an
  answer, which is exactly why train loss sat at 0.666 against a chance of 0.693;
* the **attention was uniform** — "attention pooling by a court" was mean pooling.

Verified directly against the archived file, not inferred:
`Triad(32,1)` on two totally different inputs returns `[0,0,0,0]` both times.

**It was never the Beit Din, never Ramchal, never the curriculum. It was one line.**
`bench.py::layernorm_scar` is now a permanent regression test.

---

## What is NOT proven — read before believing anything

* that the court beats a vanilla net of matched size **at ranking**
* that **dissent predicts error** — the court's own central claim
* that k>1 weights per connection beat k=1 at **equal scalar budget**
* that opposed columns beat a random-init triad **on the metric that matters**
* every logic number: the curriculum has not been trained since the fix

## What is BLOCKED

`miko/PLAN.md` step 1 wants the **156 fleet-scored relevance pairs** at `data/pairs.jsonl`.
**That file does not exist** — the archive has no `data/` directory at all. Memory recorded
"295 teacher-scored pairs and climbing" on **eran4** on 2026-08-19; if they survived, they
are there. Until real pairs are in hand, relevance and calibration do not run, and **no
synthetic substitute will be used** — synthetic corpora transfer at chance in this project
and that scar is already paid for.

## Standing rules

* Never train on the PC. The fleet, never eran3 (Iddo's personal box).
* Every experiment has a vanilla control of matched size, or it does not count.
* **The last line of every training log is read out loud** before anything is written to
  memory. The 48.2 % line sat unread for a day.
* Findings ship marked **במחלוקת** when the seats disagreed. No Google result ever tells
  you it is contested. MIKO's does.
