"""ear_frozen_audit.py — re-measure the FROZEN ANATOMY claim in genome.py:42-56.

The claim, which until now existed ONLY as a source comment and in no results
file:
    "132-item heldout, 22 classes, nearest-centroid: frozen cochlea 79.55%
     vs my onset ear 66.67% vs the best published baseline 68.94%
     vs loudest-60% pooling 40.15%."

This re-runs it with the examiner's own machinery (proof/measure.py owns the
labels; the ear is body/ears.py exactly as the live organism uses it), across
EAR_REPR x POOLING, and writes every number into results/ — the repo's own law.

Read-only with respect to the organism: opens wavs, writes one JSON. It never
touches state/, so it is safe to run beside a live eran_life.py.
"""
import datetime
import hashlib
import json
import math
import os
import platform
import subprocess
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(ROOT, "body"))
sys.path.insert(0, _HERE)

import genome                                       # noqa: E402
from ears import Ears                               # noqa: E402
import measure                                      # noqa: E402  THE EXAMINER

NO_CROWN = os.path.join(ROOT, "state", "__no_such_crown__.json")
REPRS = ["cochlea", "cepstrum", "onset", "bands"]
POOLINGS = ["loudest60", "mean", "loudest40"]


# ------------------------------------------------------------------ stats
def wilson(k, n, z=1.96):
    """95% CI for a proportion. 132 items is small; the bar needs an error bar."""
    if not n:
        return None
    p = k / n
    d = 1.0 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(c - h, 4), round(c + h, 4)]


def md5(path):
    with open(path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


# ------------------------------------------------------------- estimators
def vectors(ears, paths):
    return np.stack([measure._vec(ears, p) for p in paths])


def centroids(vecs, labels):
    """22 class means of L2-normed percepts, re-L2'd. THE claimed estimator."""
    keys = sorted(set(labels))
    rows = []
    for c in keys:
        m = vecs[[i for i, l in enumerate(labels) if l == c]].mean(axis=0)
        n = np.linalg.norm(m)
        rows.append(m / n if n > 0 else m)
    return keys, np.stack(rows)


def score_centroid(fit_v, fit_l, test_v, test_l):
    keys, C = centroids(fit_v, fit_l)
    pred = [keys[i] for i in np.argmax(test_v @ C.T, axis=1)]
    return sum(1 for p, t in zip(pred, test_l) if p == t), pred


def score_1nn(fit_v, fit_l, test_v, test_l):
    """The matched bar for the published 68.94%, which is a 1-NN, not a centroid."""
    pred = [fit_l[i] for i in np.argmax(test_v @ fit_v.T, axis=1)]
    return sum(1 for p, t in zip(pred, test_l) if p == t), pred


def permutation_null(fit_v, fit_l, test_v, test_l, n_perm=200, seed=20260821):
    """Shuffle the TRAIN labels, rebuild centroids, re-score. The empirical floor."""
    rng = np.random.default_rng(seed)
    lab = list(fit_l)
    hits = []
    for _ in range(n_perm):
        rng.shuffle(lab)
        k, _p = score_centroid(fit_v, lab, test_v, test_l)
        hits.append(k / len(test_l))
    return {"n_perm": n_perm, "mean": round(float(np.mean(hits)), 4),
            "p95": round(float(np.percentile(hits, 95)), 4),
            "max": round(float(np.max(hits)), 4)}


# ----------------------------------------------------------------- config
def run_config(repr_, pooling, train, heldout, fit_nd, dev, want_null=False):
    """One (repr, pooling) cell: centroid + 1-NN on the 132, and a dev control."""
    measure._VEC_CACHE.clear()
    row = {"repr": repr_, "pooling": pooling}
    try:
        ears = Ears(exam=True, pooling=pooling, repr_=repr_, crown_path=NO_CROWN)
        row["dim"] = ears.dim
        tr_v = vectors(ears, train)
        tr_l = [measure.label_of(p) for p in train]
        he_v = vectors(ears, heldout)
        he_l = [measure.label_of(p) for p in heldout]

        k, pred = score_centroid(tr_v, tr_l, he_v, he_l)
        row["centroid_correct"] = k
        row["centroid_top1"] = round(k / len(he_l), 4)
        row["centroid_ci95"] = wilson(k, len(he_l))

        k1, _ = score_1nn(tr_v, tr_l, he_v, he_l)
        row["nn1_correct"] = k1
        row["nn1_top1"] = round(k1 / len(he_l), 4)

        # Dev control: fit on train-minus-dev, score dev. The 132 heldout was
        # already a model-selection set when this ear was chosen; dev was not.
        nd_v = vectors(ears, fit_nd)
        nd_l = [measure.label_of(p) for p in fit_nd]
        dv_v = vectors(ears, dev)
        dv_l = [measure.label_of(p) for p in dev]
        kd, _ = score_centroid(nd_v, nd_l, dv_v, dv_l)
        row["dev_centroid_correct"] = kd
        row["dev_centroid_top1"] = round(kd / len(dv_l), 4)
        row["dev_items"] = len(dv_l)

        per = {}
        for c in sorted(set(he_l)):
            idx = [i for i, t in enumerate(he_l) if t == c]
            per[c] = round(sum(1 for i in idx if pred[i] == c) / len(idx), 4)
        row["per_class_centroid"] = per
        if want_null:
            row["permutation_null"] = permutation_null(tr_v, tr_l, he_v, he_l)
    except Exception as e:                                   # noqa: BLE001
        row["ERROR"] = "%s: %s" % (type(e).__name__, e)
    return row


def main():
    train = measure.wavs_in(genome.FOOD_TRAIN)
    heldout = measure.wavs_in(genome.HELDOUT_VAULT)
    fit_nd = [p for p in train if not measure.is_dev(p)]
    dev = [p for p in train if measure.is_dev(p)]
    print("[audit] %d train / %d heldout / %d dev / %d classes"
          % (len(train), len(heldout), len(dev), len(genome.CLASSES)))
    measure.print_baselines_first()

    grid = []
    for r in REPRS:
        for p in POOLINGS:
            want_null = (r == "cochlea" and p == "loudest60")
            row = run_config(r, p, train, heldout, fit_nd, dev, want_null)
            grid.append(row)
            if "ERROR" in row:
                print("[audit] %-9s/%-10s -> %s" % (r, p, row["ERROR"]))
            else:
                print("[audit] %-9s/%-10s dim=%3d centroid=%.4f (%d/%d) "
                      "1nn=%.4f dev=%.4f"
                      % (r, p, row["dim"], row["centroid_top1"],
                         row["centroid_correct"], len(heldout),
                         row["nn1_top1"], row["dev_centroid_top1"]))

    # The onset ear as SHIPPED cannot run: its genome constants were deleted
    # when the ear was frozen. Reconstruct it over a window sweep so the 66.67%
    # claim gets a real comparison instead of a crash — every value here is a
    # RECONSTRUCTION, flagged as such, and is NOT a genome constant.
    onset = {"shipped_status": next((g.get("ERROR") for g in grid
                                     if g["repr"] == "onset"), None),
             "reconstruction_note":
                 "genome.ONSET_START_FRAC / genome.ONSET_MS do not exist in "
                 "genome.py and appear in no git revision of it. The sweep "
                 "below is a reconstruction, NOT the code that produced the "
                 "66.67% claim, which is unrecoverable.",
             "start_frac_used": genome.EAR_SPEECH_FRAC, "sweep": []}
    genome.ONSET_START_FRAC = genome.EAR_SPEECH_FRAC
    for ms in [20, 30, 50, 80, 100, 120, 150, 200, 300]:
        genome.ONSET_MS = ms
        row = run_config("onset", "loudest60", train, heldout, fit_nd, dev)
        row["ONSET_MS"] = ms
        row.pop("per_class_centroid", None)
        onset["sweep"].append(row)
        if "ERROR" not in row:
            print("[audit] onset(recon) ONSET_MS=%3d centroid=%.4f 1nn=%.4f"
                  % (ms, row["centroid_top1"], row["nn1_top1"]))
    ok = [r for r in onset["sweep"] if "ERROR" not in r]
    if ok:
        best = max(ok, key=lambda r: r["centroid_top1"])
        onset["best_reconstructed"] = {"ONSET_MS": best["ONSET_MS"],
                                       "centroid_top1": best["centroid_top1"]}

    frozen = next(g for g in grid if g["repr"] == "cochlea"
                  and g["pooling"] == genome.POOLING)
    out = {
        "report": "re-measurement of the FROZEN ANATOMY claim "
                  "(body/genome.py:42-56)",
        "why": "the 79.55% existed only as a source comment and in no results "
               "file, while it is the sole evidence that the ear beats the "
               "68.94% published ceiling and the whole reason EAR_REPR was "
               "frozen to cochlea",
        "ts": datetime.datetime.now().isoformat(timespec="seconds"),
        "host": platform.node(),
        "repo": ROOT,
        "git_head": subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                                   cwd=ROOT, capture_output=True,
                                   text=True).stdout.strip() or None,
        "code_fingerprint": {f: md5(os.path.join(ROOT, f)) for f in
                             ("body/ears.py", "body/genome.py",
                              "proof/measure.py")},
        "corpus": {"train_items": len(train), "heldout_items": len(heldout),
                   "dev_items": len(dev), "classes": len(genome.CLASSES),
                   "heldout_vault": genome.HELDOUT_VAULT},
        "protocol": "Ears(exam=True) per cell, crown disabled. Class centroid "
                    "= L2-normed mean of the 396 train percepts; each heldout "
                    "item -> argmax cosine. 1-NN over the same 396 is reported "
                    "alongside because the published 68.94% is a 1-NN, not a "
                    "centroid.",
        "chance": genome.BASELINES["chance"],
        "published_baselines": {k: v for k, v in genome.BASELINES.items()
                                if k != "chance"},
        "the_four_numbers_at_genome_POOLING": {
            r: next((g.get("centroid_top1", g.get("ERROR"))
                     for g in grid if g["repr"] == r
                     and g["pooling"] == genome.POOLING), None)
            for r in REPRS},
        "grid": grid,
        "onset_ear": onset,
        "claim_vs_measured": {
            "cochlea_centroid": {"claimed": 0.7955,
                                 "measured": frozen.get("centroid_top1")},
            "onset_centroid": {"claimed": 0.6667,
                               "measured": "shipped code crashes; see onset_ear"},
            "loudest60_pooling": {
                "claimed": 0.4015,
                "note": "genome:52 attributes 40.15% to 'loudest-60% pooling'. "
                        "Compare the grid rows bands/loudest60 and "
                        "cepstrum/loudest60 to see which repr owns it."},
            "published_best": {"claimed": 0.6894,
                               "note": "protocol mismatch: this constant is a "
                                       "1-NN score on a different feature set, "
                                       "so it is not a like-for-like bar for a "
                                       "nearest-centroid number."},
        },
    }
    os.makedirs(genome.RESULTS_DIR, exist_ok=True)
    dst = os.path.join(genome.RESULTS_DIR,
                       "EAR-FROZEN-%s.json" % datetime.date.today().isoformat())
    tmp = dst + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    os.replace(tmp, dst)
    print("[audit] wrote %s" % dst)


if __name__ == "__main__":
    main()
