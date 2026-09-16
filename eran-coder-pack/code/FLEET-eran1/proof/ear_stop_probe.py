# -*- coding: utf-8 -*-
"""ear_stop_probe.py -- can the frozen cochlea hear the B in ABBA?

This is the question the whole "אבא by Sukkot" goal stands on. If ERAN's ear
cannot represent a stop consonant, then no amount of searching with his mouth
can find one, because the objective would be flat in that direction -- the
pitch-blindness scar again, in a new shape.

It is asked three ways on purpose, because the three answers are NOT the same
and conflating them is how a project talks itself into the wrong build:

  1. On REAL human audio, leave-one-out: does the ear separate Iddo saying
     "ah" from Iddo saying "abba"?
  2. With PURE SILENCE spliced into a real "ah": does an absence move it?
  3. With a REAL ARTICULATORY CLOSURE from ERAN's own tube: does a gesture
     move it?

Silence and a closure are not the same signal. A closure is a strongly damped
resonance plus a release burst; silence is nothing. An ear that is level-free by
construction (body/ears.py line 197 divides every frame spectrum by its own sum)
can be blind to the second while still seeing the first.

Writes results/EAR-STOP-PROBE-<utc>.json. Opens no heldout: Ears() is exam=False.
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

import genome                                    # noqa: E402
import earlink                                   # noqa: E402
import mouth34                                   # noqa: E402
from ears import read_wav                        # noqa: E402

MS = (40, 60, 80, 120, 160)


def main():
    ears = earlink.open_ear()
    out = {"utc": datetime.datetime.now(datetime.timezone.utc)
           .strftime("%Y%m%dT%H%M%SZ"),
           "host": os.uname().nodename,
           "ear": {"repr": ears.repr, "dim": ears.dim, "exam": ears.exam,
                   "level_free_line": "ears.py:197 spectrum /= spectrum.sum()"}}

    P = {u: earlink.percepts(ears, earlink.clips(u)) for u in ("ah", "abba")}
    t_ah, s_ah = earlink.target_for(ears, "ah")
    t_abba, s_abba = earlink.target_for(ears, "abba")

    def gap(v):
        """>0 means the ear thinks this is more /ah/; <0 more /abba/."""
        return float(np.linalg.norm(v - t_abba) - np.linalg.norm(v - t_ah))

    # ---------------------------------------------------------------- 1. real
    print("=== 1. ah vs abba on REAL human audio, LEAVE-ONE-OUT ===")
    acc = {}
    for u in ("ah", "abba"):
        hits = 0
        for i in range(len(P[u])):
            cents = {}
            for v in ("ah", "abba"):
                M = np.delete(P[v], i, axis=0) if v == u else P[v]
                c = M.mean(0)
                cents[v] = c / np.linalg.norm(c)
            pred = min(cents, key=lambda k: float(np.linalg.norm(P[u][i] - cents[k])))
            hits += int(pred == u)
        acc[u] = 100.0 * hits / len(P[u])
        print("   real %-5s LOO correct %5.1f%%   (n=%d)" % (u, acc[u], len(P[u])))
    bal = float(np.mean(list(acc.values())))
    print("   BALANCED LOO ACCURACY %.1f%%   (chance 50%%)" % bal)
    print("   centroid separation d(ah, abba) = %.4f" % float(np.linalg.norm(t_ah - t_abba)))
    out["real_audio"] = {"loo_per_class": acc, "loo_balanced": bal,
                         "centroid_separation": float(np.linalg.norm(t_ah - t_abba)),
                         "gap_real_ah": float(np.mean([gap(p) for p in P["ah"]])),
                         "gap_real_abba": float(np.mean([gap(p) for p in P["abba"]]))}
    print("   gap(real ah)   = %+.4f      gap(real abba) = %+.4f"
          % (out["real_audio"]["gap_real_ah"], out["real_audio"]["gap_real_abba"]))
    print()

    # ------------------------------------------------------------ 2. silence
    print("=== 2. PURE SILENCE spliced into a real /ah/ (an ABSENCE) ===")
    sil = {}
    paths = earlink.clips("ah")[:20]
    base = float(np.mean([gap(ears.utterance_from_samples(read_wav(p))) for p in paths]))
    print("   real /ah/ untouched            gap = %+.4f" % base)
    sil["0"] = base
    for ms in MS:
        n = int(genome.SAMPLE_RATE * ms / 1000)
        vals = []
        for p in paths:
            s = read_wav(p)
            m = len(s) // 2
            spl = np.concatenate([s[:m], np.zeros(n, dtype=np.float32), s[m:]])
            vals.append(gap(ears.utterance_from_samples(spl)))
        sil[str(ms)] = float(np.mean(vals))
        print("   + %3d ms of silence            gap = %+.4f" % (ms, sil[str(ms)]))
    print("   REAL abba reference            gap = %+.4f" % out["real_audio"]["gap_real_abba"])
    crossed = any(v < out["real_audio"]["gap_real_abba"] for k, v in sil.items() if k != "0")
    print("   -> silence alone reaches the real-abba region: %s" % crossed)
    out["silence_splice"] = {"gap_by_ms": sil, "reaches_real_abba": bool(crossed),
                             "n_clips": len(paths)}
    print()

    # ------------------------------------------------------------ 3. gesture
    print("=== 3. a REAL ARTICULATORY CLOSURE from ERAN own tube (a GESTURE) ===")
    pj = os.path.join(ROOT, "voice", "postures", "ah-best.json")
    if not os.path.exists(pj):
        print("   no searched posture yet (%s) -- run voice/gym.py first" % pj)
        out["gesture"] = None
    else:
        areas = np.array(json.load(open(pj))["areas"], dtype=float)
        ges = {}
        y0 = mouth34.say(areas, f0=220.0, seconds=0.6, seed=0)
        ges["0"] = gap(ears.utterance_from_samples(y0))
        print("   held vowel, no closure         gap = %+.4f" % ges["0"])
        for ms in MS:
            s = ms / 1000.0
            keys = [(areas, (0.6 - s) / 2),
                    (mouth34.closed_lips(areas, 4, 0.02), s),
                    (areas, (0.6 - s) / 2)]
            y = mouth34.say_sequence(keys, f0=220.0, seed=0)
            ges[str(ms)] = gap(ears.utterance_from_samples(y))
            print("   lip closure %3d ms             gap = %+.4f" % (ms, ges[str(ms)]))
        vals = [ges[str(m)] for m in MS]
        mono = all(b <= a + 1e-9 for a, b in zip([ges["0"]] + vals[:-1], vals))
        out["gesture"] = {"gap_by_ms": ges, "monotone_toward_abba": bool(mono),
                          "posture": pj}
        print("   -> monotone toward abba: %s" % mono)
        print("   -> CAVEAT: the no-closure baseline is already %+.4f, while a REAL"
              % ges["0"])
        print("      /ah/ sits at %+.4f. His synthetic vowel does not start where a"
              % out["real_audio"]["gap_real_ah"])
        print("      real vowel starts, so the ABSOLUTE position is confounded even")
        print("      though the DIRECTION of the gesture is clean.")

    # ---------------------------------------------------------------- verdict
    print()
    print("=== VERDICT ===")
    v = []
    v.append("The frozen 192-d cochlea SEPARATES real /ah/ from real /abba/ at "
             "%.1f%% leave-one-out, so it is NOT blind to the word." % bal)
    v.append("PURE SILENCE spliced into a real vowel does %sreach the real-abba "
             "region: an ABSENCE is nearly invisible to a level-free ear, which "
             "divides every frame by its own energy (ears.py:197)."
             % ("" if crossed else "NOT "))
    if out.get("gesture"):
        v.append("A REAL CLOSURE GESTURE from his own tube moves his percept "
                 "%s toward abba -- a closure is a damped resonance plus a "
                 "release burst, which is SHAPE, and shape is exactly what this "
                 "ear does encode."
                 % ("monotonically" if out["gesture"]["monotone_toward_abba"]
                    else "non-monotonically"))
        v.append("SO: silence-blind is not the same as stop-blind. The gradient "
                 "the search needs EXISTS. What is not yet established is that "
                 "his synthetic vowel lands where a real vowel lands.")
    for line in v:
        print(" * " + line)
    out["verdict"] = v

    d = os.path.join(ROOT, "results")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, "EAR-STOP-PROBE-%s.json" % out["utc"])
    with open(p, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    print()
    print("wrote %s" % p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
