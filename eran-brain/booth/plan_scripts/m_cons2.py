import json, collections
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
    return ytr[np.argmin(d,axis=1)], None
# --- proper shuffled control: permute labels ACROSS CLIPS ---
allx, ally = [], []
for u in units:
    for t in range(3):
        allx.append(X[u][t]); ally.append(SOUND[u])
allx = np.array(allx); ally = np.array(ally)
idx = np.arange(len(ally))
rng = np.random.default_rng(0); ctrl=[]
for rep in range(300):
    y = ally.copy(); rng.shuffle(y)
    a_=[]
    for held in range(3):
        te = idx[idx%3==held]; tr = idx[idx%3!=held]
        p,_ = nn1(allx[tr], y[tr], allx[te], y[te]); a_.append(float(np.mean(p==y[te])))
    ctrl.append(np.mean(a_))
print("shuffled-label control (clip-level) %.4f +-%.4f  chance 0.0500" % (np.mean(ctrl), np.std(ctrl)))
# --- duration-only control ---
dur = {}
for r in rows: dur.setdefault(r["unit"],{})[r["take"]] = r["dur"]
dx = np.array([[dur[u][t]] for u in units for t in range(3)])
a_=[]
for held in range(3):
    te = idx[idx%3==held]; tr = idx[idx%3!=held]
    p,_ = nn1(dx[tr], ally[tr], dx[te], ally[te]); a_.append(float(np.mean(p==ally[te])))
print("duration-only control %.4f" % np.mean(a_))
print()
# --- prototype confusability: cos to nearest OTHER consonant ---
mu, sd = allx.mean(0), allx.std(0)+1e-9
Z = (allx-mu)/sd
proto = {}
for i,u in enumerate(units):
    proto[SOUND[u]] = Z[i*3:(i+1)*3].mean(0)
S = list(SOUND.values())
P = np.array([proto[s] for s in S])
Pn = P/np.linalg.norm(P,axis=1,keepdims=True)
C = Pn@Pn.T
np.fill_diagonal(C, -9)
print("consonant prototype crowding (cos to nearest OTHER consonant), 3 takes each:")
rank = sorted(range(len(S)), key=lambda i: -C[i].max())
for i in rank:
    j = int(np.argmax(C[i]))
    print("  %-3s  %.4f  nearest=%s" % (S[i], C[i].max(), S[j]))
print("  mean over all pairs %.4f" % ((C[C>-1].sum())/ (len(S)*(len(S)-1))))
print()
# --- duplicate-sound check: same sound, different letter/spelling ---
def pcos(u1,u2,n=3):
    a = np.array([X[u1][t] for t in range(n)]).mean(0)
    b = np.array([X[u2][t] for t in range(n)]).mean(0)
    a=(a-mu)/sd; b=(b-mu)/sd
    return float(a@b/(np.linalg.norm(a)*np.linalg.norm(b)))
print("SAME SOUND, DIFFERENT SPELLING (do duplicates really coincide?):")
print("  ta(tet) vs tha(tav)  -> both t/a : cos %.4f" % pcos("ta","tha"))
print("  ah(alef+patah) vs aa(alef+kamats) -> both '/a : cos %.4f" % pcos("ah","aa"))
print("DIFFERENT SOUNDS for scale:")
for p in [("ba","ma"),("ba","la"),("da","la"),("sa","za"),("ha","va"),("qa","tsa"),("ah","ba"),("ra","sha")]:
    print("  %-4s vs %-4s cos %.4f" % (p[0],p[1],pcos(*p)))
allpairs=[]
for i in range(len(S)):
    for j in range(i+1,len(S)):
        allpairs.append(C[i,j])
print("  all 190 different-consonant pairs: mean %.4f  max %.4f  min %.4f" % (np.mean(allpairs), np.max(allpairs), np.min(allpairs)))
