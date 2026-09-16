import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import weave as W, judge_local
st = {"ema": 0.5}
def rf(bar):
    s = judge_local.score_bar(bar)
    st["ema"] = 0.995*st["ema"] + 0.005*s["score"]
    return (s["score"] - st["ema"]) * 4.0, s["score"], s
m = W.BeatWeave(W.Hyper(hidden=32, rule="perturbation-all", seed=0))
print("targets under private jitter:", len(m.perturber.knots),
      "(hidden + heads)   cords:", m.n_params())
tot = 0.0
for i in range(300):
    r = m.play_and_learn(rf)
    if i >= 200:
        tot += r["report"]["score"]
print("TRIAL 300 kick", r["bar"]["kick"])
print("          bass", r["bar"]["bass"])
print("          ", r["report"]["parts"])
print("mean score over last 100 trials: %.3f   (frozen floor = 0.626)" % (tot/100))
