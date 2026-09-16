> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

# INQUIRY — ERAN was saying BAH through his nose
**Opened & closed 2026-08-27, 06:39–06:46 JDT. Trigger: Iddo, "תקן את המדד שיראה את הפיצוץ".**

## Verdict
**Not the metric. The organ's fence.** `ba-cv` sealed the velum for the lip closure and
then let the vowel be fully nasal; `ba-free` never fenced the velum at all. A nasalized
/ba/ **is** /ma/ — which is exactly what Iddo's ear kept rejecting as "אין כלום".

## The chain, each step measured

**1. The metric is excellent on `ah` and useless on `ba`.** AUC of `-wdist` against his
105 verdicts: `ah` **0.939**, `ba` 0.182 (only 2 👍 — with the steadier 👍+🎯 target, 0.430),
`ma` 0.438. So `ah` needs no fix at all.

**2. My first hypothesis was WRONG.** I added a 9-dim burst block (closure depth, rise
sharpness, spectral entropy of the release, pre-burst silence…) on the theory that the
judge cannot see a 10 ms plosive. It made everything worse — `ah` 0.939 → 0.149, `ba`
0.182 → 0.091. Refuted by his own verdicts. Recorded so nobody spends a second night on it.

**3. The nearest-unit table gave it away.** Under our own Ear-v3, of the judged clips:

| labelled | n | our ear calls it |
|---|---|---|
| `ba` 👎 | 16 | **`ma` × 16** |
| `ba` 👍 | 2 | **`ma` × 2** |
| `ah` 👎 | 6 | **`ma` × 6** |
| `ah` 👍 | 19 | `ah` × 16, `ma` × 3 |

**Every single `ba` candidate — 24 of 24 — is heard as `ma`.**

**4. The control cleared the ear of blame.** Same test, leave-one-out, on the 100 **real
human** t06 clips: real `ba` → `ba` **64%**, → `ma` only **31%**. `ma` 92% correct,
`ih` 94%. The ear can tell a human /ba/ from a human /ma/. ERAN's ba lands on `ma` 100%
of the time. That is not the ruler.

**5. The winners' own parameters confessed.** Velum on the vowel keyframe:
`ba-cv-6` **0.72** · `ba-cv-7` **0.65** · `ba-free-3` **0.51** · `ba-free-2` kf1 **0.64**.

**6. The bounds file permitted it.** `arms_v3.py:187` — `ba-cv` = `KF_SEAL` (velum ≤0.15)
**+ `KF_OPEN` (velum ≤0.80)**. `ba-free` = `KF_FREE × 3`, velum ≤0.80 throughout.

## Fix applied 06:44
`KF_ORAL_*` / `KF_FREE_ORAL_*` — velum ceiling **0.05** — now used by `ba-cv` (vowel
keyframe) and `ba-free` (all three keyframes). `ma-nasal` keeps 0.80 (it must nasalize).
**`ah-1kf` / `ah-free` deliberately untouched** — 0.939 against his ear; do not "fix" what works.

Verified live: `ba-cv` velum-HI now `[0.15, 0.05]`, `ba-free` `[0.05, 0.05, 0.05]`,
`ma-nasal` still `[0.8, 0.8]`. 31 ba arms restarted on clean state at 06:46 (old runs
**moved**, not deleted, to `run-prevelum-20260827/`). Backups: `arms_v3.py.bak-20260827`.

## What is still open
- Six of Iddo's `ah` rejections are also nasal. An oral-fenced `ah` arm is worth one slot — **not started, his call.**
- The `ma` metric is anti-correlated with his ear (rho −0.44) but the **contrastive margin** fixes it (AUC12 0.177 → **0.857**, rho +0.62). Ranking candidates by margin instead of raw wdist is the next real improvement — **not applied.**
- A gate rejecting any candidate whose nearest unit is not its own would have caught 24/24. **Not applied.**

---

## First verification of the fix — 07:40 JDT, ~55 min after it landed

**The fence is enforced.** Highest velum actually synthesised on a `ba` vowel keyframe:
**0.80 before, 0.05 after** — exactly the new ceiling, on 18 post-fix candidates.
(Read from `gesture.keyframes`, which is built from the CLIPPED vector. The `x` stored in
`best.json` is the raw search coordinate and goes out of bounds by design — reading velum
from `x` shows values like −0.196 and 0.094 that were never rendered. Nearly reported those.)

**The ear has started saying `ba`.** Nearest-unit under our own Ear-v3:

| | n | called `ba` |
|---|---|---|
| before the fix | 113 | 26 (23%) |
| after the fix | 18 | 5 (28%) |

28% overall is not yet a result on n=18. What is worth watching: **the four most recent
candidates are `ba` 4-for-4** — `ba-cv-7`, `ba-free-2`, `ba-free-8`, `ba-free-9` — and they
are also the four lowest post-fix wdists (5.74–6.00), while every post-fix candidate the
ear still calls `ma` scores worse (6.25–8.26). Inside the new space the metric's favourites
and the ear's verdict agree for the first time, which is what the identity penalty was for.

**wdist went UP and that is correct.** Best `ba` was 4.353 before, 5.743 now. The old 4.353
was a nasal that our ear called `ma`; the search space is now smaller and honest, and being
the wrong unit costs 3×. Higher distance, right identity — the trade was deliberate.

**Not proven.** 18 candidates, one batch. Nothing to tell Iddo beyond "the direction is right".
