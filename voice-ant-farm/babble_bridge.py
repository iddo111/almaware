#!/usr/bin/env python3
"""The bridge: the colony learns to drive the head.

לזכרה של עלמה ז״ל

Until now the two halves were dead to each other. The colony has an EAR — 64
learned sound-units taken from Iddo's real voice. mouth.py has a MOUTH — nine
muscles over a 17.1 cm tube, and unlike head_sim it can MOVE: trajectories,
closure and release, frication at the constriction, voicing as a switch.

This closes the loop the way a baby does it. Not by being told which muscle
makes which sound, and not by copying a recording: by BABBLING. Throw a random
GESTURE at the throat — a posture, a glide to a second posture, a hold —
listen to what comes out with the colony's own ear, and notice which of its
units the frames of that sound landed on. Do it thousands of times and a map
appears — unit -> the gesture that produces it.

Why gestures and not poses: the first bridge held seven numbers frozen for
half a second and reached 5 of 64 units. The colony's units are frames of a
signal in MOTION — most of a real voice is transition, and a frozen posture
cannot be a transition. So a babble here is a trajectory, and a unit is
credited to a babble when at least MIN_FRAMES of the babble's frames encode
to it — because a moving gesture legitimately passes through several units,
exactly the way real speech does. The frame count per unit is stored in the
map so the strength of each claim is auditable.

Why a gain knob exists here: both synths normalise every utterance to peak
0.85, but log-energy is the dominant axis of the ear's feature space — a
mouth that can only shout can only match loud units. The gain sampled per
babble is the loudness the normaliser stripped; on the physical rig it is
simply how hard the blower runs and how far the microphone sits. It is
recorded in the map, not hidden.

Why a tilt knob exists here, with the evidence that forced it: measured over
14,304 babbled frames, the ladder's output is spectrally FLAT (mean band
profile -1.1..-3.4), while 48 of the ear's 64 units want a steeply FALLING
spectrum (-0.75..-6.9) — real voices lose high frequencies to glottal pulse
shape, tract walls and radiation, and this ladder's boundary losses are
frequency-independent, so it cannot. With no tilt, not one unsolved unit came
within quantisation distance 2 at ANY loudness; at -12 dB/oct, 29 of 48 did.
A FIXED tilt merely trades bright units for dark ones (the 16 flat units go
out of reach), so tilt is sampled PER BABBLE, like vocal effort: soft voice
is dark, pressed voice is bright. On the rig this knob is free — real air in
a real tube does this by itself. The long-term fix belongs in mouth.py as
frequency-dependent boundary loss; until then the bridge applies it as an
output filter and records it in the map, not hidden.

Nothing here is trained on Iddo's audio. The ear was. The mouth learns only
from its own noise, judged by that ear. That is the whole idea.

What honesty requires me to say about the result:

  - A unit that no babble ever lands near stays UNSOLVED. We report those
    rather than quietly filling them with the least-bad guess, because a map
    with silent holes is worse than a map that admits them.
  - The distance we minimise is quantisation distance in the colony's feature
    space. Small distance means "the ear files this sound under that unit". It
    does NOT mean the two sound alike to you. That is a different claim and
    this file does not make it.
  - The probe_min_frame_distance table records, for EVERY unit, the closest
    any single babbled frame ever came — including units never credited. A
    unit whose probe distance is far above the solved units' distances was
    never nearly reached; that is evidence about the mouth, not noise.
  - The folds in mouth.py do not self-oscillate. Whatever is learned here is
    learned against a parametric buzz, and will need re-learning against real
    silicone folds that oscillate on their own.

    python3 babble_bridge.py babble --checkpoint state/ant-a/current.json \\
        --rounds 3000 --out bridge
    python3 babble_bridge.py speak  --bridge bridge/motor_map.json \\
        --wav recordings/heldout/x.wav --out bridge/spoken.wav
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from acoustic_units import load_checkpoint, features, encode, load_wav, write_wav_atomic  # noqa: E402
import mouth as MOUTH  # noqa: E402

MOTORS = MOUTH.MOTORS            # nine: head_sim's seven + voice + fric
GESTURE_FRAME_SECONDS = 0.02     # tract re-cut every 20 ms — articulator speed
MIN_FRAMES = 2                   # frames (10 ms hop) a unit needs before a
                                 # babble may claim it; one stray boundary
                                 # frame is not a repeatable command
TILT_FC_HZ = 400.0               # tilt corner: below this the voice is untouched
TILT_MAX_DB_OCT = 12.0           # beyond -12 dB/oct everything goes out of reach
                                 # (measured: 15 and 18 are strictly worse)


def spectral_tilt(y: np.ndarray, db_per_oct: float) -> np.ndarray:
    """High-frequency roll-off above TILT_FC_HZ, -db_per_oct dB per octave.

    First-order magnitude response applied in the frequency domain — exact,
    stateless, numpy-only. This stands in for the frequency-dependent losses
    (glottal pulse shape, tract walls, lip radiation) that the waveguide's
    frequency-INDEPENDENT boundary reflections leave out.
    """
    if db_per_oct <= 0.0:
        return y
    f = np.fft.rfftfreq(len(y), 1.0 / MOUTH.RATE)
    h = (1.0 + (f / TILT_FC_HZ) ** 2) ** (-db_per_oct / 12.0)
    return np.fft.irfft(np.fft.rfft(y) * h, len(y))


def sample_posture(rng: np.random.Generator) -> dict:
    """One random posture over all nine motors.

    voice and fric are NOT sampled uniformly: real speech mostly sits at the
    extremes (fully voiced vowel, unvoiced fricative), and a babble space
    where voice is always ~0.5 never produces a clean /s/ or a clean vowel.
    Mass at the endpoints is what lets consonant-shaped sounds happen at all.
    """
    m = {k: float(rng.uniform(0.05, 0.95)) for k in MOTORS}
    m["breath"] = float(rng.uniform(0.35, 0.95))
    r = rng.random()
    m["voice"] = 1.0 if r < 0.5 else (0.0 if r < 0.8 else float(rng.uniform(0, 1)))
    m["fric"] = 0.0 if rng.random() < 0.5 else float(rng.uniform(0.4, 1.0))
    return m


def sample_gesture(rng: np.random.Generator) -> dict:
    """A babble is a small journey: hold A, glide to B, hold B.

    With probability ~1/3, posture A is a full seal (tongue clamped, jaw
    shut) so pressure builds and releases into B — that is the only road to
    a plosive, and undirected uniform sampling almost never finds it because
    the sealed region of motor space is thin.
    """
    a, b = sample_posture(rng), sample_posture(rng)
    if rng.random() < 0.35:
        a["tongue_y"] = float(rng.uniform(0.95, 1.0))
        a["jaw"] = float(rng.uniform(0.0, 0.08))
        a["voice"] = 0.0
    return {
        "a": a, "b": b,
        "hold_a": int(rng.integers(2, 12)),
        "glide": int(rng.integers(3, 16)),
        "hold_b": int(rng.integers(4, 16)),
        # log-uniform: soft utterances are as reachable as loud ones, which
        # matters because the ear's energy axis is logarithmic too
        "gain": float(np.exp(rng.uniform(np.log(0.05), np.log(1.0)))),
        # vocal effort: 0 = bright/pressed, 12 = dark/soft. Sampled, not
        # fixed, because a fixed channel trades bright units for dark ones.
        "tilt": float(rng.uniform(0.0, TILT_MAX_DB_OCT)),
        "frame_seconds": GESTURE_FRAME_SECONDS,
    }


def render(g: dict, seed: int) -> np.ndarray | None:
    """Say the gesture. None means it was silent (e.g. sealed throughout)."""
    frames = (MOUTH.hold(g["a"], g["hold_a"])
              + MOUTH.glide(g["a"], g["b"], g["glide"])
              + MOUTH.hold(g["b"], g["hold_b"]))
    audio = MOUTH.synth_sequence(frames, frame_seconds=g["frame_seconds"], seed=seed)
    if float(np.max(np.abs(audio))) < 1e-3:
        return None                                   # silence carries nothing
    audio = spectral_tilt(audio, g.get("tilt", 0.0))
    # re-normalise after the tilt so gain keeps its meaning as peak loudness
    peak = float(np.max(np.abs(audio)))
    if peak > 1e-6:
        audio = 0.85 * audio / peak
    return audio * g["gain"]


def gesture_features(g: dict, seed: int) -> np.ndarray | None:
    """Hand the babble to the colony's ear, unchanged."""
    audio = render(g, seed)
    if audio is None:
        return None
    # features() wants the same Audio shape load_wav produces.
    class _A:                                         # minimal duck-type
        samples = audio
        rate = MOUTH.RATE
    x, _ = features(_A())
    return x if len(x) else None


def credit(x: np.ndarray, centers: np.ndarray) -> tuple[dict, np.ndarray]:
    """Which units do this babble's frames land on, and how well?

    Returns ({unit: (n_frames, mean_distance)}, min_frame_distance_per_unit).
    The per-unit minimum over ALL frames — assigned or not — feeds the
    reachability probe: it answers "how close did the mouth ever get", which
    is a different question from "what did the ear file this babble under".
    """
    d2 = ((x[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2)
    ids = d2.argmin(axis=1)
    d = np.sqrt(d2)
    out = {}
    for unit in np.unique(ids):
        sel = ids == unit
        if int(sel.sum()) >= MIN_FRAMES:
            out[int(unit)] = (int(sel.sum()), float(d[sel, unit].mean()))
    return out, d.min(axis=0)


def _round_gesture(g: dict) -> dict:
    return {
        "a": {k: round(v, 4) for k, v in g["a"].items()},
        "b": {k: round(v, 4) for k, v in g["b"].items()},
        "hold_a": g["hold_a"], "glide": g["glide"], "hold_b": g["hold_b"],
        "gain": round(g["gain"], 5),
        "tilt": round(g.get("tilt", 0.0), 3),
        "frame_seconds": g["frame_seconds"],
    }


def cmd_babble(args) -> None:
    ck = load_checkpoint(Path(args.checkpoint))
    centers = np.asarray(ck["centers"], dtype=np.float32)
    n_units = len(centers)
    rng = np.random.default_rng(args.seed)

    best: dict[int, dict] = {}
    probe = np.full(n_units, np.inf)
    silent = 0

    # --- stage 1: undirected babble. No targets, no gradients, just noise. ---
    for i in range(args.rounds):
        g = sample_gesture(rng)
        x = gesture_features(g, seed=i)
        if x is None:
            silent += 1
            continue
        hits, dmin = credit(x, centers)
        probe = np.minimum(probe, dmin)
        for unit, (n, dist) in hits.items():
            if unit not in best or dist < best[unit]["distance"]:
                best[unit] = {"gesture": g, "seed": i,
                              "distance": dist, "frames_on_unit": n}
        if args.verbose and (i + 1) % 100 == 0:
            print(f"  babble {i+1}/{args.rounds}  units reached {len(best)}/{n_units}",
                  flush=True)

    # --- stage 2: for each unit found, wiggle toward it. Still no teacher. ---
    for unit, rec in best.items():
        g, dist, nf = rec["gesture"], rec["distance"], rec["frames_on_unit"]
        seed = rec["seed"]
        step = 0.18
        for _ in range(args.refine):
            trial = {
                **g,
                "a": {k: float(np.clip(v + rng.normal(0, step), 0.0, 1.0))
                      for k, v in g["a"].items()},
                "b": {k: float(np.clip(v + rng.normal(0, step), 0.0, 1.0))
                      for k, v in g["b"].items()},
                "gain": float(np.clip(g["gain"] * np.exp(rng.normal(0, step)),
                                      0.02, 1.0)),
                "tilt": float(np.clip(g.get("tilt", 0.0) + rng.normal(0, 6 * step),
                                      0.0, TILT_MAX_DB_OCT)),
            }
            tseed = int(rng.integers(1 << 30))
            x = gesture_features(trial, seed=tseed)
            if x is None:
                continue
            hits, _ = credit(x, centers)
            if unit in hits and hits[unit][1] < dist:
                nf, dist = hits[unit]
                g, seed = trial, tseed
            else:
                step *= 0.93                       # nothing better nearby: look closer
        best[unit] = {"gesture": _round_gesture(g), "seed": seed,
                      "distance": round(dist, 5), "frames_on_unit": nf}

    unsolved = sorted(set(range(n_units)) - set(best))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "motor_map.json").write_text(json.dumps({
        "checkpoint_sha256": ck["checkpoint_sha256"],
        "units_total": n_units,
        "units_solved": len(best),
        "units_unsolved": unsolved,
        "rounds": args.rounds,
        "refine_steps": args.refine,
        "silent_babbles": silent,
        "motors": list(MOTORS),
        "min_frames_to_credit": MIN_FRAMES,
        "map": {str(u): best[u] for u in sorted(best)},
        # closest any single frame ever came, per unit — including unsolved
        # ones. inf means the unit index never even appeared; a large finite
        # value is evidence the mouth cannot make that sound, not bad luck.
        "probe_min_frame_distance": [round(float(v), 4) if np.isfinite(v) else None
                                     for v in probe],
        "claim_limit": "quantisation distance in the colony's feature space; "
                       "not a claim that these sounds resemble speech",
    }, indent=2), encoding="utf-8")

    ds = [b["distance"] for b in best.values()]
    print(json.dumps({
        "units_solved": f"{len(best)}/{n_units}",
        "unsolved": unsolved,
        "distance_best": round(min(ds), 4) if ds else None,
        "distance_median": round(float(np.median(ds)), 4) if ds else None,
        "distance_worst": round(max(ds), 4) if ds else None,
        "silent_babbles": silent,
        "out": str(out / "motor_map.json"),
    }, ensure_ascii=False))


def cmd_speak(args) -> None:
    """Hear a recording, then say it back through the throat instead of the tape.

    This is the point of the whole file. `acoustic_units synthesize` replays a
    recording out of stored waveform snippets. This drives a physical model
    with muscle commands — nothing of the original audio survives into the
    output except the SEQUENCE of units the ear picked out.

    A unit's stored gesture is longer than one output frame, and only part of
    it lands on the unit — so we re-render the gesture, re-encode it with the
    same ear, and cut the slice whose frames actually sit on the unit. The
    re-encode is cheap and keeps the slice honest instead of guessing.
    """
    bridge = json.loads(Path(args.bridge).read_text(encoding="utf-8"))
    ck = load_checkpoint(Path(args.checkpoint))
    if bridge["checkpoint_sha256"] != ck["checkpoint_sha256"]:
        raise SystemExit("this map was learned against a different brain; rebuild it")

    centers = np.asarray(ck["centers"], dtype=np.float32)
    audio = load_wav(Path(args.wav))
    x, hop_s = features(audio)
    ids = encode(x, centers)

    hop = int(MOUTH.RATE * args.frame_seconds)
    cache: dict[int, np.ndarray] = {}
    pieces, spoken, skipped = [], 0, 0
    for unit in ids[::args.stride]:
        unit = int(unit)
        rec = bridge["map"].get(str(unit))
        if rec is None:
            pieces.append(np.zeros(hop, dtype=np.float32))   # honest gap
            skipped += 1
            continue
        if unit not in cache:
            y = render(rec["gesture"], seed=rec["seed"])
            if y is None:                          # should not happen; be safe
                cache[unit] = np.zeros(hop, dtype=np.float32)
            else:
                gx, _ = features(type("_A", (), {"samples": y, "rate": MOUTH.RATE}))
                gids = encode(gx, centers)
                on = np.flatnonzero(gids == unit)
                # centre the cut on the frames the ear files under this unit
                mid = int(on.mean()) if len(on) else len(gids) // 2
                start = max(0, min(int(mid * hop_s * MOUTH.RATE), len(y) - hop))
                cache[unit] = y[start:start + hop]
        piece = cache[unit]
        pieces.append(piece if len(piece) == hop else
                      np.pad(piece, (0, hop - len(piece))))
        spoken += 1

    out = Path(args.out)
    write_wav_atomic(out, np.concatenate(pieces).astype(np.float32), MOUTH.RATE)
    print(json.dumps({
        "source": str(args.wav),
        "units_in_source": int(len(ids)),
        "frames_spoken": spoken,
        "frames_silent_unmapped": skipped,
        "seconds": round(sum(len(p) for p in pieces) / MOUTH.RATE, 2),
        "out": str(out),
        "claim_limit": "the throat says the unit sequence the ear found; "
                       "no audio from the source reaches the output",
    }, ensure_ascii=False))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(required=True)

    b = sub.add_parser("babble", help="learn which muscles make which unit")
    b.add_argument("--checkpoint", required=True)
    b.add_argument("--out", default="bridge")
    b.add_argument("--rounds", type=int, default=3000)
    b.add_argument("--refine", type=int, default=60)
    b.add_argument("--seed", type=int, default=20260808)
    b.add_argument("--verbose", action="store_true")
    b.set_defaults(fn=cmd_babble)

    s = sub.add_parser("speak", help="say a recording back through the throat")
    s.add_argument("--bridge", required=True)
    s.add_argument("--checkpoint", required=True)
    s.add_argument("--wav", required=True)
    s.add_argument("--out", default="bridge/spoken.wav")
    s.add_argument("--frame-seconds", type=float, default=0.08)
    s.add_argument("--stride", type=int, default=4)
    s.set_defaults(fn=cmd_speak)

    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
