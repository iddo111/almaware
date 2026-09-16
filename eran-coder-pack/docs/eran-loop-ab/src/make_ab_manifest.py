#!/usr/bin/env python3
"""make_ab_manifest.py — turn two grown brains into a question Iddo's ear can
answer, without a single label.

לזכרה של עלמה ז״ל.

THE PROBLEM THIS WORKS AROUND
-----------------------------
The obvious test — "which arm scores higher on the exam" — is unavailable.
proof/measure.py's 132-item heldout is MISLABELLED: Iddo listened on
2026-09-03 and 0 of 10 clips matched their labels. Reporting a top-1 off it
would be laundering a broken examiner, so no accuracy number exists in this
whole experiment.

THE QUESTION THAT SURVIVES
--------------------------
A prototype is a claim: "all of these are the same thing." That claim can be
checked by ear with no labels at all. So:

  * pick an ANCHOR wav
  * arm OPEN filed it under some prototype; take 3 more members of that group
  * arm CLOSED filed it under some prototype; take 3 more members of that group
  * play the two sets of 4, unlabelled, in random order
  * ask: which set sounds more like THE SAME SOUND repeated?

The anchor sits in BOTH sets, so the two are anchored to the same sound and
the comparison is exactly "whose neighbourhood is cleaner".

ROUNDS ARE CHOSEN WHERE THE TWO BRAINS DISAGREE, and that is stated on the
page. Where they file a sound identically there is nothing for an ear to
judge, and a test made of ties measures nothing. The overall agreement rate
across all 657 wavs is reported too, so the selection is visible rather than
hidden.

Filenames are used ONLY to fetch audio. The manifest carries basenames because
a wav has to be found on disk; the page never shows one, and the syllable in
the name is never read by anything here.
"""
import gzip
import json
import os
import random
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "body"))
sys.path.insert(0, os.path.join(ROOT, "proof"))

import genome                                                     # noqa: E402
import ears as ears_mod                                           # noqa: E402

STATE = os.path.join(ROOT, "state", "arms")
GROUP_N = 4          # clips per set, anchor included
ROUNDS = 6


def load_protos(path):
    d = json.loads(gzip.open(path, "rb").read().decode("utf-8"))
    return np.asarray([p["vec"] for p in d["protos"]], dtype=np.float64)


def main():
    ears = ears_mod.Ears()
    names = sorted(n for n in os.listdir(genome.FOOD_TRAIN)
                   if n.endswith(".wav"))
    V, kept = [], []
    for n in names:
        try:
            V.append(ears.utterance(os.path.join(genome.FOOD_TRAIN, n)))
            kept.append(n)
        except (OSError, ValueError):
            continue
    V = np.stack(V)
    print(f"{len(kept)} wavs, dim {V.shape[1]}")

    arms = {}
    for arm in ("open", "closed"):
        P = load_protos(os.path.join(STATE, f"brain-{arm}.json.gz"))
        assign = np.argmax(V @ P.T, axis=1)
        groups = {}
        for i, a in enumerate(assign):
            groups.setdefault(int(a), []).append(i)
        arms[arm] = {"assign": assign, "groups": groups, "n_protos": len(P)}
        sizes = sorted((len(v) for v in groups.values()), reverse=True)
        print(f"  {arm:6s}  {len(P)} prototypes, {len(groups)} of them used, "
              f"largest groups {sizes[:6]}")

    # How often do the two brains file a sound with the same neighbours? A
    # label-free agreement measure: for each wav, the Jaccard of its two groups.
    jac = []
    for i in range(len(kept)):
        ga = set(arms["open"]["groups"][int(arms["open"]["assign"][i])])
        gb = set(arms["closed"]["groups"][int(arms["closed"]["assign"][i])])
        jac.append(len(ga & gb) / max(1, len(ga | gb)))
    jac = np.asarray(jac)
    print(f"  neighbourhood agreement (Jaccard): mean {jac.mean():.3f}, "
          f"identical for {float((jac > 0.999).mean()) * 100:.1f}% of wavs")

    rng = random.Random(genome.SEED)
    # Candidates: both groups big enough to fill a set, and the two brains
    # actually disagree about the neighbourhood.
    cand = []
    for i in range(len(kept)):
        ga = arms["open"]["groups"][int(arms["open"]["assign"][i])]
        gb = arms["closed"]["groups"][int(arms["closed"]["assign"][i])]
        if len(ga) >= GROUP_N and len(gb) >= GROUP_N and jac[i] < 0.75:
            cand.append((jac[i], i))
    cand.sort()
    print(f"  {len(cand)} anchors where both groups are big enough AND the "
          f"two brains disagree")

    rounds, used = [], set()
    for _, i in cand:
        if len(rounds) >= ROUNDS:
            break
        if i in used:
            continue
        ga = [j for j in arms["open"]["groups"][int(arms["open"]["assign"][i])]
              if j != i]
        gb = [j for j in arms["closed"]["groups"][int(arms["closed"]["assign"][i])]
              if j != i]
        rng.shuffle(ga)
        rng.shuffle(gb)
        setA = [i] + ga[:GROUP_N - 1]
        setB = [i] + gb[:GROUP_N - 1]
        used.update(setA)
        used.update(setB)
        rounds.append({
            "anchor": kept[i],
            "open": [kept[j] for j in setA],
            "closed": [kept[j] for j in setB],
            "jaccard": round(float(jac[i]), 3),
        })

    doc = {
        "what": "blind prototype-purity A/B for the ERAN closed loop",
        "clips_dir": "clips",
        "n_wavs": len(kept),
        "arms": {a: {"n_protos": arms[a]["n_protos"],
                     "n_groups_used": len(arms[a]["groups"])}
                 for a in arms},
        "agreement": {
            "mean_jaccard": round(float(jac.mean()), 4),
            "frac_identical_neighbourhood": round(float((jac > 0.999).mean()), 4),
            "n_candidate_anchors_where_they_disagree": len(cand),
        },
        "rounds": rounds,
    }
    out = os.path.join(ROOT, "results", "ab-manifest.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1, ensure_ascii=False)
    print(f"written: {out}  ({len(rounds)} rounds)")


if __name__ == "__main__":
    main()
