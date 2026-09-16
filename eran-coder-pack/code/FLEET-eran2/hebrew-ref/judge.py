#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""judge.py -- the HEBREW JUDGE for the mouth school.

A phoneme recogniser (facebook/wav2vec2-xlsr-53-espeak-cv-ft, IPA CTC) scored as a
CLOSED-SET classifier over the 24 syllables of ruler.py FACTS: for every syllable we
build its IPA target(s) and take the CTC log-likelihood of that target under the model;
softmax over the 24 gives a proper posterior, so "confidence" means something.

Nothing is played. Nothing touches eran1. Files carry their speaker label.
claude-cli-FABLE-HEB 2026-09-03, on eran2 only.
"""
import os, sys, json, math, wave
import numpy as np
import torch
import torch.nn.functional as F

SR = 16000
MODEL = os.environ.get("JUDGE_MODEL", "facebook/wav2vec2-xlsr-53-espeak-cv-ft")
DEV = "cuda" if torch.cuda.is_available() else "cpu"

SYLS = ["a","aya","ba","va","ga","da","ha","wa","za","cha","ta","ya","ka","kha",
        "la","ma","na","sa","pa","fa","tza","qa","ra","sha"]

# consonant alternates per syllable, in espeak-IPA vocab tokens
CONS = {
    "a":   [[]],
    "aya": [["ʔ"], ["ʕ"]],
    "ba":  [["b"]],
    "va":  [["v"], ["β"]],
    "ga":  [["ɡ"]],
    "da":  [["d"]],
    "ha":  [["h"]],
    "wa":  [["v"], ["w"], ["ʋ"]],
    "za":  [["z"]],
    "cha": [["χ"], ["x"], ["ħ"]],
    "ta":  [["t"], ["t̪"], ["tʰ"]],
    "ya":  [["j"]],
    "ka":  [["k"], ["kʰ"]],
    "kha": [["χ"], ["x"]],
    "la":  [["l"], ["ɫ"]],
    "ma":  [["m"]],
    "na":  [["n"]],
    "sa":  [["s"], ["s̪"]],
    "pa":  [["p"], ["pʰ"]],
    "fa":  [["f"], ["ɸ"]],
    "tza": [["ts"], ["t","s"]],
    "qa":  [["k"], ["q"]],
    "ra":  [["ʁ"], ["ɾ"], ["r"], ["ɹ"]],
    "sha": [["ʃ"]],
}
VOWELS = [["a"], ["aː"], ["ɑ"], ["ä"], ["ɐ"]]

# homophone merge in MODERN HEBREW -- the fair, "canonical" scoring
CANON = {"a":"A","aya":"A","ba":"B","va":"V","wa":"V","ga":"G","da":"D","ha":"H",
         "za":"Z","cha":"X","kha":"X","ta":"T","ya":"Y","ka":"K","qa":"K","la":"L",
         "ma":"M","na":"N","sa":"S","pa":"P","fa":"F","tza":"TS","ra":"R","sha":"SH"}
# heldout-vault filename prefixes -> canonical class
HELDOUT = {"aa":"A","ah":"A","ba":"B","da":"D","ga":"G","ha":"H","ka":"K","kha":"X",
           "la":"L","ma":"M","na":"N","pa":"P","qa":"K","ra":"R","sa":"S","sha":"SH",
           "ta":"T","tha":"T","tsa":"TS","va":"V","ya":"Y","za":"Z"}

TRIM = os.environ.get("JUDGE_TRIM", "1") == "1"
_M = {}

def load():
    if _M: return _M
    from transformers import AutoProcessor, AutoModelForCTC
    proc = AutoProcessor.from_pretrained(MODEL)
    mdl = AutoModelForCTC.from_pretrained(MODEL).to(DEV).eval()
    tok = proc.tokenizer
    vocab = tok.get_vocab()
    blank = mdl.config.pad_token_id
    targets = {}
    for s in SYLS:
        opts = []
        for c in CONS[s]:
            for v in VOWELS:
                seq = c + v
                if all(p in vocab for p in seq):
                    opts.append([vocab[p] for p in seq])
        if not opts: raise RuntimeError("no target for " + s)
        targets[s] = opts
    _M.update(proc=proc, mdl=mdl, tok=tok, vocab=vocab, blank=blank, targets=targets,
              inv={i: p for p, i in vocab.items()})
    return _M

def read_wav(path):
    with wave.open(path, "rb") as w:
        n, sw, ch, sr = w.getnframes(), w.getsampwidth(), w.getnchannels(), w.getframerate()
        raw = w.readframes(n)
    dt = {1: np.uint8, 2: np.int16, 4: np.int32}[sw]
    y = np.frombuffer(raw, dtype=dt).astype(np.float64)
    if sw == 1: y = (y - 128) / 128.0
    else: y = y / float(2 ** (8 * sw - 1))
    if ch > 1: y = y.reshape(-1, ch).mean(axis=1)
    if sr != SR:                                   # linear resample, good enough at 16-48k
        t = np.arange(0, len(y) / sr, 1.0 / SR)[: int(len(y) * SR / sr)]
        y = np.interp(t, np.arange(len(y)) / sr, y)
    m = np.max(np.abs(y)) or 1.0
    return (y / m * 0.7).astype(np.float32)

@torch.no_grad()
def logprobs(wavs):
    """list of float32 arrays -> list of (T,V) log-prob tensors on DEV"""
    M = load()
    out = []
    for i in range(0, len(wavs), int(os.environ.get("JUDGE_BS","64"))):
        batch = wavs[i:i + int(os.environ.get("JUDGE_BS","64"))]
        inp = M["proc"](batch, sampling_rate=SR, return_tensors="pt", padding=True)
        iv = inp.input_values.to(DEV)
        am = inp.get("attention_mask")
        lens = None
        if am is not None:
            am = am.to(DEV)
            lg = M["mdl"](iv, attention_mask=am).logits
            lens = M["mdl"]._get_feat_extract_output_lengths(am.sum(-1)).to(torch.long)
        else:
            lg = M["mdl"](iv).logits
            lens = torch.full((lg.shape[0],), lg.shape[1], dtype=torch.long, device=DEV)
        lp = F.log_softmax(lg.float(), dim=-1)
        for b in range(lp.shape[0]):
            out.append(lp[b, : int(lens[b])])
    return out

def greedy(lp):
    M = load()
    ids = lp.argmax(-1).tolist()
    o, prev = [], None
    for i in ids:
        if i != prev and i != M["blank"]: o.append(M["inv"].get(i, "?"))
        prev = i
    return " ".join(o)

def score_one(lp):
    """(dict syl->loglik, greedy string). CTC log-likelihood of each syllable's target."""
    M = load()
    T = lp.shape[0]
    sc = {}
    for s in SYLS:
        best = -1e30
        for tgt in M["targets"][s]:
            if len(tgt) > T: continue
            t = torch.tensor(tgt, dtype=torch.long, device=DEV).unsqueeze(0)
            ll = -F.ctc_loss(lp.unsqueeze(1), t, torch.tensor([T], device=DEV),
                             torch.tensor([len(tgt)], device=DEV),
                             blank=M["blank"], reduction="sum", zero_infinity=True).item()
            best = max(best, ll)
        sc[s] = best
    return sc, greedy(lp)

def posterior(sc):
    v = np.array([sc[s] for s in SYLS], dtype=np.float64)
    v = v - v.max()
    p = np.exp(v); p /= p.sum()
    return {s: float(p[i]) for i, s in enumerate(SYLS)}

def canon_posterior(post):
    out = {}
    for s, p in post.items(): out[CANON[s]] = out.get(CANON[s], 0.0) + p
    return out

def judge_files(paths, batch=16):
    """-> list of dicts: file, top1, conf, top3, canon_top1, canon_conf, phones"""
    res = []
    for i in range(0, len(paths), batch):
        chunk = paths[i:i + batch]
        wavs = [(trim(read_wav(p)) if TRIM else read_wav(p)) for p in chunk]
        lps = logprobs(wavs)
        for p, lp in zip(chunk, lps):
            sc, ph = score_one(lp)
            post = posterior(sc)
            cp = canon_posterior(post)
            t3 = sorted(post.items(), key=lambda kv: -kv[1])[:3]
            ct = max(cp.items(), key=lambda kv: kv[1])
            res.append({"file": p, "top1": t3[0][0], "conf": t3[0][1],
                        "top3": [[a, round(b, 4)] for a, b in t3],
                        "canon_top1": ct[0], "canon_conf": ct[1], "phones": ph})
    return res

if __name__ == "__main__":
    import glob
    fs = []
    for a in sys.argv[1:]: fs += sorted(glob.glob(a))
    for r in judge_files(fs):
        print("%-52s %-4s %.3f  canon %-3s %.3f  [%s]" % (
            os.path.basename(r["file"]), r["top1"], r["conf"], r["canon_top1"],
            r["canon_conf"], r["phones"]), flush=True)

def trim(y, sr=SR, pad=0.06, thr_db=18.0):
    """energy-gate: keep from `pad` before the first frame within thr_db of the peak, to `pad` after the last."""
    h = 160
    if len(y) < 3 * h: return y
    e = np.array([np.sqrt((y[i:i+h]**2).mean()) for i in range(0, len(y)-h, h)])
    e = 20*np.log10(e + 1e-9)
    keep = np.where(e > e.max() - thr_db)[0]
    if len(keep) == 0: return y
    a = max(0, int((keep[0]*h) - pad*sr)); b = min(len(y), int((keep[-1]+1)*h + pad*sr))
    seg = y[a:b]
    if len(seg) < 0.08*sr: return y
    m = np.max(np.abs(seg)) or 1.0
    return (seg / m * 0.7).astype(np.float32)

# ---------------------------------------------------------------- fast path for the search
def _flat_targets():
    M = load(); flat = []; owner = []
    for s in SYLS:
        for t in M["targets"][s]: flat.append(t); owner.append(s)
    return flat, owner

_FT = {}
def score_batch(lps):
    """list of (T,V) log-probs -> list of {syl: loglik}. One ctc_loss call per clip."""
    M = load()
    if not _FT:
        f, o = _flat_targets()
        mx = max(len(t) for t in f)
        pad = torch.zeros(len(f), mx, dtype=torch.long, device=DEV)
        for i, t in enumerate(f): pad[i, :len(t)] = torch.tensor(t, device=DEV)
        _FT["pad"] = pad
        _FT["tl"] = torch.tensor([len(t) for t in f], dtype=torch.long, device=DEV)
        _FT["owner"] = o
    N = _FT["pad"].shape[0]
    out = []
    for lp in lps:
        T = lp.shape[0]
        rep = lp.unsqueeze(1).expand(T, N, lp.shape[1])
        il = torch.full((N,), T, dtype=torch.long, device=DEV)
        ll = -F.ctc_loss(rep, _FT["pad"], il, _FT["tl"], blank=M["blank"],
                         reduction="none", zero_infinity=True)
        sc = {s: -1e30 for s in SYLS}
        for v, s in zip(ll.tolist(), _FT["owner"]):
            if v > sc[s]: sc[s] = v
        out.append(sc)
    return out

def judge_wavs(wavs):
    """np arrays (already 16k float) -> list of (post, top3)."""
    lps = logprobs([np.asarray(w, dtype=np.float32) for w in wavs])
    res = []
    for sc, lp in zip(score_batch(lps), lps):
        post = posterior(sc)
        res.append((post, sorted(post.items(), key=lambda kv: -kv[1])[:3], greedy(lp)))
    return res
