# -*- coding: utf-8 -*-
"""cma.py -- a compact, standard CMA-ES. Pure numpy, no pip, state fully
serialisable to JSON so a 48-hour worker can die and resume mid-generation.

Hansen's (mu/mu_w, lambda)-CMA-ES with rank-1 + rank-mu covariance update and
cumulative step-size adaptation, exactly as in the tutorial (arXiv:1604.00772).
Nothing clever added. sanity0.py proves it on a sphere before any worker runs.
"""
from __future__ import annotations

import numpy as np


class CMA:
    def __init__(self, x0, sigma0, seed=0, popsize=None):
        x0 = np.asarray(x0, dtype=float)
        self.n = x0.size
        self.mean = x0.copy()
        self.sigma = float(sigma0)
        self.lam = int(popsize or (4 + int(3 * np.log(self.n))))
        self.mu = self.lam // 2
        w = np.log(self.mu + 0.5) - np.log(np.arange(1, self.mu + 1))
        self.weights = w / w.sum()
        self.mueff = 1.0 / float(np.sum(self.weights ** 2))
        n, mueff = self.n, self.mueff
        self.cc = (4 + mueff / n) / (n + 4 + 2 * mueff / n)
        self.cs = (mueff + 2) / (n + mueff + 5)
        self.c1 = 2 / ((n + 1.3) ** 2 + mueff)
        self.cmu = min(1 - self.c1,
                       2 * (mueff - 2 + 1 / mueff) / ((n + 2) ** 2 + mueff))
        self.damps = 1 + 2 * max(0.0, np.sqrt((mueff - 1) / (n + 1)) - 1) + self.cs
        self.chiN = np.sqrt(n) * (1 - 1 / (4 * n) + 1 / (21 * n * n))
        self.pc = np.zeros(n)
        self.ps = np.zeros(n)
        self.C = np.eye(n)
        self.gen = 0
        self.rng = np.random.default_rng(seed)
        self._eig()

    def _eig(self):
        self.C = (self.C + self.C.T) / 2.0
        d, B = np.linalg.eigh(self.C)
        d = np.maximum(d, 1e-20)
        self.B = B
        self.D = np.sqrt(d)
        self.invsqrtC = B @ np.diag(1.0 / self.D) @ B.T

    def ask(self):
        z = self.rng.standard_normal((self.lam, self.n))
        return self.mean[None, :] + self.sigma * (z * self.D[None, :]) @ self.B.T

    def tell(self, xs, fs):
        xs = np.asarray(xs, dtype=float)
        fs = np.asarray(fs, dtype=float)
        order = np.argsort(fs)
        xs = xs[order[:self.mu]]
        old_mean = self.mean.copy()
        self.mean = self.weights @ xs
        y = (self.mean - old_mean) / self.sigma
        self.ps = ((1 - self.cs) * self.ps
                   + np.sqrt(self.cs * (2 - self.cs) * self.mueff)
                   * (self.invsqrtC @ y))
        hsig = (np.linalg.norm(self.ps)
                / np.sqrt(1 - (1 - self.cs) ** (2 * (self.gen + 1)))
                / self.chiN) < (1.4 + 2 / (self.n + 1))
        self.pc = ((1 - self.cc) * self.pc
                   + (np.sqrt(self.cc * (2 - self.cc) * self.mueff) * y
                      if hsig else 0.0))
        artmp = (xs - old_mean[None, :]) / self.sigma
        self.C = ((1 - self.c1 - self.cmu) * self.C
                  + self.c1 * (np.outer(self.pc, self.pc)
                               + (0.0 if hsig else 1.0)
                               * self.cc * (2 - self.cc) * self.C)
                  + self.cmu * (artmp.T * self.weights) @ artmp)
        self.sigma *= float(np.exp((self.cs / self.damps)
                                   * (np.linalg.norm(self.ps) / self.chiN - 1)))
        self.sigma = float(min(self.sigma, 1e6))
        self.gen += 1
        self._eig()

    @property
    def condition(self):
        return float((self.D.max() / self.D.min()) ** 2)

    # ------------------------------------------------------------- persistence
    def state(self):
        return {"n": self.n, "lam": self.lam, "sigma": self.sigma,
                "gen": self.gen,
                "mean": self.mean.tolist(), "pc": self.pc.tolist(),
                "ps": self.ps.tolist(), "C": self.C.tolist(),
                "rng": self.rng.bit_generator.state}

    @classmethod
    def restore(cls, st, seed=0):
        o = cls(np.asarray(st["mean"], dtype=float), st["sigma"], seed=seed,
                popsize=st["lam"])
        o.gen = int(st["gen"])
        o.pc = np.asarray(st["pc"], dtype=float)
        o.ps = np.asarray(st["ps"], dtype=float)
        o.C = np.asarray(st["C"], dtype=float)
        o.rng.bit_generator.state = st["rng"]
        o._eig()
        return o
