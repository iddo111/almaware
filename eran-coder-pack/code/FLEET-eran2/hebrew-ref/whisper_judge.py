#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""whisper_judge.py -- second opinion: ivrit-ai/whisper-large-v3-turbo (Hebrew word ASR).
Not a closed-set classifier; we read the FIRST Hebrew consonant letter of the transcript.
Used only to CROSS-CHECK the phoneme judge -- two independent models disagreeing with the
label means the CLIP is suspect, not the judge."""
import os, sys, glob, json, torch, numpy as np
import judge as J
from transformers import AutoProcessor, AutoModelForSpeechSeq2Seq

LET2C = {"א":"A","ע":"A","ב":"B","ו":"V","ג":"G","ד":"D","ה":"H","ז":"Z","ח":"X","כ":"K",
         "ך":"K","ט":"T","ת":"T","י":"Y","ק":"K","ל":"L","מ":"M","ם":"M","נ":"N","ן":"N",
         "ס":"S","פ":"P","ף":"P","צ":"TS","ץ":"TS","ר":"R","ש":"SH"}
_W = {}
def load():
    if _W: return _W
    M = "ivrit-ai/whisper-large-v3-turbo"
    _W["p"] = AutoProcessor.from_pretrained(M)
    _W["m"] = AutoModelForSpeechSeq2Seq.from_pretrained(M, dtype=torch.float16).to("cuda").eval()
    return _W

def transcribe(paths, batch=8):
    W = load(); out = []
    for i in range(0, len(paths), batch):
        ch = paths[i:i+batch]
        ws = [J.read_wav(f) for f in ch]
        inp = W["p"](ws, sampling_rate=16000, return_tensors="pt").to("cuda")
        with torch.no_grad():
            ids = W["m"].generate(inp.input_features.half(), language="he", task="transcribe", max_new_tokens=10)
        for f, t in zip(ch, W["p"].batch_decode(ids, skip_special_tokens=True)):
            out.append((f, t.strip()))
    return out

def first_class(txt):
    for ch in txt:
        if ch in LET2C: return LET2C[ch]
    return "?"

if __name__ == "__main__":
    fs = []
    for a in sys.argv[1:]: fs += sorted(glob.glob(a))
    rows = transcribe(fs)
    import collections
    ok = n = 0; per = collections.defaultdict(lambda: [0,0]); dump=[]
    for f, t in rows:
        pre = os.path.basename(f).split("_")[0]
        truth = J.HELDOUT.get(pre)
        pred = first_class(t)
        dump.append({"file": os.path.basename(f), "truth": truth, "text": t, "pred": pred})
        if truth:
            n += 1; hit = pred == truth; ok += hit
            per[truth][1]+=1; per[truth][0]+=hit
    for c in sorted(per): print("   %-3s %d/%d"%(c, per[c][0], per[c][1]), flush=True)
    if n: print("whisper first-letter top1 = %d/%d = %.1f%%"%(ok,n,100*ok/n), flush=True)
    json.dump(dump, open(os.path.join(os.path.dirname(os.path.abspath(__file__)),"val","whisper-human132.json"),"w",encoding="utf-8"), ensure_ascii=False, indent=1)
