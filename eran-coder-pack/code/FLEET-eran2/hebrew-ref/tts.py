#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tts.py -- the HEBREW REFERENCE CORPUS. A Hebrew TTS model says the 24 syllables of the
mouth school, many ways each. LABEL LAW: every file is HEBTTS-<model>-<syl>-vNN.wav.
This is a REFERENCE, not food: nothing here is wired into the living ERAN.
claude-cli-FABLE-HEB 2026-09-03, eran2 only. Nothing is played."""
import os, sys, json, wave, itertools
import numpy as np, torch

SR = 16000
HERE = os.path.dirname(os.path.abspath(__file__))

TEXT = {  # syllable -> Hebrew WITH nikud (patach)
 "a":"אַ","aya":"עַ","ba":"בַּ","va":"בַ","ga":"גַ","da":"דַ","ha":"הַ","wa":"וַ","za":"זַ",
 "cha":"חַ","ta":"טַ","ya":"יַ","ka":"כַּ","kha":"כַ","la":"לַ","ma":"מַ","na":"נַ","sa":"סַ",
 "pa":"פַּ","fa":"פַ","tza":"צַ","qa":"קַ","ra":"רַ","sha":"שַׁ"}
# frame: (template, which voiced segment to keep: 0 first, -1 last)
FRAMES = [("{s}", -1), ("{s}.", 0), ("אָה {s}", -1), ("{s} {s}", -1)]
SPEEDS = [0.85, 1.0, 1.2]
PITCH  = [-3, 0, 3]

def seg_split(y, sr, thr_db=26.0, min_gap=0.05, hop=160):
    e = np.array([np.sqrt((y[i:i+hop]**2).mean()) for i in range(0, max(1,len(y)-hop), hop)])
    e = 20*np.log10(e + 1e-9); on = e > (e.max() - thr_db)
    segs = []; i = 0; G = int(min_gap*sr/hop)
    while i < len(on):
        if on[i]:
            j = i
            while j < len(on):
                if on[j]: j += 1; continue
                k = j
                while k < len(on) and not on[k]: k += 1
                if k - j >= G or k >= len(on): break
                j = k
            segs.append((i*hop, min(len(y), j*hop))); i = j
        else: i += 1
    return segs or [(0, len(y))]

def pitch_shift(y, semitones):
    if semitones == 0: return y
    r = 2.0 ** (semitones / 12.0)              # resample -> shifts pitch AND rate
    n = int(len(y) / r)
    return np.interp(np.arange(n) * r, np.arange(len(y)), y)

def norm_trim(y, sr, keep, max_s=0.9, pad=0.03):
    segs = seg_split(y, sr)
    a, b = segs[keep]
    a = max(0, int(a - pad*sr)); b = min(len(y), int(b + pad*sr))
    y = y[a:b]
    if len(y) > max_s*sr: y = y[:int(max_s*sr)]
    m = np.max(np.abs(y)) or 1.0
    return (y / m * (10**(-3/20))).astype(np.float32)

def wav_write(p, y, sr=SR):
    w = wave.open(p, "wb"); w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
    w.writeframes((np.clip(y, -1, 1)*32767).astype(np.int16).tobytes()); w.close()

def run_mms(out):
    from transformers import VitsModel, AutoTokenizer
    name = "facebook/mms-tts-heb"
    tok = AutoTokenizer.from_pretrained(name)
    m = VitsModel.from_pretrained(name).to("cuda").eval()
    msr = m.config.sampling_rate
    rows = []
    for syl, heb in TEXT.items():
        n = 0
        for (tpl, keep), sp, pt in itertools.product(FRAMES, SPEEDS, PITCH):
            txt = tpl.format(s=heb)
            m.speaking_rate = float(sp)
            torch.manual_seed(1000 + n)
            with torch.no_grad():
                y = m(**{k: v.to("cuda") for k, v in tok(txt, return_tensors="pt").items()}).waveform[0].cpu().numpy()
            if msr != SR:
                t = np.arange(0, len(y)/msr, 1.0/SR)[:int(len(y)*SR/msr)]
                y = np.interp(t, np.arange(len(y))/msr, y)
            y = pitch_shift(y, pt)
            try: y = norm_trim(y, SR, keep)
            except Exception: continue
            if len(y) < 0.08*SR: continue
            nm = "HEBTTS-mms-%s-v%02d" % (syl, n)
            wav_write(os.path.join(out, nm + ".wav"), y)
            rows.append({"file": nm+".wav", "syl": syl, "model": "facebook/mms-tts-heb",
                         "text": txt, "frame": tpl, "speed": sp, "pitch": pt,
                         "dur": round(len(y)/SR, 3)})
            n += 1
        print("%-4s %2d" % (syl, n), flush=True)
    return rows

if __name__ == "__main__":
    out = os.path.join(HERE, "corpus", "mms"); os.makedirs(out, exist_ok=True)
    rows = run_mms(out)
    with open(os.path.join(HERE, "corpus", "corpus.jsonl"), "w", encoding="utf-8") as f:
        for r in rows: f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("TOTAL", len(rows), flush=True)
