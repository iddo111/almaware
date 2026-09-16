# -*- coding: utf-8 -*-
"""verify_dead_dims.py — prove the two DEAD search dimensions the audit claims,
by running the real agent rather than by reading the code.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL
> output, never a proxy.

CLAIM A  ne_gain does nothing whenever chemistry=False (which is every arm
         except `chem` and `taucap+chem`), because Chemistry.observe_rpe
         returns immediately when frozen. If true, two agents differing ONLY in
         ne_gain must produce byte-identical trajectories.

CLAIM B  eps0 does nothing whenever eps0 < eps_floor, because the schedule
         eps = max(eps_floor, eps - eps_decay) clamps on the first step.
"""
import sys

import numpy as np

import es as ES
from eran_agent import EranAgent, PARAM_NAMES
from tasks import RuleSwitchTask


def trajectory(knob_overrides, seed=7, episodes=3, chemistry=False):
    task_factory = lambda: RuleSwitchTask()
    ag = EranAgent(RuleSwitchTask.n_obs, RuleSwitchTask.n_actions, mode="ctx",
                   chemistry=chemistry, seed=seed)
    ag.p = dict(ag.p)
    ag.p.update(knob_overrides)
    ag.hard_reset()
    ag.p.update(knob_overrides)          # hard_reset re-reads p; re-apply
    out = []
    for i in range(episodes):
        task = task_factory()
        obs = task.reset(1000 + i)
        ag.reset_episode()
        done = False
        while not done:
            a = ag.act(obs)
            obs, r, done, _ = task.step(a)
            ag.learn(r, done)
            out.append((a, r))
    return out


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    common = {"lam": 0.3, "ctx_gain": 0.9, "trace_tau": 5.0, "eta_q": 0.3,
              "eta_v": 0.2, "eps_decay": 1e-3, "strict_scale": 0.7}

    print("CLAIM A — ne_gain is inert without chemistry")
    a = trajectory({**common, "ne_gain": 0.0, "eps0": 0.2, "eps_floor": 0.05},
                   chemistry=False)
    b = trajectory({**common, "ne_gain": 2.0, "eps0": 0.2, "eps_floor": 0.05},
                   chemistry=False)
    print(f"  chemistry=False : ne_gain 0.0 vs 2.0 -> identical trajectory? "
          f"{a == b}   ({len(a)} steps compared)")
    c = trajectory({**common, "ne_gain": 0.0, "eps0": 0.2, "eps_floor": 0.05},
                   chemistry=True)
    d = trajectory({**common, "ne_gain": 2.0, "eps0": 0.2, "eps_floor": 0.05},
                   chemistry=True)
    print(f"  chemistry=True  : ne_gain 0.0 vs 2.0 -> identical trajectory? "
          f"{c == d}   (must be False, or the knob is dead everywhere)")

    print("\nCLAIM B — eps0 is inert whenever eps0 < eps_floor")
    e = trajectory({**common, "ne_gain": 1.0, "eps0": 0.05, "eps_floor": 0.30})
    f = trajectory({**common, "ne_gain": 1.0, "eps0": 0.25, "eps_floor": 0.30})
    print(f"  eps0 0.05 vs 0.25, both < eps_floor=0.30 -> identical? {e == f}")
    g = trajectory({**common, "ne_gain": 1.0, "eps0": 0.60, "eps_floor": 0.05})
    h = trajectory({**common, "ne_gain": 1.0, "eps0": 0.90, "eps_floor": 0.05})
    print(f"  eps0 0.60 vs 0.90, both > eps_floor=0.05 -> identical? {g == h}"
          f"   (must be False)")

    ok = (a == b) and (c != d) and (e == f) and (g != h)
    print(f"\nboth dead-dimension claims verified on the REAL agent: {ok}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
