"""
Faithful software reproduction of the 1958/1960 Rosenblatt Mark I Perceptron.

Architecture (matches the Mark I hardware, canonical configuration):
  - S-units (retina): 400 = a 20x20 binary photocell grid.
  - A-units (association): 512. Each A-unit is wired to a RANDOM fixed subset of
    the 400 S-units with random +/-1 weights (~20 excitatory + ~20 inhibitory,
    the plugboard "table of random numbers"). Output = step(sum(w*s) - theta).
    These weights are FIXED and RANDOM -- never trained. Exactly like the machine.
  - R-units (response): trainable. One binary threshold unit per class.
    ONLY the A->R weights are learned.

Learning rule: Rosenblatt error-correction / perceptron rule.
    On each pattern, for each R-unit: prediction = step(w . a - b).
    w += lr * (target - prediction) * a  (and bias += lr*(target-prediction)).
    Weights change only when the R-unit is wrong. NOT backprop.

Pure numpy. No prebuilt Perceptron/MLP model class is imported.
"""

import numpy as np


def step(x):
    """Heaviside step: 1 if x > 0 else 0. The Mark I R-unit / A-unit fires when
    the algebraic sum exceeds threshold."""
    return (x > 0).astype(np.float64)


class AssociationLayer:
    """The fixed random S->A projection (the Mark I plugboard).

    Each of n_a A-units connects to a random subset of the 400 S-units with
    random +/-1 weights (roughly half excitatory, half inhibitory) and a fixed
    threshold. This is a random nonlinear feature expansion -- the historical
    seed of Random Features / Extreme Learning Machines. It is never trained.
    """

    def __init__(self, n_s=400, n_a=512, n_exc=20, n_inh=20, seed=1958):
        rng = np.random.default_rng(seed)
        self.n_s = n_s
        self.n_a = n_a
        # Fixed weight matrix W_sa: shape (n_s, n_a), entries in {-1, 0, +1}.
        W = np.zeros((n_s, n_a), dtype=np.float64)
        for j in range(n_a):
            k = n_exc + n_inh
            k = min(k, n_s)
            idx = rng.choice(n_s, size=k, replace=False)
            signs = np.array([1.0] * n_exc + [-1.0] * n_inh)[:k]
            rng.shuffle(signs)
            W[idx, j] = signs
        self.W = W
        # Fixed A-unit thresholds. The manual set theta slightly above the
        # integer sum (~+1/3) to avoid integer ties. We use a small positive
        # threshold; because inputs are 0/1 and weights +/-1, a threshold of
        # ~0.5 near the expected active-sum keeps ~half the A-units firing.
        # We fire when (sum - theta) > 0. A small threshold theta_j per unit.
        self.theta = np.full(n_a, 0.5, dtype=np.float64)

    def project(self, S):
        """S: (N, n_s) binary. Returns A: (N, n_a) binary A-unit activations."""
        pre = S @ self.W  # algebraic sum of +/- connections
        return step(pre - self.theta)


class PerceptronRUnits:
    """The trainable A->R (or S->R for vanilla) layer: one binary perceptron per
    class, trained with the Rosenblatt error-correction rule. One-vs-all over
    the class R-units. Prediction across classes = argmax of the raw score
    (w.x - b), matching a winner-take-all readout over the R-units."""

    def __init__(self, n_in, n_classes, lr=1.0, seed=0):
        rng = np.random.default_rng(seed)
        # Start from zero weights (classic perceptron init); bias zero.
        self.W = np.zeros((n_in, n_classes), dtype=np.float64)
        self.b = np.zeros(n_classes, dtype=np.float64)
        self.lr = lr
        self.n_classes = n_classes

    def _scores(self, X):
        return X @ self.W - self.b  # (N, n_classes)

    def fit(self, X, y, epochs=20, shuffle=True, seed=0):
        """Error-correction training. y: integer class labels.
        Per-R-unit binary target = 1 for the true class, 0 otherwise (one-vs-all).
        Weight update happens only on the R-units that are wrong."""
        rng = np.random.default_rng(seed)
        N = X.shape[0]
        # One-hot targets for the R-units.
        T = np.zeros((N, self.n_classes), dtype=np.float64)
        T[np.arange(N), y] = 1.0
        for ep in range(epochs):
            order = rng.permutation(N) if shuffle else np.arange(N)
            for i in order:
                x = X[i]
                pred = step(x @ self.W - self.b)  # (n_classes,) binary
                err = T[i] - pred                 # in {-1,0,+1}
                if not np.any(err):
                    continue
                # w += lr * err * x ; b += lr * err * (-1)  (bias input = -1)
                self.W += self.lr * np.outer(x, err)
                self.b -= self.lr * err

    def predict(self, X):
        """Winner-take-all across R-units (argmax of the analog score)."""
        return np.argmax(self._scores(X), axis=1)
