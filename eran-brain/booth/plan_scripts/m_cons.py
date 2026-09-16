import json, itertools, collections
import numpy as np
rows = json.load(open("feats.json"))
X = {}
for r in rows:
    X.setdefault(r["unit"], {})[r["take"]] = np.array(r["vec"])
SOUND = {"ah":"'","ba":"b","ga":"g","da":"d","ha":"h","va":"v","za":"z","kha":"kh",
         "ta":"t","ya":"y","ka":"k","la":"l","ma":"m","na":"n","sa":"s","pa":"p",
         "tsa":"ts","qa":"q","ra":"r","sha":"sh"}
units = list(SOUND)
def nn1(Xtr,ytr,Xte,yte):
    mu,sd = Xtr.mean(0), Xtr.std(0)+1e-9
    A,B = (Xtr-mu)/sd, (Xte-mu)/sd
    d = (B*B).sum(1)[:,None] + (A*A).sum(1)[None,:] - 2.0*(B@A.T)
    pred = ytr[np.argmin(d,axis=1)]
    return pred, float(np.mean(pred==yte))
# leave-one-take-out over the FIRST 3 takes, 20 sound classes
correct = collections.Counter(); total = collections.Counter()
conf = collections.Counter(); accs=[]
for held in range(3):
    tr_x,tr_y,te_x,te_y = [],[],[],[]
    for u in units:
        for t in range(3):
            (te_x if t==held else tr_x).append(X[u][t])
            (te_y if t==held else tr_y).append(SOUND[u])
    pred,a = nn1(np.array(tr_x),np.array(tr_y),np.array(te_x),np.array(te_y))
    accs.append(a)
    for p,y in zip(pred,te_y):
        total[y]+=1
        if p==y: correct[y]+=1
        else: conf[(y,p)]+=1
print("20-way /a/ row, leave-one-take-out on 3 back-to-back takes (LEAKY split, flagged)")
print("mean acc %.4f  folds %s  chance %.4f" % (np.mean(accs), ["%.3f"%a for a in accs], 1/20))
# shuffled control
rng = np.random.default_rng(0); ctrl=[]
for rep in range(200):
    lab = list(SOUND.values()); rng.shuffle(lab)
    perm = dict(zip(units,lab)); a_=[]
    for held in range(3):
        tr_x,tr_y,te_x,te_y = [],[],[],[]
        for u in units:
            for t in range(3):
                (te_x if t==held else tr_x).append(X[u][t])
                (te_y if t==held else tr_y).append(perm[u])
        _,a = nn1(np.array(tr_x),np.array(tr_y),np.array(te_x),np.array(te_y)); a_.append(a)
    ctrl.append(np.mean(a_))
print("shuffled-label control %.4f +-%.4f (n=200)" % (np.mean(ctrl), np.std(ctrl)))
print()
print("per-sound recall (3 tries each):")
order = sorted(SOUND.values(), key=lambda s: (correct[s]/total[s], s))
for s in order:
    misses = ", ".join("%s->%s x%d"%(y,p,c) for (y,p),c in sorted(conf.items(),key=lambda kv:-kv[1]) if y==s)
    print("  %-3s %d/3  %s" % (s, correct[s], misses))
print()
print("most common confusions overall:")
for (y,p),c in sorted(conf.items(), key=lambda kv:-kv[1])[:15]:
    print("   %-3s -> %-3s  x%d" % (y,p,c))
