# -*- coding: utf-8 -*-
"""VAADA-MIKO-BIO: the honest ladder.

A  word BM25                       (the incumbent control, 9/30)
B  char 4-gram tf-idf cosine       (no transducer)
C  + consonant-skeleton TRANSDUCER (Hebrew abjad <-> Latin, 0 params, innate)
D  + k-WTA sparsification on C     (does biological sparsity help or hurt?)
E  + fly-hash random projection    (does FlyLSH help or hurt at n=835?)
F  modern-Hopfield readout on C    (does energy descent add anything over argmax cosine?)

CPU only, numpy only, no downloads, no pretrained anything.
"""
import json, sys, re, math, time
import numpy as np
from collections import Counter, defaultdict
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r"D:\CLAUDE\miko\v1")
from bm25 import BM25

RNG = np.random.default_rng(1337)
BASE = r"D:\CLAUDE\miko\v1"
docs = [json.loads(l) for l in open(BASE + r"\corpus.jsonl", encoding='utf-8')]
exam = json.load(open(BASE + r"\exam.json", encoding='utf-8'))
ids = [d['id'] for d in docs]
texts = [d['text'] for d in docs]
gold_idx = {i: ids.index(e['target_id']) for i, e in enumerate(exam)}
N = len(docs)
TAV, YETIV = chr(0x05EA), chr(0x05AA)

# ---------------------------------------------------------------- the TRANSDUCER
# Fixed, innate, zero learned parameters -- the olfactory-receptor layer.
# Hebrew is an abjad: written consonants only. So project BOTH scripts onto a
# common consonant skeleton. This is a sensory transform, not a learned mapping.
HEB2LAT = {
    'א': '',  'ב': 'b', 'ג': 'g', 'ד': 'd', 'ה': 'h', 'ו': 'w', 'ז': 'z',
    'ח': 'h', 'ט': 't', 'י': '',  'כ': 'k', 'ך': 'k', 'ל': 'l', 'מ': 'm',
    'ם': 'm', 'נ': 'n', 'ן': 'n', 'ס': 's', 'ע': '',  'פ': 'p', 'ף': 'p',
    'צ': 'c', 'ץ': 'c', 'ק': 'k', 'ר': 'r', 'ש': 's', 'ת': 't',
}
LAT_FOLD = str.maketrans({'v': 'w', 'f': 'p', 'q': 'k', 'x': 'ks', 'j': 'y'})
VOWELS = set('aeiou')

def transduce(s: str) -> str:
    """Map any string onto the shared consonant skeleton."""
    s = s.replace(YETIV, TAV)
    out = []
    for ch in s.lower():
        if ch in HEB2LAT:
            out.append(HEB2LAT[ch])
        elif ch.isascii() and ch.isalpha():
            if ch in VOWELS:
                continue                     # abjad: drop written vowels
            out.append(ch.translate(LAT_FOLD))
        elif ch.isdigit():
            out.append(ch)
        else:
            out.append(' ')
    # collapse doubled consonants (sh/ss, ww) and runs of space
    t = ''.join(out)
    t = re.sub(r'(.)\1+', r'\1', t)
    return re.sub(r'\s+', ' ', t).strip()

# ---------------------------------------------------------------- featurisers
WORD_RE = re.compile(r'\w+', re.UNICODE)

def feats_charngram(s, lo=3, hi=5, transducer=False):
    s = transduce(s) if transducer else s.replace(YETIV, TAV).lower()
    out = []
    for tok in s.split():
        p = f'#{tok}#'
        for n in range(lo, hi + 1):
            for i in range(len(p) - n + 1):
                out.append(p[i:i + n])
    return out

# ---------------------------------------------------------------- tf-idf matrix
def build_tfidf(doc_feats, query_feats_list):
    vocab = {}
    df = Counter()
    for f in doc_feats:
        for g in set(f):
            if g not in vocab:
                vocab[g] = len(vocab)
            df[g] += 1
    V = len(vocab)
    idf = np.zeros(V, dtype=np.float32)
    for g, i in vocab.items():
        idf[i] = math.log(1.0 + (N - df[g] + 0.5) / (df[g] + 0.5))

    def vec(feats):
        v = np.zeros(V, dtype=np.float32)
        for g, c in Counter(feats).items():
            j = vocab.get(g)
            if j is not None:
                v[j] = (1.0 + math.log(c)) * idf[j]
        n = np.linalg.norm(v)
        return v / n if n > 0 else v

    D = np.stack([vec(f) for f in doc_feats])
    Q = np.stack([vec(f) for f in query_feats_list])
    return D, Q, V

def score(rank_matrix, label, extra=""):
    """rank_matrix: (30, N) similarity. Higher = better."""
    r1 = r5 = 0; mrr = 0.0; he1 = en1 = 0; he_n = en_n = 0
    for qi in range(len(exam)):
        order = np.argsort(-rank_matrix[qi])
        rank = int(np.where(order == gold_idx[qi])[0][0]) + 1
        if rank == 1: r1 += 1
        if rank <= 5: r5 += 1
        mrr += 1.0 / rank
        if exam[qi]['lang'] == 'he':
            he_n += 1; he1 += (rank == 1)
        else:
            en_n += 1; en1 += (rank == 1)
    n = len(exam)
    print(f"{label:44s} r@1 {r1:2d}/{n}={r1/n:.3f}  r@5 {r5:2d}/{n}  MRR {mrr/n:.3f}  "
          f"[he {he1}/{he_n}  en {en1}/{en_n}] {extra}")
    return r1

print(f"corpus {N} docs | exam {len(exam)} questions\n")
print("=" * 112)

# ---- A: word BM25 control
bm = BM25(ids, texts)
Sa = np.full((len(exam), N), -1e9, dtype=np.float32)
for qi, e in enumerate(exam):
    for did, s in bm.search(e['query'].replace(YETIV, TAV), top_k=N):
        Sa[qi, ids.index(did)] = s
score(Sa, "A  word BM25 (control)")

# ---- B: char n-gram tf-idf cosine, no transducer
t0 = time.time()
df_b = [feats_charngram(t) for t in texts]
qf_b = [feats_charngram(e['query']) for e in exam]
Db, Qb, Vb = build_tfidf(df_b, qf_b)
score(Qb @ Db.T, "B  char 3-5gram tf-idf cosine", f"V={Vb}")

# ---- C: + the transducer
df_c = [feats_charngram(t, transducer=True) for t in texts]
qf_c = [feats_charngram(e['query'], transducer=True) for e in exam]
Dc, Qc, Vc = build_tfidf(df_c, qf_c)
Sc = Qc @ Dc.T
score(Sc, "C  + consonant-skeleton TRANSDUCER", f"V={Vc}")

# ---- C2: fuse A and C (lexical + transduced), rank-normalised
def zn(S):
    m = S.mean(axis=1, keepdims=True); s = S.std(axis=1, keepdims=True) + 1e-9
    return (S - m) / s
Sa_z = zn(np.where(Sa < -1e8, 0.0, Sa))
score(Sa_z + zn(Sc), "C2 fuse: word-BM25 + transduced n-grams")

print("-" * 112)

# ---- D: k-WTA sparsification of C (biological sparsity, no projection)
for kfrac in (0.005, 0.01, 0.02, 0.05, 0.10):
    k = max(1, int(kfrac * Vc))
    def kwta(M, k):
        out = np.zeros_like(M)
        idx = np.argpartition(-M, k, axis=1)[:, :k]
        rows = np.arange(M.shape[0])[:, None]
        out[rows, idx] = M[rows, idx]
        nn = np.linalg.norm(out, axis=1, keepdims=True) + 1e-9
        return out / nn
    Dk, Qk = kwta(Dc, k), kwta(Qc, k)
    score(Qk @ Dk.T, f"D  k-WTA on C, k={kfrac*100:.1f}% of V ({k} dims)")

print("-" * 112)

# ---- E: fly hash (sparse binary random projection + k-WTA -> binary tag)
def flyhash(D, Q, m=8192, samples=64, hash_k=256, seed=1337):
    rng = np.random.default_rng(seed)
    V = D.shape[1]
    # each Kenyon cell samples `samples` random input features, weight 1
    proj_idx = rng.integers(0, V, size=(m, samples))
    M = np.zeros((V, m), dtype=np.float32)
    for j in range(m):
        M[proj_idx[j], j] += 1.0
    def tag(X):
        # fly divisive normalisation: centre by the mean of active inputs
        Xn = X - X.mean(axis=1, keepdims=True)
        H = Xn @ M
        out = np.zeros_like(H, dtype=np.float32)
        idx = np.argpartition(-H, hash_k, axis=1)[:, :hash_k]
        rows = np.arange(H.shape[0])[:, None]
        out[rows, idx] = 1.0                  # binary tag, top hash_k Kenyon cells
        return out
    return tag(D), tag(Q)

for m, hk in ((8192, 256), (8192, 64), (16384, 128)):
    Df, Qf = flyhash(Dc, Qc, m=m, hash_k=hk)
    score(Qf @ Df.T, f"E  FlyLSH on C: m={m} KC, tag={hk} ({hk/m*100:.1f}%)")

print("-" * 112)

# ---- F: modern Hopfield readout on C -- does energy descent beat argmax cosine?
def hopfield(Q, D, beta, steps=1):
    xi = Q.copy()
    for _ in range(steps):
        A = beta * (xi @ D.T)
        A -= A.max(axis=1, keepdims=True)
        P = np.exp(A); P /= P.sum(axis=1, keepdims=True)
        xi = P @ D
        nn = np.linalg.norm(xi, axis=1, keepdims=True) + 1e-9
        xi = xi / nn
    return xi @ D.T

for beta in (1.0, 8.0, 32.0, 128.0):
    for steps in (1, 3):
        score(hopfield(Qc, Dc, beta, steps), f"F  modern Hopfield on C: beta={beta:g} steps={steps}")

print("=" * 112)
print(f"elapsed {time.time()-t0:.1f}s")
