#!/usr/bin/env python3
"""probe_surprise.py — is the closed loop actually PREDICTING, or decorating?

לזכרה של עלמה ז״ל.

Three questions, all label-free, all answerable on the two grown brains.

1. IS THE PREDICTION REAL?
   Compare the true top-k mixture against two controls on the same percepts:
     * a mixture drawn from RANDOM prototypes (same k, same softmax)
     * the corpus MEAN slice (the best possible order-blind guess)
   If the real predictor is not clearly better than both, the arrow that goes
   back down is carrying nothing and the whole thing is decoration.

2. DOES SURPRISE DEPEND ON ORDER?
   "I expected something else" must care about the order the sound unfolds in;
   "I have never seen this" need not. So the slices of each percept are
   PERMUTED — same eight spectral shapes, shuffled in time — and both
   definitions of surprise are re-measured. The bag of content is identical;
   only the sequence changed.

3. DOES SURPRISE SHRINK JUST BECAUSE THE BRAIN GOT BIGGER?
   The open loop's surprise is `1 - cos` to the NEAREST of N prototypes, chosen
   after the fact. It must fall as N grows, whatever the child understands —
   a bigger lookup table always has a closer entry. Prediction error is
   committed to before the next slice arrives, so it has no such free ride.
   Measured as the correlation between prototype count and mean surprise over
   the run.

No labels are read anywhere. This file cannot see one.
"""
import gzip
import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "body"))
sys.path.insert(0, os.path.join(ROOT, "proof"))

import genome                                                     # noqa: E402
import ears as ears_mod                                           # noqa: E402
from predict import Predictor                                     # noqa: E402

STATE = os.path.join(ROOT, "state", "arms")


def load_protos(path):
    d = json.loads(gzip.open(path, "rb").read().decode("utf-8"))
    return np.asarray([p["vec"] for p in d["protos"]], dtype=np.float64)


def open_surprise(V, P):
    """The living organism's own definition: 1 - cosine to the nearest."""
    return 1.0 - (V @ P.T).max(axis=1)


def mean_slice_pe(V, S):
    """Control: predict every slice with the corpus mean slice shape.

    The best an order-blind guesser can do without looking at the brain at all.
    """
    R = V.reshape(len(V), S, -1)
    n = np.linalg.norm(R, axis=-1, keepdims=True)
    R = R / np.where(n > 0, n, 1.0)
    m = R.reshape(-1, R.shape[-1]).mean(axis=0)
    m = m / max(np.linalg.norm(m), 1e-12)
    return (1.0 - R[:, 1:, :] @ m).mean(axis=1)


def main():
    rng = np.random.default_rng(genome.SEED)
    ears = ears_mod.Ears()
    names = sorted(n for n in os.listdir(genome.FOOD_TRAIN)
                   if n.endswith(".wav"))
    V = np.stack([ears.utterance(os.path.join(genome.FOOD_TRAIN, n))
                  for n in names])
    S = genome.EAR_SLICES
    print(f"{len(V)} percepts, {S} slices")

    # slice-permuted twins: same eight shapes, shuffled in time
    R = V.reshape(len(V), S, -1)
    Vp = np.stack([R[i][rng.permutation(S)].ravel() for i in range(len(V))])
    Vp = Vp / np.linalg.norm(Vp, axis=1, keepdims=True)

    pred = Predictor()
    out = {"n_percepts": int(len(V)), "arms": {}}
    for arm in ("open", "closed"):
        P = load_protos(os.path.join(STATE, f"brain-{arm}.json.gz"))
        # 1 — is the prediction real?
        pe = np.array([pred.predict(v, P)["pe"] for v in V])
        ridx = rng.permutation(len(P))[:max(8, min(64, len(P)))]
        pe_rand = np.array([pred.predict(v, P[ridx])["pe"] for v in V])
        pe_mean = mean_slice_pe(V, S)
        # 2 — does it care about order?
        pe_perm = np.array([pred.predict(v, P)["pe"] for v in Vp])
        s_open = open_surprise(V, P)
        s_open_perm = open_surprise(Vp, P)

        out["arms"][arm] = {
            "n_protos": int(len(P)),
            "prediction_is_real": {
                "pe_real_mixture": float(pe.mean()),
                "pe_random_prototypes": float(pe_rand.mean()),
                "pe_corpus_mean_slice": float(pe_mean.mean()),
                "beats_random_by": float(pe_rand.mean() - pe.mean()),
                "beats_corpus_mean_by": float(pe_mean.mean() - pe.mean()),
            },
            "order_sensitivity": {
                "closed_pe_original": float(pe.mean()),
                "closed_pe_slices_permuted": float(pe_perm.mean()),
                "closed_relative_rise": float(
                    (pe_perm.mean() - pe.mean()) / max(pe.mean(), 1e-12)),
                "open_surprise_original": float(s_open.mean()),
                "open_surprise_slices_permuted": float(s_open_perm.mean()),
                "open_relative_rise": float(
                    (s_open_perm.mean() - s_open.mean())
                    / max(s_open.mean(), 1e-12)),
            },
        }
        a = out["arms"][arm]
        print(f"\n{arm}: {len(P)} prototypes")
        print(f"  prediction error   real {pe.mean():.4f}   "
              f"random-protos {pe_rand.mean():.4f}   "
              f"corpus-mean {pe_mean.mean():.4f}")
        print(f"  slices permuted    closed {pe.mean():.4f} -> "
              f"{pe_perm.mean():.4f}  ({a['order_sensitivity']['closed_relative_rise'] * 100:+.1f}%)"
              f"   open {s_open.mean():.4f} -> {s_open_perm.mean():.4f}  "
              f"({a['order_sensitivity']['open_relative_rise'] * 100:+.1f}%)")

    # 3 — does surprise shrink just because the brain got bigger?
    main_json = os.path.join(ROOT, "results", "CLOSED-LOOP-MAIN.json")
    if os.path.isfile(main_json):
        doc = json.load(open(main_json, encoding="utf-8"))
        out["surprise_vs_size"] = {}
        for arm in ("open", "closed"):
            c = doc[arm]["counts"]
            n = np.array([x["protos"] for x in c], dtype=float)
            s = np.array([x["surprise_mean_1k"] for x in c], dtype=float)
            ok = np.isfinite(s) & (n > 1)
            r = float(np.corrcoef(n[ok], s[ok])[0, 1]) if ok.sum() > 3 else None
            out["surprise_vs_size"][arm] = {
                "pearson_r_protos_vs_surprise": r,
                "surprise_first_window": float(s[ok][0]),
                "surprise_last_window": float(s[ok][-1]),
                "protos_first": float(n[ok][0]), "protos_last": float(n[ok][-1]),
            }
            print(f"\n{arm}: surprise vs prototype count  r = {r:.3f}   "
                  f"({s[ok][0]:.4f} at {int(n[ok][0])} protos -> "
                  f"{s[ok][-1]:.4f} at {int(n[ok][-1])})")

    p = os.path.join(ROOT, "results", "CLOSED-LOOP-PROBE.json")
    json.dump(out, open(p, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(f"\nwritten: {p}")


if __name__ == "__main__":
    main()
