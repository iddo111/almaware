# -*- coding: utf-8 -*-
"""VAADA-MIKO-BIO exp7: the CEILING.

If a correct Hebrew->English content lexicon existed, what would BM25 score?
This is an ORACLE (hand-glossed by the commission), i.e. an upper bound on the value
of the one capability every method is missing. It is NOT a measured system.

Also: a bootstrap significance check, because n=30 and 9-vs-11 may be pure noise.
"""
import json, sys, re
import numpy as np
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r"D:\CLAUDE\miko\v1")
from bm25 import BM25

BASE = r"D:\CLAUDE\miko\v1"
docs = [json.loads(l) for l in open(BASE + r"\corpus.jsonl", encoding='utf-8')]
exam = json.load(open(BASE + r"\exam.json", encoding='utf-8'))
ids = [d['id'] for d in docs]; N = len(docs); pos = {d: i for i, d in enumerate(ids)}
TAV, YETIV = chr(0x05EA), chr(0x05AA)
bm = BM25(ids, [d['text'] for d in docs])

# hand gloss of the CONTENT words of each hebrew exam query (oracle lexicon)
GLOSS = {
 'איפה חי ערן באמ֪ עכשיו': 'where lives eran now',
 'קוד המודל של מיקו, ספירו֪ וקבלה': 'code model miko sefirot kabbalah',
 'אורגן הרינדור ה֪ל֪ מימדי של ערן, הפעימה היא העומק': 'render organ three dimensional eran beat depth',
 'פריצ֪ הדרך בהברה בא של ערן': 'breakthrough syllable ba eran',
 'מרכז ערן בנגב, מיחזור פסול֪ אלקטרוני֪ לרובוטים': 'center eran negev recycling electronic waste robots',
 'דארוויש מודל המידי שהיה בהקפאה ואז שוחרר': 'darwish midi model parked frozen released',
 'איך מגיעים לכל אח֪ מארבע מכונו֪ ה-DGX': 'how reach each four dgx boxes machines',
 'כ֪וב֪ ה-IP של מדפס֪ ה֪ל֪ מימד קריאליטי': 'ip address printer 3d creality',
 'חוק החלונו֪ השבורו֪ - ל֪קן מיד ולא לחכו֪': 'broken windows law fix immediately not wait',
 'כל משקל הוא שיר, שפ֪ אלמה כשירה': 'every weight poem alma language poetry',
 'השופט נבנה ועובד, אבל לא מה שציפינו': 'judge built works not what expected',
 'LTX-2.3 עובד באמ֪ על eran4, לא רק הורד': 'ltx works really eran4 not just downloaded',
 'מסלול האוזן נפ֪ח, באישור עידו': 'ear track opened approval iddo',
 'דוח בנייה של ֪וכנ֪ FAMESH בשלושה צמ֪ים': 'build report famesh software three nodes',
 'מדריך מחקר מעמיק ל-LoRa ו֪דרי רדיו': 'deep research guide lora radio frequencies',
}

def rank_of(q, gold):
    s = np.zeros(N, dtype=np.float32)
    for did, v in bm.search(q.replace(YETIV, TAV), top_k=N): s[pos[did]] = v
    return int(np.where(np.argsort(-s) == pos[gold])[0][0]) + 1

def run(transform, label):
    ranks = []
    for e in exam:
        ranks.append((e['lang'], rank_of(transform(e), e['target_id'])))
    r1 = sum(1 for _, r in ranks if r == 1); r5 = sum(1 for _, r in ranks if r <= 5)
    mrr = sum(1.0 / r for _, r in ranks) / len(ranks)
    he1 = sum(1 for l, r in ranks if l == 'he' and r == 1)
    en1 = sum(1 for l, r in ranks if l == 'en' and r == 1)
    print(f"{label:46s} r@1 {r1:2d}/30={r1/30:.3f}  r@5 {r5:2d}/30  MRR {mrr:.3f}  [he {he1}/15  en {en1}/15]")
    return [r for _, r in ranks]

matched = sum(1 for e in exam if e['lang'] == 'he' and e['query'] in GLOSS)
print(f"gloss table covers {matched}/15 hebrew queries\n")
print("=" * 112)
base = run(lambda e: e['query'], "A  word BM25, queries as written (control)")
orac = run(lambda e: GLOSS.get(e['query'], e['query']), "Z  ORACLE: hebrew queries glossed to english")
augm = run(lambda e: e['query'] + ' ' + GLOSS.get(e['query'], ''), "Z2 ORACLE: hebrew query + english gloss")
print("=" * 112)

# ---- bootstrap: is any of this distinguishable from noise at n=30? ----------
rng = np.random.default_rng(1337)
def boot(a, b, B=20000):
    a = np.array(a); b = np.array(b); n = len(a); d = []
    for _ in range(B):
        idx = rng.integers(0, n, n)
        d.append((a[idx] == 1).sum() - (b[idx] == 1).sum())
    d = np.array(d)
    return np.percentile(d, 2.5), np.percentile(d, 97.5), (d <= 0).mean()

lo, hi, p = boot(orac, base)
print(f"\nbootstrap, ORACLE minus control, r@1 count difference:")
print(f"   point estimate {sum(1 for r in orac if r==1) - sum(1 for r in base if r==1):+d} questions,"
      f"  95% CI [{lo:+.0f}, {hi:+.0f}],  P(no improvement) = {p:.4f}")
print(f"\nFor scale: the whole exam is 30 questions, so 1 question = 3.3 points of recall@1.")
print(f"A +/-3 question swing is inside the noise band of an exam this small.")
