# -*- coding: utf-8 -*-
"""render.py -- one named parameter set in, one wav and one honest number out.

THE MISSING PRIMITIVE. Before this file, no command anywhere in this project
rendered a single wav from a single GIVEN motor command. Every entry point ran a
search first, and organs/babble.py -- the script that achieved the first closed
sensorimotor loop -- held the converged 34-number shape in RAM and lost it on
exit: no open(), no json.dump, no --out anywhere in the file. The product of the
first learning event in this project's history exists today only as prose in a
memory note. That is why this exists and why gym.py writes everything down.

USAGE
    python3 render.py --areas voice/postures/uniform34.json --out /tmp/a.wav
    python3 render.py --areas 1.0 1.2 ... --f0 220 --seconds 0.6 --score-against ah
    python3 render.py --areas <json> --sequence abba --out /tmp/abba.wav

SACRED AUDIO LAW: writes wavs, never plays them.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import earlink                                   # noqa: E402
import mouth34                                   # noqa: E402
from ears import write_wav                       # noqa: E402


def load_areas(tokens):
    """--areas may be a path to a .json, or the raw floats themselves."""
    if len(tokens) == 1 and not _isfloat(tokens[0]):
        path = os.path.expanduser(tokens[0])
        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f)
        if isinstance(obj, dict):
            obj = obj.get("areas", obj.get("final_areas"))
        return np.asarray(obj, dtype=float)
    return np.asarray([float(t) for t in tokens], dtype=float)


def _isfloat(s):
    try:
        float(s)
        return True
    except ValueError:
        return False


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--areas", nargs="+", required=True,
                    help="34 floats, or a path to a .json holding them")
    ap.add_argument("--f0", type=float, default=220.0,
                    help="FENCED, never searched. A baby is 200-500 Hz.")
    ap.add_argument("--seconds", type=float, default=0.6)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--glottal-reflect", type=float, default=mouth34.GLOTTAL_REFLECT)
    ap.add_argument("--lip-reflect", type=float, default=mouth34.LIP_REFLECT)
    ap.add_argument("--out", default=None, help="where to write the wav")
    ap.add_argument("--score-against", default=None, metavar="UNIT",
                    help="score in ERAN's own frozen ear against Iddo's real UNIT")
    ap.add_argument("--corpus", default=None)
    ap.add_argument("--sequence", default=None, choices=("abba",),
                    help="render a MOVEMENT, not a posture (see mouth34 warning)")
    a = ap.parse_args(argv)

    areas = load_areas(a.areas)
    print("areas          n=%d  min=%.3f max=%.3f  max|k_interior|=%.3f"
          % (areas.size, areas.min(), areas.max(), mouth34.max_k_interior(areas)))

    if a.sequence == "abba":
        shut = mouth34.closed_lips(areas, n_closed=4, area=0.02)
        keys = [(areas, 0.22), (shut, 0.09), (areas, 0.29)]
        print("sequence       /a/ 0.22s -> lips shut 0.09s (max|k|=%.3f) -> /a/ 0.29s"
              % mouth34.max_k_interior(shut))
        y = mouth34.say_sequence(keys, f0=a.f0, seed=a.seed,
                                 glottal_reflect=a.glottal_reflect,
                                 lip_reflect=a.lip_reflect)
        seconds = 0.60
    else:
        y = mouth34.say(areas, f0=a.f0, seconds=a.seconds, seed=a.seed,
                        glottal_reflect=a.glottal_reflect,
                        lip_reflect=a.lip_reflect)
        seconds = a.seconds

    if y is None:
        print("REFUSED: the tube is unstable or not physical. No wav written.")
        return 2

    print("rendered       %d samples @ %d Hz = %.3f s  peak=%.3f"
          % (y.size, mouth34.SR, y.size / mouth34.SR, float(np.max(np.abs(y)))))

    if a.out:
        out = os.path.expanduser(a.out)
        os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
        write_wav(out, y)
        print("wrote          %s (%d bytes)" % (out, os.path.getsize(out)))

    if a.score_against:
        ears = earlink.open_ear()
        target, stats = earlink.target_for(ears, a.score_against, a.corpus)
        v = ears.utterance_from_samples(y)
        d = earlink.distance(v, target)
        print("")
        print("ear            frozen cochlea, repr=%s dim=%d" % (ears.repr, ears.dim))
        print("d(rendered, %s centroid)          = %.4f" % (a.score_against, d))
        print("  a REAL clip of %-4s sits at      = %.4f  (mean of %d, best %.4f)"
              % (a.score_against, stats["real_to_centroid_mean"],
                 stats["n_clips"], stats["real_to_centroid_min"]))
        print("  within-class spread of %-4s      = %.4f"
              % (a.score_against, stats["within_class_spread"]))
        # The claim body/ears.py line 279 makes, checked here every single time:
        if a.out:
            v2 = ears.utterance(os.path.expanduser(a.out))
            print("  |percept(samples) - percept(wav)| = %.3e   (ears.py:279 claim)"
                  % float(np.linalg.norm(v - v2)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
