"""test_220.py — does Eran's 22×10 FACTORED base token beat a flat vocabulary?
Iddo, 2026-08-20: "22 אותיות ו-10 ספירות ... כתוקן הבסיסי ביותר של ערן. תבנה את המבחן."

THE CLAIM under test: a token that is a COORDINATE on a (letter × nekuda) grid —
letter_embed[l] combined with nekuda_embed[n] — represents Hebrew better, at equal
parameter budget, than a FLAT embedding that gives every observed (letter,nekuda)
combination its own unrelated id. If factored wins, 220 is a real base token; if it
loses, it is a beautiful idea and we say so (the MIKO rule).

Honest anchoring: the "10 sefirot / 10 nekudim" axis is grounded in NIQQUD — the
vowel points, which are measurable in the text. That is the whole reason this is
testable and not mysticism. The letter axis is the 22(+final forms) consonants.

Fair fight:
  * both models: same tiny GRU LM, same context, same steps, same seed;
  * FACTORED embedding = letter_emb[L,d] + nekuda_emb[N,d]  → L*d + N*d params;
  * FLAT embedding     = combo_emb[K,d']  over the K observed (letter,nekuda) pairs,
    with d' shrunk so K*d' ≈ L*d + N*d  → the flat model is NOT given more capacity;
  * task: predict the NEXT (letter, nekuda) token; report held-out accuracy for the
    letter, the nekuda, and the full pair. Matched params, so any gap is structure.
No PC training (standing law) — run on eran4.
"""
from __future__ import annotations

import argparse
import pathlib
import time
import unicodedata

import torch
import torch.nn as nn
import torch.nn.functional as F

NIQQUD = {chr(c) for c in range(0x05B0, 0x05BD)} | {chr(0x05C1), chr(0x05C2), chr(0x05C7)}
CONS = {chr(c) for c in range(0x05D0, 0x05EB)}     # א..ת incl. final forms


def parse(path: pathlib.Path):
    """Text → list of sequences of (consonant_id, nekuda_id). A consonant plus
    the niqqud marks that follow it = one base token; the nekuda id is the sorted
    tuple of those marks (so shin-dot+kamatz is its own class, etc.)."""
    letters, nekudot = {}, {"": 0}
    seqs = []
    for line in path.read_text(encoding="utf-8").splitlines():
        seq = []
        cur = None
        marks = []

        def flush():
            nonlocal cur, marks
            if cur is not None:
                key = "".join(sorted(marks))
                li = letters.setdefault(cur, len(letters))
                ni = nekudot.setdefault(key, len(nekudot))
                seq.append((li, ni))
            cur, marks = None, []

        for ch in unicodedata.normalize("NFC", line):
            if ch in CONS:
                flush(); cur = ch
            elif ch in NIQQUD and cur is not None:
                marks.append(ch)
            else:
                flush()
        flush()
        if len(seq) > 4:
            seqs.append(seq)
    return seqs, len(letters), len(nekudot)


class FactoredLM(nn.Module):
    def __init__(self, L, N, d, hid):
        super().__init__()
        self.le = nn.Embedding(L, d)
        self.ne = nn.Embedding(N, d)
        self.rnn = nn.GRU(d, hid, batch_first=True)
        self.hl = nn.Linear(hid, L)
        self.hn = nn.Linear(hid, N)

    def forward(self, l, n):
        x = self.le(l) + self.ne(n)                 # the 22×10 grid, composed
        h, _ = self.rnn(x)
        return self.hl(h), self.hn(h)


class FlatLM(nn.Module):
    """Every observed (letter,nekuda) pair is its own id — no shared structure.
    d' is shrunk so the embedding table matches the factored budget."""
    def __init__(self, K, dprime, hid, L, N, combo2ln):
        super().__init__()
        self.emb = nn.Embedding(K, dprime)
        self.rnn = nn.GRU(dprime, hid, batch_first=True)
        self.hl = nn.Linear(hid, L)
        self.hn = nn.Linear(hid, N)
        self.register_buffer("c2l", combo2ln[:, 0].clone())
        self.register_buffer("c2n", combo2ln[:, 1].clone())

    def forward(self, k):
        h, _ = self.rnn(self.emb(k))
        return self.hl(h), self.hn(h)


def batches(seqs, ctx, bs, dev, gen):
    flat = [t for s in seqs for t in s]
    L = torch.tensor([a for a, _ in flat], device=dev)
    N = torch.tensor([b for _, b in flat], device=dev)
    hi = len(flat) - ctx - 1
    while True:
        ix = torch.randint(0, hi, (bs,), generator=gen, device=dev)
        off = torch.arange(ctx, device=dev)
        idx = ix[:, None] + off[None]
        yield (L[idx], N[idx], L[idx + 1], N[idx + 1])


def run(kind, seqs_tr, seqs_ev, L, N, combo, steps, ctx, bs, seed, dev):
    torch.manual_seed(seed)
    gen = torch.Generator(device=dev).manual_seed(seed)
    d, hid = 24, 96
    if kind == "factored":
        model = FactoredLM(L, N, d, hid).to(dev)
        emb_params = L * d + N * d
    else:
        K = len(combo)
        dprime = max(2, (L * d + N * d) // K)       # match the factored budget
        c2ln = torch.tensor(combo, device=dev)
        model = FlatLM(K, dprime, hid, L, N, c2ln).to(dev)
        emb_params = K * dprime
        # contiguous combo-id LUT: (l*N+n) -> row in [0,K). Without this the flat
        # embedding was indexed up to L*N-1 into a K-row table -> CUDA OOB.
        lut = torch.zeros(L * N, dtype=torch.long, device=dev)
        for i, (a, b) in enumerate(combo):
            lut[a * N + b] = i
    opt = torch.optim.AdamW(model.parameters(), lr=3e-3)
    it = batches(seqs_tr, ctx, bs, dev, gen)
    for step in range(1, steps + 1):
        lp, ln, yl, yn = next(it)
        if kind == "factored":
            ol, on = model(lp, ln)
        else:
            ol, on = model(lut[lp * N + ln])         # map to contiguous combo id
        loss = F.cross_entropy(ol.reshape(-1, L), yl.reshape(-1)) + \
               F.cross_entropy(on.reshape(-1, N), yn.reshape(-1))
        opt.zero_grad(set_to_none=True); loss.backward(); opt.step()

    # held-out accuracy
    model.eval()
    gene = torch.Generator(device=dev).manual_seed(999)
    ite = batches(seqs_ev, ctx, bs, dev, gene)
    cl = cn = cp = tot = 0
    with torch.no_grad():
        for _ in range(60):
            lp, ln, yl, yn = next(ite)
            if kind == "factored":
                ol, on = model(lp, ln)
            else:
                ol, on = model(lut[lp * N + ln])
            pl, pn = ol.argmax(-1), on.argmax(-1)
            cl += (pl == yl).sum().item(); cn += (pn == yn).sum().item()
            cp += ((pl == yl) & (pn == yn)).sum().item(); tot += yl.numel()
    return dict(kind=kind, emb_params=emb_params,
                letter_acc=cl/tot, nekuda_acc=cn/tot, pair_acc=cp/tot)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default="corpus_pointed.txt")
    ap.add_argument("--steps", type=int, default=1500)
    ap.add_argument("--ctx", type=int, default=24)
    ap.add_argument("--bs", type=int, default=128)
    ap.add_argument("--seed", type=int, default=17)
    A = ap.parse_args()
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    seqs, L, N = parse(pathlib.Path(A.corpus))
    combo = sorted({(a, b) for s in seqs for a, b in s})
    cut = int(len(seqs) * 0.9)
    tr, ev = seqs[:cut], seqs[cut:]
    print(f"letters L={L}  nekudot N={N}  -> grid {L}x{N}={L*N}  "
          f"observed pairs K={len(combo)}  verses {len(seqs)} (train {len(tr)}/eval {len(ev)})")
    for kind in ("factored", "flat"):
        t0 = time.time()
        r = run(kind, tr, ev, L, N, combo, A.steps, A.ctx, A.bs, A.seed, dev)
        print(f"  {kind:9} emb_params {r['emb_params']:6}  "
              f"letter {r['letter_acc']*100:5.1f}%  nekuda {r['nekuda_acc']*100:5.1f}%  "
              f"PAIR {r['pair_acc']*100:5.1f}%  ({time.time()-t0:.0f}s)")


if __name__ == "__main__":
    main()
