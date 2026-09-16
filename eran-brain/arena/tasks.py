# -*- coding: utf-8 -*-
"""tasks.py — the three AGENTIC tasks, one contract.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL
> output, never a proxy.

Contract every task honours:

    t = Task(...); obs = t.reset(seed)
    obs, reward, done, info = t.step(action)     # action is an int in [0, n_actions)
    t.n_obs, t.n_actions

Every observation is a float32 vector and ALWAYS ends with
``[prev_action one-hot | prev_reward]`` so that a frozen-weight policy has, in
principle, the information it needs to adapt inside an episode (the standard
meta-RL contract). Handing that to everybody is what makes the comparison fair:
no arm gets a private channel.

TASK 1  PONG            — sensorimotor, continuous. Wraps Iddo's own pong_env.py
                          unchanged (D:\\CLAUDE\\pong-alma\\pong_env.py).
TASK 2  DMS             — delayed match to sample. Cue, N blank steps, then two
                          choices. Chance = 50%. The delay sweep is the whole
                          point: a pure input->output map dies at N>=1.
TASK 3  RULE SWITCH     — Wisconsin-card-sort structure. Sort by colour until
                          criterion, then the rule silently becomes shape.
                          Chance = 33.3%. Measures trials-to-criterion and
                          PERSEVERATIVE errors (still obeying the dead rule).
"""
import numpy as np

from pong_env import PongEnv


# ────────────────────────────────────────────────────────────────────────────
# TASK 2 — DELAYED MATCH TO SAMPLE
# ────────────────────────────────────────────────────────────────────────────
class DMSTask:
    """Cue -> (delay-1 blank steps) -> two choices. Pick the one that matches.

    delay = 0  : cue and choices appear on the SAME observation. A memoryless
                 map CAN solve this. It is the control that proves the task is
                 learnable at all and that the agent understands "match".
    delay = N>0: the cue is shown on step 0 and is GONE from step 1 onward; the
                 choices appear on step N. Nothing but internal state can carry
                 the cue across the gap.

    Actions: 0 = pick A, 1 = pick B.   Chance = 50%.
    Reward:  0 on cue/delay steps, +1 / -1 on the choice step. Episode ends there.
    """

    N_ITEMS = 4
    n_actions = 2

    # obs = phase(3) | cue item(4) | choice A(4) | choice B(4) | prev act(2) | prev r(1)
    n_obs = 3 + N_ITEMS + N_ITEMS + N_ITEMS + 2 + 1

    def __init__(self, delay):
        self.delay = int(delay)
        self.rng = np.random.default_rng(0)

    # ---------------------------------------------------------------- helpers
    def _obs(self):
        o = np.zeros(self.n_obs, dtype=np.float64)
        cue_slot = 3
        a_slot = cue_slot + self.N_ITEMS
        b_slot = a_slot + self.N_ITEMS
        pa_slot = b_slot + self.N_ITEMS

        if self.delay == 0:
            o[2] = 1.0                                  # phase = choice
            o[cue_slot + self.cue] = 1.0                # cue still visible
            o[a_slot + self.cA] = 1.0
            o[b_slot + self.cB] = 1.0
        elif self.t == 0:
            o[0] = 1.0                                  # phase = cue
            o[cue_slot + self.cue] = 1.0
        elif self.t < self.delay:
            o[1] = 1.0                                  # phase = blank delay
        else:
            o[2] = 1.0                                  # phase = choice
            o[a_slot + self.cA] = 1.0
            o[b_slot + self.cB] = 1.0

        # ── the prev-action / prev-reward channel is deliberately held at ZERO
        # in DMS, for every arm alike. Leaving it live opens an EXTERNAL memory
        # loop: a memoryless policy can encode a bit of the cue into its own
        # action during the cue step and read it back through this channel on
        # the next step, relaying it across a blank delay indefinitely. That is
        # a real strategy, but it is memory in the ENVIRONMENT, not in the
        # agent, and it would wreck the very thing this task measures. In the
        # RULE task the channel is live for everyone, because there feedback is
        # the only possible way to learn that the rule changed.
        _ = pa_slot
        return o

    def _choice_step(self):
        return 0 if self.delay == 0 else self.delay

    # ------------------------------------------------------------------ api
    def reset(self, seed=None):
        if seed is not None:
            self.rng = np.random.default_rng(seed)
        self.cue = int(self.rng.integers(self.N_ITEMS))
        d = int(self.rng.integers(self.N_ITEMS - 1))
        self.dis = d if d < self.cue else d + 1          # distractor != cue
        self.match_is_A = bool(self.rng.integers(2))
        self.cA, self.cB = ((self.cue, self.dis) if self.match_is_A
                            else (self.dis, self.cue))
        self.t = 0
        self.prev_a = -1
        self.prev_r = 0.0
        return self._obs()

    def step(self, action):
        info = {}
        if self.t < self._choice_step():
            self.prev_a = int(action)
            self.prev_r = 0.0
            self.t += 1
            return self._obs(), 0.0, False, info
        correct = 0 if self.match_is_A else 1
        ok = (int(action) == correct)
        r = 1.0 if ok else -1.0
        info["correct"] = ok
        self.prev_a = int(action)
        self.prev_r = r
        self.t += 1
        return self._obs(), r, True, info

    def ep_len(self):
        return self._choice_step() + 1


# ────────────────────────────────────────────────────────────────────────────
# TASK 3 — RULE SWITCHING  (Wisconsin card sort)
# ────────────────────────────────────────────────────────────────────────────
class RuleSwitchTask:
    """A card has a COLOUR and a SHAPE, always different from each other so
    every single trial discriminates the two rules.

    Rule 'colour': the correct action is the colour index.
    Rule 'shape' : the correct action is the shape index.
    Nobody is ever told which rule is live. After the agent hits criterion
    (>= CRIT_HITS correct in the last CRIT_WINDOW trials) the rule SILENTLY
    flips. If it never hits criterion, the block times out at BLOCK_MAX.

    Actions: 0,1,2.  Chance = 33.3%.
    A PERSEVERATIVE error = the action that WOULD have been correct under the
    previous rule, played after the switch (within PERSEV_WINDOW trials).
    """

    N_COL = 3
    N_SHAPE = 3
    n_actions = 3

    CRIT_WINDOW = 10
    CRIT_HITS = 8
    BLOCK_MAX = 60
    PERSEV_WINDOW = 20
    N_BLOCKS = 6

    # obs = colour(3) | shape(3) | prev act(3) | prev r(1)
    n_obs = N_COL + N_SHAPE + 3 + 1

    def __init__(self, n_blocks=None):
        self.rng = np.random.default_rng(0)
        self.n_blocks = int(n_blocks or self.N_BLOCKS)

    def _deal(self):
        self.col = int(self.rng.integers(self.N_COL))
        s = int(self.rng.integers(self.N_SHAPE - 1))
        self.shape = s if s < self.col else s + 1        # shape != colour

    def _obs(self):
        o = np.zeros(self.n_obs, dtype=np.float64)
        o[self.col] = 1.0
        o[self.N_COL + self.shape] = 1.0
        if self.prev_a >= 0:
            o[self.N_COL + self.N_SHAPE + self.prev_a] = 1.0
        o[-1] = self.prev_r
        return o

    def reset(self, seed=None):
        if seed is not None:
            self.rng = np.random.default_rng(seed)
        self.rule = int(self.rng.integers(2))            # 0 = colour, 1 = shape
        self.prev_rule = None
        self.block = 0
        self.since_switch = 0
        self.window = []
        self.prev_a = -1
        self.prev_r = 0.0
        # per-episode measurements
        self.ttc = []            # trials-to-criterion, one per block
        self.persev = 0          # perseverative errors (post-switch window)
        self.persev_opportunities = 0
        self.n_correct = 0
        self.n_trials = 0
        self._deal()
        return self._obs()

    def step(self, action):
        a = int(action)
        correct_now = self.col if self.rule == 0 else self.shape
        ok = (a == correct_now)
        r = 1.0 if ok else -1.0

        info = {"correct": ok}
        self.n_trials += 1
        self.n_correct += int(ok)

        # perseveration: the answer the DEAD rule would have wanted
        if (self.prev_rule is not None
                and self.since_switch < self.PERSEV_WINDOW):
            old_correct = self.col if self.prev_rule == 0 else self.shape
            if old_correct != correct_now:
                self.persev_opportunities += 1
                if a == old_correct:
                    self.persev += 1
                    info["perseverative"] = True

        self.window.append(int(ok))
        if len(self.window) > self.CRIT_WINDOW:
            self.window.pop(0)
        self.since_switch += 1

        switched = False
        if (len(self.window) == self.CRIT_WINDOW
                and sum(self.window) >= self.CRIT_HITS):
            self.ttc.append(self.since_switch)
            switched = True
        elif self.since_switch >= self.BLOCK_MAX:
            self.ttc.append(self.BLOCK_MAX)              # censored: never got there
            switched = True

        if switched:
            self.block += 1
            self.prev_rule = self.rule
            self.rule = 1 - self.rule
            self.since_switch = 0
            self.window = []
            info["switch"] = True

        self.prev_a = a
        self.prev_r = r
        done = (self.block >= self.n_blocks)
        if not done:
            self._deal()
        return self._obs(), r, done, info

    def report(self):
        return {"ttc": list(self.ttc),
                "persev": self.persev,
                "persev_opportunities": self.persev_opportunities,
                "n_correct": self.n_correct,
                "n_trials": self.n_trials}


# ────────────────────────────────────────────────────────────────────────────
# TASK 1 — PONG (wraps Iddo's env unchanged)
# ────────────────────────────────────────────────────────────────────────────
class RandomOpp:
    def __init__(self, seed=0):
        self.rng = np.random.default_rng(seed)

    def act(self, obs):
        return int(self.rng.integers(3)) - 1


class PongTask:
    """The agent plays LEFT. Actions 0,1,2 -> paddle -1,0,+1.

    Episode = ``ticks`` env ticks with an automatic re-serve after every point,
    exactly like pong-alma's play_match. Reward per tick = +1 hit / -1 miss.
    """

    n_actions = 3
    # obs = pong obs(5) | prev act(3) | prev r(1)
    n_obs = 5 + 3 + 1

    def __init__(self, ticks=200, opponent=None):
        self.ticks = int(ticks)
        self.opponent = opponent or RandomOpp(9999)

    def _obs(self, raw):
        o = np.zeros(self.n_obs, dtype=np.float64)
        o[:5] = raw
        if self.prev_a >= 0:
            o[5 + self.prev_a] = 1.0
        o[-1] = self.prev_r
        return o

    def reset(self, seed=None):
        self.env = PongEnv(seed=int(seed if seed is not None else 0))
        self.obsL, self.obsR = self.env.reset()
        self.t = 0
        self.prev_a = -1
        self.prev_r = 0.0
        return self._obs(self.obsL)

    def step(self, action):
        aL = int(action) - 1
        aR = self.opponent.act(self.obsR)
        (self.obsL, self.obsR), rL, rR, done = self.env.step(aL, aR)
        if done:
            self.obsL, self.obsR = self.env.reset()
        self.t += 1
        self.prev_a = int(action)
        self.prev_r = rL
        fin = (self.t >= self.ticks)
        return self._obs(self.obsL), rL, fin, {"hit": rL > 0, "miss": rL < 0}

    def ep_len(self):
        return self.ticks


# ────────────────────────────────────────────────────────────────────────────
def make_task(name, **kw):
    if name == "dms":
        return DMSTask(kw.get("delay", 0))
    if name == "rule":
        return RuleSwitchTask(kw.get("n_blocks"))
    if name == "pong":
        return PongTask(kw.get("ticks", 200), kw.get("opponent"))
    raise ValueError(name)
