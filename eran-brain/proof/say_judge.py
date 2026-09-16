"""say_judge.py — THE HONEST JUDGE for the mouth. Labels live HERE, like
proof/measure.py, and nowhere else in the voice/ pipeline.

Given a wav the mouth actually produced, reports:
  (a) cosine similarity to each of the 22 class centroids, built from
      food/train through the FROZEN ear (body/ears.py, EAR_REPR=cochlea) —
      a live comparison against everything the sound could have been, not
      only the one prototype it was told to imitate
  (b) the argmax class, and whether it is the intended one
  (c) a permutation/null control: what similarity 200 RANDOM articulator
      settings achieve against the intended class's centroid, so a win
      cannot be luck

PASS = the produced sound's nearest class centroid is the intended one, AND
its similarity to that centroid beats the 95th percentile of the random-
articulation null. Both conditions, fail-closed, exactly like measure.py's
mastery gate: a good number alone is not enough if a coin flip could have
produced it.

This file also holds pick_target_prototype() — the ONLY place that may
answer "which prototype in the organism's own brain does the examiner call
X?" — because that question needs the label mapping that measure.py holds
and voice/babble.py must never see.

Writes results/SAY-AH-<date>.json. Chance and the examiner's baselines are
printed first, by the same law as measure.py.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(ROOT, "body"))
sys.path.insert(0, os.path.join(ROOT, "voice"))
sys.path.insert(0, _HERE)

import genome                                     # noqa: E402
from ears import Ears, read_wav                   # noqa: E402
import measure                                     # noqa: E402
import mouth                                       # noqa: E402


# --------------------------------------------------------- label-side helpers
def class_centroids(ears, train_dir=None):
    """label -> L2-normalized mean percept vector, from food/train ONLY.

    Labels come from filenames via measure.label_of — this is the examiner's
    file, so reading a filename here is the same allowance measure.py itself
    has, and no other module in voice/ or body/ may do this.
    """
    train_dir = train_dir or genome.FOOD_TRAIN
    sums, counts = {}, {}
    for p in measure.wavs_in(train_dir):
        c = measure.label_of(p)
        v = ears.utterance(p)
        sums[c] = sums.get(c, np.zeros(ears.dim)) + v
        counts[c] = counts.get(c, 0) + 1
    out = {}
    for c, s in sums.items():
        m = s / counts[c]
        n = np.linalg.norm(m)
        out[c] = m / n if n > 0 else m
    return out


def pick_target_prototype(brain, ears, label, train_dir=None):
    """Which prototype in the organism's OWN brain does the examiner call
    `label`? Majority-vote mapping (measure.fit_proto_labels), then the
    prototype with the most mass among those that vote for `label` — the
    clearest, most-experienced version of that sound the child actually
    grew from its own living. Returns None if the organism never grew one.

    This — and only this — is how voice/say.py turns "ah" into a plain
    integer before handing it to voice/babble.py, which never sees the
    label itself.
    """
    train_dir = train_dir or genome.FOOD_TRAIN
    proto_label = measure.fit_proto_labels(brain, ears, measure.wavs_in(train_dir))
    candidates = [i for i, lab in proto_label.items() if lab == label]
    if not candidates:
        return None
    return max(candidates, key=lambda i: brain.protos[i]["mass"])


# ------------------------------------------------------------ the null control
def null_control_vecs(ears, n=200, seconds=0.32, seed=20260821):
    """What n RANDOM articulator settings sound like, through the frozen
    ear. Reused against whichever centroid the caller needs — the draws
    themselves do not depend on the target, only the mouth and the ear do."""
    sys.path.insert(0, os.path.join(ROOT, "voice"))
    import babble as babble_mod        # local import: avoids a hard cycle at module load
    rng = np.random.default_rng(seed)
    vecs = []
    for _ in range(n):
        m = babble_mod.random_posture(rng)
        y = mouth.articulate(seconds=seconds, seed=int(rng.integers(1, 2 ** 31 - 1)),
                             **m)
        vecs.append(ears.utterance_from_samples(y))
    return np.stack(vecs) if vecs else np.zeros((0, ears.dim))


# ------------------------------------------------------------------- the judge
def judge(wav_path, intended="ah", train_dir=None, null_n=200, write=True,
         results_dir=None, seed=20260821, seconds=0.32):
    ears = Ears(exam=True)
    measure.print_baselines_first()

    y = read_wav(wav_path)
    v = ears.utterance_from_samples(y)
    v_wav = ears.utterance(wav_path)
    if not np.allclose(v, v_wav):
        raise RuntimeError("ear path mismatch between utterance() and "
                           "utterance_from_samples() — the judge cannot be "
                           "trusted until this is fixed")

    centroids = class_centroids(ears, train_dir)
    if intended not in centroids:
        raise RuntimeError(f"no '{intended}' class in {train_dir or genome.FOOD_TRAIN} "
                           "— the judge needs food/train populated")
    sims = {c: float(v @ vec) for c, vec in centroids.items()}
    argmax_class = max(sims, key=sims.get)

    null_vecs = null_control_vecs(ears, n=null_n, seconds=seconds, seed=seed)
    null_sims = null_vecs @ centroids[intended]
    p95 = float(np.percentile(null_sims, 95)) if len(null_sims) else float("nan")
    sim_intended = sims[intended]
    beats_null = bool(len(null_sims) and sim_intended > p95)
    argmax_ok = argmax_class == intended
    passed = bool(argmax_ok and beats_null)

    result = {
        "ts": datetime.datetime.now().isoformat(timespec="seconds"),
        "wav": os.path.basename(wav_path),
        "intended": intended,
        "sims_to_centroids": {c: round(s, 5) for c, s in sims.items()},
        "argmax_class": argmax_class,
        "argmax_is_intended": argmax_ok,
        "null_control": {
            "n": int(len(null_sims)),
            "mean": round(float(null_sims.mean()), 5) if len(null_sims) else None,
            "sd": round(float(null_sims.std()), 5) if len(null_sims) else None,
            "p95": round(p95, 5) if len(null_sims) else None,
            "max": round(float(null_sims.max()), 5) if len(null_sims) else None,
        },
        "sim_to_intended_centroid": round(sim_intended, 5),
        "beats_null_p95": beats_null,
        "pass": passed,
        "pass_rule": "argmax_class == intended AND "
                     "sim_to_intended_centroid > null p95 (200 random "
                     "articulator settings)",
    }
    print(f"[say_judge] argmax={argmax_class} (want '{intended}') | "
          f"sim({intended})={sim_intended:.4f} vs null p95="
          f"{result['null_control']['p95']} | {'PASS' if passed else 'FAIL'}")
    if write:
        out_dir = results_dir or genome.RESULTS_DIR
        os.makedirs(out_dir, exist_ok=True)
        out = os.path.join(out_dir,
                          f"SAY-{intended.upper()}-{datetime.date.today().isoformat()}.json")
        tmp = out + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=1, ensure_ascii=False)
        os.replace(tmp, out)
        print(f"[say_judge] wrote {out}")
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(description="the honest judge for a produced wav")
    ap.add_argument("wav")
    ap.add_argument("--intended", default="ah")
    ap.add_argument("--null-n", type=int, default=200)
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args(argv)
    result = judge(a.wav, intended=a.intended, null_n=a.null_n,
                   write=not a.no_write)
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
