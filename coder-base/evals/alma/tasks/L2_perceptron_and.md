# L2 — a perceptron: linear neuron + step activation, computing AND

**Level:** medium. This is the first task that needs a **nonlinearity**.
ALMA's six original verbs (`pass/sum/prod/pool/gate/fringe`) only ever
*combine* — SPEC.md §5 says so explicitly. There is no sigmoid/relu/step
among them. The only activation-shaped tool ALMA ships today is the seventh
verb, `spell`, which already carries `sign`, `max`, `min`, `xor` in
`alma/spells.py` (SPEC.md §5a). This task is about **composing** a real
perceptron out of that: a linear stage (bias lives here) feeding a
threshold stage (`spell=sign`).

**Important implementation detail you must get right (it is easy to get
backwards):** in `alma/loom.py`, a `spell` knot's bias is added **after**
the spell function runs (`float(said) + knot.bias`), not before. So the
threshold constant (`-1.5` below) must live in a `sum` knot's `bias` field
(where bias really is added before the verb's output is used), and the
`spell=sign` knot that follows it should have `bias=0`.

## Task

Build the two-input logical AND, with output encoded as **+1.0 = true,
−1.0 = false** (never exactly 0 for these test cases):

```
y = sign(x1 + x2 - 1.5)
```
Truth table this must reproduce: (0,0)→−1, (1,0)→−1, (0,1)→−1, (1,1)→+1.

**Contract:**
- Inputs are seeds into knots named `x1`, `x2` (values will always be
  exactly `0.0` or `1.0`).
- Output at one fringe knot named `y`.
- Do not special-case the four inputs (e.g. four different seeded weaves) —
  submit **one** weave; the grader supplies all four input combinations by
  overwriting only the `x1`/`x2` seeds.

## Grading

Exhaustive and exact: all 4 boolean combinations are tested, and the
recorded `y` must equal the expected sign exactly (no tolerance — `sign`
never returns a fractional value).

```
PYTHONIOENCODING=utf-8 python grader.py L2 your_submission.json
```

Reference solutions: `reference_solutions/L2.json` (JSON) and
`reference_solutions/L2.voice` (same weave, SPEC.md §9 voice grammar — proof
both text formats can express it and round-trip through `parse_voice`/
`to_voice` unchanged).
