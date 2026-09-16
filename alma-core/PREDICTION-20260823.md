> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

> **STATUS (moved here 2026-09-06 from almido/, lean-move pass): still UNJUDGED.**
> eran2:~/almido/runs_clean holds the 18-run sweep this file describes. Nobody has yet
> computed the paired per-depth delta below to call it CONFIRMED or DEAD. Close it when
> that track reopens — do not report a verdict without the paired statistic.

# Iddo's prediction, written down BEFORE the results

**2026-08-23 10:29–10:30, his words, verbatim:**

> *"התולעת תוכיח את עצמה בדברים שהם יותר ארוכים ועמוקים ומורכבים."*
> *"בדברים פשוטים הוונילה תעקוף אותה. לדעתי."*

Written here **before a single run of the sweep finished**, because a prediction made
after the numbers is not a prediction ([[feedback_clean_experiments]]).

## The claim, stated so it can be killed

This is not "the Beit-Din neuron is better." It is a **crossover**:

| regime | Iddo predicts |
|---|---|
| shallow / short / simple | **vanilla wins** |
| deep / long / complex | **Beit-Din wins** |

A crossover is a much harder claim than "mine is better", and therefore worth far
more if it survives. A single direction could be luck; a *sign change* that tracks
depth is a mechanism.

## Why the mechanism makes it plausible

Every neuron here is a court of three seats and the ruling is the **median**, not the
mean. A median only pays for itself when there are bad seats to ignore. At 4 layers
there is almost nothing to be robust against — and the court costs capacity, because
three seats share the parameter budget one dense layer would have had. The deeper the
stack, the more chances a seat has to saturate, die, or go out of distribution, and
the more a median earns its keep.

So the prediction is not decoration. **Shallow: the court is overhead. Deep: the court
is insurance.**

## What is running (launched 2026-08-23 10:31 on eran2, detached)

- **corpus:** 40 real Darwish token tracks, **310,048 tokens** — 3.5× the first
  attempt's 89K, and split **by track**, never by segment.
- **sweep:** depth ∈ {4, 8, 16} × arch ∈ {beitdin, vanilla} × seed ∈ {17, 18, 19}
  = 18 runs, 8,000 steps each (the first attempt ran 3,000).
- params matched by the script's own `match_vanilla_width()`, not by hand.
- also still running: the shallow 10-seed replication on the small corpus, which is
  the **left-hand end** of this same prediction.

## How it will be judged

Per depth, the paired delta `vanilla_heldout − beitdin_heldout` across the three
shared seeds. Positive = Beit-Din wins.

- **Prediction CONFIRMED** if the delta is **negative at depth 4** and **positive at
  depth 16**, with the depth-16 margin larger than the seed-to-seed spread.
- **Prediction DEAD** if the sign does not change, or if the margin at every depth
  stays inside the noise — which is exactly where the first attempt landed.

## The scar this replaces

On 2026-08-23 09:59 I told Iddo "the worm won, 5.8 % better" off **one seed**. Re-runs
of that same seed gave +0.086, then +0.0034 — run-to-run drift larger than the effect
being claimed. The first sweep then died silently because it was launched without
`nohup` and went down with its ssh session, leaving one pair behind and looking
finished. Both runs now are detached and logged.

**Nothing gets reported to Iddo from this sweep until there is a paired statistic
across at least three seeds per depth.**
