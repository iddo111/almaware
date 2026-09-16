import json
import numpy as np

DEEP = ["ah", "ba", "ma", "ima", "ih", "abba"]

def load():
    R = json.load(open("feats_sit.json"))
    X = np.array([r["vec"] for r in R], dtype=np.float64)
    unit = np.array([r["unit"] for r in R])
    take = np.array([r["take"] for r in R])
    mt   = np.array([r["mtime"] for r in R])
    sit  = np.array([r["sit"] for r in R])
    dur  = np.array([r["dur"] for r in R])
    return X, unit, take, mt, sit, dur

def nn1(Xtr, ytr, Xte, yte, zs=True):
    """verify.py's probe: z-score by TRAIN mu/sd, squared euclidean, 1-NN.
    Distances via ||a||^2+||b||^2-2ab -- identical result, no (n,m,d) tensor."""
    if zs:
        mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-9
        A, B = (Xtr - mu) / sd, (Xte - mu) / sd
    else:
        A, B = Xtr, Xte
    d = (B*B).sum(1)[:, None] + (A*A).sum(1)[None, :] - 2.0 * (B @ A.T)
    pred = ytr[np.argmin(d, axis=1)]
    return pred, float(np.mean(pred == yte))
