# L4 — ReLU, a nonlinearity ALMA does not ship, built from what it does ship

**Level:** hard. This is the task that probes the actual **gap** in the
language rather than working around it. ALMA ships `max`/`min`/`sign`/`xor`
as spells — no ReLU. The interesting question is whether the model can
notice that `max(x, 0)` **is** ReLU, and that the shipped `max` spell can
compute it *if* a permanent, reliable `0.0` is available to compare against
— then build that reference out of ALMA's own primitives (a `spell=max`
knot needs **two** values in its tray on the same beat: the real signal and
a zero) instead of asking for a new verb.

There are (at least) two honest ways to manufacture that permanent zero:
1. **A one-shot helper seed**: bake an extra `seed` into the weave itself,
   targeting your ReLU knot at exactly the beat your real signal's spark
   also lands there (`trigger="count 2"` so it waits for both).
2. **An eternal "zero" knot**: a knot that seeds itself once with `0.0` and
   has a self-thread of weight 1, delay 1 — it then re-fires every beat
   forever, forever re-emitting `0.0` (a permanent clock). Either is fine;
   the grader only checks input/output behaviour, never your topology.

## Task

Build `y = max(x, 0)` for any real `x`.

**Contract:**
- Input: seed into a knot named `x`.
- Output: one fringe knot named `y`, one recorded value per run.
- The grader will **only** touch the seed targeting `x` between test cases —
  any other seed you bake into the file (like the helper zero above) is
  preserved untouched across every test.

## Grading

Five test values of `x`: two negative, zero, and two positive (including a
non-integer). Exact match required (`max` involves no floating-point
rounding beyond what the two compared numbers already carry).

```
PYTHONIOENCODING=utf-8 python grader.py L4 your_submission.json
```

Reference solution (3 knots + 1 helper seed, verified): `reference_solutions/L4.json`.

## Why this task exists

SPEC.md §11's honest ledger already says the tensor door is shut and there is
no gradient. It does *not* say there is no ReLU — that gap only shows up when
you actually try to write one, which is the whole point of building this
ladder instead of just reading the spec and guessing. If a model solves L0-L3
but fails here, the honest reading is: *ALMA can express perceptrons and
sign-threshold multi-layer nets natively, but any smooth or ramp-shaped
activation must be smuggled in via a hand-built spell-composition trick, not
because a syntax is missing but because the seventh verb only calls spells
someone has already taught in Python* (`alma/spells.py`'s `teach()` refuses
everything but a real Python callable — see SPEC.md §5a and the module
docstring). That is a real, load-bearing finding for whoever decides what to
train the coder model on next.
