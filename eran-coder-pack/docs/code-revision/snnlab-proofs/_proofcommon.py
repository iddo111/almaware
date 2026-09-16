"""Shared scaffolding for the REV-2026-09-06 proof scripts. Import only."""
import importlib.machinery
import importlib.util
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)


def load(path, name):
    loader = importlib.machinery.SourceFileLoader(name, path)
    spec = importlib.util.spec_from_file_location(name, path, loader=loader)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


class Quiet:
    """An events sink that says nothing."""
    def __init__(self):
        self.seen = []

    def __call__(self, ev, **kw):
        self.seen.append((ev, kw))

    def close(self):
        pass

    def kinds(self):
        return [e for e, _ in self.seen]


def tiny_cfg(**over):
    """A run small enough to be honest about, and CPU-only on purpose: this
    box carries Iddo's phone mic and the GPU is not ours to borrow."""
    cfg = dict(dataset="syllables", encoding="cochlea-time", surrogate="atan",
               hidden=16, beta=0.9, threshold=1.0, lr=2e-3, batch=64,
               epochs=2, steps=8, input_gain=13.86, recurrent=False,
               seed=0, threads=1, device="cpu", log_every=10 ** 9,
               eval_train_n=64, run_id="proof", events=None, results=None,
               gpu_mem_frac=0.5)
    cfg.update(over)
    return cfg


def fake_percepts(n=132, n_class=22, slices=8, bands=24, seed=0, scale=1.0):
    """Class-separable stand-ins for the cochlear percept, unit-norm like the
    real thing. Synthetic ON PURPOSE — a proof must not need the corpus."""
    rng = np.random.RandomState(seed)
    y = np.arange(n) % n_class
    # The prototypes must NOT depend on `seed`, or the "test" set would be a
    # different world from the training set and nothing could ever learn it.
    proto = np.random.RandomState(1234).randn(n_class, slices, bands).astype(np.float32)
    x = proto[y] + 0.25 * rng.randn(n, slices, bands).astype(np.float32)
    x /= np.linalg.norm(x.reshape(n, -1), axis=1)[:, None, None]
    return (x * scale).astype(np.float32), y.astype(np.int64)


def verdict(ok, msg):
    print("PASS" if ok else "FAIL", "—", msg)
    return 0 if ok else 1
