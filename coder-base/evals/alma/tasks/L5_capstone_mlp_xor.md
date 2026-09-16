# L5 — CAPSTONE: a real 2-layer MLP (ReLU hidden units), computing XOR

**Level:** capstone. This is "write a neural network in ALMA" made concrete
and falsifiable: two ReLU hidden units, a linear combiner, and a threshold —
the smallest network shape that is unambiguously "an MLP" rather than a
single perceptron or a lookup-shaped trick, using the *actual* piecewise-
linear ReLU identity for XOR rather than the sign-only trick from L3.

Mathematical fact you can verify by hand: for `x1, x2 ∈ {0, 1}`,

```
h1 = ReLU(x1 + x2)
h2 = ReLU(x1 + x2 - 1)
XOR(x1, x2) = h1 - 2*h2          # already exactly 0 or 1, no threshold needed
```

Check it: (0,0)→h1=0,h2=0→0. (1,0)→h1=1,h2=0→1. (0,1)→1. (1,1)→h1=2,h2=1→0.
This task asks for that combiner value shifted and thresholded through a
final `sign`, for consistency with L2/L3's ±1 output convention:

```
y = sign(h1 - 2*h2 - 0.5)
```

## Task

Build this network:
- Two independent ReLU hidden units (L4's construction — linear-then-max-
  with-a-zero-reference), computing `h1 = ReLU(x1+x2)` and
  `h2 = ReLU(x1+x2-1)`.
- A linear combiner: `outlin = h1 - 2*h2 - 0.5` (bias `-0.5` lives in this
  `sum` knot).
- A final `spell=sign` knot (`bias=0`), feeding a fringe knot.

**Contract:**
- Inputs: seeds into knots named `x1`, `x2` (values `0.0`/`1.0`).
- Output: one fringe knot named `y`.
- No knot may use `spell="xor"` (same reasoning as L3 — this must be a real
  hidden layer, not a call to the shipped answer).
- Any other baked-in helper seeds (your ReLU zero-references) are preserved
  by the grader across test cases exactly as in L4.

## Grading

Exhaustive XOR truth table (4 cases), exact match, plus the same static
`spell="xor"` check as L3.

```
PYTHONIOENCODING=utf-8 python grader.py L5 your_submission.json
```

Reference solution (9 knots: 2 input relays, 2×(linear+ReLU) hidden units,
1 linear combiner, 1 sign, 1 fringe — verified deterministic by beat 6):
`reference_solutions/L5.json`.

## What passing L5 actually proves — and does not prove

Passing proves ALMA's **inference-time** primitives (weighted sums via
strand weight + knot bias, and a hand-composed ReLU/sign nonlinearity via
`spell`) are sufficient to hand-wire a small, real, multi-layer feed-forward
network and get exactly the right answer on every input, checked by
executing the real loom — not by inspection.

It does **not** prove ALMA can *train* a network like this one from data.
The only weight-adjustment mechanism ALMA has today is per-strand `drift`
(SPEC.md §4a): a local rule — a cord thickens if its destination fired on
the beat the spark landed, thins (at a quarter rate) if not, bounded by
`floor`/`ceil`. There is no error signal, no backward pass, and SPEC.md is
explicit that "nothing travels backwards" is a structural law of the whole
language (§2, §7), not a missing feature. Every weight in this reference
solution (and in any correct submission) was **derived by hand** the same
way a textbook XOR-MLP's weights are derived by hand — not learned. See
`../FINDINGS.md` for the full honest accounting of what that means for
"write a neural network in ALMA."
