# Does the junction's OWN decision layer have any reach, or is it structurally blind?
# The loop's exam froze at 0.2500 / 24-hushed for 8 rounds while its ruler climbed to
# 0.7222. Either theta/tau can move it, or the junction is the blind component and the
# answer is STOP.
import sys, json
import numpy as np
sys.path.insert(0, "/home/eran3/sibling-ear")
sys.path.insert(0, "/home/eran3/sibling-ear/models/eran-brain/holobrain2")
sys.path.insert(0, "/home/eran3/sibling-ear/models/alma-language")
import sibling as S
import anatomy

sib = S.Sibling("/home/eran3/sibling-ear")
V, y, t = sib.corpus()
h = sib._load("state/heldout.json", None)
st = sib._load("state/posture.json", {})
g = np.asarray(st["g"], dtype=np.float64); bias = dict(st.get("bias", {}))
train = [i for i in range(len(y)) if int(t[i]) != S.EXAM_TAKE]
R = S.build_refs(V, y, train, len(S.CORPUS_UNITS))
probe = h["exam_idx"]

def junc(g, theta, tau):
    us, D = S.wdist_matrix(V, probe, R, g, bias)
    hit = hush = 0
    for k, i in enumerate(probe):
        n = {S.CORPUS_UNITS[u]: float(D[k][j]) for j, u in enumerate(us)}
        o = anatomy.listen(n, theta=theta, tau=tau)
        if o["said"] is None: hush += 1
        elif o["said"] == S.CORPUS_UNITS[y[i]]: hit += 1
    return hit/len(probe), hush

one = np.ones(V.shape[1])
print("posture = the one the 14 rounds actually learned; exam take t05, n=36")
print("%8s %8s | %-18s | %-18s" % ("tau", "theta", "LEARNED posture", "BORN posture g=1"))
best = (0, None)
for tau in (0.25, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0):
    for theta in (0.02, 0.05, 0.10, 0.20, 0.35, 0.50):
        a, hu = junc(g, theta, tau)
        b, hb = junc(one, theta, tau)
        if a > best[0]: best = (a, (tau, theta, hu))
        print("%8.2f %8.2f | acc %.4f hush %-3d | acc %.4f hush %-3d" % (tau, theta, a, hu, b, hb))
print()
print("BORN default (tau 1.0 theta 0.20): learned %.4f / born %.4f" % (junc(g,0.20,1.0)[0], junc(one,0.20,1.0)[0]))
print("BEST over the dials: acc %.4f at tau=%s theta=%s hush=%s" % (best[0], best[1][0], best[1][1], best[1][2]))
print("ruler ceiling (argmin, no junction): %.4f" % S.ruler_accuracy(V, y, probe, R, g, bias))
