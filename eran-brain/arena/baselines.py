# -*- coding: utf-8 -*-
"""baselines.py — the arms that keep everybody honest.

> BROKEN WINDOWS LAW: test the REAL output, never a proxy.

Last time (ERAN-vs-SNN, 2026-08-21) the boring control that did no learning at
all beat every learning arm. So the boring controls come first, always:

  RANDOM     — uniform action. Prints the chance line before any result.
  ORACLE     — a tiny hand-coded controller per task. Not learned; it is the
               ceiling, and it proves the task is solvable.
  Q-TAB      — tabular reward learning keyed on the CURRENT observation only.
               A memoryless online learner. On DMS at delay>=1 it must sit at
               chance; if it doesn't, something is leaking.
  Q-TAB-MEM  — the same tabular learner keyed on the WHOLE episode history so
               far. Perfect memory, no architecture, no spikes, no organism.
               This is the "nearest centroid" of this arena: if it wins, the
               interesting architectures bought nothing.
"""
import numpy as np


class RandomAgent:
    online = False

    def __init__(self, n_obs, n_actions, seed=0):
        self.n_actions = int(n_actions)
        self.rng = np.random.default_rng(seed)

    def reset_episode(self):
        pass

    def act(self, obs):
        return int(self.rng.integers(self.n_actions))

    def learn(self, reward, done=False):
        pass

    def stats(self):
        return {"n_params": 0}


class DMSOracle:
    """Reads the cue off the observation, keeps it, compares at the choice step.
    Hand-coded on purpose: it is the task ceiling, not a contender."""
    online = False

    def __init__(self, n_obs, n_actions, n_items=4, seed=0):
        self.k = int(n_items)
        self.rng = np.random.default_rng(seed)

    def reset_episode(self):
        self.cue = None

    def act(self, obs):
        o = np.asarray(obs)
        cue_slot, a_slot, b_slot = 3, 3 + self.k, 3 + 2 * self.k
        cue_vec = o[cue_slot:cue_slot + self.k]
        if cue_vec.sum() > 0:
            self.cue = int(np.argmax(cue_vec))
        if o[2] > 0:                              # choice phase
            A = o[a_slot:a_slot + self.k]
            B = o[b_slot:b_slot + self.k]
            if A.sum() > 0 and self.cue is not None:
                return 0 if int(np.argmax(A)) == self.cue else 1
        return 0

    def learn(self, reward, done=False):
        pass

    def stats(self):
        return {"n_params": 0, "hand_coded": True}


class RuleOracle:
    """Win-stay / lose-shift over the two hypotheses. The classic near-optimal
    strategy for a Wisconsin card sort with two candidate rules."""
    online = False

    def __init__(self, n_obs, n_actions, seed=0):
        self.rng = np.random.default_rng(seed)

    def reset_episode(self):
        self.rule = 0
        self.prev_a = None
        self.prev_correct = None

    def act(self, obs):
        o = np.asarray(obs)
        col = int(np.argmax(o[0:3]))
        shp = int(np.argmax(o[3:6]))
        prev_r = o[-1]
        if self.prev_a is not None and prev_r < 0:
            self.rule = 1 - self.rule          # lose -> shift hypothesis
        a = col if self.rule == 0 else shp
        self.prev_a = a
        return a

    def learn(self, reward, done=False):
        pass

    def stats(self):
        return {"n_params": 0, "hand_coded": True}


class PongOracle:
    """Track the ball's y. The house's simplest possible controller."""
    online = False

    def __init__(self, n_obs, n_actions, seed=0):
        pass

    def reset_episode(self):
        pass

    def act(self, obs):
        by, my = obs[1], obs[4]
        if by > my + 0.01:
            return 2
        if by < my - 0.01:
            return 0
        return 1

    def learn(self, reward, done=False):
        pass

    def stats(self):
        return {"n_params": 0, "hand_coded": True}


# ── tabular online learners ────────────────────────────────────────────────
def _disc(o, bins=6):
    a = np.asarray(o)
    return tuple(np.clip((a * bins).astype(np.int32), -bins, bins).tolist())


class TabularQ:
    """Online reward learning over a discretised state key.

    memory=False : key = the current observation. Memoryless.
    memory=True  : key = every observation seen this episode. Perfect memory,
                   zero architecture. The control that must be beaten.
    """
    online = True

    def __init__(self, n_obs, n_actions, memory=False, seed=0,
                 eta=0.25, eps0=1.0, eps_decay=5e-5, eps_floor=0.02):
        self.n_actions = int(n_actions)
        self.memory = bool(memory)
        self.rng = np.random.default_rng(seed)
        self.eta, self.eps0 = eta, eps0
        self.eps_decay, self.eps_floor = eps_decay, eps_floor
        self.hard_reset()

    def hard_reset(self):
        self.Q = {}
        self.eps = self.eps0
        self.frozen_eval = False
        self.reset_episode()

    def reset_episode(self):
        self.hist = ()
        self._key = None
        self._a = None

    def act(self, obs):
        d = _disc(obs)
        if self.memory:
            self.hist = self.hist + (d,)
            key = self.hist
        else:
            key = d
        q = self.Q.get(key)
        if q is None:
            q = np.zeros(self.n_actions)
            if not self.frozen_eval:
                self.Q[key] = q
        if self.rng.random() < self.eps:
            a = int(self.rng.integers(self.n_actions))
        else:
            m = float(np.max(q))
            ties = np.flatnonzero(q >= m - 1e-12)
            a = int(ties[0]) if len(ties) == 1 else int(self.rng.choice(ties))
        self._key, self._a = key, a
        if not self.frozen_eval:
            self.eps = max(self.eps_floor, self.eps - self.eps_decay)
        return a

    def learn(self, reward, done=False):
        if self.frozen_eval or self._key is None or reward == 0.0:
            return
        q = self.Q.get(self._key)
        if q is None:
            return
        q[self._a] += self.eta * (reward - q[self._a])

    def stats(self):
        return {"n_params": int(sum(len(v) for v in self.Q.values())),
                "n_states": len(self.Q), "memory": self.memory,
                "eps": round(float(self.eps), 4)}
