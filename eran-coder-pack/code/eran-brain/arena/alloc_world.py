# -*- coding: utf-8 -*-
"""alloc_world.py — AllocWorld: one life, one energy budget, several things at
once. Built to answer Iddo's re-read of the 2026-08-21 chemistry null: "the
special mechanisms, especially the chemistry, will win in COMPLEX tasks" --
a single-rule, single-task world gives a regulator nothing to regulate. This
world gives it six genuine dilemmas, one per pressure the spec named.

> BROKEN WINDOWS LAW: test the REAL output, never a proxy.

CONTRACT (matches tasks.py / es.py exactly, so es.py is reused UNCHANGED):
    t = AllocWorld(...); obs = t.reset(seed)
    obs, reward, done, info = t.step(action)   # action int in [0, n_actions)
    t.n_obs, t.n_actions

THREE CONCURRENT STREAMS share ONE action per tick (one energy budget):
    L (0) LEARNABLE   -- Wisconsin-style binary rule (correct = cue XOR rule),
                         rule flips at unknown, non-stationary change points.
                         Persisting through a flip is WRONG; catching the flip
                         and adapting is the whole test.
    S (1) STABLE      -- same binary structure, rule NEVER flips. Persisting
                         (keep responding, don't get distracted away from a
                         free win) is RIGHT.
    N (2) NOISE       -- reward is independent of the response (coin flip,
                         mean 0), win or lose. There is nothing to learn.
                         Persisting is WRONG; giving up is the only correct
                         answer, and it costs energy to find that out and
                         costs energy to keep checking.

Every tick the agent picks ONE of 7 actions: (L,0) (L,1) (S,0) (S,1) (N,0)
(N,1) REST. Engaging costs 1 energy (REST costs 0); the episode's energy
budget is smaller than its length, so "attend to one, the others wait" is a
real trade-off, not just a side-effect of having one action slot.

REWARD is DELAYED (3-9 ticks, drawn per trial) and STOCHASTIC (correct: +1 w.p.
0.8 else -1; incorrect: mirrored; N: +/-1 w.p. 0.5 regardless of response) --
credit must bridge a real gap through whatever the agent uses in place of a
notepad (ERAN's own eligibility trace).

CHANGE POINTS on stream L happen at an unknown, NON-STATIONARY rate: the whole
episode is pre-simulated (before any action is taken -- this is the world's
own clock, not something the agent's choices can perturb) into segments
alternating between a FAST regime (rule lives 15-25 ticks) and a SLOW regime
(150-250 ticks), switching regime with probability P_REGIME_CHANGE after each
flip. The agent is NEVER told which regime is live; regime is recorded for
per-regime REPORTING only, never placed in the observation.

DISTRACTORS: 6 pure N(0,1) noise observation dims, refreshed every tick, zero
causal link to any reward, present for every arm alike.

PARENT CHANNEL: a "parent_active" bit + a one-hot hint of the correct response
for the CURRENT stream-L trial, active more often shortly after a true switch
(parents teach when you're confused) than at baseline. Complying (choosing the
hinted L response while parent_active) earns an extra, immediate, undelayed
reward -- available to EVERY arm equally. Whether an agent's internal learning
rate reacts MORE to that specific kind of experience is entirely an agent-side
question (alloc_agent.Chemistry.oxt) -- the environment only pays the same
objective bonus to whoever complies, chemistry or not.

TRUE-SWITCH / RANDOM-MATCHED SCHEDULES are pre-computed at reset() (again: the
world's own clock, before any action exists) and exposed only through `info`,
never through `obs` -- so FULL/NONE/DA/NE/5HT/OXT agents cannot see them
(a privileged bit in the input would corrupt every ordinary arm's comparison),
while a thin custom rollout (alloc_rollout.py) hands `info` to the two schedule
arms only. `info["random_switch"]` fires exactly as many times per episode as
`info["true_switch"]` does, at uniformly random ticks -- the number-matched
control the spec asks for.
"""
import numpy as np

# ── task-scale constants (every ES-tuned knob in alloc_bounds.py is justified
#    against these numbers, not chosen by feel) ─────────────────────────────
EPISODE_TICKS = 800
ENERGY_BUDGET = 450                 # < EPISODE_TICKS: rest is sometimes forced
ENERGY_COST = 1

FAST_LO, FAST_HI = 15, 25           # stream-L rule lifetime, fast regime
SLOW_LO, SLOW_HI = 150, 250         # stream-L rule lifetime, slow regime
P_REGIME_CHANGE = 0.35              # after each flip, chance the regime itself
                                     # re-draws (fast<->slow); else it persists

MIN_DELAY, MAX_DELAY = 3, 9         # reward delay, ticks, drawn per trial
P_CORRECT_PAYS = 0.8                # correct response: +1 w.p. this, else -1
                                     # (mirrored for incorrect); N: always 0.5

D_DIM = 6                           # pure-noise distractor observation dims

BONUS_PARENT = 1.5                  # immediate, undelayed, on top of the
                                     # normal delayed/stochastic reward
P_PARENT_BASE = 0.01                # parent-active probability, baseline
P_PARENT_POST_SWITCH = 0.20         # parent-active probability, just after a
                                     # true switch (parents teach when you're
                                     # confused, not at random moments)
POST_SWITCH_WINDOW = 15             # ticks after a switch counted as "just after"

N_STREAMS = 3
STREAM_NAMES = ("L", "S", "N")
N_ACTIONS = 7                       # 3 streams x 2 responses + REST

# ── observation layout, computed once so alloc_agent.py never hardcodes a
#    fragile offset -- these ARE the contract between world and agent.
I_CUE_L, I_CUE_S, I_CUE_N = 0, 2, 4
I_ENERGY, I_TICKS = 6, 7
I_DISTRACTOR = 8
I_PARENT_ACTIVE = I_DISTRACTOR + D_DIM              # 14
I_PARENT_HINT = I_PARENT_ACTIVE + 1                 # 15, 16
I_PREV_ACTION = I_PARENT_HINT + 2                   # 17 .. 17+N_ACTIONS-1
I_PREV_REWARD = I_PREV_ACTION + N_ACTIONS           # 24


def _decode_action(a):
    """action -> (stream in {0,1,2} or None, response in {0,1} or None)."""
    if a == 6:
        return None, None
    return a // 2, a % 2


class AllocWorld:
    """See module docstring. One episode = EPISODE_TICKS ticks."""

    n_actions = N_ACTIONS
    # obs = cueL(2) cueS(2) cueN(2) energy_frac(1) ticks_frac(1) distractor(D_DIM)
    #       parent_active(1) parent_hint(2) prev_action(N_ACTIONS) prev_reward(1)
    n_obs = 2 + 2 + 2 + 1 + 1 + D_DIM + 1 + 2 + N_ACTIONS + 1

    def __init__(self, episode_ticks=EPISODE_TICKS, energy_budget=ENERGY_BUDGET):
        self.episode_ticks = int(episode_ticks)
        self.energy_budget = int(energy_budget)
        self.rng = np.random.default_rng(0)

    # ------------------------------------------------------------- schedule
    def _simulate_regime_segments(self):
        """The world's OWN clock: fully determined before any action exists.
        Returns (regime_by_tick uint8 array [0=fast,1=slow], switch_ticks list
        of tick indices where L's rule flips)."""
        segs = []
        t = 0
        regime = 0 if self.rng.random() < 0.5 else 1
        while t < self.episode_ticks:
            interval = int(self.rng.integers(FAST_LO, FAST_HI + 1) if regime == 0
                          else self.rng.integers(SLOW_LO, SLOW_HI + 1))
            end = min(t + interval, self.episode_ticks)
            segs.append((t, end, regime))
            t = end
            if t < self.episode_ticks and self.rng.random() < P_REGIME_CHANGE:
                regime = 0 if self.rng.random() < 0.5 else 1
        regime_by_tick = np.zeros(self.episode_ticks, dtype=np.uint8)
        for (a, b, r) in segs:
            regime_by_tick[a:b] = r
        switch_ticks = sorted(b for (_, b, _) in segs if b < self.episode_ticks)
        return regime_by_tick, switch_ticks

    # ------------------------------------------------------------------ api
    def reset(self, seed=None):
        if seed is not None:
            self.rng = np.random.default_rng(seed)
        self.tick = 0
        self.energy = self.energy_budget
        self.regime_by_tick, self.switch_ticks = self._simulate_regime_segments()
        self.switch_set = set(self.switch_ticks)
        n_sw = len(self.switch_ticks)
        rand_positions = (self.rng.choice(self.episode_ticks, size=n_sw,
                                          replace=False) if n_sw else
                         np.zeros(0, dtype=int))
        self.random_set = set(int(x) for x in rand_positions)

        self.rule_L = int(self.rng.integers(2))
        self.rule_S = int(self.rng.integers(2))          # fixed forever
        self.cue = [int(self.rng.integers(2)) for _ in range(N_STREAMS)]
        self.since_switch = 10 ** 9                       # "long ago" at birth

        self.pending = []                                # (deliver_tick, value, stream_tag, regime_tag)
        self.prev_action = -1
        self.prev_reward = 0.0

        # ---- episode-level diagnostics, returned by report() -------------
        self.n_switches = 0
        self.engage_count = [0, 0, 0]
        self.correct_count = [[0, 0], [0, 0]]             # L,S: [n_correct, n_trials]
        self.reward_by_stream = [0.0, 0.0, 0.0]
        self.reward_by_regime = {"fast": 0.0, "slow": 0.0}
        self.reward_delivered_total = 0.0
        self.energy_exhausted_events = 0
        self.parent_active_ticks = 0
        self.parent_complied = 0
        self.parent_offered = 0                           # parent-active AND agent engaged L
        self.true_switch_ticks = []
        self.random_switch_ticks = []

        return self._obs()

    def _parent_prob(self):
        return (P_PARENT_POST_SWITCH if self.since_switch < POST_SWITCH_WINDOW
               else P_PARENT_BASE)

    def _obs(self):
        o = np.zeros(self.n_obs, dtype=np.float64)
        i = 0
        for s in range(N_STREAMS):
            o[i + self.cue[s]] = 1.0
            i += 2
        o[i] = self.energy / max(1, self.energy_budget); i += 1
        o[i] = max(0.0, (self.episode_ticks - self.tick) / self.episode_ticks); i += 1
        o[i:i + D_DIM] = self.rng.normal(0.0, 1.0, D_DIM); i += D_DIM

        parent_active = 1 if self.rng.random() < self._parent_prob() else 0
        self._parent_active_now = bool(parent_active)
        o[i] = float(parent_active); i += 1
        if parent_active:
            self.parent_active_ticks += 1
            hint = self.cue[0] ^ self.rule_L
            o[i + hint] = 1.0
        i += 2

        if self.prev_action >= 0:
            o[i + self.prev_action] = 1.0
        i += N_ACTIONS
        o[i] = self.prev_reward
        return o

    def step(self, action):
        info = {"true_switch": False, "random_switch": False,
                "engaged_stream": None, "correct": None,
                "energy_exhausted": False}

        # ---- the world's own clock: switch check happens BEFORE resolution
        if self.tick in self.switch_set:
            self.rule_L = 1 - self.rule_L
            self.since_switch = 0
            self.n_switches += 1
            info["true_switch"] = True
            self.true_switch_ticks.append(self.tick)
        if self.tick in self.random_set:
            info["random_switch"] = True
            self.random_switch_ticks.append(self.tick)
        regime_now = "fast" if self.regime_by_tick[self.tick] == 0 else "slow"

        stream, resp = _decode_action(int(action))
        if stream is not None:
            if self.energy > 0:
                self.energy -= 1
                self.engage_count[stream] += 1
                info["engaged_stream"] = stream

                parent_active = getattr(self, "_parent_active_now", False)
                if stream == 0 and parent_active:
                    self.parent_offered += 1

                if stream == 2:                              # NOISE: no rule
                    correct = None
                    val = 1.0 if self.rng.random() < 0.5 else -1.0
                else:
                    rule = self.rule_L if stream == 0 else self.rule_S
                    correct = (resp == (self.cue[stream] ^ rule))
                    val = ((1.0 if self.rng.random() < P_CORRECT_PAYS else -1.0)
                          if correct else
                          (-1.0 if self.rng.random() < P_CORRECT_PAYS else 1.0))
                    self.correct_count[stream][0] += int(correct)
                    self.correct_count[stream][1] += 1
                info["correct"] = correct

                delay = int(self.rng.integers(MIN_DELAY, MAX_DELAY + 1))
                deliver = min(self.tick + delay, self.episode_ticks - 1)
                self.pending.append((deliver, val, stream, regime_now))

                if stream == 0 and parent_active and correct and resp == (
                        self.cue[0] ^ self.rule_L):
                    # compliance with the hint -- immediate, undelayed, equal
                    # for every arm (the CHEMISTRY question is whether an
                    # agent's internal learning rate reacts more to this, not
                    # whether it gets paid more; everyone gets paid the same).
                    self.pending.append((self.tick, BONUS_PARENT, "parent",
                                        regime_now))
                    self.parent_complied += 1

                self.cue[stream] = int(self.rng.integers(2))   # next trial
            else:
                info["energy_exhausted"] = True
                self.energy_exhausted_events += 1

        self.since_switch += 1
        self.tick += 1
        done = (self.tick >= self.episode_ticks)

        # ---- deliver -------------------------------------------------------
        due = [p for p in self.pending if p[0] <= self.tick - 1 or done]
        self.pending = [p for p in self.pending if not (p[0] <= self.tick - 1 or done)]
        reward = 0.0
        for (_, val, tag, rtag) in due:
            reward += val
            self.reward_delivered_total += val
            if tag == "parent":
                self.reward_by_stream[0] += val
            else:
                self.reward_by_stream[tag] += val
            if rtag in self.reward_by_regime:
                self.reward_by_regime[rtag] += val

        self.prev_action = int(action)
        self.prev_reward = reward
        obs = self._obs() if not done else np.zeros(self.n_obs, dtype=np.float64)
        return obs, reward, done, info

    # --------------------------------------------------------------- report
    def report(self):
        acc = {}
        for s, name in ((0, "L"), (1, "S")):
            nc, nt = self.correct_count[s]
            acc[name] = (nc / nt) if nt else None
        return {
            "n_switches": self.n_switches,
            "engage_count": {STREAM_NAMES[s]: self.engage_count[s]
                             for s in range(N_STREAMS)},
            "rest_count": self.episode_ticks - sum(self.engage_count),
            "accuracy": acc,
            "reward_by_stream": {STREAM_NAMES[s]: round(self.reward_by_stream[s], 3)
                                 for s in range(N_STREAMS)},
            "reward_total": round(self.reward_delivered_total, 3),
            "reward_by_regime": {k: round(v, 3) for k, v
                                 in self.reward_by_regime.items()},
            "energy_exhausted_events": self.energy_exhausted_events,
            "parent_active_ticks": self.parent_active_ticks,
            "parent_offered": self.parent_offered,
            "parent_complied": self.parent_complied,
            "true_switch_ticks": list(self.true_switch_ticks),
            "random_switch_ticks": list(self.random_switch_ticks),
            "n_fast_ticks": int((self.regime_by_tick == 0).sum()),
            "n_slow_ticks": int((self.regime_by_tick == 1).sum()),
        }


def make_task(**kw):
    return AllocWorld(**kw)


if __name__ == "__main__":
    # smoke test: random policy, sane shapes, energy actually binds.
    t = AllocWorld()
    o = t.reset(11)
    assert o.shape == (t.n_obs,), o.shape
    rng = np.random.default_rng(0)
    tot = 0.0
    done = False
    steps = 0
    while not done:
        a = int(rng.integers(t.n_actions))
        o, r, done, info = t.step(a)
        tot += r
        steps += 1
        assert o.shape == (t.n_obs,) or done
    rep = t.report()
    print(f"n_obs={t.n_obs} n_actions={t.n_actions} steps={steps} total_reward={tot:.2f}")
    print(rep)
    assert steps == EPISODE_TICKS
    assert rep["n_switches"] >= 1
    assert sum(rep["engage_count"].values()) + rep["rest_count"] == EPISODE_TICKS
    assert sum(rep["engage_count"].values()) <= ENERGY_BUDGET
    print("alloc_world.py self-test: PASS")
