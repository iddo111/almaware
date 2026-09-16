> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

# Decode-range audit — the eight remaining knobs, against all three arena tasks

**Date:** 2026-08-22 · **Box:** eran4 `~/snn-lab/arena` (mirror `D:\CLAUDE\eran-brain`)
**Subject:** `eran_agent.decode(theta)` — the ten ES-tunable knobs
**Evidence base:** `arena/structural_probe.py` → `results/STRUCTURAL-PROBE-2026-08-22.json`

---

## תקציר בעברית

שני ניסויים כבר נשרפו בגלל טווחי `decode` לא־פיזיקליים (`ctx_gain`, `trace_tau`).
בדקתי את שמונת הנותרים מול **שלוש** המשימות, לא רק מול משימת החוקים.

**מה שנמצא:**

1. **הנחה של משימה אחת נכתבה כחוק גלובלי.** התיקון הקודם חתך את `trace_tau` ל־10
   לפי משימת החוקים — אבל אותו `decode()` משרת גם DMS וגם פונג, שדורשים אופק
   קרדיט ארוך בהרבה. **חזיתי שזה ישבור אותן — מדדתי, וטעיתי:** ההפרש אפס
   (DMS ‎+0.018±0.048‎, פונג ‎+0.47±0.41‎). הסיבה: שתי הזרועות ממילא ברצפה
   (DMS = מקריות, פונג = הפסד), ואי אפשר לשבור יכולת שלא קיימת. זה פגם *רדום*,
   לא נזק מדוד.
2. **שתי טענות בביקורת הקודמת פשוט לא נכונות** (נמדדו והופרכו): אין "קיר מתמטי"
   ב־`eps_floor=0.30`, ו־`strict_scale` לא יכול להרוג יצירת אב־טיפוס.
3. **הבעיה האמיתית היא איפה החיפוש מתחיל, לא עד לאן הוא מגיע.** ב־theta=0 כל
   חיפוש מתחיל ב־`trace_tau=61` וב־`ctx_gain=4.1` — עמוק בתוך האזור האבסורדי.
4. `ne_gain` הוא **ממד מת** בכל זרוע בלי כימיה — 10% מהחיפוש הולך לכלום.
5. על `lam` — ההשערה המובילה — **לא מצאתי מנגנון**. אני אומר את זה בפירוש
   במקום להמציא הסבר.

מדידה רצה עכשיו: 6 וריאנטים, **שינוי אחד בכל פעם**, אותם 24 seeds, אותו תקציב.

---

## The method rule this audit holds itself to

The user's instruction was explicit: bounds must be **justified from task structure rather than from measured accuracy**, and any change must be measured **one at a time**.

That rule is not pedantry here — it is the correction to a specific failure. The
existing `decode_audit.py` (2026-08-22 01:00) set several of its bounds by looking
at which knob values the *succeeding seeds* happened to use:

> "1.5 sits just above the best success" · "3.0 keeps more than 2x headroom above the
> best success" · "0.35 sits just above the best success"

and then scored those bounds **on the same 24 seeds**. A bound chosen to exclude the
region where the observed failures sat will exclude the observed failures. The
resulting 24/24 is not evidence about the range; it is the definition of the range
read back. It also changed **six ranges simultaneously**, so even taken at face value
it cannot say which range mattered.

So every number below comes from `tasks.py`, `eran_agent.py` and `pong_env.py`
mechanics. `structural_probe.py` reads no accuracy field from any results file.
Where I use the recorded per-seed data at all, it is to *diagnose a mechanism* or to
*flag a confound* — never to place a bound — and it is labelled as such.

**Absurd vs suboptimal**, as used throughout:

- **Absurd** — the setting contradicts the task's own structure, so *no* policy can
  work there. The region should not be reachable.
- **Suboptimal** — the setting costs performance, but the task remains solvable and
  ES can legitimately be left to find its way out. The region may stay.

---

## Finding 0 — one `decode()`, three tasks: a rule-specific assumption written globally

*(This section was written as a prediction, then measured. The measurement went
against me. Both versions are kept, because a prediction that is quietly deleted
after it fails is worth nothing.)*

`eran_agent.decode()` is shared by **DMSTask, RuleSwitchTask and PongTask alike**.
The existing audit states plainly that it judges every knob "against the RULE-SWITCH
TASK'S OWN SCALE", then writes those rule-derived bounds into a single global table.

**The structural argument** — which still stands as a statement about the tasks:

| knob | rule-derived bound | what the other two tasks structurally require |
|---|---|---|
| `trace_tau` | `[1, 10]` | **DMS:** credit must span the delay — up to **16** steps; traces *are* cleared per episode, so a long tau cannot leak between trials. **Pong:** measured reward gaps mean **42.6** ticks (p10 20, p90 80); the ball crosses in **40** ticks. |
| `lam` | `[0, 0.9]` | **DMS:** cue energy at the choice step peaks at lam ≈ 1−1/delay = **0.9375**; the cap forbids the optimum. |
| `eps_floor` | `[0, 0.25]` | derived from 3 actions; DMS has **2** (ceiling 1−½ε, not 1−⅔ε), and Pong has no criterion at all. |

**The prediction I made from it:** applying the rule-derived `trace_tau` cap to DMS
and Pong would visibly cost performance.

**The measurement (`crosstask_tau.py`, 6 seeds, paired, same budget, one knob
changed):**

| task | orig `[1,121]` | tau10 `[1,10]` | paired Δ (tau10 − orig) |
|---|---|---|---|
| DMS delay-16 (accuracy) | 0.5354 (tau ≈ 62) | 0.5533 (tau ≈ 5.7) | **+0.018 ± 0.048** |
| Pong (reward/episode) | −2.433 (tau ≈ 64) | −1.967 (tau ≈ 5.6) | **+0.467 ± 0.409** |

**The prediction is not supported.** Both deltas are consistent with zero, and both
are nominally in the *cap's* favour.

**Why, and what it actually means.** ERAN-CTX is already at floor on both tasks —
DMS-16 sits at chance (0.50) whatever tau does, and Pong loses (~−2 reward/episode)
whatever tau does. **A cap cannot degrade a capability that is not there.** The
arena's own earlier verdict said exactly this: ERAN dies at one step of delay, and
loses to random at Pong.

So Finding 0 must be downgraded, and is: from *"the next bug is already written"* to
**a latent design defect**. A global table encodes a rule-specific timing assumption
in code that three tasks share. It costs nothing measurable today only because the
other two arms have no performance to lose. It becomes a real bug the moment either
arm works at all — which is the whole point of keeping them in the arena.

**Power caveat, stated rather than buried:** 6 paired seeds. An effect smaller than
~0.10 accuracy (DMS) or ~0.8 reward/episode (Pong) would not have been detected here.
The null is "no detectable harm", not "proof of no harm".

**Recommendation unchanged, but the reason is now prudential rather than measured:**
scope the bounds to the arm they were derived for (`RULE_KNOB_BOUNDS`), rather than
asserting them for tasks whose structure was never consulted.

## The per-knob audit

Reference numbers used throughout, all from task constants:

- **Rule** — 3 actions, `CRIT_WINDOW=10`, `CRIT_HITS=8`, `BLOCK_MAX=60`, `N_BLOCKS=6`;
  action→reward gap **0**; episode = all 6 blocks (60–360 trials); **traces are NOT
  cleared at a switch**, only at episode end.
- **DMS** — 2 actions, delays (0,1,2,4,8,16), episode = delay+1 steps, **one** rewarded
  step (the last); traces cleared per episode; the prev-action/prev-reward channel is
  deliberately held at zero.
- **Pong** — 3 actions, 200-tick episodes, ball crosses in 40 ticks, reward ±1 on
  hit/miss; traces cleared per episode.

---

### 1. `lam` — context leak · reachable **(0, 1)**

**Mechanism.** `ctx ← lam·ctx + (1−lam)·obs`, updated *after* the key is formed, then
concatenated as `[obs | ctx_gain·ctx]` and L2-normalised. `reset_episode()` zeroes it.

**What the widest value physically means.** Not what the name suggests. As lam→1 the
context does **not** become an ever-longer memory, and it does not go quiet either —
it converges to the **stationary mean of the observation stream**, i.e. a large
near-constant vector welded into every key. Measured `‖ctx‖/‖obs‖` at lam=0.99:
**rule 0.527, dms16 0.832, pong 0.765**. It stays loud; it stops carrying information.

| task | at the widest reachable lam | absurd? |
|---|---|---|
| **Rule** | a constant block that dilutes every key equally. Measured card margin at gain 1.0 **rises** with lam (0.209 at lam=0 → 0.394 at lam=0.99), because at low lam the context is the *previous card* — independent of the current one, i.e. active noise. Within-episode drift is flat (cos(early,late) ≈ 0.73 at every lam ≥ 0.5). | **No** |
| **DMS** | lam is the *only* memory. Cue energy surviving to the choice step peaks exactly at lam ≈ 1−1/delay, as theory predicts (delay 16: 0.0000 at lam=0.3, **0.023 at lam=0.95**). High lam is **required**. | **No** — and capping it is harmful |
| **Pong** | obs already carries velocity; context adds a smoothed history that costs margin (0.033 → 0.011 at lam 0.95 + gain 8.1). Useless. | **No** |

**Verdict: no reachable region of `lam` is physically absurd in any of the three
tasks.** If anything the *low* end is worse for the rule task.

**But this is where I must be straight.** The recorded data disagrees. Inside the
well-behaved `ctx_gain < 1.5` band, lam still separates success from failure at
**AUC 0.986** (successes lam ≤ 0.591, failures lam ≥ 0.481). Four separate structural
probes — context loudness, card/rule margin, within-episode drift, post-switch
addressing recovery — **failed to find the mechanism**. I am not going to invent one.
See *Open question* at the end; `lamcap` is running as a measurement, not as a
conclusion.

---

### 2. `eta_q` — action-head learning rate · reachable **[0, 0.6]**

**Mechanism.** `Q[i,a] += eta_q · plasticity() · e · rpe`, then clipped to ±20.

The knob's own range is unremarkable: 0.6 < 1, so a single update cannot overshoot.
That is what the existing audit says, and with `chemistry=False` it is correct for all
three tasks.

**It is wrong with chemistry on.** `plasticity() = ach·(1+da)·(1+ne)`, with
`ach=1.0`, `da ≤ DA_MAX = 2.0`, `ne ≤ NE_MAX = 3.0`:

```
plasticity() ≤ 1.0 · (1+2.0) · (1+3.0) = 12.0
effective rate ≤ 0.6 × 12.0 = 7.2
```

With `|rpe|` up to ~2, one update can move a Q entry by ~14 on a ±20 clip — the action
head is slammed to its rail by a single trial. This is reachable in **all three tasks**
whenever `chemistry=True` (the `chem` and `taucap+chem` arms).

**Verdict: `eta_q`'s own range is fine — suboptimal at worst. The absurd region lives
in the product `eta_q × plasticity()`, which nothing bounds.** Flagged, not fixed:
the chemistry arm measured as a clean null (−2.9 ± 2.2 pp), so this is not currently
costing an experiment. It should be bounded before chemistry is ever taken seriously.

---

### 3. `eta_v` — value-baseline rate · reachable **[0, 0.6]**

**Mechanism.** `V[i0] += eta_v · rpe`, where `rpe = reward − V[i0]`. Note `eta_v` is
**not** multiplied by plasticity, so it decouples from `eta_q` under chemistry.
`1/eta_v` is the effective averaging window.

| task | at eta_v = 0.6 (window ≈ 1.7 trials) | absurd? |
|---|---|---|
| **Rule** | V forgets ~6× faster than the rule it is meant to average over (rule lives ≥10 trials). `rpe` becomes a reward *difference* rather than a baseline error. Noisy, still signed correctly. | **No** — suboptimal |
| **DMS** | the choice-step prototype is visited once per episode and match/non-match alternates at random, so V oscillates between ±1 rather than settling near 0. Halves the useful `rpe`. | **No** — suboptimal |
| **Pong** | same, with sparser rewards. | **No** — suboptimal |

The genuinely absurd value is `eta_v = 1.0` (V copies the reward exactly, `rpe` → 0 on
the next visit, learning stops). **That value is not reachable**: the ceiling is 0.6,
which still retains 40% of the old estimate.

**Verdict: suboptimal at the top, absurd nowhere.** A bound at ⅓ is defensible from
the rule's own 10-trial timescale, but it is an optimality argument, not an absurdity
one — and the existing audit's version of it was anchored to "just above the best
success", which is exactly the move this audit exists to undo.

---

### 4. `eps0` — exploration at birth · reachable **[0, 1]**

It is a probability. `[0, 1]` is the type, not a choice. No absurd region in any task.

**One real defect, and it is not a bound.** Whenever `eps0 < eps_floor` the schedule
`eps = max(eps_floor, eps − eps_decay)` clamps on the first step and `eps0` has **no
effect whatsoever**. Measured over the ES initialisation distribution
(θ ~ N(0,1)¹⁰): **16.3% of draws**. In that region ES is perturbing a dimension wired
to nothing — in all three tasks.

**Verdict: not absurd. Partly degenerate.** The fix is a joint parameterisation
(e.g. decode `eps_floor` as a *fraction of* `eps0`), not a narrower interval.

---

### 5. `eps_decay` — exploration decay · reachable **[1e-5, 1e-1]**

**First, a semantic correction.** Despite the name this is a **linear decrement**
(`eps -= eps_decay`), not an exponential decay. The schedule length is
`(eps0 − eps_floor) / eps_decay` steps ∈ **[0, ~1e5]**.

| task | widest-value meaning | absurd? |
|---|---|---|
| **Rule** | online life is 6,000,000 steps; even the slowest schedule (1e-5) completes in ~1.7% of it. The fastest (1e-1) collapses eps to the floor in ≤10 steps. Both resolve. | **No** |
| **DMS** | same lifetime logic. | **No** |
| **Pong** | same. | **No** |

**The real observation is about the ES phase, not the range.** During evolution each
candidate is `hard_reset` and lives only `eps_per_gen` episodes — rule 6 episodes
(≈360–2,160 steps), DMS 50 × ≤17 (≤850 steps), Pong 8 × 200 (1,600 steps). At
`eps_decay = 1e-5` epsilon moves by **less than 0.02 across an entire candidate
evaluation**. So for every task, `eps_decay` is close to **inert during the search**
that is supposed to tune it; it only acts in the online life afterwards.

**Verdict: not absurd in any task; near-dead during ES; misleadingly named.**

---

### 6. `eps_floor` — residual exploration · reachable **[0, 0.5]**

**Mechanism, and why it matters more than it looks.** `act()` applies `self.eps`
regardless of `frozen_eval`, and `instrumented_rule_eval` never resets `eps`. So
`eps_floor` is a **permanent tax on the reported score**, not just a training setting.

**The existing audit's claim is false.** It states that above `eps_floor = 0.30` the
8-of-10 criterion is "mathematically unreachable", "guaranteeing a BLOCK_MAX=60
timeout every single block". That compares an *expected accuracy* (1−⅔ε = 0.80) with
a *threshold* (8/10) and concludes impossibility. But the criterion is a stochastic
sliding-window event, tested up to 51 times per block. Simulated with the task's exact
criterion logic and a **perfect** greedy policy:

| eps_floor | best-case accuracy | mean trials-to-criterion | blocks reaching criterion |
|---|---|---|---|
| 0.00 | 1.000 | 10.00 | 100.0% |
| 0.15 | 0.900 | 10.33 | 100.0% |
| 0.25 | 0.833 | 11.25 | 100.0% |
| **0.30** | 0.800 | **12.12** | **100.0%** |
| 0.40 | 0.733 | 14.82 | 99.8% |
| **0.50** | 0.667 | **19.59** | **98.3%** |

There is no wall. At the very top of the range a perfect policy still reaches criterion
in 98.3% of blocks.

| task | at eps_floor = 0.5 | absurd? |
|---|---|---|
| **Rule** | best attainable accuracy 66.7% (chance 33.3%, oracle 90.5%); criterion still reachable. | **No** — suboptimal |
| **DMS** | 2 actions, so the ceiling is 1−½ε = **75%** (chance 50%). | **No** — suboptimal |
| **Pong** | paddle speed 0.05 vs ball 0.025/tick: a random tick is recoverable on the next. | **No** — suboptimal |

**Verdict: suboptimal everywhere, absurd nowhere.** A structural bound does exist, but
it is an *optimality* bound and should be labelled as one: parity with this arena's own
oracle (90.5%) requires `1 − ⅔·eps_floor ≥ 0.905`, i.e. **eps_floor ≤ 0.1425**. One
caveat worth keeping: at 0.5 the best-case mean ttc (19.59) sits just under the
experiment's own success threshold (20) with no headroom for any learning error at all.

---

### 7. `strict_scale` — spawn strictness · reachable **[0.2, 3.2]**

**Mechanism, including an inverted name.** `k = strictness() = (0.5 → 3.0 over the
critical period) × strict_scale`, so effective `k ∈ [0.1, 9.6]`. Spawn happens iff
`sim < tolerance(i) = mean_i − k·sd_i`. A **larger** k gives a **lower** threshold and
therefore **fewer** spawns — the knob called "strictness" makes the organism *more
tolerant*.

**The existing audit's claim is false.** It caps this at 1.5 on the argument that at
k = 9.6 "the organism can no longer spawn a new prototype for the rest of its life".
Measured — real absorbed-similarity means and sds from a live agent, against the real
cosine distribution each task can produce:

| task | absorbed mean / sd (median) | lowest cosine the task produces | **k at which spawning actually dies** |
|---|---|---|---|
| Rule | 0.923 / 0.041 | −0.253 | **28.4** |
| DMS-16 | 0.9997 / 0.020 | 0.000 | **50.0** |
| Pong | 0.987 / 0.020 | −0.022 | **39.3 – 50.5** |

Maximum reachable k is **9.6**. The dead region the argument describes is **three to
five times outside the reachable range, in every task.**

**Verdict: not absurd in any of the three tasks.** Suboptimal at most. Worth noting
that rule and pong saturate the 256-prototype cap anyway at mid settings, so the
binding constraint on prototype count is `max_protos`, not this knob.

---

### 8. `ne_gain` — NE jump size · reachable **[0, 2]**

**Mechanism.** Used only in `Chemistry.observe_rpe`, which returns immediately when
`frozen=True`. `EranAgent(chemistry=False)` constructs `Chemistry(frozen=True)`.

**So in `ERAN-CTX`, `base`, `taucap`, and every variant except `chem` / `taucap+chem`,
`ne_gain` is wired to nothing at all — in all three tasks.** ES perturbs all ten
components of θ, so **10% of the search dimension is spent on a knob that cannot
affect the rollout.** It is also reported in every results file as though it were a
tuned property of the organism.

With chemistry on: `ne_gain = 2` saturates NE (cap 3.0) in two events, giving
`plasticity ×4` — which is the `eta_q` product problem in section 2.

**Verdict: not absurd — inert.** The honest fix is to drop it from θ for non-chemistry
arms (9 knobs, not 10), not to narrow it.

---

## The two already-known knobs, restated per task

Included because their fix is now known to be **task-specific**, which was not part of
the original diagnosis.

### `trace_tau` · reachable **[1, 121]**

| task | credit the task actually requires | absurd region |
|---|---|---|
| **Rule** | action→reward gap **0**; rule lives 10–60 trials; **traces cross every silent switch** (cleared only at episode end). Credit longer than the rule's own life pays post-switch reward to pre-switch prototypes. | **Yes, above ~10.** Confirmed. |
| **DMS** | credit must span the delay, up to **16** steps; traces *are* cleared per episode, so a long tau merely credits every step of the current episode — exactly what one terminal reward requires. | **None.** A cap at 10 breaks delay-16. |
| **Pong** | measured reward gaps mean **42.6** ticks (p10 20, p90 80); ball crossing **40** ticks. Credit must reach 20–40 ticks back. | **None below ~80.** A cap at 10 is physically wrong. |

### `ctx_gain` · reachable **[0.1, 8.1]**

The key is L2-normalised, so this knob sets what fraction of the unit key is context
rather than the thing being classified. Measured on the real stream, under a
**competent (85%-correct)** policy — the regime evaluation actually scores:

| ctx_gain | card margin (lam=0.3) | best rule margin at **any** (lam, gain) |
|---|---|---|
| 0.1 | 0.403 | 0.004 |
| 1.0 | 0.242 | 0.004 |
| 1.5 | 0.162 | 0.004 |
| 3.0 | 0.061 | 0.004 |
| 8.1 | 0.012 | 0.004 |

The context channel's *entire* purchase — the ability to tell "colour rule live" from
"shape rule live" on the same card — **never exceeds 0.004 at any setting**, while the
cost to card discrimination is a factor of ~34. That is the structural case, and it
does not depend on which seeds won.

**Why the channel buys so little:** ERAN does not switch rules through its key at all.
It switches through the **action head** — after a flip the old action stops paying,
`Q[i][a_old]` falls, another action wins. The context is not what enables switching,
so on this task it is nearly all cost.

| task | absurd region |
|---|---|
| **Rule** | **Yes, above ~1.5** — the card being classified becomes a minority of its own key. |
| **DMS** | **None** — the context *is* the memory; margin holds at 0.365 even at gain 8.1 (lam 0.99). |
| **Pong** | **None** — merely useless (margin 0.033 → 0.011). |

---

## Finding 9 — the ES prior, and the control that overturned my reading of it

Every ES search initialises θ ~ N(0,1), so it begins at the **midpoint of whatever
range the decode declares**. At θ = 0:

| knob | value at θ=0 | against the rule task's own scale |
|---|---|---|
| `trace_tau` | **61.0** | **6× the rule's minimum lifetime** |
| `ctx_gain` | **4.1** | card margin **0.023** — the card is ~2% of its own key |
| `eps_floor` | 0.25 | a permanent 16.7 pp accuracy tax |
| `strict_scale` | 1.7 | effective k up to 5.1 |
| `lam` | 0.5 | horizon 2 trials |

**99.46%** of ES initialisation draws give `trace_tau > CRIT_WINDOW`; **71.5%** give
`ctx_gain > 3`. So the search does not merely *permit* the absurd region — it
**begins inside it, on two knobs at once**.

**My hypothesis, written before the run:** since a squash-style cap changes both the
ceiling *and* the starting point, perhaps the caps in this project have been fixing a
**prior** while calling it a **bound**. `taushift` was built to separate them: it
leaves `trace_tau`'s ceiling at the original **121** — the whole absurd region stays
reachable — and moves *only* the start, from 61 to 10.

**The result destroys the hypothesis, and in the more interesting direction:**

| arm | trace_tau range | starts at | success |
|---|---|---|---|
| `base` (recorded) | [1, 121] | 61 | **9/24** |
| `taucap` (recorded) | **[1, 10]** | 5.5 | **15/24** |
| `taushift` (new) | [1, 121] *unchanged* | **10** | **1/24** |

Starting the search at a physically sensible `trace_tau` and leaving the bad region
reachable is **far worse than not intervening at all** — 1/24 against base's 9/24.
The failing seeds ended at `trace_tau` ≈ **107.6**: given the chance, ES climbs all
the way back to the ceiling.

**What this actually establishes**, and it is the most useful thing in this audit:

> **ES actively selects the physically absurd region. It is not falling into it by
> accident of where it starts — it is pulled there, because a long credit horizon
> improves the training objective while destroying the held-out one.**

Three consequences:

1. **Capping is the right instrument, and the only one that works.** Re-centring the
   prior is not a substitute, and on this evidence is actively harmful.
2. **A knob's range cannot be defended on the grounds that "ES will find its way out".**
   It demonstrably will not; it goes the other way. Any reachable region that is
   physically wrong for the task is a live liability, not a harmless one.
3. The train/held-out gap here is a **selection** effect, not a variance effect —
   which is also why the earlier audit's practice of choosing bounds from the
   succeeding seeds was doubly unsafe.

## Proposals, and the measurement now running

Each variant changes **exactly one knob's decode range** and leaves the other nine
byte-identical to `eran_agent.decode()` — enforced by a self-test in
`arena/range_variants.py` that samples 200 random θ per variant and asserts the diff
is a single key. Every run: the **same 24 seeds** (11·k, k=1..24), the **same
12,000,000-step budget**, the **same harness** (`bimodal.py`), against the recorded
**base 9/24** and **taucap 15/24**.

| variant | knob | change | ES start moves | argument | prediction |
|---|---|---|---|---|---|
| `gaincap` | `ctx_gain` | `[0.1, 8.1] → [0.1, 1.5]` | 4.1 → 0.8 | card margin 0.40→0.012 across the range buys a rule signal that never exceeds 0.004 | **large gain** |
| `taushift` | `trace_tau` | **ceiling unchanged [1, 121]**; only re-centred | 61 → 10 | isolates prior from ceiling | **the informative one** |
| `lamcap` | `lam` | `[0, 1) → [0, 0.9]` | 0.5 → 0.45 | *no structural mechanism found* — measured as an open question | unknown |
| `epsfloorcap` | `eps_floor` | `[0, 0.5] → [0, 0.15]` | 0.25 → 0.075 | oracle-parity bound 1−⅔ε ≥ 0.905 (optimality, not absurdity) | modest |
| `strictcap` | `strict_scale` | `[0.2, 3.2] → [0.2, 1.5]` | 1.7 → 0.85 | falsification test — the claimed dead region is unreachable | **no effect** |
| `etavcap` | `eta_v` | `[0, 0.6] → [0, ⅓]` | 0.3 → 0.167 | rule's 10-trial timescale (optimality) | small |

**`taushift` is the run that changes what we believe.** It leaves the entire "absurd"
`trace_tau` region reachable up to 121 and moves *only* the starting point to 10. If it
recovers most of `taucap`'s +6/24, then the pathology was never the reachable range —
it was that ES starts its search six times outside the rule's own lifetime. In that
case every "cap" in this project is fixing a **prior** while calling it a **bound**,
and the right repair is to re-centre the decode, not to amputate ranges that DMS and
Pong actually need.

Predictions are recorded here **before** the results are read, so that the
`strictcap`-shows-nothing case counts as evidence rather than being explained away.

---

## What I am **not** proposing

- **No global `KNOB_BOUNDS` table.** `decode_audit.py`'s bounds are rule-derived and
  would break DMS and Pong. If they survive measurement they belong to the rule arm.
- **No bound on `strict_scale` or `eps_floor` as absurdity fixes.** Both underlying
  claims are falsified above. `epsfloorcap` is run as an *optimality* proposal and is
  labelled as one.
- **Nothing retuned silently.** `eran_agent.decode()` is untouched on disk; every
  change is an additive variant class.

---

## Open question — `lam` — now half answered

The task brief named `lam` a leading suspect, and the recorded data supported it:
inside the well-behaved `ctx_gain < 1.5` band it separates success from failure at
**AUC 0.986**. Four structural probes came back negative:

1. **Context loudness** — high lam does not silence the context; it makes it constant
   (`‖ctx‖/‖obs‖` = 0.527 at lam 0.99).
2. **Card / rule margin** — card margin *rises* with lam at fixed gain (0.209 → 0.394);
   rule margin is flat at ~0.004 everywhere.
3. **Within-episode drift** — flat (cos(early,late) ≈ 0.73 for every lam ≥ 0.5).
4. **Post-switch addressing recovery** — no clean lam-dependence.

So the audit predicted a null, said openly that it had no mechanism, and ran `lamcap`
as a measurement rather than a conclusion.

**What the measurement returned** (`SINGLE-KNOB-CAMPAIGN-2026-08-22.md`):

| test | result |
|---|---|
| `lamcap` vs `base` | 8/24 vs 9/24 — **null** (+2/−3, p=1.0) |
| `tau+lamcap` vs `taucap` | 19/24 vs 15/24 — +5/−1, p=0.219 |
| `tau+gain+lamcap` vs `tau+gaincap` | 24/24 vs 21/24 — +3/−0, p=0.250 |

**The prediction was right unconditionally and wrong conditionally.** Bounding `lam`
alone does nothing. In combination it adds seeds and never loses one, and it is what
closes the last three seeds to 24/24. The brief's own framing — *"after the trace_tau
fix they became the binding constraint"* — is the accurate description; mine was not.

Two things remain true and should not be lost in the correction:

- **The observational signal still overstated the effect by a wide margin.** AUC 0.986
  is the profile of a dominant cause; the true contribution is ~3 seeds, and only
  after two other ranges are fixed. A bound fitted to that AUC would have looked
  extremely well justified.
- **There is still no mechanism.** The measurement establishes *that* `lam`
  contributes, not *why*. Every probe run here was static key geometry; the one class
  of measurement never taken is **spawn dynamics over a full lifetime** — how
  prototypes are created and consumed as `lam` varies. That is the next experiment,
  and it is the honest reason to stop here rather than write a story that fits.

## Files

| file | what |
|---|---|
| `arena/structural_probe.py` | 10 probes, reads no accuracy — the evidence base |
| `results/STRUCTURAL-PROBE-2026-08-22.json` | its output |
| `arena/range_variants.py` | the single-knob variants + the one-knob-only self-test |
| `results/STRUCTURAL-AUDIT-2026-08-22.md` | this document |
| `results/SINGLE-KNOB-CAMPAIGN-2026-08-22.md` | results, appended when the runs land |

Untouched: `eran1`, ports **8737 / 8806 / 8821** on eran4 (verified UP before and
during), and `eran_agent.decode()` itself.
