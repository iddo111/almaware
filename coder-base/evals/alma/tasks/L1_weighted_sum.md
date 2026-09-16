# L1 — a single linear neuron (dot product + bias)

**Level:** easy. This is the atomic operation every neural network is built
from: `y = w·x + b`. If ALMA can express this cleanly, it can express any
feed-forward layer, just wired out by hand, one weight per strand.

## Task

Implement a single linear neuron with **three inputs** and these exact,
fixed weights and bias:

```
w = [0.5, -0.25, 2.0]      b = -1.0
y = 0.5*x1 - 0.25*x2 + 2.0*x3 - 1.0
```

**Contract:**
- Inputs arrive as seeds into knots named exactly `x1`, `x2`, `x3`.
- Output observable at one fringe knot named `y`, exactly one recorded value
  per run.
- The three input sparks must reach the summing knot **on the same beat**
  (pick equal delays, and use `trigger="count 3"` — or equivalent — so the
  knot waits for all three before it fires; SPEC.md §6 `rise` also works if
  you prefer temporal integration over an exact count).
- This is the direct ALMA reading of SPEC.md's own worked example ("the
  *thread* does the arithmetic... there is no `x*1.8` anywhere in a knot") —
  here it is three strands and one knot instead of one.

## Grading

`grader.py` tests **five** random-but-fixed `(x1,x2,x3)` triples (including
an all-zero case that isolates the bias, and both signs), recomputes the
expected value from the formula above in plain Python, and checks your
weave's `y` matches to `1e-6`.

```
PYTHONIOENCODING=utf-8 python grader.py L1 your_submission.json
```

Reference solution (verified against the real loom): `reference_solutions/L1.json`.
