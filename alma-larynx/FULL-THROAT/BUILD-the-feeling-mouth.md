> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

# THE FEELING MOUTH — build proposal
# הפה שמרגיש — הצעת בנייה

**Iddo, 2026-08-30 04:55:** *"קח את הכל וגם תריץ את מיקו האמיתי... ותתן הצעה לבילד.
אפשר להתחיל מפה לבד — לבנות פרופריוצפטורים בפה ואחר כך בכל הפה והגרון.
אין לי בעיה לפתור את החידה אות אות."*

---

## 0. Why proprioception is not an accessory — it is FACTOR ONE
## למה פרופריוצפציה אינה תוספת — היא הגורם הראשון

MIKO's own learning rule (`miko/model/loop.py`, `ThreeFactor`) takes exactly three inputs:

| factor | what it is | where it comes from in a mouth |
|---|---|---|
| 1 | pre-synaptic activity | **what the mouth FELT** ← the proprioceptors |
| 2 | post-synaptic activity | what the motor unit did |
| 3 | one global scalar | the ear says right, or wrong |

**Without proprioceptors there is no factor 1, and MIKO cannot run on a mouth at all.**
Factors 1 and 2 lay a tag that changes nothing; factor 3 captures it. *Nothing travels
backwards* — which is the whole reason this rule can drive real hardware. You cannot
differentiate through silicone, air and a microphone. Backprop needs a differentiable
body. MIKO does not.

**בעברית:** בלי פרופריוצפטורים אין גורם ראשון, ומיקו לא יכול לרוץ על פה בכלל. אי אפשר
לגזור דרך סיליקון ואוויר — ולכן דווקא החוק הזה, שלא צריך גרדיאנט, הוא היחיד שמתאים לחומרה.

And the world sweep agrees from the other side: **Waseda needed tactile sensors and an
intraoral pressure sensor to learn obstruents, because auditory feedback alone was
insufficient for /t/ and /d/.** Two independent arguments, one conclusion.

---

## 1. Phase 0 — ONE STRAND, ONE EVENING
## שלב אפס — גיד אחד, ערב אחד

Do not build a tongue. Build **one sensing strand** and find out whether the physics
is on our side. Everything below depends on this and nothing else does.

**Cast:** a silicone strip about 60 × 12 × 4 mm with a single conductive-silicone strand
running down its length, a thin copper wire crimped into each end.

**Materials — most already on the shelf:**

| item | have? | note |
|---|---|---|
| Shore 10A silicone | ✅ in inventory | the strip body |
| carbon black (or graphite powder) | ❌ **buy** | the conductive filler, ~10–20% by weight |
| thin stranded copper wire | probably | the two leads |
| Arduino | ✅ in inventory | one analog pin, one fixed resistor, a voltage divider |

**Measure, and write the numbers down:**
1. R at rest, and R at 1, 2, 3, 4, 5 mm of deflection. Is it **monotonic**?
2. Cycle it 100 times. What is the **hysteresis** and the spread?
3. Leave it an hour under constant strain. What is the **drift**?

**Acceptance — decide honestly:**
- monotonic over the working range, repeatable within ~10%, drift bounded and correctable
  → **go to phase 1.**
- not monotonic, or drift swamps the signal → **go capacitive** (§4), do not patch it.

Cost of finding out: roughly ₪50 and an evening. This is the cheapest decisive experiment
in the whole project.

---

## 2. The ladder after that
## הסולם שאחרי

| phase | what | why |
|---|---|---|
| **1** | a 2×2 sensing patch | recover local 2-D deformation, not just one axis |
| **2** | the sensing tongue — 6 strands in a cross | curvature **and direction**. Endo (Tokyo Denki) proved a soft tongue can discriminate bending direction this way |
| **3** | **palate contact + intraoral pressure** | this is precisely what Waseda needed for the plosives. Eight letters wait here: **ד ט ת ג כ ק ב פ** |
| **4** | **the pharynx** | **ח ע**. Nobody on earth has built a pharyngeal constrictor. This part is ours to be first at |

---

## 3. The letter ladder — what to chase, in what order
## סולם האותיות

Iddo: *"אין לי בעיה לפתור את החידה אות אות."* Then the order should be by **what each
letter costs**, not by the alphabet:

| # | letter | why it is next | what it needs that we do not have |
|---|---|---|---|
| 1 | **/a/** (a vowel, not a letter) | ERAN already found it digitally. Getting it out of hardware proves the loop closes at all. | nothing — this is the commissioning test |
| 2 | **ה** | glottal fricative: airflow, no voicing, no articulator | fold abduction |
| 3 | **ל** | Dresden has a **measured, printable** /l/ tract already on our disk | a tongue tip, eventually |
| 4 | **ס ש** | Dresden has both, printable and measured | the pressure: sibilants want up to **4.8 kPa**, ten times a vowel |
| 5 | the eight **plosives** | the whole reason for phase 3 | contact sensing. The ear will not do it |
| 6 | **ח ע** | last, and first in the world | a pharyngeal squeeze that does not exist anywhere |
| 7 | **ץ** | an affricate; zero physical models exist since 2015 | closure→hiss timing |

---

## 4. The three sensing methods, compared honestly
## שלוש השיטות, בכנות

| method | for | against | verdict |
|---|---|---|---|
| **resistive conductive silicone** | one material family, casts into the same pour, ~₪50, no special chip | drift, hysteresis, nonlinearity | **START HERE** — cheapest way to learn the truth |
| **capacitive / dielectric elastomer** | linear, low drift, and **Endo discriminates bending direction with it** | three layers to cast, needs a capacitance-to-digital chip | **phase 2**, or phase 0's fallback |
| **optical** — light through the silicone | immune to electrical drift; reuses our own optical-loop work (measured 7.1 bits per round trip, 2026-08-22) | an emitter and detector per channel, light leaks between channels | keep as the fallback if both electrical routes drift |

Magnets and Hall sensors work well but put rigid parts inside a soft tongue, which is the
one thing a soft tongue exists to avoid.

---

## 5. What this does NOT claim

- Nothing here has been built. **Zero of the 22 letters come out of any hardware we own.**
- The MIKO run in `miko_mouth.py` is a **simulation** of the body. It decides whether the
  learning rule is worth wiring to hardware. It does not prove any sound.
- The scale question — adult 180 mm versus a child's tract — is **still open and still
  Iddo's**. Every number above is scale-independent.

*Filed 2026-08-30 by claude-cli, alongside `miko_mouth.py`, `hebrew22.py`, `WORLD-MAP.png`.*

---

## 6. ⚠️ SECTION 0 IS NOW PARTLY OVERTURNED — by three of my own runs
## שלוש הרצות שלי הפכו את סעיף 0

**2026-08-30 05:33.** MIKO's ThreeFactor was run against size-matched controls on a
simulated mouth, three times. It lost every time.

| run | result |
|---|---|
| `miko_mouth.py` — find one posture | random **0.000** vs miko 0.318 median. Random won 8/8 seeds |
| `miko_mouth_transfer.py` — 15 targets in a row | random best at every stage, 22.2 → 16.8 trials; miko worst, 37.7 → 31.1 |
| `miko_mouth_dims.py` — 5 / 10 / 20 stations | random wins at **every** dimension: 20.6 / 16.7 / 15.0 vs miko 41.7 / 35.0 / 29.9 |

**Two errors of mine, named:**
1. In run 1 the "random" arm was **not random** — every arm kept a posture only if the ear
   liked it, which makes it a random-mutation **hill climber**. In five smooth dimensions
   that simply solves the problem, leaving a learner nothing to contribute.
2. In run 2 the script printed *"miko LEARNED — 17.6% improvement"*. **Random showed 24.2%
   on the same metric, and random has no memory.** The metric cannot separate learning from
   noise, so its verdict was void. Do not trust that line.

**And the finding that settles it:** matching two formants is a **2-dimensional goal** no
matter how many motors exist. Adding stations adds *redundancy* — more ways to reach the
same sound — not difficulty. That is why random got **better** with more stations, and why
**this task can never justify a learner at any scale.**

### What this changes in the build

- **The first hardware does not need MIKO.** A servo, a microphone, and an accept-if-the-ear-
  liked-it rule is enough to find a posture. That is far cheaper and simpler than §0 implied.
- **§0's argument still stands for the plosives**, because it never rested on this simulation:
  Waseda *measured* that auditory feedback alone was insufficient for /t/ and /d/. Touch is
  still required there.
- **The learner's real job is TIME, not posture** — and time is precisely what I did not test.
  Sawada needed a cerebellar spiking network for plosive *release timing*; Yoshinaga found
  the /su/–/zu/ contrast is a **20-60% temporal overlap** of hiss and voice. Sequence, timing
  and a body that drifts (Dresden measured folds that stop oscillating over 8 weeks) are where
  a hill climber has nothing to offer. **That is the next honest test of MIKO, and it has not
  been run.**

*Nothing above was copied from memory; every number was measured tonight and the scripts are
beside this file.*
