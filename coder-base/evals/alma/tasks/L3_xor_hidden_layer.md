# L3 — XOR with a genuine hidden layer (no cheating with `spell=xor`)

**Level:** hard. This is the task that actually tests whether ALMA can
express a *multi-layer* network, not just one neuron. XOR is the textbook
example precisely because it is **not linearly separable** — no single
line (no single `sign(w·x+b)`) can solve it. A real solution needs at least
one hidden layer.

`alma/spells.py` happens to ship `xor` already (it exists as the *positive
control* for `tests/test_spell.py::TestFloor`, which searches all 10,290
single-knot weaves over 5 verbs × 6 triggers × 7 biases × 7×7 strand weights
and finds that none of them compute XOR — proving one knot of the six
original verbs genuinely cannot). **Using `spell=xor` directly in this task
is disqualified** — it would just be calling the answer instead of building
it. The grader checks your submission's knots and fails immediately if any
knot uses `spell="xor"`.

## Task

Build XOR (again encoded +1.0 = true, −1.0 = false) using the classic
two-layer construction:

```
hidden_OR   = sign(x1 + x2 - 0.5)          # OR
hidden_NAND = sign(-x1 - x2 + 1.5)         # NAND  (note the negative weights)
y           = sign(hidden_OR + hidden_NAND - 1.0)
```

You can check by hand that `OR AND NAND` is exactly XOR. Every threshold
constant above must live in a `sum` knot's bias (see L2's note on why —
`spell` adds bias *after*, not before), followed by a `spell=sign` knot with
`bias=0`.

**Contract:**
- Inputs: seeds into knots named `x1`, `x2` (values `0.0`/`1.0`).
- Output: one fringe knot named `y`, one recorded value per run.
- No knot may use `spell="xor"`.
- One weave; the grader supplies all 4 input combinations.

## Grading

Exhaustive truth table (4 cases), exact match, plus the static check that
`spell="xor"` was not used.

```
PYTHONIOENCODING=utf-8 python grader.py L3 your_submission.json
```

Reference solution (7 knots, verified against the real loom, deterministic
by beat 6): `reference_solutions/L3.json`. A deliberately disqualified
"cheat" submission that uses `spell="xor"` directly is kept at
`reference_solutions/negative_examples/L3_cheat_uses_xor_spell_directly.json`
— run the grader on it yourself to see it get rejected; that is the proof
this check actually works and is not a rubber stamp.
