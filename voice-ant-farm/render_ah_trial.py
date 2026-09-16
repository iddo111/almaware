# -*- coding: utf-8 -*-
"""Render every /a/ attempt to state/ah-trial/ so IDDO CAN LISTEN HIMSELF.

No number in this repository outranks his ear. The judge (ah_criterion) says
whether a sound is admissible; only Iddo says whether it is right.

Note what this file is: the WRITER lives out here, not in the mouth. mouth_v1.py
cannot open a file, which is why it can be trusted; this script can, which is why
it can never be the production module. That separation is the design, not an
inconvenience.

    python3 render_ah_trial.py
"""
from __future__ import annotations

import json
import wave
from pathlib import Path

import numpy as np

import ah_criterion as A
import glottis
import head_sim as H
import mouth_v1 as M

SR = 16000
OUT = Path(__file__).resolve().parent / "state" / "ah-trial"

# The tuned head_sim motor command, found by the same search that tuned mouth_v1.
HEAD_SIM_AH = {"breath": 0.80, "pitch": 0.46, "press": 0.8922,
               "tongue_x": 0.6133, "tongue_y": 0.2714, "lips": 1.00,
               "jaw": 1.00}


def write_wav(path, y, rate=SR):
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = (np.clip(np.asarray(y, dtype=np.float64), -1.0, 1.0) *
           32767.0).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())
    return path


def gap(seconds=0.30):
    return np.zeros(int(seconds * SR), dtype=np.float32)


def codebook():
    """The reigning queen's stored recorded frames, for gate 4b."""
    p = Path(__file__).resolve().parent / "state-hebbian" / "vowel-cochlea" / \
        "queen-ant-a" / "current.json"
    if not p.exists():
        return None
    with open(p, "r", encoding="utf-8") as fh:
        ck = json.load(fh)
    bank = ck.get("exemplars_pcm16")
    return None if bank is None else np.asarray(bank, dtype=np.float64) / 32768.0


def report(name, y, module, ck):
    v = A.judge_ah(y, SR, production_module=module, codebook=ck)
    m = v.measurements
    return {
        "file": name,
        "verdict": "PASS" if v.passed else "FAIL",
        "gates": {k: {"passed": bool(g.passed), "detail": g.detail}
                  for k, g in v.gates.items()},
        "F1_hz": round(m.get("F1", float("nan")), 1),
        "F2_hz": round(m.get("F2", float("nan")), 1),
        "mahalanobis": round(m.get("mahalanobis", float("nan")), 3),
        "nearest_vowel": m.get("nearest_vowel"),
        "bark_margin": round(m.get("bark_margin_over_runner_up",
                                   float("nan")), 3),
        "f0_hz": round(m.get("f0_hz", float("nan")), 1),
        "cv_f0": round(m.get("cv_f0", float("nan")), 4),
        "harmonics": m.get("harmonics"),
        "cv_f1": round(m.get("cv_f1", float("nan")), 4),
        "cv_f2": round(m.get("cv_f2", float("nan")), 4),
        "drift_f1_hz_s": round(m.get("drift_f1_hz_s", float("nan")), 1),
        "drift_f2_hz_s": round(m.get("drift_f2_hz_s", float("nan")), 1),
        "duration_ms": round(m.get("duration_ms", float("nan")), 1),
        "mosaic_snr_db": round(m.get("mosaic_snr_db", float("nan")), 1),
        "static_violations": m.get("static_violations", []),
    }


def main():
    ck = codebook()
    rows = []

    # 1. THE WINNER - the one to listen to first.
    y = M.articulate(seconds=1.00, seed=5, **M.AH)
    write_wav(OUT / "01-AH-mouth_v1-WINNER.wav", y)
    rows.append(report("01-AH-mouth_v1-WINNER.wav", y, M.__file__, ck))

    # 2. Same mouth, six different seeds - is it one lucky roll of the dice?
    seeds = [M.articulate(seconds=0.60, seed=s, **M.AH) for s in range(1, 7)]
    write_wav(OUT / "02-AH-mouth_v1-six-seeds.wav",
              np.concatenate([np.concatenate([s, gap(0.25)]) for s in seeds]))
    rows.append(report("02-AH-mouth_v1-six-seeds.wav", seeds[0], M.__file__, ck))

    # 3. Same tube shape, five pitches. A vowel is a SHAPE, not a pitch - if
    #    /a/ survives the pitch sweep, the identity is in the tube.
    sweep = [M.articulate(seconds=0.55, seed=2, **{**M.AH, "pitch": p})
             for p in (0.20, 0.32, 0.46, 0.60, 0.75)]
    write_wav(OUT / "03-AH-mouth_v1-pitch-sweep.wav",
              np.concatenate([np.concatenate([s, gap(0.2)]) for s in sweep]))

    # 4. The same mouth saying something that is NOT /a/, so the ear can hear
    #    that the articulators really move.
    ee = M.articulate(seconds=0.80, seed=5, **M.EE)
    write_wav(OUT / "04-NOT-AH-mouth_v1-says-ee.wav", ee)
    rows.append(report("04-NOT-AH-mouth_v1-says-ee.wav", ee, M.__file__, ck))

    # 5. head_sim, DRIVEN. Acoustically it is the best /a/ here. It cannot be
    #    crowned because `import wave` sits in its call graph.
    hs = H.synth(HEAD_SIM_AH, seconds=1.00, seed=5)
    write_wav(OUT / "05-AH-head_sim-driven-FAILS-provenance.wav", hs)
    rows.append(report("05-AH-head_sim-driven-FAILS-provenance.wav", hs,
                       "head_sim.py", ck))

    # 6. head_sim BEFORE the search - its own hand-tuned preset. The A/B that
    #    shows what driving the parameters actually bought.
    hs0 = H.synth(H.VOWELS["ah"], seconds=1.00, seed=5)
    write_wav(OUT / "06-AH-head_sim-UNTUNED-preset-for-comparison.wav", hs0)
    rows.append(report("06-AH-head_sim-UNTUNED-preset-for-comparison.wav", hs0,
                       "head_sim.py", ck))

    # 7. glottis.py - the source-filter reference. Formants typed in directly
    #    rather than emerging from a tube; the control, not a competitor.
    g = glottis.articulate_vowel(f0_hz=194.2, formants_hz=(689.0, 1464.0, 2600.0),
                                 duration_s=1.00, seed=5)
    write_wav(OUT / "07-AH-glottis-source-filter-reference.wav", g)
    rows.append(report("07-AH-glottis-source-filter-reference.wav", g,
                       glottis.__file__, ck))

    # 8. Everything in a row, for one pass of the ear.
    write_wav(OUT / "08-ALL-in-one-listen.wav", np.concatenate([
        y, gap(), hs, gap(), hs0, gap(), g, gap(), ee]))

    (OUT / "GATES.json").write_text(
        json.dumps({"rows": rows, "mouth_v1_AH": M.AH,
                    "head_sim_AH": HEAD_SIM_AH,
                    "order_in_08": ["mouth_v1 WINNER", "head_sim driven",
                                    "head_sim untuned", "glottis reference",
                                    "mouth_v1 says ee"]},
                   indent=2, ensure_ascii=False), encoding="utf-8")

    for r in rows:
        print(f"{r['verdict']:4}  {r['file']}")
        print(f"        F1={r['F1_hz']:.0f} F2={r['F2_hz']:.0f}  "
              f"MD={r['mahalanobis']}  near=/{r['nearest_vowel']}/  "
              f"f0={r['f0_hz']:.0f}  mosaic={r['mosaic_snr_db']} dB")
        for k, gt in r["gates"].items():
            print(f"        [{'ok  ' if gt['passed'] else 'FAIL'}] {k}: "
                  f"{gt['detail'][:120]}")
    print(f"\nwrote {len(list(OUT.glob('*.wav')))} wav files to {OUT}")


if __name__ == "__main__":
    main()
