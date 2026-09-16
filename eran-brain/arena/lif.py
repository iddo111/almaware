# -*- coding: utf-8 -*-
"""lif.py — Leaky-Integrate-and-Fire policy nets, in numpy, bit-matched to snnTorch.

> BROKEN WINDOWS LAW: test the REAL output, never a proxy.

Two arms:
  * ``LIFNet(recurrent=False)`` — feedforward LIF. It is NOT memoryless: the
    membrane potential of every neuron carries over from env-step to env-step
    and leaks by ``beta``. That is a genuine (exponentially fading) memory, and
    measuring exactly how far it carries is one of the points of this arena.
  * ``LIFNet(recurrent=True)``  — snn.RLeaky: the hidden layer's spikes are fed
    back through a learned square matrix. This is the arm that has real,
    trainable state.

Dynamics per layer, identical to snnTorch ``snn.Leaky`` with the default
``reset_mechanism='subtract'`` and ``reset_delay=True``:

    reset = 1[mem_prev > threshold]
    mem   = beta * mem_prev + I - reset * threshold
    spk   = 1[mem > threshold]

Hidden layer emits SPIKES (the nonlinearity). The output layer is read at its
MEMBRANE — snnTorch's own recommended classification readout — and argmax over
it is the action. Verified numerically against snnTorch in ``verify_lif.py``.

We use numpy rather than torch because the whole arena is evolution strategies
on tiny nets: no gradients are needed, and numpy on 20 CPU cores is ~50x faster
here than torch's per-call overhead. The dynamics are the same to 1e-12.
"""
import numpy as np


class LIFNet:
    def __init__(self, n_in, n_hidden, n_out, recurrent=False,
                 beta=0.9, threshold=1.0, in_gain=1.0):
        self.n_in = int(n_in)
        self.n_hidden = int(n_hidden)
        self.n_out = int(n_out)
        self.recurrent = bool(recurrent)
        self.beta = float(beta)
        self.thr = float(threshold)
        self.in_gain = float(in_gain)
        self.reset_state()

    # ------------------------------------------------------------ parameters
    def n_params(self):
        n = self.n_in * self.n_hidden + self.n_hidden          # W1, b1
        if self.recurrent:
            n += self.n_hidden * self.n_hidden                 # V
        n += self.n_hidden * self.n_out + self.n_out           # W2, b2
        return n

    def set_params(self, theta):
        t = np.asarray(theta, dtype=np.float64)
        i = 0
        k = self.n_in * self.n_hidden
        self.W1 = t[i:i + k].reshape(self.n_in, self.n_hidden); i += k
        self.b1 = t[i:i + self.n_hidden]; i += self.n_hidden
        if self.recurrent:
            k = self.n_hidden * self.n_hidden
            self.V = t[i:i + k].reshape(self.n_hidden, self.n_hidden); i += k
        k = self.n_hidden * self.n_out
        self.W2 = t[i:i + k].reshape(self.n_hidden, self.n_out); i += k
        self.b2 = t[i:i + self.n_out]; i += self.n_out
        assert i == len(t), (i, len(t))

    # ----------------------------------------------------------------- state
    def reset_state(self):
        self.mem1 = np.zeros(self.n_hidden)
        self.spk1 = np.zeros(self.n_hidden)
        self.mem2 = np.zeros(self.n_out)

    # ------------------------------------------------------------------ step
    def forward(self, x):
        cur1 = self.in_gain * (np.asarray(x) @ self.W1) + self.b1
        if self.recurrent:
            cur1 = cur1 + self.spk1 @ self.V
        reset1 = (self.mem1 > self.thr).astype(np.float64)
        self.mem1 = self.beta * self.mem1 + cur1 - reset1 * self.thr
        self.spk1 = (self.mem1 > self.thr).astype(np.float64)

        cur2 = self.spk1 @ self.W2 + self.b2
        reset2 = (self.mem2 > self.thr).astype(np.float64)
        self.mem2 = self.beta * self.mem2 + cur2 - reset2 * self.thr
        return self.mem2


class LIFAgent:
    """An ES-trained LIF policy. Frozen weights at eval; its only within-episode
    adaptation is membrane state + recurrence + the prev-action/prev-reward
    channel every arm receives."""

    online = False

    def __init__(self, n_obs, n_actions, hidden=16, recurrent=False,
                 beta=0.9, in_gain=3.0, seed=0):
        self.net = LIFNet(n_obs, hidden, n_actions, recurrent=recurrent,
                          beta=beta, in_gain=in_gain)
        self.rng = np.random.default_rng(seed)
        self.n_actions = int(n_actions)
        self.set_params(self.random_params(seed))

    def random_params(self, seed):
        rng = np.random.default_rng(seed)
        return rng.normal(0.0, 0.5, self.net.n_params())

    def n_params(self):
        return self.net.n_params()

    def set_params(self, theta):
        self.theta = np.asarray(theta, dtype=np.float64)
        self.net.set_params(self.theta)

    def reset_episode(self):
        self.net.reset_state()

    def act(self, obs):
        m = self.net.forward(obs)
        return int(np.argmax(m))

    def learn(self, reward, done=False):
        pass

    def stats(self):
        return {"n_params": int(self.n_params()),
                "recurrent": bool(self.net.recurrent),
                "hidden": int(self.net.n_hidden)}
