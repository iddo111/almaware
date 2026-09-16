# -*- coding: utf-8 -*-
"""eran_agent.py — ERAN's organism, ported honestly into an AGENT.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL
> output, never a proxy.

THE HONEST PREMISE, stated up front. ERAN's organism as it exists today
(``eran-brain/body/brain.py``) is an associative PROTOTYPE MEMORY. It
recognises. It has **no action selection at all**. To put it in an arena we
must give it an action head, and *how* we give it one is itself the experiment.
Three ports, from the most literal to the most generous:

  MODE "proto"  — the literal organism. The prototype key is the current
                  observation and nothing else; the action comes from the
                  winning prototype's own learned preference. A pure
                  input->output map. PREDICTION: it cannot hold anything across
                  time, so DMS at delay>=1 must sit at chance. We measure it
                  rather than assert it.

  MODE "trace"  — the organism's OWN memory mechanism: the eligibility traces
                  already in brain.py (``self.elig``), which remember which
                  prototypes were recently active. The action score becomes
                  sum_i elig[i] * Q[i][a]. This is real memory — but it is
                  ADDITIVE over prototypes, and DMS needs a conjunction
                  ("the cue was X **and** choice A is X"). Additive scoring
                  provably cannot represent that. We measure it anyway; that is
                  the same XOR wall the single-neuron work already hit.

  MODE "ctx"    — the generous port. The prototype key becomes
                  [observation | leaky context], where context is an
                  exponential trace of past observations, m <- lam*m + (1-lam)*o.
                  Now a prototype IS a conjunction ("cue was X while choices are
                  (X,Y)"), which is exactly the ``gist`` idea already in
                  pong-alma. lam is tuned by ES, so the memory horizon is
                  learned, not gifted — and the delay at which lam^N falls under
                  the prototype's own discrimination noise is the arm's
                  measurable BREAK POINT.

Everything else is transplanted from brain.py without softening:
  * spawn-on-surprise using each prototype's OWN ``tolerance()``
    (mean - k*sd of its absorbed similarities, TOLERANCE_WARMUP freebies),
  * strictness k that grows over the critical period,
  * Hebbian pull toward the absorbed vector at rate ETA0 * chem.plasticity(),
  * eligibility traces with TRACE_TAU / TRACE_FLOOR,
  * pay_trace('up'/'down') on reward: mass grows, scars accumulate.

THE ACTION HEAD is the minimum addition: one preference row Q[i][a] per
prototype and a per-prototype value V[i], both updated ONLINE by the reward
prediction error, paid through the very same eligibility traces the organism
already uses for the parent's thumb-tap. Nothing else is added.

CHEMISTRY (arm 3) is ``body/chemistry.py`` transplanted, plus ONE extension we
name openly: the original Chemistry only ever sees PERCEPTUAL surprise
(1 - cosine), which in these tasks is nearly constant, so NE could never fire.
Rule-switching's change-point is a REWARD surprise. ``observe_rpe`` gives NE
that channel. If the chemistry still does nothing, we say so.
"""
import math

import numpy as np

# ── transplanted genome constants (eran-brain/body/genome.py) ───────────────
ETA0 = 0.10
TRACE_TAU = 60.0
TRACE_FLOOR = 0.01
TOLERANCE_WARMUP = 5
TOLERANCE_MIN_SD = 0.02
TOLERANCE_WARMUP_FLOOR = 0.0
STRICTNESS_INFANT = 0.5
STRICTNESS_ADULT = 3.0
CRITICAL_PERIOD_BEATS = 200_000
SCAR_HIT = 0.05
TAP_UP_BONUS = 10.0

# chemistry constants
DA0, ACH0, NE0, SHT0, OXT0 = 0.0, 1.0, 0.0, 0.5, 0.0
DA_GAIN, DA_MAX = 4.0, 2.0
NE_JUMP, NE_MAX, NE_DECAY = 0.15, 3.0, 0.85
PROG_TAU_FAST, PROG_TAU_SLOW = 20.0, 200.0
SHT_TAU = 0.02


class Chemistry:
    """body/chemistry.py, transplanted. ``frozen=True`` is the ablation: every
    channel pinned at baseline and plasticity() == 1.0, so arm 2 is arm 3 with
    the chemistry surgically removed and nothing else changed."""

    def __init__(self, frozen=False, ne_gain=1.0, da_gain=DA_GAIN):
        self.frozen = bool(frozen)
        self.ne_gain = float(ne_gain)
        self.da_gain = float(da_gain)
        self.reset()

    def reset(self):
        self.da, self.ach, self.ne, self.sht, self.oxt = DA0, ACH0, NE0, SHT0, OXT0
        self._fast, self._slow = 0.5, 0.5
        self._rfast, self._rslow = 0.0, 0.0
        self.ne_events = 0

    def observe(self, surprise):
        if self.frozen:
            return
        self._fast += (surprise - self._fast) / PROG_TAU_FAST
        self._slow += (surprise - self._slow) / PROG_TAU_SLOW
        progress = self._slow - self._fast
        self.da = min(DA_MAX, max(0.0, self.da_gain * progress))
        if surprise > self._slow + NE_JUMP:
            self.ne = min(NE_MAX, self.ne + 1.0)
            self.ne_events += 1

    def observe_rpe(self, rpe):
        """EXTENSION (named openly): NE spikes on a REWARD change-point.
        The world just stopped paying for what used to work -> reset."""
        if self.frozen:
            return
        a = abs(float(rpe))
        self._rfast += (a - self._rfast) / 8.0
        self._rslow += (a - self._rslow) / 80.0
        if self._rfast > self._rslow + NE_JUMP:
            self.ne = min(NE_MAX, self.ne + self.ne_gain)
            self.ne_events += 1

    def valence(self, v):
        if self.frozen:
            return
        self.sht = min(1.0, max(0.0, self.sht + 0.1 * v))

    def decay(self):
        if self.frozen:
            return
        self.ne *= NE_DECAY
        self.sht += SHT_TAU * (SHT0 - self.sht)

    def plasticity(self):
        if self.frozen:
            return 1.0
        return self.ach * (1.0 + self.da) * (1.0 + self.ne)


# ── the ERAN parameter vector that ES tunes ────────────────────────────────
# Kept deliberately tiny (9 knobs) and every one of them is reported in the
# results file, so nothing is hidden in a hyperparameter.
PARAM_NAMES = ("lam", "eta_q", "eta_v", "eps0", "eps_decay", "eps_floor",
               "strict_scale", "trace_tau", "ne_gain", "ctx_gain")
N_PARAMS = len(PARAM_NAMES)


def _sig(x):
    return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, x))))


def decode(theta):
    t = np.asarray(theta, dtype=np.float64)
    return {
        "lam":          _sig(t[0]),                       # context leak 0..1
        "eta_q":        0.6 * _sig(t[1]),                 # action-head lr
        "eta_v":        0.6 * _sig(t[2]),                 # value lr
        "eps0":         _sig(t[3]),                       # explore at birth
        "eps_decay":    10.0 ** (-1.0 - 4.0 * _sig(t[4])),  # per-step decay
        "eps_floor":    0.5 * _sig(t[5]),                 # explore at eval
        "strict_scale": 0.2 + 3.0 * _sig(t[6]),           # scales strictness k
        "trace_tau":    1.0 + 120.0 * _sig(t[7]),         # eligibility horizon
        "ne_gain":      2.0 * _sig(t[8]),
        # How loud the context channel is next to the raw observation. WITHOUT
        # this knob the comparison is rigged: the key is L2-normalised (that is
        # ERAN's own cosine mechanism), the observation block carries two or
        # three one-hots, and the leaky context block carries a fraction of one
        # — so the memory is drowned by the present and the arm would "break"
        # at a delay set by MY concatenation rather than by the architecture.
        # ES tunes it on TRAIN seeds and the tuned value is reported per arm.
        "ctx_gain":     0.1 + 8.0 * _sig(t[9]),
    }


class EranAgent:
    """Prototype memory + action head. ``mode`` in {"proto","trace","ctx"}."""

    online = True

    def __init__(self, n_obs, n_actions, mode="ctx", chemistry=False,
                 max_protos=256, seed=0, theta=None):
        self.n_obs = int(n_obs)
        self.n_actions = int(n_actions)
        self.mode = mode
        self.max_protos = int(max_protos)
        self.chem_on = bool(chemistry)
        self.rng = np.random.default_rng(seed)
        self.key_dim = self.n_obs * (2 if mode == "ctx" else 1)
        self.set_params(theta if theta is not None
                        else self.random_params(seed))
        self.hard_reset()

    # ------------------------------------------------------------ parameters
    def n_params(self):
        return N_PARAMS

    def random_params(self, seed):
        rng = np.random.default_rng(seed)
        return rng.normal(0.0, 1.0, N_PARAMS)

    def set_params(self, theta):
        self.theta = np.asarray(theta, dtype=np.float64)
        self.p = decode(self.theta)

    # ----------------------------------------------------------------- state
    def hard_reset(self):
        """Forget everything — a newborn."""
        self.vecs = np.zeros((0, self.key_dim))
        self.mass = []
        self.scar = []
        self.n_abs = []
        self.s_sum = []
        self.s_sq = []
        self.Q = np.zeros((0, self.n_actions))
        self.V = np.zeros(0)
        self.elig = {}
        self.beat = 0
        self.eps = self.p["eps0"]
        self.chem = Chemistry(frozen=not self.chem_on, ne_gain=self.p["ne_gain"])
        self.frozen_eval = False      # when True: recognise but do not learn
        self.reset_episode()

    def reset_episode(self):
        self.ctx = np.zeros(self.n_obs)
        self.elig = {}
        self._last_idx = None
        self._last_a = None

    # ------------------------------------------------------------- prototypes
    def strictness(self):
        age = self.beat / CRITICAL_PERIOD_BEATS
        grown = 1.0 - math.exp(-age)
        k = STRICTNESS_INFANT + (STRICTNESS_ADULT - STRICTNESS_INFANT) * grown
        return k * self.p["strict_scale"]

    def tolerance(self, i):
        n = self.n_abs[i]
        if n < TOLERANCE_WARMUP:
            return TOLERANCE_WARMUP_FLOOR
        mean = self.s_sum[i] / n
        var = max(0.0, self.s_sq[i] / n - mean * mean)
        sd = max(var ** 0.5, TOLERANCE_MIN_SD)
        return mean - self.strictness() * sd

    def _key(self, obs):
        o = np.asarray(obs, dtype=np.float64)
        if self.mode == "ctx":
            v = np.concatenate([o, self.p["ctx_gain"] * self.ctx])
        else:
            v = o
        n = np.linalg.norm(v)
        return v / n if n > 1e-12 else v

    def _spawn(self, v):
        self.vecs = np.vstack([self.vecs, v[None, :]]) if len(self.vecs) else v[None, :].copy()
        self.mass.append(1.0)
        self.scar.append(0.0)
        self.n_abs.append(0)
        self.s_sum.append(0.0)
        self.s_sq.append(0.0)
        self.Q = np.vstack([self.Q, np.zeros((1, self.n_actions))])
        self.V = np.append(self.V, 0.0)
        return len(self.mass) - 1

    def _decay_traces(self):
        f = math.exp(-1.0 / self.p["trace_tau"])
        dead = []
        for i in list(self.elig):
            self.elig[i] *= f
            if self.elig[i] < TRACE_FLOOR:
                dead.append(i)
        for i in dead:
            del self.elig[i]

    # ------------------------------------------------------------------- act
    def act(self, obs):
        v = self._key(obs)
        # ---- nearest prototype (attraction = cosine - scar), exactly brain.py
        if len(self.vecs):
            sims = self.vecs @ v
            att = sims - np.asarray(self.scar)
            idx = int(np.argmax(att))
            sim = float(sims[idx])
        else:
            idx, sim = None, 0.0
        surprise = 1.0 - sim if idx is not None else 1.0

        learn = not self.frozen_eval
        if learn:
            if (idx is None or sim < self.tolerance(idx)) and len(self.mass) < self.max_protos:
                idx = self._spawn(v)
            elif idx is not None:
                eta = ETA0 * self.chem.plasticity()
                w = self.vecs[idx] + eta * (v - self.vecs[idx])
                n = np.linalg.norm(w)
                self.vecs[idx] = w / n if n > 0 else w
                self.mass[idx] += 1.0
                self.n_abs[idx] += 1
                self.s_sum[idx] += sim
                self.s_sq[idx] += sim * sim
            self.chem.observe(surprise)
        elif idx is None:
            idx = 0 if len(self.mass) else None

        self._decay_traces()
        if idx is not None:
            self.elig[idx] = 1.0

        # ---- ACTION HEAD ------------------------------------------------
        if idx is None:
            scores = np.zeros(self.n_actions)
        elif self.mode == "trace":
            scores = np.zeros(self.n_actions)
            for i, e in self.elig.items():
                scores += e * self.Q[i]
        else:
            scores = self.Q[idx]

        if self.rng.random() < self.eps:
            a = int(self.rng.integers(self.n_actions))
        else:
            m = float(np.max(scores))
            ties = np.flatnonzero(scores >= m - 1e-12)
            a = int(ties[0]) if len(ties) == 1 else int(self.rng.choice(ties))

        self._last_idx = idx
        self._last_a = a
        self._last_scores = scores
        self.beat += 1
        if learn:
            self.eps = max(self.p["eps_floor"],
                           self.eps - self.p["eps_decay"])
        # context is updated AFTER the key is formed, so the key sees the past
        if self.mode == "ctx":
            lam = self.p["lam"]
            self.ctx = lam * self.ctx + (1.0 - lam) * np.asarray(obs, dtype=np.float64)
        return a

    # ----------------------------------------------------------------- learn
    def learn(self, reward, done=False):
        """Reward pays through the SAME eligibility traces the parent's tap uses."""
        if self.frozen_eval or self._last_idx is None:
            self.chem.decay()
            return
        i0 = self._last_idx
        baseline = float(self.V[i0])
        rpe = float(reward) - baseline
        self.V[i0] += self.p["eta_v"] * rpe

        plast = self.chem.plasticity()
        eta = self.p["eta_q"] * plast
        a = self._last_a
        for i, e in self.elig.items():
            self.Q[i, a] += eta * e * rpe
        np.clip(self.Q, -20.0, 20.0, out=self.Q)

        # the organism's own payout: mass up on pleasure, scar on pain
        if reward > 0:
            for i, e in self.elig.items():
                self.mass[i] += TAP_UP_BONUS * e * 0.01
        elif reward < 0:
            for i, e in self.elig.items():
                self.scar[i] = min(1.0, self.scar[i] + SCAR_HIT * e * 0.02)

        self.chem.observe_rpe(rpe)
        self.chem.valence(float(reward))
        self.chem.decay()

    # ----------------------------------------------------------------- stats
    def stats(self):
        return {"n_prototypes": int(len(self.mass)),
                "key_dim": int(self.key_dim),
                "memory_cells": int(len(self.mass) * (self.key_dim + self.n_actions)),
                "n_params": int(N_PARAMS),
                "mode": self.mode,
                "chemistry": self.chem_on,
                "ne_events": int(self.chem.ne_events),
                "eps": round(float(self.eps), 4),
                "knobs": {k: round(float(v), 5) for k, v in self.p.items()}}
