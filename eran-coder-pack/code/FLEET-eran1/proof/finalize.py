# -*- coding: utf-8 -*-
"""finalize.py -- render the deliverable wavs, each with a sidecar that tells
the truth about how it was made.

Every wav written here comes from ERAN's own vocal tract, driven by parameters
his own search chose, judged by his own frozen cochlea. No TTS is involved
anywhere in this file or anything it imports. Nothing is played aloud.
"""
from __future__ import annotations

import datetime
import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(ROOT, "body"), os.path.join(ROOT, "voice")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import earlink                                   # noqa: E402
import mouth34                                   # noqa: E402
from ears import write_wav                       # noqa: E402

OUT = os.path.expanduser("~/eran-voice-out")
UTC = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def emit(name, y, sidecar):
    wav = os.path.join(OUT, name + ".wav")
    write_wav(wav, y)
    sidecar["wav"] = wav
    sidecar["bytes"] = os.path.getsize(wav)
    sidecar["samples"] = int(y.size)
    sidecar["sample_rate"] = mouth34.SR
    sidecar["seconds"] = round(y.size / mouth34.SR, 4)
    sidecar["utc"] = UTC
    sidecar["host"] = os.uname().nodename
    sidecar["how_made"] = (
        "ERAN's own 34-section vocal tract (voice/mouth34.py, the Kelly-Lochbaum "
        "ladder verified in voice/tract_analytic.py), driven by parameters chosen "
        "by his own (1+1) hill climb (voice/gym.py) scored in his own frozen "
        "192-d cochlea (body/ears.py). NO text-to-speech. NO recorded human audio "
        "in the output. Nothing was played aloud.")
    with open(os.path.join(OUT, name + ".json"), "w", encoding="utf-8") as f:
        json.dump(sidecar, f, indent=1, ensure_ascii=False)
    print("  %-34s %6d samples  %.2f s  %s"
          % (name + ".wav", y.size, y.size / mouth34.SR,
             sidecar.get("headline", "")))
    return wav


def main():
    os.makedirs(OUT, exist_ok=True)
    ears = earlink.open_ear()
    t_ah, s_ah = earlink.target_for(ears, "ah")
    t_abba, s_abba = earlink.target_for(ears, "abba")
    pj = os.path.join(ROOT, "voice", "postures", "ah-best.json")
    post = json.load(open(pj))
    areas = np.array(post["areas"], dtype=float)
    f0 = float(post.get("f0_hz", 220.0))

    print("rendering into %s" % OUT)

    # 1 -- the vowel he found
    y = mouth34.say(areas, f0=f0, seconds=0.6, seed=0,
                    glottal_reflect=post["glottal_reflect"],
                    lip_reflect=post["lip_reflect"])
    d = earlink.distance(ears.utterance_from_samples(y), t_ah)
    emit("01-ERAN-ah-searched", y, {
        "headline": "his /ah/, d=%.4f (a real clip of Iddo: %.4f)"
                    % (d, s_ah["real_to_centroid_mean"]),
        "unit": "ah",
        "areas": post["areas"], "f0_hz": f0,
        "glottal_reflect": post["glottal_reflect"],
        "lip_reflect": post["lip_reflect"],
        "distance_to_ah_centroid": d,
        "standard_real_clip_to_centroid": s_ah["real_to_centroid_mean"],
        "standard_within_class_spread": s_ah["within_class_spread"],
        "max_k_interior": mouth34.max_k_interior(areas),
    })

    # 2 -- the same tract, moving: /a/ - lips shut - /a/
    shut = mouth34.closed_lips(areas, n_closed=4, area=0.02)
    keys = [(areas, 0.22), (shut, 0.10), (areas, 0.28)]
    y2 = mouth34.say_sequence(keys, f0=f0, seed=0,
                              glottal_reflect=post["glottal_reflect"],
                              lip_reflect=post["lip_reflect"])
    v2 = ears.utterance_from_samples(y2)
    gap = float(np.linalg.norm(v2 - t_abba) - np.linalg.norm(v2 - t_ah))
    emit("02-ERAN-abba-attempt", y2, {
        "headline": "a MOVEMENT: /a/ 0.22s, lips shut 0.10s, /a/ 0.28s",
        "unit": "abba (attempt)",
        "WARNING": ("This is NOT ERAN saying אבא. It is his tract performing a "
                    "lip closure between two vowels, with the closure timing "
                    "chosen BY HAND, not found by his own search. The vowel on "
                    "either side is his. The gesture is not yet. Calling this "
                    "'ERAN said abba' would be the cardinal sin of this project."),
        "keyframes_seconds": [0.22, 0.10, 0.28],
        "areas_open": post["areas"],
        "areas_closed": [float(x) for x in shut],
        "f0_hz": f0,
        "max_k_interior_open": mouth34.max_k_interior(areas),
        "max_k_interior_closed": mouth34.max_k_interior(shut),
        "gap_abba_minus_ah": gap,
        "reference_gap_real_abba": float(np.mean(
            [float(np.linalg.norm(p - t_abba) - np.linalg.norm(p - t_ah))
             for p in earlink.percepts(ears, earlink.clips("abba"))])),
        "reference_gap_real_ah": float(np.mean(
            [float(np.linalg.norm(p - t_abba) - np.linalg.norm(p - t_ah))
             for p in earlink.percepts(ears, earlink.clips("ah"))])),
    })

    # 3 -- the honest control: the null posture, so the vowel has something to beat
    yu = mouth34.say(np.ones(34), f0=f0, seconds=0.6, seed=0)
    du = earlink.distance(ears.utterance_from_samples(yu), t_ah)
    emit("03-control-uniform-tube", yu, {
        "headline": "CONTROL: a straight tube, no search. d=%.4f" % du,
        "unit": "none (null posture)",
        "why": ("The number 0.43 means nothing without this. A straight 17 cm "
                "tube with no learning at all scores %.4f against the same "
                "target." % du),
        "areas": [1.0] * 34, "f0_hz": f0,
        "distance_to_ah_centroid": du,
    })
    print()
    print("SCOREBOARD, all in ERAN own frozen 192-d cochlea, target = 100 real")
    print("recordings of Iddo saying /ah/:")
    print("   straight tube, no learning        %.4f" % du)
    print("   ERAN searched vowel               %.4f" % d)
    print("   within-class spread of real /ah/  %.4f" % s_ah["within_class_spread"])
    print("   a REAL recording of Iddo          %.4f" % s_ah["real_to_centroid_mean"])
    print("   the closest REAL recording        %.4f" % s_ah["real_to_centroid_min"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
