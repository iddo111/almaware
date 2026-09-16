"""A10 -- is the ear separating VOWELS or CONSONANTS?

The 220-unit board is 22 consonants x 10 nekudot. If the cochlea separates
vowels and not consonants, the board's 140 distinct sounds collapse toward
~10 distinguishable groups and the whole take question is the wrong question.

  (a) 4-way among the /a/ family {ah, ba, ma, abba} -- vowel held constant,
      only the consonant differs. chance 25%. HONEST design.
  (b) 2-way vowel contrast {ah, ih} -- consonant held (both bare vowels).
      chance 50%. HONEST design.
  (c) the 19 shallow units are ALL consonant+/a/. Their only measurement is
      3 back-to-back takes, i.e. zero temporal separation -- the leakiest
      possible split. State the size of that leak, measured on the deep units.
"""
import json, numpy as np
from probe import load, nn1, DEEP
X, unit, take, mt, sit, dur = load()
rng = np.random.default_rng(67)
idx = {u: np.where(unit == u)[0][np.argsort(take[np.where(unit == u)[0]])] for u in DEEP}
EARLY, LATE = np.arange(0,33), np.arange(67,100)
NG = [1,2,3,5,8,10,15,20,33]

def hcurve(us, draws=150):
    out=[]
    for N in NG:
        a=[]
        for _ in range(draws):
            tr=np.concatenate([idx[u][rng.choice(EARLY,N,replace=False)] for u in us])
            te=np.concatenate([idx[u][LATE] for u in us])
            a.append(nn1(X[tr],unit[tr],X[te],unit[te])[1])
        out.append(100*float(np.mean(a)))
    return out

print("  set                                    chance  " + "".join(f"N={n:<5d}" for n in NG))
for name, us in [("/a/ family, consonant only {ah,ba,ma,abba}", ["ah","ba","ma","abba"]),
                 ("vowel contrast {ah, ih}", ["ah","ih"]),
                 ("vowel contrast {ah, ima}", ["ah","ima"]),
                 ("consonant contrast {ba, ma}", ["ba","ma"]),
                 ("consonant contrast {ah, ba}", ["ah","ba"]),
                 ("consonant contrast {ba, abba}", ["ba","abba"])]:
    c = hcurve(us)
    print(f"  {name:38s}  {100/len(us):5.1f}%  " + "".join(f"{v:<7.1f}" for v in c))

print("\n(c) size of the zero-separation leak, measured on the deep 6 at N=2")
print("    (the shallow units' 3 takes are ~2 s apart -- this IS their split)")
res = {}
for lo, hi, lab in [(0,3,"takes 0,1,2 -- back to back, like the shallow units"),
                    (0,33,"train early third, test late third")]:
    a=[]
    for _ in range(400):
        if lab.startswith("takes"):
            tr,te=[],[]
            for u in DEEP:
                p=rng.permutation(3); tr.append(idx[u][p[:2]]); te.append(idx[u][p[2:]])
            tr,te=np.concatenate(tr),np.concatenate(te)
        else:
            tr=np.concatenate([idx[u][rng.choice(EARLY,2,replace=False)] for u in DEEP])
            te=np.concatenate([idx[u][LATE] for u in DEEP])
        a.append(nn1(X[tr],unit[tr],X[te],unit[te])[1])
    res[lab]=100*float(np.mean(a))
    print(f"    {lab:48s} {100*np.mean(a):6.2f}%")
k=list(res); print(f"    -> the shallow-unit split is {res[k[0]]-res[k[1]]:+.2f} points optimistic at N=2.")
