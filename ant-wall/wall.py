#!/usr/bin/env python3
"""The glowing Hebrew alphabet wall — a toy the ants press.

An ant presses a shape and hears a syllable. The letter's identity is NEVER
given to the ant: `press()` returns audio and nothing else. No index, no name,
no label. That keeps the colony honest to its founding rule — voice, not
letters — while giving the ants something they have never had: agency.

Why agency matters: until now sound simply arrived and the ants quantised it.
A press is an *action* whose consequence is a *sensation*, and that correlation
is the raw material Hebbian learning feeds on.

    python wall.py list
    python wall.py press --letter 0 --out heard.wav
    python wall.py explore --ant ant-b --presses 40 --out-dir sessions/
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import wave

import numpy as np

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
SYLLABLES = os.path.join(HERE, "syllables")
SR = 16000

# Display glyph + the audio file. The ant sees neither of these — only samples.
LETTERS = [
    ("א", "ah"), ("ב", "ba"), ("ג", "ga"), ("ד", "da"), ("ה", "ha"),
    ("ו", "va"), ("ז", "za"), ("ח", "kha"), ("ט", "ta"), ("י", "ya"),
    ("כ", "ka"), ("ל", "la"), ("מ", "ma"), ("נ", "na"), ("ס", "sa"),
    ("ע", "aa"), ("פ", "pa"), ("צ", "tsa"), ("ק", "qa"), ("ר", "ra"),
    ("ש", "sha"), ("ת", "tha"),
]


class WallNotBuilt(RuntimeError):
    pass


def read_wav(path: str) -> np.ndarray:
    with wave.open(path, "rb") as w:
        if w.getframerate() != SR:
            raise ValueError(f"{path}: expected {SR} Hz, got {w.getframerate()}")
        raw = w.readframes(w.getnframes())
    return np.frombuffer(raw, dtype=np.int16).astype(np.float64) / 32768.0


def write_wav(path: str, x: np.ndarray) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    pcm = np.clip(x * 32767, -32768, 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


class Wall:
    """22 pressable panels. Press one, get sound back. That is the whole API."""

    def __init__(self, syllable_dir: str = SYLLABLES) -> None:
        self.dir = syllable_dir
        missing = [
            sid for _, sid in LETTERS
            if not os.path.exists(os.path.join(syllable_dir, f"{sid}.wav"))
        ]
        if missing:
            raise WallNotBuilt(
                f"{len(missing)} syllables missing from {syllable_dir} "
                f"(e.g. {missing[:3]}). Run: python make_syllables.py"
            )
        self._audio = [read_wav(os.path.join(syllable_dir, f"{sid}.wav"))
                       for _, sid in LETTERS]

    def __len__(self) -> int:
        return len(LETTERS)

    def press(self, index: int) -> np.ndarray:
        """Press panel `index`. Returns ONLY audio — deliberately no label.

        Handing back the letter identity here is what would quietly turn this
        back into the letters farm the project rejected.
        """
        if not 0 <= index < len(LETTERS):
            raise IndexError(f"no panel {index}; wall has {len(LETTERS)}")
        return self._audio[index].copy()

    def glyph(self, index: int) -> str:
        """For the human display only. Never call this from ant code."""
        return LETTERS[index][0]


def frame_features(audio: np.ndarray, *, frame: int = 400, hop: int = 160,
                   bands: int = 12) -> np.ndarray:
    """[n_frames, 2 + bands] of log-energy, ZCR and log band energies.

    Split out of encode_with_ant so the same maths can be used to build a
    codebook in tests — otherwise "is this sound near the codebook?" cannot be
    asked without duplicating the feature extraction and grading the copy.
    """
    feats = []
    for start in range(0, max(0, audio.size - frame + 1), hop):
        seg = audio[start:start + frame]
        win = seg * np.hanning(seg.size)
        energy = np.log(np.sum(seg ** 2) + 1e-10)
        zcr = float(np.mean(np.abs(np.diff(np.sign(seg))) > 0))
        sp = np.abs(np.fft.rfft(win)) ** 2
        edges = np.linspace(0, sp.size, bands + 1).astype(int)
        band = [np.log(sp[edges[i]:edges[i + 1]].sum() + 1e-10)
                for i in range(bands)]
        feats.append(np.array([energy, zcr] + band))
    return np.array(feats) if feats else np.zeros((0, 2 + bands))


def encode_with_ant(checkpoint: str, audio: np.ndarray, *,
                    return_distances: bool = False):
    """Run audio through an ant's own codebook — what the ant 'heard'.

    With `return_distances`, also gives back the per-frame distance to the
    winning centre. The argmin already computes these; throwing them away is
    what forced `surprise()` to invent a proxy out of unit counts.
    """
    ck = json.load(open(checkpoint, encoding="utf-8"))
    centers = np.asarray(ck["centers"], dtype=np.float64)
    spec = ck["feature_spec"]
    frame = int(spec.get("frame_samples", 400))
    hop = int(spec.get("hop_samples", 160))
    bands = int(spec.get("spectral_bands", 12))

    units: list[int] = []
    dists: list[float] = []
    for feat in frame_features(audio, frame=frame, hop=hop, bands=bands):
        if feat.size != centers.shape[1]:      # tolerate spec drift
            feat = np.resize(feat, centers.shape[1])
        d2 = ((centers - feat) ** 2).sum(axis=1)
        units.append(int(np.argmin(d2)))
        dists.append(float(np.sqrt(d2.min())))
    return (units, dists) if return_distances else units


def surprise_score(checkpoint: str, audio: np.ndarray) -> float:
    """Mean distance to the nearest known unit — how alien this sounds.

    Module level, not a closure inside cmd_explore, because as a closure
    nothing could observe it: it returned `len(set(units)) / n_centers`, which
    is unit *diversity* and not a distance at all, and disagreed with this
    docstring for its whole life. Diversity grows with clip length, so the
    curiosity policy reliably picked the longest syllable and called it the
    most alien one — measured corr(duration, score) = +0.51, now -0.32. The
    argmin distances were already computed and thrown away.
    """
    _units, dists = encode_with_ant(checkpoint, audio, return_distances=True)
    if not dists:
        return 0.0
    return float(np.mean(dists))


def cmd_list(args) -> int:
    wall = Wall()
    print(f"{len(wall)} panels:")
    for i, (glyph, sid) in enumerate(LETTERS):
        dur = wall.press(i).size / SR
        print(f"  [{i:2d}] {glyph}  {sid:4s}  {dur:.2f}s")
    return 0


def cmd_press(args) -> int:
    wall = Wall()
    heard = wall.press(args.letter)
    write_wav(args.out, heard)
    print(f"pressed panel {args.letter} ({wall.glyph(args.letter)}) -> {args.out} "
          f"({heard.size / SR:.2f}s)")
    if args.ant:
        units = encode_with_ant(args.ant, heard)
        uniq = sorted(set(units))
        print(f"ant heard {len(units)} frames across {len(uniq)} distinct units: "
              f"{uniq[:12]}{'...' if len(uniq) > 12 else ''}")
    return 0


def cmd_explore(args) -> int:
    """Let an ant press panels on its own and record what it heard.

    The policy is deliberately simple: press what you understand least. The ant
    scores each panel by how poorly its current codebook reconstructs that
    sound, then presses the worst one. That is curiosity, not a curriculum —
    nobody tells it the alphabet order.
    """
    wall = Wall()
    rng = np.random.default_rng(args.seed)
    os.makedirs(args.out_dir, exist_ok=True)

    # Fail on a bad checkpoint now, not eight presses into the run.
    json.load(open(args.ant, encoding="utf-8"))

    def surprise(audio: np.ndarray) -> float:
        return surprise_score(args.ant, audio)

    # Curiosity alone is a fixed point: the codebook does not change while the
    # ant explores, so the most-surprising panel stays most surprising and the
    # ant presses it forever. Observed: 18 presses of the same panel in a row.
    # Animals solve this by habituating — a stimulus you just had is worth less.
    pressed = np.zeros(len(wall), dtype=np.float64)

    # Warmup is babble before curiosity, so it has to scale with the run. A
    # flat 8 meant `--presses 10` spent 80% of the session pressing at random
    # and exercised the curiosity policy twice — the thing the run is for.
    warmup = min(args.warmup, max(1, args.presses // 4))
    if warmup != args.warmup:
        print(f"warmup {args.warmup} -> {warmup} (capped at presses//4 so a "
              f"short run still exercises curiosity)")

    log = []
    for step in range(args.presses):
        if step < warmup:
            idx = int(rng.integers(0, len(wall)))     # babble first
            why = "random"
        else:
            scores = np.array([surprise(wall.press(i)) for i in range(len(wall))])
            scores = scores / (1.0 + args.habituation * pressed)
            idx = int(np.argmax(scores))
            why = "curiosity"
        pressed *= args.forgetting          # boredom fades; novelty returns
        pressed[idx] += 1.0
        heard = wall.press(idx)
        path = os.path.join(args.out_dir, f"press-{step:03d}.wav")
        write_wav(path, heard)
        log.append({"step": step, "panel": idx, "glyph": wall.glyph(idx),
                    "policy": why, "samples": int(heard.size), "wav": path})
        print(f"  {step:3d}  panel {idx:2d} {wall.glyph(idx)}  ({why})")

    manifest = os.path.join(args.out_dir, "session.json")
    json.dump({"ant": args.ant, "presses": args.presses, "seed": args.seed,
               "log": log}, open(manifest, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    counts = {}
    for e in log:
        counts[e["glyph"]] = counts.get(e["glyph"], 0) + 1
    print(f"\n{args.presses} presses -> {args.out_dir}")
    print("most pressed: " + ", ".join(
        f"{g}x{c}" for g, c in sorted(counts.items(), key=lambda t: -t[1])[:6]))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list").set_defaults(fn=cmd_list)

    p = sub.add_parser("press")
    p.add_argument("--letter", type=int, required=True)
    p.add_argument("--out", default="heard.wav")
    p.add_argument("--ant", help="checkpoint json; show what the ant heard")
    p.set_defaults(fn=cmd_press)

    e = sub.add_parser("explore")
    e.add_argument("--ant", required=True, help="path to an ant current.json")
    e.add_argument("--presses", type=int, default=40)
    e.add_argument("--warmup", type=int, default=8,
                   help="random presses first; capped at presses//4 so short "
                        "runs are not all babble")
    e.add_argument("--habituation", type=float, default=2.0,
                   help="how fast a repeated panel loses its appeal (0=never)")
    e.add_argument("--forgetting", type=float, default=0.85,
                   help="per-step decay of boredom; novelty returns over time")
    e.add_argument("--seed", type=int, default=0)
    e.add_argument("--out-dir", default="sessions/run")
    e.set_defaults(fn=cmd_explore)

    args = ap.parse_args(argv)
    try:
        return args.fn(args)
    except WallNotBuilt as exc:
        print(f"wall not built: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
