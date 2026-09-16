#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""judge_score.py -- THE JUDGE, callable.   wav path -> P(human)

Built 2026-09-01 on Iddo's order "תבנה שופט".  It answers ONE question:
"is this mouth a person?"  It is NOT "is this near the average" -- the ruler
that asked that was measured independent of Iddo's ear (rho -0.0055, p 0.95)
and below a coin flip at telling his GOOD from his NO.

It predicts an ear.  It never overrules one.  Iddo is the final authority.

USE FROM PYTHON (on eran2 or eran4, with ~/ear-v3/venv/bin/python):

    import sys; sys.path.insert(0, "/home/eran4/judge2")
    from judge_score import p_human
    p = p_human("/path/to/clip.wav")        # float in [0, 1]

USE FROM THE SHELL:

    ~/ear-v3/venv/bin/python judge_score.py clip.wav [more.wav ...]
    ~/ear-v3/venv/bin/python judge_score.py --json clip.wav
    ls run/*/best.wav | ~/ear-v3/venv/bin/python judge_score.py --stdin

REQUIREMENTS
  * host eran2 or eran4 (the PC copy of ear3 has no calibration and cannot run)
  * interpreter ~/ear-v3/venv/bin/python
  * 16 kHz mono 16-bit PCM wav
  * imports ear3.features ONLY -- never ear3.judge, whose BLOCK_GAINS give
    legacy192 a x12 gain and 75% of the old metric.  This judge learned its
    own weights from plain per-dim standardisation.
"""
from __future__ import annotations
import argparse, json, os, sys, wave
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
EARV3 = os.path.expanduser("~/ear-v3")
if EARV3 not in sys.path:
    sys.path.insert(0, EARV3)

FS, HOP, FRAC = 16000, 160, 0.10
def _default_model():
    r"""judge-v1.npz sits beside this file on the fleet and under models/ in the
    D:\CLAUDE mirror.  Accept both so the same file works in both trees."""
    for c in (os.path.join(HERE, "judge-v1.npz"),
              os.path.join(HERE, "models", "judge-v1.npz")):
        if os.path.exists(c):
            return c
    return os.path.join(HERE, "judge-v1.npz")


DEFAULT_MODEL = _default_model()

_M = None
_F = None


def _feat():
    global _F
    if _F is None:
        from ear3 import features as F      # NOT ear3.judge
        _F = F
    return _F


def _model(path=None):
    global _M
    if _M is None or path:
        p = path or DEFAULT_MODEL
        z = np.load(p, allow_pickle=False)
        _M = dict(w=z["w"], b=float(z["b"]), mu=z["mu"], sd=z["sd"],
                  feats=str(z["feats"]), setname=str(z["setname"]),
                  lam=float(z["lam"]), dim=int(z["dim"]), path=p,
                  thr=float(z["thr"]) if "thr" in z.files else 0.5)
    return _M


def read_wav(p):
    with wave.open(p, "rb") as w:
        if not (w.getnchannels() == 1 and w.getframerate() == FS
                and w.getsampwidth() == 2):
            raise ValueError("%s: need 16 kHz mono 16-bit PCM, got %s"
                             % (p, (w.getnchannels(), w.getframerate(),
                                    w.getsampwidth())))
        raw = w.readframes(w.getnframes())
    return np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0


def _env_rms(x, hop=HOP):
    nf = x.size // hop
    return (np.sqrt((x[:nf * hop].reshape(nf, hop) ** 2).mean(axis=1))
            if nf else np.zeros(0))


def trim_span(x, frac=FRAC, hop=HOP, pad_ms=25.0, fs=FS):
    """Same trim the judge was TRAINED on: speech span + 25 ms each side.
    Without it the judge would be reading silence padding, not a mouth."""
    e = _env_rms(x, hop)
    if e.size == 0 or e.max() <= 0:
        return x
    idx = np.where(e > e.max() * frac)[0]
    if idx.size == 0:
        return x
    pad = int(round(pad_ms * fs / 1000.0))
    a = max(0, int(idx[0]) * hop - pad)
    b = min(x.size, (int(idx[-1]) + 1) * hop + pad)
    y = x[a:b]
    return y if y.size >= hop * 4 else x


RMS_TARGET = 0.05


def rms_norm(x, target=RMS_TARGET):
    """The level normalisation the judge was TRAINED with.  ear3's spl_gain is
    a FROZEN SCALAR (features.py line 86), so loudness passes straight into the
    cochleagram: measured human 0.048 vs ERAN 0.107 raw RMS, and an RMS-only
    classifier reached balacc 0.762 on the un-normalised features.  Skipping
    this step turns the judge into a volume meter."""
    r = float(np.sqrt(np.mean(x ** 2)))
    if r < 1e-9:
        return x
    y = x * (target / r)
    m = float(np.max(np.abs(y)))
    if m > 0.99:
        y = y * (0.99 / m)
    return y.astype(np.float32)


def _sig(z):
    return 1.0 / (1.0 + np.exp(-z)) if z >= 0 else np.exp(z) / (1.0 + np.exp(z))


def p_human_samples(x, model_path=None):
    """P(human) for a float32 [-1,1] 16 kHz mono waveform."""
    M = _model(model_path)
    F = _feat()
    if M["feats"] == "trim":
        x = trim_span(x)
    elif M["feats"] == "norm":
        x = rms_norm(trim_span(x))
    v = np.asarray(F.features(x), dtype=np.float64)
    z = (v - M["mu"]) / M["sd"]
    return float(_sig(float(z @ M["w"] + M["b"])))


def p_human(path, model_path=None):
    """P(human) for a wav on disk.  THE one function to call."""
    return p_human_samples(read_wav(path), model_path)


def main():
    ap = argparse.ArgumentParser(description="THE JUDGE: wav -> P(human)")
    ap.add_argument("wav", nargs="*")
    ap.add_argument("--stdin", action="store_true", help="read paths from stdin")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--model", default=None)
    ap.add_argument("--thr", type=float, default=None,
                    help="default: the threshold stored in the model, which is "
                         "the median of the CV folds own training-fold thresholds")
    a = ap.parse_args()
    paths = list(a.wav)
    if a.stdin:
        paths += [l.strip() for l in sys.stdin if l.strip()]
    if not paths:
        ap.error("no wav given")
    M = _model(a.model)
    thr = a.thr if a.thr is not None else M["thr"]
    out = []
    for p in paths:
        try:
            v = p_human(p, a.model)
            out.append(dict(path=p, p_human=v,
                            verdict="human" if v >= thr else "eran"))
        except Exception as e:
            out.append(dict(path=p, error=str(e)))
    if a.json:
        print(json.dumps(dict(model=os.path.basename(M["path"]),
                              feats=M["feats"], set=M["setname"], thr=thr,
                              results=out), indent=1))
    else:
        for r in out:
            if "error" in r:
                print("%-60s ERROR %s" % (os.path.basename(r["path"]), r["error"]))
            else:
                print("%-60s P(human)=%.4f  %s"
                      % (os.path.basename(r["path"]), r["p_human"], r["verdict"]))


if __name__ == "__main__":
    main()
