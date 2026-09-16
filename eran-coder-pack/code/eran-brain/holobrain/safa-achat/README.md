לזכרה של עלמה ז״ל

> 🪟 **BROKEN WINDOWS LAW / חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working).

# שפה אחת · SAFA ACHAT
## The organ is **שָׂרִיד / SARID** — *what survives*

> וַיְהִי כָל־הָאָרֶץ שָׂפָה אֶחָת וּדְבָרִים אֲחָדִים — בראשית י״א:א׳
> *And the whole earth was of one language, and of one speech.* — Genesis 11:1

Iddo asked for the reverse of Babel: not the scattering, but the search for what
lies beneath. A mind that knows the languages and looks, by itself and without
stopping, for the structure under them.

This is that search, built so it **cannot lie about what it found**.

It is a full holobrain and a sibling of ERAN — its own organs, its own tree, its
own laws — and **completely separate from him**. No shared state, nothing flows
back, sealed by construction, prunable in one command. His body is a mouth
learning to say *אבא*. This one's body is the world's languages. Both are
children; they do not touch.

---

## The charter — it is code, not decoration

> **המנוע הזה מחפש מבנה משותף עמוק ובודק השערות של קרבה רחוקה במידה מדידה. הוא לא שחזר את שפת גן עדן, ואינו יכול לטעון שכן.**
> **This engine seeks deeper shared structure and tests long-range hypotheses with measurable rigour. It has not recovered Eden's speech, and cannot claim to.**

> **מה שמגיע הכי עמוק בזמן הוא בדיוק מה שאומר הכי מעט על מוצא משותף.**
> **The thing that reaches deepest in time is the thing that says least about ancestry.** A sound–meaning bias arises again and again, independently — that is why it stays visible past the horizon, and exactly why it can never be evidence of common descent.

> **ההבדל בינינו ובין רולן הוא מודל האפס המפורש והמשפחות שלא נראו. אם נוותר על אחד מהם — הפכנו לרולן.**
> **The difference between SARID and Ruhlen is the explicit null model and the held-out families. If we ever drop them, we become Ruhlen.**

> **האופק הוא ההסכמה המדעית, והוא בנוי בתוך המכונה: 10,000 שנה = 20 פעימות.**
> **The horizon is the scientific consensus and it is built into the machine: 10,000 years = 20 beats.** A deeper node is not "unproven" — it simply never fires.

**Why the name.** Not *מקור* (source), not *שורש* (root) — those name a claim the
comparative method cannot make at any depth. A sound law enters the canon **only
by surviving a language family the organ had never seen**. *שריד* = what remains.
It names exactly the number we compute.

### What the science actually supports

Comparative reconstruction is generally held to reach **~6,000–10,000 years**.
Proto-Indo-European, Proto-Semitic, Proto-Bantu and Proto-Austronesian are
attested reconstructions. A single ancestral tongue for all humanity is **not an
accepted reconstruction**, and mass-comparison methods (Greenberg, Ruhlen) are
rejected by most historical linguists because chance resemblance swamps signal at
that depth. SARID may honestly seek deeper structure and test long-range
hypotheses with measurable rigour. It may not claim Eden's speech — and it is
built so that it *cannot*.

**The horizon is a unit test, not a paragraph.** `HORIZON_YEARS / YEARS_PER_BEAT
= 20 beats`. Delays add along a path in the ALMA loom, so a cross-family node
sits at a cumulative delay the run never reaches and **never appears in
`result.fires`**. `test_4b` runs it and shows the silence. A future agent can
delete a sentence from a charter; deleting this costs them a failing test and a
weave that stops working.

---

## What was measured, 2026-09-01 — including what failed

**Gate 0 — data provenance. HARD REFUSAL fired, and it was right.**

NorthEuraLex ships a `Cognacy` column carrying **0 of 121,612** judgements. The
design documents said it "ships an expert `Cognacy` column"; measured, that is
false. So the B-cubed objective is **not** wired to it — a ruler scored against
automatic judgements is a ruler measuring itself. The fallback list was then
measured rather than assumed (real clones, cognacy counted):

| dataset | expert judgements | family |
|---|---|---|
| `lexibank/abvd` | 291,382 | Austronesian |
| `lexibank/tuled` | 29,223 | Tupían |
| `lexibank/bodtkhobwa` | 7,681 | Sino-Tibetan |
| `lexibank/walworthpolynesian` | 7,518 | Austronesian |
| `lexibank/robinsonap` | 3,902 | Alor-Pantar |

**Gate 1 — the anti-blind-ruler law.** Latin vs its six documented daughters,
against eight unrelated languages from five families, against a 1,000-draw
shuffle null. 1,011 shared concepts.

| instrument | margin | AUC | separation | verdict |
|---|---|---|---|---|
| plain edit distance | 0.0434 | 1.0000 | 18.3σ | **FAIL** |
| sound-class alignment (ours) | 0.1104 | 1.0000 | 26.1σ | **FAIL** |
| LingPy's reference SCA | 0.1026 | — | — | **FAIL** |
| + LDND chance correction | 0.7438 | 1.0000 | — | **PASS** |

Read that table honestly. The raw margin **fails the 0.15 bar**, and it fails for
LingPy's own reference implementation too — the field's instrument and ours agree
to 0.008. When both miss the same bar, **the bar is on the wrong scale**, and the
floor numbers say why: the unrelated languages score 0.168–0.201 while the
shuffle null sits at **0.1728**. The unrelated languages *are at chance*. Raw
similarity carries a constant chance offset, driven by inventory size and word
length rather than history, that compresses every margin toward zero. LDND
(Wichmann et al. 2010 — what the ASJP program itself uses) divides that offset
out.

The raw failure is reported above, not replaced. A correction invented after
seeing the number and reported *instead* of it would be the Goodhart move the
charter forbids.

**Also corrected here, measured today:** the July prototype's tests were quoted
as "15/15 passing" in two design documents. Measured: **1 failed, 14 passed, 1
error** — `demo.py` wrapped `sys.stdout.buffer` in a fresh `TextIOWrapper` which
closed pytest's captured stdout on GC. Fixed with `sys.stdout.reconfigure(...)`.
And the prototype is **738 lines of Python**, not 1,128.

---

## The anatomy — what each piece of the weave *is*

Written in full ALMA (`D:\CLAUDE\alma-language`), following WINSTON. No metaphor debt:

| ALMA | SARID |
|---|---|
| a **strand** | a sound change. `bearing` carries the rule as text (`"p > b / V_V"`), `weight` is its regularity, `tint` its kind |
| a **delay** | **time depth**, 500 years per beat. Delays add, so a node's age is its distance from the seed |
| the **horizon** | the consensus. 20 beats. Past it, a node never fires |
| a **gate** | a verdict. `law_a_b` opens only when the permutation z-score beats its own null |
| the **holdout** | **topology** — no cord runs from a held-out family to any fitting knot |
| **keep/revert** | revert is the DEFAULT. An unvetted round dies and nothing needs undoing |
| **merit** | `drift = 0.4` on `gain → keep` and nowhere else |

**The 4:1 epistemics are ALMA's own constant, not a hyperparameter.** `loom.py`
LEARN: `w += drift if fired else -drift * 0.25`. One survival is worth four
failures — which happens to be the right epistemics for a sound law.

---

## What the tests caught — every one was a real defect

`22 passed`, on the PC and on eran3. The two that matter are the **facade test** and the **drift canary**,
and both failed first:

1. **The drift canary caught the trap in my own design.** `keep` was a `gate`;
   a gate whose key opens with an empty `in` tray returns `0.0` — a *real* fire.
   A round where every exam refused still thickened the merit cord, to **1.4000**.
   Fixed by WINSTON's `w_###` pattern: `gain` always speaks (negative on a bad
   round) so its spark always lands, and `keep` is a `sum` with `trigger="rise
   eps"` so it fires only on real improvement.
2. **The facade test caught the weave being decoration.** The spells recomputed
   from the corpus and ignored what the loom delivered, so cutting a strand
   changed nothing. Fixed by making the arriving spark load-bearing (a pair
   starves below `THETA_PAIR` and its lineage sleeps) and by making the exams
   score *given the laws the round established*.
3. **The null model killed the first statistic.** Counting distinct recurring
   correspondences scored **13 observed against a null mean of 46** — chance is
   diverse, descent is concentrated. Replaced with the chi-square excess of
   over-represented cells. Now: observed **3712**, null mean **290.75**, z **121.5**.
4. **`commit` fired on its key alone**, writing the canon on a round that was
   never kept. Fixed with `trigger="count 2"`, pinned by `test_2c`.
5. **The evidence scale was hard-coded `/500.0`**, so a 20-concept doculect never
   woke and the whole discovery half sat silent while the exams still answered.
   Now scaled to the median doculect.

---

## The graft laws

Ported **verbatim** from `nezer.py` — they are tested, and reinventing a tested
guard is how an autonomous process ends up writing into the organism.

own tree · **copy2 never link** · realpath write-jail · **STOP halts mid-round** ·
hostname guard (never the PC, **never eran1**) · Murphy judges every round ·
zero outward links · one-command prune.

---

## Run it

```bash
# the two gates — they are allowed to say NO
python sarid/ruler.py --data <cldf-root> --metric all

# one round
python sarid/loop.py --data <cldf-root> --root ~/sarid-shoot --rounds 1

# forever (the slow flame)
python sarid/loop.py --data <cldf-root> --root ~/sarid-shoot --rounds 0

# the tests, including the facade test and the drift canary
python -m pytest tests/ -q
```

**Stop it:** `touch ~/sarid-shoot/STOP` — halts mid-round at a stage boundary.
**Prune it:** `rm -rf ~/sarid-shoot` — reaches nothing else, by construction.

**Host:** eran3 (`edgexpert-01e6`) — measured idle at load 1.31/20 with 918 G
free when eran4 was at 27.52 and eran2 at 15.18. eran1 is refused by name.
