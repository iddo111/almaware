#!/usr/bin/env python3
"""A talking head Eran can learn to drive. Software first, body later.

The physical rig in docs/TALKING_HEAD_ANT_ARCHITECTURE.md needs a blower, cast
silicone folds, actuators and a safety MCU. This is that instrument in numpy,
with the same control surface, so a learner can babble a few hundred thousand
times before anything is fabricated — and so the motor commands it learns mean
the same thing when the hardware exists.

Physics, honestly labelled:

  source  A parametric glottal flow pulse (Rosenberg-style), NOT a self
          oscillating two-mass model. Pitch, loudness and how hard the folds
          are pressed together are parameters we set, not results the air
          produces. The real folds self-oscillate; these do not. That is the
          single largest gap between this and the rig.

  tract   A Kelly-Lochbaum waveguide ladder — the honest part. A tube cut into
          16 sections, each with a diameter. Sound reflects wherever the
          diameter changes, and the pattern of reflections IS the vowel. This
          is real acoustics, not a filter bank pretending. Each section is
          half a sample of travel each way, so 16 sections at 16 kHz make a
          17.1 cm tube — adult-vocal-tract length, by construction.

So: a fake buzz through a real tube. Vowel identity comes from the tube, which
is exactly the part the learner has to solve, so the gap is in the right place.

Motor command — seven numbers, every one in 0..1, matching the rig's actuators:

    breath      blower / subglottal pressure     (silence below ~0.05)
    pitch       fold tension -> f0, 70..320 Hz
    press       adduction; breathy .. pressed
    tongue_x    front .. back
    tongue_y    low .. high
    lips        rounded .. spread
    jaw         closed .. open

    python3 head_sim.py demo   --out /tmp/head     # vowels + a pitch sweep
    python3 head_sim.py babble --n 8 --out /tmp/head
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

RATE = 16_000          # matches the colony's exemplar_rate exactly

# Each waveguide section is c/(2*RATE) = 1.07 cm of tube (half a sample of
# travel in each direction). 16 sections * 1.07 cm = 17.1 cm — an adult vocal
# tract. The old value of 44 made a 47 cm tube; a corridor, not a mouth.
N_SECTIONS = 16
MOTORS = ("breath", "pitch", "press", "tongue_x", "tongue_y", "lips", "jaw")

F0_MIN, F0_MAX = 70.0, 320.0
GLOTTIS_REFLECT = 0.95  # closed end: reflects in phase, a little loss
LIP_REFLECT = 0.85      # open end: radiation, most escapes, some reflects inverted


def clamp01(x: float) -> float:
    return float(min(1.0, max(0.0, x)))


def tract_diameters(tongue_x: float, tongue_y: float, lips: float, jaw: float) -> np.ndarray:
    """Turn four articulator numbers into the bore of the tube, in cm.

    Section 0 is the glottis, section 43 is the lips. A tongue hump is a local
    narrowing whose position along the tube is tongue_x and whose depth is
    tongue_y — that pairing is what separates /i/ from /a/ from /u/. The jaw
    opens the whole oral half; the lips set the final aperture.
    """
    d = np.full(N_SECTIONS, 1.8, dtype=np.float64)
    pos = np.arange(N_SECTIONS) / (N_SECTIONS - 1)   # 0 = glottis, 1 = lips

    # Pharynx stays fairly open; the mouth half responds to the jaw.
    d[pos >= 0.5] = 1.2 + 1.4 * jaw

    # Tongue hump: a Gaussian constriction. Front (x=0) sits near the lips.
    # Positions are fractions of tube length, so this survives N changing.
    centre = 0.82 - 0.55 * tongue_x
    width = 0.16
    depth = 0.25 + 1.35 * tongue_y          # higher tongue -> tighter
    bump = depth * np.exp(-0.5 * ((pos - centre) / width) ** 2)
    d = d - bump

    # Lip aperture: rounded (0) pinches the last couple of sections hard.
    d[-2:] *= 0.25 + 0.75 * lips

    # A tube that closes completely stops being a tube.
    return np.maximum(d, 0.05)


def reflection_coefficients(d: np.ndarray) -> np.ndarray:
    """Kelly-Lochbaum: at every junction, area mismatch reflects the wave."""
    a = d ** 2                                   # area goes as diameter squared
    return (a[:-1] - a[1:]) / np.maximum(a[:-1] + a[1:], 1e-9)


def glottal_pulse(phase: np.ndarray, press: float) -> np.ndarray:
    """One period of glottal flow, shaped by how hard the folds are pressed.

    Pressed voice closes fast and hard -> a sharp pulse, rich in harmonics.
    Breathy voice barely closes -> nearly a sine, plus turbulence noise.
    """
    open_q = 0.75 - 0.35 * press                 # open fraction of the cycle
    p = np.clip(phase / max(open_q, 1e-3), 0.0, 1.0)
    return np.where(phase < open_q, 3.0 * p ** 2 - 2.0 * p ** 3, 0.0)


def _run_tract(source: np.ndarray, d: np.ndarray) -> np.ndarray:
    """Push a source signal through the Kelly-Lochbaum ladder. The real physics.

    Each section is half a sample of travel in each direction, so a round trip
    through one section costs exactly one sample — that is what makes a section
    c/(2*RATE) = 1.07 cm long. The half-sample delays are commuted into the
    backward path (a standard, exact rearrangement): the forward wave sweeps
    glottis-to-lips within the sample, the backward wave crawls one section per
    sample. Loop resonances come out identical to the textbook ladder.

    At each junction j (pressure waves, k from reflection_coefficients):
        w = k[j] * (f - b[j+1]);  onward f += w;  returning b[j] = b[j+1] + w
    Boundaries: glottis is nearly closed (reflects in phase, +GLOTTIS_REFLECT),
    lips are open (reflects inverted, -LIP_REFLECT). Closed-open means a
    uniform tube must resonate at odd multiples of RATE/(2*N_SECTIONS) — the
    1:3:5 quarter-wave series. That is the test that caught the old version,
    which took a full sample per section per direction and behaved as 91 cm.

    Plain-Python inner loop on purpose: 15 junctions of float arithmetic per
    sample beat numpy's per-call overhead at this array size.
    """
    k = reflection_coefficients(d).tolist()
    n_junctions = len(k)
    b = [0.0] * N_SECTIONS          # backward waves; this list IS the delay line
    out = np.empty(len(source))
    for i, s in enumerate(source.tolist()):
        f = s + GLOTTIS_REFLECT * b[0]
        for j in range(n_junctions):
            back = b[j + 1]
            w = k[j] * (f - back)
            b[j] = back + w          # transmitted + reflected, heading back
            f += w                   # transmitted + reflected, heading on
        out[i] = f                   # what leaves the lips
        b[-1] = -LIP_REFLECT * f     # radiation reflects, inverted
    return out


def synth(motor: dict, seconds: float = 0.6, seed: int = 0) -> np.ndarray:
    """Run the head for `seconds` and return what a microphone at the lips hears."""
    rng = np.random.default_rng(seed)
    m = {k: clamp01(float(motor.get(k, 0.5))) for k in MOTORS}

    if m["breath"] < 0.05:                       # no air, no sound. Correct.
        return np.zeros(int(seconds * RATE), dtype=np.float32)

    d = tract_diameters(m["tongue_x"], m["tongue_y"], m["lips"], m["jaw"])

    n = int(seconds * RATE)
    f0 = F0_MIN + (F0_MAX - F0_MIN) * m["pitch"]

    # The whole source can be built up front; only the tube needs a time loop.
    phase = (np.arange(1, n + 1) * (f0 / RATE)) % 1.0
    drive = glottal_pulse(phase, m["press"]) * m["breath"]

    # Breathiness injects turbulence; pressed voice injects almost none.
    noise_gain = 0.05 * (1.0 - m["press"]) * m["breath"]
    source = drive + noise_gain * rng.standard_normal(n)

    out = _run_tract(source, d)

    # De-click the ends and normalise to a sane level.
    edge = min(400, n // 8)
    if edge > 1:
        ramp = np.linspace(0.0, 1.0, edge)
        out[:edge] *= ramp
        out[-edge:] *= ramp[::-1]
    peak = float(np.max(np.abs(out)))
    if peak > 1e-6:
        out = 0.85 * out / peak
    return out.astype(np.float32)


def write_wav(path: Path, samples: np.ndarray) -> None:
    import wave
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = np.clip(samples, -1.0, 1.0)
    pcm = (pcm * 32767.0).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm.tobytes())


# Articulator settings for five vowels, tuned against the measured resonances
# of this ladder (impulse-response FFT of the actual tract, grid search on the
# four articulators). Tract resonances landed at, vs targets in parentheses:
#   ah 665/1113 (700/1100)   ee 296/2116 (300/2200)   oo 324/805 (320/800)
#   eh 514/1619 (550/1800)   oh 495/904  (500/900)
# eh is the honest miss: this area function cannot push F2 past ~1650 with F1
# held near 550, so eh sits a little dark. Everything else is within a few %.
VOWELS = {
    "ah": {"breath": .8, "pitch": .35, "press": .55, "tongue_x": 1.0, "tongue_y": .55, "lips": .90, "jaw": 1.0},
    "ee": {"breath": .8, "pitch": .40, "press": .60, "tongue_x": .35, "tongue_y": .95, "lips": 1.0, "jaw": .60},
    "oo": {"breath": .8, "pitch": .35, "press": .60, "tongue_x": .80, "tongue_y": .90, "lips": .30, "jaw": .50},
    "eh": {"breath": .8, "pitch": .35, "press": .55, "tongue_x": .30, "tongue_y": .65, "lips": 1.0, "jaw": 1.0},
    "oh": {"breath": .8, "pitch": .32, "press": .55, "tongue_x": .80, "tongue_y": .60, "lips": .40, "jaw": 1.0},
}


def cmd_demo(args) -> None:
    out = Path(args.out)
    gap = np.zeros(int(0.25 * RATE), dtype=np.float32)
    pieces = []
    for name, motor in VOWELS.items():
        y = synth(motor, seconds=0.9)
        write_wav(out / f"vowel-{name}.wav", y)
        pieces.append(np.concatenate([y, gap]))
    write_wav(out / "ALL-vowels.wav", np.concatenate(pieces))

    # A pitch sweep on /ah/ — proves the source is really driving the tube.
    sweep = [synth({**VOWELS["ah"], "pitch": p}, seconds=0.35)
             for p in np.linspace(0.05, 0.95, 8)]
    write_wav(out / "AH-pitch-sweep.wav", np.concatenate(sweep))

    print(json.dumps({
        "rate": RATE, "sections": N_SECTIONS, "motors": list(MOTORS),
        "files": sorted(p.name for p in out.glob("*.wav")),
        "claim_limit": "parametric glottal source + Kelly-Lochbaum tract; "
                       "the folds do not self-oscillate",
    }, ensure_ascii=False))


def cmd_babble(args) -> None:
    """Random motor commands. This is what the learner will search over."""
    rng = np.random.default_rng(args.seed)
    out = Path(args.out) / "babble"
    rows = []
    for i in range(args.n):
        motor = {k: float(rng.uniform(0.15, 0.95)) for k in MOTORS}
        motor["breath"] = float(rng.uniform(0.4, 0.95))   # keep it audible
        y = synth(motor, seconds=0.5, seed=i)
        name = f"babble-{i:03d}.wav"
        write_wav(out / name, y)
        rows.append({"file": name, "motor": {k: round(v, 3) for k, v in motor.items()},
                     "rms": round(float(np.sqrt(np.mean(y * y))), 4)})
    (out / "babble.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(json.dumps({"babbles": len(rows), "dir": str(out)}, ensure_ascii=False))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(required=True)
    d = sub.add_parser("demo"); d.add_argument("--out", required=True); d.set_defaults(fn=cmd_demo)
    b = sub.add_parser("babble"); b.add_argument("--out", required=True)
    b.add_argument("--n", type=int, default=8); b.add_argument("--seed", type=int, default=7)
    b.set_defaults(fn=cmd_babble)
    a = ap.parse_args(); a.fn(a)


if __name__ == "__main__":
    main()
