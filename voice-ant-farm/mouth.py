#!/usr/bin/env python3
"""A full mouth. Not a mouth that can only sing.

לזכרה של עלמה ז״ל

head_sim.py can hold a vowel. Measured: /ah/ at 641/1117 Hz against 700/1100
for a human, and a uniform tube at exactly 1:3:5. That part is right and this
file does not touch it — it imports the same tract_diameters(), so both share
one geometry and one truth about the tube.

What head_sim CANNOT do is why babbling reached only 5 of the colony's 64
units. Four things were missing, and none of them is a law of physics — they
were simply not written:

  1. MOVEMENT.  The deepest one. The colony's units are frames of a signal in
     motion. head_sim holds seven numbers frozen for half a second. A frozen
     posture can never match a transition, and most of a real voice IS
     transition. This file takes a TRAJECTORY, not a pose.

  2. CLOSURE and RELEASE.  Seal the tube, let pressure build, open it: that
     burst is a plosive. Without a true seal there is no /p/, /t/, /k/ ever.

  3. FRICATION.  Noise made AT the constriction, where fast air meets a narrow
     gap — not at the glottis. That is /s/, /sh/, /f/. head_sim only ever had
     breath noise at the source, which is a different sound entirely.

  4. VOICING as a switch.  /s/ and /z/ are the same constriction; one has the
     folds running and one does not.

Nine motors now. The first seven are head_sim's, unchanged and in the same
order, so anything learned there still means the same thing here:

    breath pitch press tongue_x tongue_y lips jaw   voice fric

    voice  0 = whispered / unvoiced, 1 = fully voiced
    fric   0 = clean, 1 = full turbulence at the narrowest point

STILL NOT TRUE, and it matters: the folds do not self-oscillate. Pitch is a
number we set, not a thing the air discovers. A physical larynx will have to
re-learn what is learned here.

    python3 mouth.py demo --out /tmp/mouth
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from head_sim import (RATE, N_SECTIONS, F0_MIN, F0_MAX, GLOTTIS_REFLECT,  # noqa: E402
                      LIP_REFLECT, tract_diameters, reflection_coefficients,
                      glottal_pulse, clamp01, write_wav)

MOTORS = ("breath", "pitch", "press", "tongue_x", "tongue_y", "lips", "jaw",
          "voice", "fric")

# Below this bore the tube is sealed: no sound leaves, pressure accumulates.
CLOSURE_MM = 0.9
# How much stored pressure a release burst converts into sound.
BURST_GAIN = 2.2


def _min_bore_index(d: np.ndarray) -> int:
    return int(np.argmin(d))


def synth_sequence(frames: list[dict], frame_seconds: float = 0.02,
                   seed: int = 0) -> np.ndarray:
    """Say a MOVING gesture. Each frame is a motor dict; the tube is re-cut
    every frame and the waveguide state carries across, so transitions are
    continuous rather than spliced."""
    rng = np.random.default_rng(seed)
    n_per = max(8, int(frame_seconds * RATE))

    b = np.zeros(N_SECTIONS)          # backward waves — this array is the delay line
    out = []
    phase = 0.0
    pressure = 0.0                    # builds while the tube is sealed

    for fi, raw in enumerate(frames):
        m = {k: clamp01(float(raw.get(k, 0.5))) for k in MOTORS}
        d = tract_diameters(m["tongue_x"], m["tongue_y"], m["lips"], m["jaw"])
        d_mm = d * 10.0
        k = reflection_coefficients(d).tolist()
        n_j = len(k)

        sealed = d_mm.min() < CLOSURE_MM
        cons = _min_bore_index(d)                 # where the air is fastest
        # Turbulence rises as the gap closes and as more air is pushed through.
        narrow = float(np.clip(1.0 - (d_mm.min() - CLOSURE_MM) / 6.0, 0.0, 1.0))
        fric_gain = 0.35 * m["fric"] * narrow * m["breath"]

        f0 = F0_MIN + (F0_MAX - F0_MIN) * m["pitch"]
        step = f0 / RATE
        buf = np.empty(n_per)

        for i in range(n_per):
            phase += step
            if phase >= 1.0:
                phase -= 1.0

            # ---- source at the glottis ----
            if m["voice"] > 0.02:
                drive = float(glottal_pulse(np.array(phase), m["press"]))
                drive *= m["breath"] * m["voice"]
            else:
                drive = 0.0
            # unvoiced air still makes a quiet hiss at the folds
            drive += 0.02 * (1.0 - m["voice"]) * m["breath"] * rng.standard_normal()

            if sealed:
                # Nothing escapes; the air keeps arriving. Store it.
                pressure = min(pressure + drive * 0.01, 1.0)
                buf[i] = 0.0
                continue

            # ---- release: the stored pressure leaves as a burst ----
            if pressure > 1e-4:
                drive += BURST_GAIN * pressure
                pressure *= 0.55                  # spends itself over a few samples

            f = drive + GLOTTIS_REFLECT * b[0]

            for j in range(n_j):
                # Frication is injected AT the constriction, not at the source.
                if fric_gain > 0.0 and j == cons:
                    f += fric_gain * rng.standard_normal()
                back = b[j + 1]
                w = k[j] * (f - back)
                b[j] = back + w
                f += w

            buf[i] = f
            b[-1] = -LIP_REFLECT * f

        out.append(buf)

    y = np.concatenate(out) if out else np.zeros(1)
    edge = min(300, len(y) // 8)
    if edge > 1:
        r = np.linspace(0.0, 1.0, edge)
        y[:edge] *= r
        y[-edge:] *= r[::-1]
    peak = float(np.max(np.abs(y)))
    if peak > 1e-6:
        y = 0.85 * y / peak
    return y.astype(np.float32)


def glide(a: dict, b: dict, n: int) -> list[dict]:
    """Interpolate between two postures. Movement is the point."""
    out = []
    for i in range(n):
        t = i / max(1, n - 1)
        out.append({k: (1 - t) * clamp01(float(a.get(k, .5))) +
                       t * clamp01(float(b.get(k, .5))) for k in MOTORS})
    return out


def hold(m: dict, n: int) -> list[dict]:
    return [dict(m) for _ in range(n)]


# Postures. Starting guesses to be tuned by ear and by measurement, not data.
AH   = {"breath": .8, "pitch": .35, "press": .55, "tongue_x": .75, "tongue_y": .15, "lips": .75, "jaw": .95, "voice": 1, "fric": 0}
EE   = {"breath": .8, "pitch": .40, "press": .60, "tongue_x": .10, "tongue_y": .90, "lips": .95, "jaw": .25, "voice": 1, "fric": 0}
OO   = {"breath": .8, "pitch": .35, "press": .60, "tongue_x": .85, "tongue_y": .80, "lips": .05, "jaw": .30, "voice": 1, "fric": 0}
SHUT = {**AH, "tongue_y": 1.0, "tongue_x": .30, "jaw": .05, "lips": .5, "voice": 0, "fric": 0}   # sealed, 0.5 mm
# A fricative is a GAP, not a seal. The first version used tongue_y .93, which
# bottoms out at the 0.5 mm floor — under CLOSURE_MM, so the tube was sealed and
# both /s/ and /z/ came out at exactly 0.0 RMS. Swept the parameter: .78 leaves
# ~1.8 mm, narrow enough to whistle and open enough to pass air.
SSS  = {**AH, "tongue_y": .78, "tongue_x": .18, "jaw": .20, "lips": .9, "voice": 0, "fric": 1}   # unvoiced hiss
ZZZ  = {**SSS, "voice": 1}                                                                       # same gap, folds on


def cmd_demo(args) -> None:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    fs = 0.02
    gap = np.zeros(int(0.25 * RATE), dtype=np.float32)

    pieces = {
        # a plosive IS a movement: seal, hold, release into a vowel
        "plosive-ta":  hold(SHUT, 8) + glide(SHUT, AH, 3) + hold(AH, 20),
        "fricative-s": hold(SSS, 30),
        "voiced-z":    hold(ZZZ, 30),
        "glide-ah-ee": hold(AH, 12) + glide(AH, EE, 14) + hold(EE, 12),
        "glide-ee-oo": hold(EE, 12) + glide(EE, OO, 14) + hold(OO, 12),
        "word-ta-ee":  hold(SHUT, 8) + glide(SHUT, EE, 3) + hold(EE, 18),
    }
    joined = []
    for name, frames in pieces.items():
        y = synth_sequence(frames, frame_seconds=fs, seed=7)
        write_wav(out / f"{name}.wav", y)
        joined.append(np.concatenate([y, gap]))
    write_wav(out / "ALL-mouth.wav", np.concatenate(joined))

    rep = {n: round(float(np.sqrt(np.mean(synth_sequence(f, fs, 7) ** 2))), 4)
           for n, f in pieces.items()}
    print(json.dumps({"motors": list(MOTORS), "frame_seconds": fs,
                      "rms_per_gesture": rep,
                      "files": sorted(p.name for p in out.glob("*.wav")),
                      "claim_limit": "parametric source, real tract; "
                                     "folds still do not self-oscillate"},
                     ensure_ascii=False))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(required=True)
    d = sub.add_parser("demo")
    d.add_argument("--out", required=True)
    d.set_defaults(fn=cmd_demo)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
