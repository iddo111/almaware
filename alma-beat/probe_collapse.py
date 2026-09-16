import sys, random
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import weave as W, judge_local
st = {"ema": 0.5}
def rf(bar):
    s = judge_local.score_bar(bar)
    st["ema"] = 0.995*st["ema"] + 0.005*s["score"]
    return (s["score"] - st["ema"]) * 4.0, s["score"], s
m = W.BeatWeave(W.Hyper(hidden=32, rule="three-factor", seed=0))
b0, _ = m.bar()
print("TRIAL 0   kick", b0["kick"])
print("          bass", b0["bass"])
print("          ", judge_local.score_bar(b0)["parts"])
for i in range(120):
    r = m.play_and_learn(rf)
print("TRIAL 120 kick", r["bar"]["kick"])
print("          bass", r["bar"]["bass"])
print("          ", r["report"]["parts"])
sat = sum(1 for st_ in m.strands if abs(st_.weight) >= 7.9)
print("cords pinned at the +-8 ceiling: %d / %d" % (sat, len(m.strands)))
