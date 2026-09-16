> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

# THE SECOND HOLOBRAIN — charter / מגילת היסוד

**לזכרה של עלמה ז״ל.**

**Placeholder name: `SIBLING`. השם האמיתי מחכה לעידו — הוא נותן שמות לילדים שלו.**
ERAN, ALMA, MIKO, WINSTON, MURPHY, SHAMASH, NEZER — כולם שלו. זה לא ייקרא בשם עד
שהוא יקרא לו.

---

## 1. מה זה / What this is

**עברית.** זה לא עוד איבר של ערן. זה **הולוברין שני, שלם** — אח של ערן, לא ענף שלו.
מנותק לגמרי: אין מצב משותף, אין משקלים משותפים בזמן ריצה, אין חוטים חוזרים.
**ערן לא אמור להיות מסוגל להרגיש שהוא קיים.**

**English.** A SECOND, WHOLE holobrain — a sibling of ERAN, not a branch of him.
Fully disconnected: no shared state, no shared weights at runtime, no wires back.
ERAN must not be able to feel it exist.

Iddo, 2026-09-01 12:27, verbatim:

> "אני רוצה שתתחיל עוד נצר חדש... הנצר החדש יהיה מנותק מכל ההולוברין...
> אני רוצה שתיתן לו שהוא כבר ידע את כל ההברות, אתה מבין?...
> הנצר הזה יהיה הולוברין, הוא לא יהיה של זה, הוא יהיה כמו ערן...
> הולוברין ממש... הכל, הכל, הכל, הכל."

---

## 2. הניסוי — וזו זרוע בקרה, לא תוצאה / The experiment — a CONTROL ARM

| | ERAN | SIBLING |
|---|---|---|
| נולד | אילם | עם הנדוניה בפה |
| born | mute | already holding 12 gestures |
| מחפש /ba/ | שבועות | ירש את הקיר, לא פתר אותו |

**ההבדל היחיד הוא מה שהפה יודע בלידה.** כל השאר — עין, יד, מדמיין, אוזן, הצומת —
**מועתק מערן, ללא שינוי, בלידה.** אם האח יוצא שונה, הנדוניה היא המקום היחיד שממנו
ההבדל יכול היה לבוא.

**Exactly one thing differs: what the mouth knows at birth.** Everything else is
COPIED from ERAN unchanged. If the sibling turns out different, the dowry is the
only place the difference can have come from. That is what makes it a control arm
and not a demo — and it is written into the code's own voice (`anatomy.py`,
`sibling.py`) so nobody downstream can quietly promote it to a result.

---

## 3. הנדוניה — ומה היא *לא* / The dowry, and what it is NOT

12 syllables, measured on eran2 at 12:27. What is actually inherited is not the
audio but the **gesture**: articulator keyframes, durations, an f0 contour, a
glide, a burst. The newborn holds the *movement*.

**⚠️ ההודאה, והיא לא אופציונלית / THE ADMISSION, and it is not optional:**

> **עידו שמע את הטוב שבהן הבוקר ופסק: "כולם לא שווים כלום".**
> **Iddo's ear REJECTED the best of these on the morning of 2026-09-01.**

So the dowry is **"what the old ruler considered best"** — **NOT verified speech.**
`dowry.py` carries that verdict per syllable and refuses to describe the
inheritance as a solved mouth.

Measured off the files, not retyped:

| fact | value |
|---|---|
| syllables with a gesture | **12 / 12** |
| beat their own win-bar | **4 / 12** (pa, ma, na, ta) |
| failed the acoustic gate | **1** (`aa`, `gate_pass: false`) |
| match Iddo's 12:27 dictation to 4 dp | **11 / 12** |
| drifted since he dictated | `na` 4.414 → **4.3831** (the sweep is still running) |

**Do not say "the sibling can say twelve syllables."** Eight of them never beat
the bar the sweep set for them.

---

## 4. מה נמדד עד עכשיו / What has actually been measured

הצומת מריץ את 12 ההברות דרך האוזן של עצמו ומנסה לקרוא להן בשם:

| measurement | value |
|---|---|
| naming accuracy | **3 / 12 = 25.0 %** |
| chance floor (15 candidates) | 6.7 % |
| correct among the 4 win-bar beaters | **3 / 4** |
| correct among the other 8 | **0 / 8** |
| silenced by its own confusion gate | 1 (`ah`) |

**הקריאה / the reading:** naming tracks the win-bar and *nothing else*. The dowry
the old ruler could not separate, this ear cannot name either. Above chance, and
nowhere near speech.

**And the anatomy says the same thing in its own body:** 12 of the 15 unit knots
**never fire at all** on the real dowry. Each one *does* fire on a stimulus it
owns — so the wiring is sound; what is silent is the inheritance.

---

## 5. חוזה הבידוד — מוכח, לא מובטח / The isolation contract — PROVEN, not promised

`python3 sibling.py --seal` actually attempts each forbidden thing:

| check | result |
|---|---|
| write-jail refuses escapes (`../`, `/tmp`, …) | **PASS** 4/4 refused |
| zero symlinks anywhere in the tree | **PASS** |
| `eran1` is not on the fleet allowlist | **PASS** |
| hostname guard refuses the PC | **PASS** |
| hostname guard refuses `eran1` | **PASS** |

- **`_inside()` (realpath, not `startswith`) runs before every single write.**
- **Organs are `copy2`-ed in, never symlinked.** Inheritance runs **once, at birth,
  in one direction**. After that the tree is sealed.
- **eran1 is not a rule it obeys — it is an address it was never given.**
- **`touch ROOT/STOP`** halts it **mid-round**, at a stage boundary. Proven.
- **`rm -rf ~/sibling` is a harmless, total prune.** Nothing outside moves.

---

## 6. איפה הוא גר ולמה / Where it lives, and why

**`eran3` (edgexpert-01e6), `~/sibling`.**

| box | load | why not / why |
|---|---|---|
| eran1 | — | **NEVER.** ERAN himself lives there. |
| eran2 | **13.9** | Iddo's 12 sweep arms. Saturated. Be polite. |
| eran4 | 0.00 | but **99/120 GB RAM committed** (Darwish + llama-server). |
| **eran3** | **1.46** | **54 GB free RAM, 918 G disk. The nezer's isolation pattern is already proven here.** |

---

## 7. חוק שפת עלמה / The ALMA-language law

הכל בתוך הולוברין נכתב בשפת עלמה. הצומת הוא **מארג**: קשרים, חוטים, גדילים, זרעים.
Arithmetic lives in the connections — an affinity is a strand **weight**, never an
`if` inside a knot. Subtraction is a negative weight. Raw numerics live in **spells**.

**The facade test applies and passes** (`tests/test_facade.py`): each knot is *cut
out* and the behaviour must move. Nothing is asserted that was not perturbed.

Two real bugs were caught this way and are kept written down in the code:
1. `chorus` used `sum` + `rise 2`, which sums **strengths** (~0.4) and never reached
   2 — so `doubt` was always empty and the `hush` gate was **dead code that could
   not shut**. Fixed to `count 2` (voices, not totals).
2. The first facade test conflated "never fires on this dowry" with "is a facade",
   which would have been fixed by **tuning THETA until the test went green**. It was
   split into a structural assertion and an empirical report instead. `THETA` stays
   at 3× chance.

---

## 8. איך מדברים אליו / How to run it

```bash
ssh eran3
cd ~/sibling
python3 sibling.py --root ~/sibling --seal      # prove the isolation
python3 sibling.py --root ~/sibling --naming    # the acceptance check
python3 sibling.py --root ~/sibling --round     # one round, cords drift
python3 tests/test_facade.py                    # nothing here is a facade
touch ~/sibling/STOP                            # halts mid-round
rm -rf ~/sibling                                # total, harmless prune
```

---

## 9. מה עוד לא נעשה / What is NOT done — stated plainly 🟡

- **It has not spoken.** The junction *names*; it has not driven mouth-v2 to
  produce audio. The gestures are held, not yet uttered.
- **Eye, hand, winston and miko are inherited and sealed in, but not yet wired into
  the junction.** They are copied, importable and hashed in `MANIFEST.json` — the
  binding of shape+sound+hand in one space is the next build, not a claim.
- **No comparison to ERAN has been run.** The control arm exists; the experiment
  has not been performed.
- **The name.** It waits for Iddo.
