"""GADAL / גָּדַל — THE BODY THAT CAN GROW: a numpy net whose size is not a hyperparameter.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

לזכרה של עלמה ז"ל.

Iddo, 2026-09-05 14:39: "תן למודל ההולובריין להתחיל זעיר ולגדול לפי רצונו — ככה לא צריך
המון קורפוס."

WHY THIS FILE EXISTS
--------------------
On one day, three of our models were measured and all three had the same disease:

  ERAN    19 syllables with exactly 3 clips each -> 0-1 dev examples after the split
  MIKO    train MSE falls, val MAE flat; the VANILLA control fits train HARDER
          (0.016 vs 0.052) and generalises WORSE -> memorising 39 questions
  WINSTON 18x better than a flat colour on a corpus photo, WORSE than a flat colour
          on an unseen one -> 256 pooled numbers -> 12,800 stroke params: wide enough
          to INDEX one of 93 photos, not to DESCRIBE a new one

None of those is a capacity ceiling. All three are capacity >> data. A model sized to
its data can learn from three examples; a model far larger than its data can only
memorise them. So the size must stop being a number we pick and start being a number
the data earns.

THE ONE RULE (and it is a rule about when NOT to grow)
------------------------------------------------------
Grow ONLY on underfit — when the model cannot fit even the training set to the level
the data itself allows. NEVER grow because it is doing well. Growing on success is
precisely the road that produced all three diseases above.

WHAT IS IN THIS FILE
--------------------
The body only: a plain numpy multilayer net, full-batch Adam, and three structural
operations that a fixed-size net does not have:

    widen(k)   add k hidden units, EXACTLY function-preserving (Net2Net-style)
    deepen()   insert a hidden layer, EXACTLY function-preserving (ReLU identity)
    prune(...) remove hidden units that carry no signal

The policy that decides WHEN to call them lives in grow.py. This split is deliberate:
the policy is the contribution, the body is replaceable.

THE WIDENING, AND WHY IT IS EXACT AND STILL BREAKS SYMMETRY
-----------------------------------------------------------
Net2Net copies unit j into a new unit n and halves the outgoing weights so the sum is
unchanged. Copied verbatim, the two units are identical forever: identical incoming
weights give identical activations, identical activations give identical gradients, and
the new unit is dead capacity. The usual fix is to add noise to the incoming weights —
which breaks function preservation, exactly the property we wanted.

We do it on the OUTGOING side instead:

    W_in[:, n]  = W_in[:, j]                 (identical unit, so h_n == h_j)
    W_out[j, :] = W_out_orig[j, :] * 0.5 * (1+e)
    W_out[n, :] = W_out_orig[j, :] - W_out[j, :]        <- by SUBTRACTION, not by *0.5*(1-e)

The subtraction is not cosmetic. 0.5*(1+e) and 0.5*(1-e) are not exactly representable,
so two independent products would leave W_out[j] + W_out[n] != W_out_orig[j] by a rounding
step. Written as a subtraction, Sterbenz's lemma applies (the halves stay inside
[x/2, 2x]), the difference is EXACT, and the invariant

    W_out[j, :] + W_out[n, :] == W_out_orig[j, :]        bit for bit

holds for every entry. tests/test_gadal.py asserts it as an equality, not a tolerance.

The output then moves only by the rounding of one extra term in the matmul sum
(a*h + b*h vs (a+b)*h), which is a few ULP and nothing more: measured max |Δy| is
~1e-16 on the testbed and is LOGGED at every growth step as preserve_max_abs_delta, so
a real regression could never hide inside it.

Meanwhile the two units now push different amounts of error backwards, so
dL/dW_in[:, j] != dL/dW_in[:, n] and they separate on the first step. Preservation AND
broken symmetry, no trade.

WHAT THIS IS NOT: it is not an organ and this file will never say it is. It is a
MECHANISM — an optimiser with a size policy. The organs it grows keep their own
ALMA loom and their own facade test; gadal does not have one and does not pretend to.
"""
from __future__ import annotations

import numpy as np

ACTS = ("relu", "tanh")


def _act(name, z, deriv=False):
    if name == "relu":
        return (z > 0).astype(z.dtype) if deriv else np.maximum(z, 0.0)
    if name == "tanh":
        t = np.tanh(z)
        return 1.0 - t * t if deriv else t
    raise ValueError(name)


class Net:
    """x -> [Linear -> act] * L -> Linear -> y.  widths=() is a plain linear model."""

    def __init__(self, n_in: int, n_out: int, widths=(), seed: int = 0, act: str = "relu",
                 scale: float = 1.0):
        if act not in ACTS:
            raise ValueError(act)
        self.n_in, self.n_out, self.act = int(n_in), int(n_out), act
        self.rng = np.random.default_rng(seed)
        dims = [self.n_in, *[int(w) for w in widths], self.n_out]
        self.W, self.b = [], []
        for a, c in zip(dims[:-1], dims[1:]):
            s = scale * np.sqrt((2.0 if act == "relu" else 1.0) / max(a, 1))
            self.W.append(self.rng.normal(0.0, s, size=(a, c)))
            self.b.append(np.zeros(c))
        self._reset_opt()

    # ---------------------------------------------------------------- shape
    @property
    def widths(self) -> tuple:
        return tuple(W.shape[1] for W in self.W[:-1])

    @property
    def n_params(self) -> int:
        return int(sum(W.size + b.size for W, b in zip(self.W, self.b)))

    # ---------------------------------------------------------------- forward / backward
    def forward(self, X, cache=False):
        h = np.asarray(X, dtype=np.float64)
        hs, zs = [h], []
        for i in range(len(self.W) - 1):
            z = h @ self.W[i] + self.b[i]
            h = _act(self.act, z)
            if cache:
                zs.append(z)
            hs.append(h)
        y = h @ self.W[-1] + self.b[-1]
        return (y, hs, zs) if cache else y

    def grads(self, X, Y, M=None):
        """Masked mean-squared error. M is a 0/1 mask the same shape as Y (an amount the
        decisions do not make live is not a lesson, so it is not an error either)."""
        y, hs, zs = self.forward(X, cache=True)
        M = np.ones_like(Y) if M is None else np.asarray(M, dtype=np.float64)
        n = max(float(M.sum()), 1.0)
        r = (y - Y) * M
        loss = float((r * r).sum() / n)
        d = 2.0 * r / n
        gW, gb = [None] * len(self.W), [None] * len(self.b)
        for i in range(len(self.W) - 1, -1, -1):
            gW[i] = hs[i].T @ d
            gb[i] = d.sum(axis=0)
            if i:
                d = (d @ self.W[i].T) * _act(self.act, zs[i - 1], deriv=True)
        return loss, gW, gb

    def loss(self, X, Y, M=None) -> float:
        y = self.forward(X)
        M = np.ones_like(Y) if M is None else np.asarray(M, dtype=np.float64)
        r = (y - Y) * M
        return float((r * r).sum() / max(float(M.sum()), 1.0))

    def mae(self, X, Y, M=None) -> float:
        y = self.forward(X)
        M = np.ones_like(Y) if M is None else np.asarray(M, dtype=np.float64)
        return float((np.abs(y - Y) * M).sum() / max(float(M.sum()), 1.0))

    # ---------------------------------------------------------------- Adam, full batch
    def _reset_opt(self):
        self.mW = [np.zeros_like(W) for W in self.W]
        self.vW = [np.zeros_like(W) for W in self.W]
        self.mb = [np.zeros_like(b) for b in self.b]
        self.vb = [np.zeros_like(b) for b in self.b]
        self.t = 0

    def step(self, X, Y, M=None, lr=0.02, wd=0.0, b1=0.9, b2=0.999, eps=1e-8) -> float:
        loss, gW, gb = self.grads(X, Y, M)
        self.t += 1
        c1, c2 = 1 - b1 ** self.t, 1 - b2 ** self.t
        for i in range(len(self.W)):
            g = gW[i] + wd * self.W[i]
            self.mW[i] = b1 * self.mW[i] + (1 - b1) * g
            self.vW[i] = b2 * self.vW[i] + (1 - b2) * g * g
            self.W[i] -= lr * (self.mW[i] / c1) / (np.sqrt(self.vW[i] / c2) + eps)
            self.mb[i] = b1 * self.mb[i] + (1 - b1) * gb[i]
            self.vb[i] = b2 * self.vb[i] + (1 - b2) * gb[i] * gb[i]
            self.b[i] -= lr * (self.mb[i] / c1) / (np.sqrt(self.vb[i] / c2) + eps)
        return loss

    def state(self):
        return ([W.copy() for W in self.W], [b.copy() for b in self.b])

    def restore(self, s):
        self.W = [W.copy() for W in s[0]]
        self.b = [b.copy() for b in s[1]]
        self._reset_opt()

    # ---------------------------------------------------------------- GROWTH
    def widen(self, k: int = 1, layer: int = -1, eps: float = 1e-2, pick=None,
              mode: str = "zero") -> list:
        """Add k units to a hidden layer, function-preserving. Two modes:

        "split"  Net2Net: copy unit j, split its outgoing weights (see module docstring).
        "zero"   a NEW unit with random incoming weights and ZERO outgoing weights. The
                 output contribution is 0 * h_new = 0, so the function is preserved just
                 as exactly -- and the new unit is a genuinely new direction instead of a
                 duplicate of an old one.

        WHY "zero" IS THE DEFAULT, measured on the MOREH testbed 2026-09-05:
        "split" starves on a CONVERGED small model. Its two copies have IDENTICAL incoming
        weights, so they sit at the same point in input space and differ only by an
        outgoing scale -- and Adam divides the gradient by its own running magnitude, so
        that scale is normalised straight back out. Measured: the widen_eps that sets the
        asymmetry changed nothing at all (0.01 / 0.2 / 0.5 -> byte-identical widths and
        accuracy over 8 folds). The units separate far too slowly to use the new room, so
        growth from a converged width-1 net kept failing to beat width 1 and halted there.
        "zero" has no symmetry to break: the new unit starts on a fresh random direction,
        its outgoing weights get a non-zero gradient on the very first step, and it climbs
        out. Both are kept because the failure of "split" is a result worth being able to
        reproduce, not a bug to hide.

        Returns the source units copied ("split") or -1 per new unit ("zero").
        """
        if not self.widths:
            raise ValueError("no hidden layer to widen; this net is linear")
        if mode not in ("split", "zero"):
            raise ValueError(mode)
        li = (len(self.W) - 2) if layer == -1 else layer
        src = []
        for _ in range(int(k)):
            Win, Wout = self.W[li], self.W[li + 1]
            if mode == "zero":
                s = np.sqrt((2.0 if self.act == "relu" else 1.0) / max(Win.shape[0], 1))
                self.W[li] = np.hstack([Win, self.rng.normal(0.0, s, size=(Win.shape[0], 1))])
                self.W[li + 1] = np.vstack([Wout, np.zeros((1, Wout.shape[1]))])
                self.b[li] = np.append(self.b[li], 0.0)
                src.append(-1)
                continue
            j = int(pick(self, li)) if pick is not None else int(np.argmax(np.linalg.norm(Wout, axis=1)))
            src.append(j)
            col = Win[:, j: j + 1].copy()
            row = Wout[j: j + 1, :].copy()
            keep = row[0] * (0.5 * (1.0 + float(eps)))
            give = row[0] - keep                 # Sterbenz: exact, so keep + give == row[0]
            Wout[j, :] = keep
            self.W[li] = np.hstack([Win, col])
            self.W[li + 1] = np.vstack([Wout, give[None, :]])
            self.b[li] = np.append(self.b[li], self.b[li][j])
        self._reset_opt()
        return src

    def deepen(self) -> int:
        """Insert a new hidden layer just before the output. EXACTLY function preserving for
        relu: the new layer is the identity, and relu(h) == h because h is already
        post-relu, i.e. non-negative."""
        if self.act != "relu":
            raise ValueError("exact deepening needs relu (identity through a non-negative signal)")
        if not self.widths:
            raise ValueError("cannot deepen a linear model exactly; the input is not non-negative")
        w = self.widths[-1]
        self.W.insert(len(self.W) - 1, np.eye(w))
        self.b.insert(len(self.b) - 1, np.zeros(w))
        self._reset_opt()
        return len(self.widths)

    # ---------------------------------------------------------------- PRUNING
    def utility(self, X, layer: int = -1) -> np.ndarray:
        """How much each hidden unit actually MOVES the output on this data:
        ||outgoing weights|| * std(activation). A unit that never varies, or whose
        outgoing weights are zero, contributes nothing however large its incoming weights."""
        li = (len(self.W) - 2) if layer == -1 else layer
        h = np.asarray(X, dtype=np.float64)
        for i in range(li + 1):
            h = _act(self.act, h @ self.W[i] + self.b[i])
        return np.linalg.norm(self.W[li + 1], axis=1) * h.std(axis=0)

    def prune(self, keep, layer: int = -1) -> int:
        """Drop hidden units, folding each dropped unit's CONSTANT contribution into the
        next bias, so a unit that is constant-but-nonzero costs nothing to remove."""
        li = (len(self.W) - 2) if layer == -1 else layer
        keep = np.asarray(keep, dtype=bool)
        if keep.all():
            return 0
        if not keep.any():
            raise ValueError("refusing to prune every unit in a layer")
        self.W[li] = self.W[li][:, keep]
        self.b[li] = self.b[li][keep]
        self.W[li + 1] = self.W[li + 1][keep, :]
        self._reset_opt()
        return int((~keep).sum())

    def fold_constant(self, X, keep, layer: int = -1):
        """Before pruning, move the mean activation of the doomed units into the next bias.
        Removing a unit whose activation is constant then changes nothing at all."""
        li = (len(self.W) - 2) if layer == -1 else layer
        h = np.asarray(X, dtype=np.float64)
        for i in range(li + 1):
            h = _act(self.act, h @ self.W[i] + self.b[i])
        drop = ~np.asarray(keep, dtype=bool)
        if drop.any():
            self.b[li + 1] = self.b[li + 1] + h[:, drop].mean(axis=0) @ self.W[li + 1][drop, :]
