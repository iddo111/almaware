> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

# Single-knob decode-range campaign — results

**Date:** 2026-08-22 · **Box:** eran4 `~/snn-lab/arena` (mirror `D:\CLAUDE\eran-brain`)
**Companion:** `STRUCTURAL-AUDIT-2026-08-22.md` (the reasoning, written before these runs)

**Protocol.** Every arm: the **same 24 seeds** (11·k, k=1..24), the **same 12,000,000
env-step budget** (half ES over 10 knobs, half online life), the **same harness**
(`bimodal.py`), the **same success rule** fixed before any number was read (mean
trials-to-criterion < 20), the **same held-out evaluation** (24 episodes from seed
7,000,000; training only ever saw 0..4,000,000). `base` and `taucap` are the
**recorded** arms from `ARENA-BIMODAL-2026-08-21.json`, produced by this identical
harness at this identical budget on these identical seeds.

**One change at a time, against a stated reference.** Layer 1 changes one range
against `base`. Layer 2 = `taucap` + one further range, against `taucap`. Layer 3 =
`taucap`+`gaincap` + one further range, against `tau+gaincap`. All statistics are
**paired by seed** (McNemar exact on discordant seeds).

---

## The table

| arm | one change | reference | success | 95% Wilson | acc | incremental McNemar |
|---|---|---|---|---|---|---|
| `base` *(recorded)* | — | — | 9/24 | [21.2, 57.3] | 54.9% | — |
| `taucap` *(recorded)* | `trace_tau` → [1, 10] | base | 15/24 | [42.7, 78.8] | 66.4% | — |
| **`gaincap`** | `ctx_gain` → [0.1, 1.5] | base | **16/24** | [46.7, 82.0] | 67.5% | **+7/−0, p=0.016** |
| `lamcap` | `lam` → [0, 0.9] | base | 8/24 | [18.0, 53.3] | 52.6% | +2/−3, p=1.0 |
| `epsfloorcap` | `eps_floor` → [0, 0.15] | base | 9/24 | [21.2, 57.3] | 53.7% | +3/−3, p=1.0 |
| `strictcap` | `strict_scale` → [0.2, 1.5] | base | 8/24 | [18.0, 53.3] | 53.6% | +1/−2, p=1.0 |
| `etavcap` | `eta_v` → [0, ⅓] | base | 8/24 | [18.0, 53.3] | 54.7% | +1/−2, p=1.0 |
| **`taushift`** | `trace_tau` **ceiling unchanged**, start 61→10 | base | **1/24** | [0.7, 20.2] | 39.0% | **+0/−8, p=0.008** |
| **`tau+gaincap`** | + `ctx_gain` → [0.1, 1.5] | taucap | **21/24** | [69.0, 95.7] | 81.9% | +8/−2, p=0.109 |
| `tau+lamcap` | + `lam` → [0, 0.9] | taucap | 19/24 | [59.5, 90.8] | 70.8% | +5/−1, p=0.219 |
| `tau+epsfloorcap` | + `eps_floor` → [0, 0.15] | taucap | 13/24 | [35.1, 72.1] | 63.2% | +2/−4, p=0.688 |
| **`tau+gain+lamcap`** | + `lam` → [0, 0.9] | tau+gaincap | **24/24** | [86.2, 100.0] | 84.0% | +3/−0, p=0.250 |

`tau+gain+lamcap` vs `base`: **+15/−0, p=0.0001**.

---

## 1. Three ranges reproduce the six-range bundle exactly

The earlier `decode_audit.py` changed **six** ranges at once and reported 24/24.
This campaign reaches the **same 24/24 with three** — `trace_tau`, `ctx_gain`, `lam` —
and shows the other three (`eps_floor`, `strict_scale`, `eta_v`) are inert.

| ranges changed | success |
|---|---|
| none (`base`) | 9/24 |
| 1 (`taucap`) | 15/24 |
| 1 (`gaincap`) | 16/24 |
| 2 (`tau+gaincap`) | 21/24 |
| **3 (`tau+gain+lamcap`)** | **24/24** |
| 6 (earlier bundle) | 24/24 |

Ranges 4–6 of the bundle add nothing measurable. Two of them were also argued for on
grounds that are factually wrong (§4).

## 2. `ctx_gain` was the largest single defect — larger than the one that got the attention

`gaincap` alone reaches **16/24**, edging `taucap`'s 15/24, and it is the only
single-knob arm that beats base with **zero losing seeds** (+7/−0, p=0.016).

This is the knob that had *already been "fixed once"* mid-arena — that fix raised its
floor so the context would not be drowned, and left the ceiling at 8.1. The structural
probe says why the ceiling is the real problem: the key is L2-normalised, so at gain
8.1 the card being classified is ~2% of its own key. Card-discrimination margin falls
**0.40 → 0.012** across the range, while the rule signal the context buys **never
exceeds 0.004 at any (lam, gain)** — even under a competent 85%-correct policy.

The two dominant fixes are also **complementary**: `taucap` and `gaincap` succeed on
largely different seeds (both 9, taucap-only 6, gaincap-only 7, neither 2; union 22).

## 3. `lam` — inert alone, contributing only in combination

This is the subtlest result, and my structural audit got it half right.

| test | result |
|---|---|
| `lamcap` vs `base` | 8/24 vs 9/24 — **null** (+2/−3, p=1.0) |
| `tau+lamcap` vs `taucap` | 19/24 vs 15/24 — **+5/−1**, p=0.219 |
| `tau+gain+lamcap` vs `tau+gaincap` | 24/24 vs 21/24 — **+3/−0**, p=0.250 |

**Bounding `lam` on its own does nothing.** But in both combinations it adds seeds and
**never loses one** (+5/−1 and +3/−0). No single incremental comparison reaches
significance at 24 seeds; the consistent sign across two independent combinations is
suggestive, and the three-way arm is what closes the last 3 seeds to 24/24.

So the honest verdict is an **interaction**, and the framing in the original task
brief — *"after the trace_tau fix they became the binding constraint"* — is the
accurate one. My audit predicted a flat null for `lam` because four structural probes
found no mechanism; that prediction is right unconditionally and **wrong
conditionally**.

What this does *not* rescue is the observational argument. `lam` separates success
from failure at **AUC 0.986** inside the well-behaved `ctx_gain < 1.5` band — a signal
far stronger than its true effect, which is worth ~3 seeds and only once two other
ranges are fixed. A bound fitted to that AUC would have looked superbly justified and
badly overstated the case.

**The open question stays open.** There is still no structural mechanism for `lam`.
The measurement says *that* it contributes; nothing here says *why*. The follow-up is
the one measurement this audit never had: a spawn-dynamics probe over a full lifetime,
since every probe run here was static key geometry.

## 4. Four bounds buy nothing, and two rest on false arguments

| single-knob arm | vs base | on top of taucap |
|---|---|---|
| `epsfloorcap` | 9/24 — null | 13/24 — null (+2/−4) |
| `strictcap` | 8/24 — null | not run (null alone) |
| `etavcap` | 8/24 — null | not run (null alone) |

| bound | earlier argument | what measurement says |
|---|---|---|
| `eps_floor` ≤ 0.25 | "above 0.30 the 8-of-10 criterion is mathematically unreachable, guaranteeing a BLOCK_MAX timeout every block" | **False.** At `eps_floor` = 0.50 a *perfect* policy still reaches criterion in **98.3%** of blocks (mean ttc 19.59). |
| `strict_scale` ≤ 1.5 | "at the combined multiplier 9.6 the organism can never spawn a prototype again" | **False.** Spawning dies at effective k ≈ **28** (rule), **50** (dms16), **39–50** (pong). Maximum reachable is **9.6** — the region does not exist. |

Both were additionally anchored to "just above the best observed success", i.e. fitted
to the same 24 seeds they were then scored on.

## 5. The absurd region is *selected*, not merely permitted

`taushift` leaves `trace_tau`'s ceiling at the original **121** and moves only the ES
starting point, 61 → 10. Result: **1/24** — far worse than doing nothing (9/24),
p=0.008. Failing seeds ended at `trace_tau` ≈ **107.6**.

> Given the chance, ES climbs straight back to the ceiling. A long credit horizon
> improves the training objective while destroying the held-out one, so the search is
> **pulled** into the physically absurd region rather than falling into it by accident
> of where it starts.

Two consequences worth carrying beyond this experiment:

1. **Re-centring a prior is not a substitute for a bound** — here it was actively
   harmful.
2. **"ES will find its way out of a bad range" is not a defence.** It demonstrably
   goes the other way. Any reachable region that is physically wrong for the task is a
   live liability.

---

## Predictions, recorded before the runs

Written into `range_variants.py` and the audit before any result was read, so that a
null counts as evidence rather than being explained away.

| prediction | measured | verdict |
|---|---|---|
| `gaincap` → large gain | 16/24, +7/−0, p=0.016 | ✅ |
| `strictcap` → no effect | 8/24, null | ✅ |
| `etavcap` → small | 8/24, null | ✅ (null) |
| `epsfloorcap` → modest gain | 9/24, null | ❌ over-predicted |
| `lamcap` → unknown, no mechanism found | 8/24 alone; **+3/−0 in combination** | ⚠️ right alone, **wrong in combination** |
| `taushift` → separates prior from ceiling | 1/24 | ✅ informative — **refuted my hypothesis** |
| *Finding 0:* rule-derived tau cap breaks DMS + Pong | Δ +0.018 ± 0.048 (DMS), +0.47 ± 0.41 (Pong) | ❌ **refuted** |

**Three of seven were wrong.** All are kept, with the reasoning that produced them.

---

## Cross-task check (`crosstask_tau.py`)

Does the rule-derived `trace_tau` ≤ 10 cap cost anything on the two tasks that share
the same `decode()`? 6 seeds, paired, one knob changed.

| task | orig [1,121] | tau10 [1,10] | paired Δ |
|---|---|---|---|
| DMS delay-16 (accuracy) | 0.5354 | 0.5533 | +0.018 ± 0.048 |
| Pong (reward/episode) | −2.433 | −1.967 | +0.467 ± 0.409 |

**No detectable harm** — because ERAN-CTX is already at floor on both (DMS at chance,
Pong losing). A cap cannot degrade a capability that is not there. The global-table
hazard is therefore **latent, not measured**. Power caveat: 6 seeds would not detect
an effect below ~0.10 accuracy or ~0.8 reward/episode.

---

## Verified separately (`verify_dead_dims.py`, against the real agent)

- **`ne_gain` is inert whenever `chemistry=False`** — agents differing only in
  `ne_gain` (0.0 vs 2.0) produce **byte-identical** 892-step trajectories. Positive
  control passes (they diverge with `chemistry=True`). So in `base`, `taucap`,
  `gaincap` and every arm here, **10% of the ES search dimension is wired to nothing.**
- **`eps0` is inert whenever `eps0 < eps_floor`** — identical trajectories for eps0
  0.05 vs 0.25 under `eps_floor` 0.30; positive control passes above the floor. That
  region is **16.3%** of the ES initialisation distribution.

---

## Recommendation

1. **Adopt three ranges for the rule arm**, not six: `trace_tau` → [1, 10],
   `ctx_gain` → [0.1, 1.5], `lam` → [0, 0.9]. Measured 24/24, +15/−0 vs base
   (p=0.0001) — identical to the six-range bundle with half the changes.
2. **Drop the `eps_floor`, `strict_scale` and `eta_v` bounds** from `decode_audit.py`.
   All three are measurably inert; two rest on arguments that are factually wrong.
   Keep the `eps_floor` reasoning only if relabelled as *optimality* (oracle parity
   needs ≤ 0.1425), never as absurdity.
3. **Scope the table to the arm it was derived for** (`RULE_KNOB_BOUNDS`) rather than
   globally — prudential, since the cross-task harm is latent rather than measured.
4. **Never substitute a prior for a bound** (`taushift` = 1/24).
5. **Drop `ne_gain` from θ for non-chemistry arms** (9 knobs, not 10) and make
   `eps_floor` a fraction of `eps0`, retiring two dead search dimensions.
6. **Bound `eta_q × plasticity()`**, not `eta_q`. The knob's own ceiling is 0.6, but
   the product reaches **7.2** with chemistry on — the only genuinely unbounded
   quantity found in the audit. Not costing anything today (chemistry measured null),
   so flagged rather than fixed.

**Not proposed:** any bound justified by which seeds succeeded.

---

## Files

| file | what |
|---|---|
| `arena/structural_probe.py` | 10 probes, reads no accuracy — the evidence base |
| `arena/range_variants.py` | single-knob variants, layers 1–3, + one-knob-only self-test |
| `arena/crosstask_tau.py` | the DMS/Pong cap test |
| `arena/verify_dead_dims.py` | dead-dimension proofs against the real agent |
| `arena/analyse_campaign.py` | paired scoring |
| `results/STRUCTURAL-PROBE-2026-08-22.json` | probe output |
| `results/SINGLE-KNOB-CAMPAIGN-2026-08-22.json` | campaign output |
| `results/CROSSTASK-TAU-2026-08-22.json` | cross-task output |
| `results/BIMODAL-single-*.json` | 10 raw per-seed run files |

Untouched: `eran1`, ports **8737 / 8806 / 8821** on eran4 (verified UP before, during
and after), and `eran_agent.decode()` itself — every change is an additive variant.
