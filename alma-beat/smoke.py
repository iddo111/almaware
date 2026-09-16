import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import weave, judge_local
for H in (8, 32):
    hw = weave.Hyper(hidden=H, seed=1)
    bw = weave.BeatWeave(hw)
    t = time.time(); bar, _ = bw.bar(); dt = time.time() - t
    print("H=%3d knots=%d strands=%d learnable=%d bar=%.0fms score=%.3f" % (
        H, len(bw.weave.knots), len(bw.strands), bw.n_params(), dt*1000,
        judge_local.score_bar(bar)["score"]))
    print("      kick", bar["kick"])
    print("      bass", bar["bass"])
hw = weave.Hyper(hidden=16, seed=3)
bw = weave.BeatWeave(hw)
st = {"ema": 0.5}
def rf(bar):
    s = judge_local.score_bar(bar)
    st["ema"] = 0.95*st["ema"] + 0.05*s["score"]
    return (s["score"] - st["ema"]) * hw.gain, s["score"], s
t = time.time(); out = bw.play_and_learn(rf); dt = time.time() - t
print("trial ok in %.0fms score=%.3f moved=%.5f" % (dt*1000, out["report"]["score"], out["moved"]))
