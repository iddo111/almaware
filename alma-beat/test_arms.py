import sys, time, random
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import weave as W, judge_local, render_mid
from baseline import VHyper, VanillaBeat

H = 16
bw = W.BeatWeave(W.Hyper(hidden=H, seed=0))
vb = VanillaBeat(VHyper(hidden=H, seed=0))
print("PARAM MATCH: weave cords=%d   vanilla params=%d   equal=%s" % (
    bw.n_params(), vb.n_params(), bw.n_params() == vb.n_params()))

st = {"ema": 0.5}
def rf(bar):
    s = judge_local.score_bar(bar)
    st["ema"] = 0.995 * st["ema"] + 0.005 * s["score"]
    return (s["score"] - st["ema"]) * 4.0, s["score"], s

rng = random.Random(1)
for arm, rule in (("alma-pert", "perturbation"), ("alma-3f", "three-factor"),
                  ("frozen", "frozen")):
    m = W.BeatWeave(W.Hyper(hidden=H, rule=rule, seed=0))
    t = time.time()
    for _ in range(20):
        r = m.play_and_learn(rf)
    print("%-10s 20 trials in %.1fs  last=%.3f moved=%.4f" % (
        arm, time.time() - t, r["report"]["score"], m.moved))
t = time.time()
for _ in range(20):
    r = vb.play_and_learn(rf, rng)
print("%-10s 20 trials in %.1fs  last=%.3f" % ("vanilla", time.time() - t,
                                               r["report"]["score"]))
p = render_mid.write("/tmp/probe.mid", [r["bar"]], repeats=4)
import midi_in
L = midi_in.lanes(p)
print("render+reread ok: steps=%d kick=%d bass=%d" % (
    L["steps"], sum(L["kick"]), sum(1 for b in L["bass"] if b)))
