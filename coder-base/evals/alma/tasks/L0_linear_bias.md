# L0 — warm-up: a knot that computes `y = 3x + 7`

**Level:** trivial (sanity check — if a model fails this, it does not understand
ALMA's basic vocabulary well enough to attempt anything harder).

## Task

Write an ALMA weave (JSON per SPEC.md §8, or the voice grammar per §9) that
computes `y = 3*x + 7` for a real number `x`.

**Contract (the grader depends on these exact names):**
- The input value arrives as a **seed into a knot named `x`**.
- The result must be observable at **exactly one fringe knot named `y`**,
  which must record exactly one value per run.
- Any internal knot names/topology are your choice. You may use one knot or
  several.
- Remember ALMA's second design law: arithmetic lives in the connections.
  The multiplication by 3 belongs on a **strand's weight**, not inside a
  knot. The `+7` belongs in a knot's **bias**.

## Grading

Fully automatic and exact. `grader.py` loads your file, then for each of five
test values of `x` (including negative, zero, and a fraction) it **overwrites
only the seed targeting `x`**, runs the real `alma.Loom`, and checks the
recorded `y` equals `3*x + 7` to within `1e-6`.

```
PYTHONIOENCODING=utf-8 python grader.py L0 your_submission.json
```

Pass = all 5 cases match. There is no partial credit and no human judgment
involved — the loom either produces the right number or it does not.

A verified reference solution (2 knots + relay) lives at
`reference_solutions/L0.json` — it is not shown to the model under test, only
used to prove the task is solvable and that the grader's own logic is
correct.
