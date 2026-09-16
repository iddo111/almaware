"""ozen.py -- OZEN: KESHEV's from-scratch Hebrew acoustic model.

Iddo's order, 2026-08-22: real weights, from scratch, trained on his own speech,
running in shadow beside Whisper until it earns the right to replace it.

THE CONSTRAINT THAT DICTATES EVERYTHING: 0.95 labelled hours.
Plain CTC on one hour of speech does not converge to anything useful. But there
are 11.03 unlabelled hours of the same voice in the same rooms, and that is the
larger half of the corpus. So:

  stage 1  PRETRAIN  on all 11 h, no labels, BEST-RQ style: a frozen random
                     projection plus a frozen random codebook turns every mel
                     frame into a discrete id; the encoder must predict the ids
                     of frames that have been masked out. Nothing is learned in
                     the quantizer, so there is no codebook collapse to debug --
                     which matters when you get one shot on a small corpus.
  stage 2  FINETUNE  the same encoder with a CTC head on the 0.95 labelled
                     hours, 24 Hebrew symbols.

Everything is measured against the same held-out sessions, which are whole and
never seen in training (the 2026-08-21 session-leak scar).

  python ozen.py pretrain --hours 11 --steps 40000
  python ozen.py finetune --init runs/pretrain/best.pt --steps 20000
  python ozen.py eval     --ckpt runs/finetune/best.pt
"""
import argparse
import json
import math
import random
import time
import wave
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

SR = 16000
N_MELS = 80
WIN = 400          # 25 ms
HOP = 160          # 10 ms
SUBSAMPLE = 4      # conv frontend -> 40 ms frames


def _conv_len(L):
    """exact output length of one k=5,s=2,p=2 conv"""
    return (L - 1) // 2 + 1


def sub_len(L):
    """Frames out of the frontend for L mel frames in. This must be a single
    formula used EVERYWHERE -- the first version assumed L//4 and the convs
    actually returned ceil-ish lengths, so the mask and the features came out
    one frame apart and the run died. One function, no second guess."""
    return _conv_len(_conv_len(L))


# --------------------------------------------------------------------------
# features
# --------------------------------------------------------------------------
def mel_filterbank(n_mels=N_MELS, n_fft=512, sr=SR, fmin=20.0, fmax=7600.0):
    def hz2mel(f):
        return 2595.0 * np.log10(1.0 + f / 700.0)

    def mel2hz(m):
        return 700.0 * (10 ** (m / 2595.0) - 1.0)

    pts = mel2hz(np.linspace(hz2mel(fmin), hz2mel(fmax), n_mels + 2))
    bins = np.floor((n_fft + 1) * pts / sr).astype(int)
    fb = np.zeros((n_mels, n_fft // 2 + 1), dtype=np.float32)
    for i in range(n_mels):
        l, c, r = bins[i], bins[i + 1], bins[i + 2]
        if c == l:
            c = l + 1
        if r == c:
            r = c + 1
        fb[i, l:c] = np.linspace(0, 1, c - l, endpoint=False)
        fb[i, c:r] = np.linspace(1, 0, r - c, endpoint=False)
    return fb


_FB = None
_WINDOW = np.hanning(WIN).astype(np.float32)


def logmel(x):
    """x: float32 [-1,1] mono 16k -> [T, 80] log-mel, per-utterance normalised."""
    global _FB
    if _FB is None:
        _FB = mel_filterbank()
    n_fft = 512
    if len(x) < WIN:
        x = np.pad(x, (0, WIN - len(x)))
    n = 1 + (len(x) - WIN) // HOP
    idx = np.arange(WIN)[None, :] + HOP * np.arange(n)[:, None]
    frames = x[idx] * _WINDOW
    spec = np.abs(np.fft.rfft(frames, n=n_fft)) ** 2
    m = spec @ _FB.T
    m = np.log(m + 1e-6).astype(np.float32)
    m = (m - m.mean()) / (m.std() + 1e-5)
    return m


def read_wav(path):
    with wave.open(str(path), "rb") as f:
        sr = f.getframerate()
        n = f.getnframes()
        raw = f.readframes(n)
    x = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if sr != SR:                       # crude but the corpus is already 16k
        idx = (np.arange(int(len(x) * SR / sr)) * sr / SR).astype(int)
        idx = idx[idx < len(x)]
        x = x[idx]
    return x


# --------------------------------------------------------------------------
# model
# --------------------------------------------------------------------------
class ConvFrontend(nn.Module):
    """two stride-2 convs: 10 ms frames -> 40 ms, 80 mels -> d_model"""

    def __init__(self, d_model):
        super().__init__()
        self.net = nn.Sequential(
            nn.Conv1d(N_MELS, d_model, 5, stride=2, padding=2), nn.GELU(),
            nn.Conv1d(d_model, d_model, 5, stride=2, padding=2), nn.GELU(),
        )

    def forward(self, x):              # [B, T, 80]
        return self.net(x.transpose(1, 2)).transpose(1, 2)


class Block(nn.Module):
    def __init__(self, d, heads, ff, drop):
        super().__init__()
        self.n1 = nn.LayerNorm(d)
        self.att = nn.MultiheadAttention(d, heads, dropout=drop, batch_first=True)
        self.n2 = nn.LayerNorm(d)
        self.ff = nn.Sequential(nn.Linear(d, ff), nn.GELU(), nn.Dropout(drop), nn.Linear(ff, d))
        self.drop = nn.Dropout(drop)

    def forward(self, x, pad_mask):
        h = self.n1(x)
        a, _ = self.att(h, h, h, key_padding_mask=pad_mask, need_weights=False)
        x = x + self.drop(a)
        x = x + self.drop(self.ff(self.n2(x)))
        return x


class Encoder(nn.Module):
    def __init__(self, d=256, layers=6, heads=4, ff=1024, drop=0.1, max_len=4096):
        super().__init__()
        self.front = ConvFrontend(d)
        self.pos = nn.Parameter(torch.randn(1, max_len, d) * 0.02)
        self.blocks = nn.ModuleList([Block(d, heads, ff, drop) for _ in range(layers)])
        self.norm = nn.LayerNorm(d)
        self.d = d

    def forward(self, mel, lens, mask_frames=None):
        x = self.front(mel)
        T = x.size(1)
        out_lens = torch.clamp(((lens - 1) // 2 + 1 - 1) // 2 + 1, min=1, max=T)
        if mask_frames is not None:
            x = torch.where(mask_frames.unsqueeze(-1), self.mask_emb.expand_as(x), x)
        x = x + self.pos[:, :T]
        pad = torch.arange(T, device=x.device)[None, :] >= out_lens[:, None]
        for b in self.blocks:
            x = b(x, pad)
        return self.norm(x), out_lens


class Ozen(nn.Module):
    def __init__(self, n_symbols, d=256, layers=6, heads=4, ff=1024, drop=0.1, n_codes=4096):
        super().__init__()
        self.enc = Encoder(d, layers, heads, ff, drop)
        self.enc.mask_emb = nn.Parameter(torch.randn(1, 1, d) * 0.02)
        self.ctc = nn.Linear(d, n_symbols)
        self.code_head = nn.Linear(d, n_codes)

    def forward(self, mel, lens, mask_frames=None):
        h, out_lens = self.enc(mel, lens, mask_frames)
        return h, out_lens


class RandomQuantizer(nn.Module):
    """BEST-RQ: a FROZEN random projection into a FROZEN random codebook.
    Nothing here is trained, which is exactly why it cannot collapse."""

    def __init__(self, in_dim, dim=16, n_codes=4096, seed=1234):
        super().__init__()
        g = torch.Generator().manual_seed(seed)
        proj = torch.randn(in_dim, dim, generator=g)
        proj = proj / proj.norm(dim=0, keepdim=True)
        book = torch.randn(n_codes, dim, generator=g)
        book = book / book.norm(dim=-1, keepdim=True)
        self.register_buffer("proj", proj)
        self.register_buffer("book", book)

    @torch.no_grad()
    def forward(self, mel_stack):
        z = mel_stack @ self.proj
        z = z / (z.norm(dim=-1, keepdim=True) + 1e-6)
        return (z @ self.book.T).argmax(-1)


# --------------------------------------------------------------------------
# data
# --------------------------------------------------------------------------
class Corpus:
    def __init__(self, jsonl, root, alphabet=None, labelled=True, max_sec=20.0):
        self.root = Path(root)
        self.rows = []
        for line in Path(jsonl).open(encoding="utf-8"):
            if not line.strip():
                continue
            r = json.loads(line)
            if r.get("sec", 0) > max_sec:
                continue
            self.rows.append(r)
        self.labelled = labelled
        self.sym2i = {s: i + 1 for i, s in enumerate(alphabet)} if alphabet else None

    def __len__(self):
        return len(self.rows)

    def get(self, i):
        r = self.rows[i]
        p = self.root / r["wav"] if not Path(r["wav"]).is_absolute() else Path(r["wav"])
        m = logmel(read_wav(p))
        y = None
        if self.labelled:
            y = [self.sym2i[c] for c in r["text"] if c in self.sym2i]
        return m, y, r


def collate(items, device):
    mels = [torch.from_numpy(m) for m, _, _ in items]
    lens = torch.tensor([m.size(0) for m in mels])
    T = int(lens.max())
    x = torch.zeros(len(mels), T, N_MELS)
    for i, m in enumerate(mels):
        x[i, : m.size(0)] = m
    return x.to(device), lens.to(device)


# --------------------------------------------------------------------------
# training
# --------------------------------------------------------------------------
def span_mask(B, T, device, prob=0.06, span=10):
    """mask contiguous spans -- masking single frames is trivially solved by
    interpolating the neighbours and teaches the model nothing."""
    m = torch.zeros(B, T, dtype=torch.bool, device=device)
    n = max(1, int(T * prob))
    for b in range(B):
        for _ in range(n):
            s = random.randint(0, max(0, T - span))
            m[b, s : s + span] = True
    return m


def pretrain(args):
    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    root = Path(args.data)
    alpha = json.loads((root / "alphabet.json").read_text(encoding="utf-8"))["symbols"]
    corpus = Corpus(root / "unlabelled.jsonl", root, labelled=False, max_sec=args.max_sec)
    print(f"pretrain corpus: {len(corpus)} clips, "
          f"{sum(r['sec'] for r in corpus.rows)/3600:.2f} h  device={dev}")

    model = Ozen(len(alpha) + 1, d=args.dim, layers=args.layers).to(dev)
    quant = RandomQuantizer(N_MELS * SUBSAMPLE).to(dev)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.01, betas=(0.9, 0.98))
    n_par = sum(p.numel() for p in model.parameters())
    print(f"parameters: {n_par/1e6:.2f} M")

    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    best = math.inf
    step = 0
    t0 = time.time()
    while step < args.steps:
        idx = random.sample(range(len(corpus)), min(args.batch, len(corpus)))
        items = []
        for i in idx:
            try:
                items.append(corpus.get(i))
            except Exception:
                pass
        if not items:
            continue
        x, lens = collate(items, dev)
        B, T, _ = x.shape
        Tsub = sub_len(T)
        if Tsub < 12:
            continue
        need = Tsub * SUBSAMPLE
        xs = F.pad(x, (0, 0, 0, max(0, need - T)))[:, :need]
        stack = xs.reshape(B, Tsub, N_MELS * SUBSAMPLE)
        targets = quant(stack)
        mask = span_mask(B, Tsub, dev, prob=args.mask_prob, span=args.mask_span)
        out_lens = torch.clamp(((lens - 1) // 2 + 1 - 1) // 2 + 1, min=1, max=Tsub)
        valid = torch.arange(Tsub, device=dev)[None, :] < out_lens[:, None]
        mask = mask & valid
        if mask.sum() == 0:
            continue

        h, _ = model(x, lens, mask_frames=mask)
        h = h[:, :Tsub]
        logits = model.code_head(h)
        loss = F.cross_entropy(logits[mask], targets[mask])

        opt.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step()
        step += 1

        if step % args.log_every == 0:
            acc = (logits[mask].argmax(-1) == targets[mask]).float().mean().item()
            rate = step / (time.time() - t0)
            print(f"step {step:6d}  loss {loss.item():.4f}  code-acc {acc:.3f}  "
                  f"{rate:.2f} it/s", flush=True)
            if loss.item() < best:
                best = loss.item()
                torch.save({"model": model.state_dict(), "args": vars(args),
                            "alphabet": alpha, "step": step}, out / "best.pt")
    torch.save({"model": model.state_dict(), "args": vars(args),
                "alphabet": alpha, "step": step}, out / "last.pt")
    print(f"done. best loss {best:.4f}. saved to {out}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pretrain")
    p.add_argument("--data", default="data")
    p.add_argument("--out", default="runs/pretrain")
    p.add_argument("--steps", type=int, default=40000)
    p.add_argument("--batch", type=int, default=16)
    p.add_argument("--dim", type=int, default=256)
    p.add_argument("--layers", type=int, default=6)
    p.add_argument("--lr", type=float, default=3e-4)
    p.add_argument("--mask-prob", type=float, default=0.06)
    p.add_argument("--mask-span", type=int, default=10)
    p.add_argument("--max-sec", type=float, default=12.0)
    p.add_argument("--log-every", type=int, default=50)
    args = ap.parse_args()
    if args.cmd == "pretrain":
        pretrain(args)


if __name__ == "__main__":
    main()
