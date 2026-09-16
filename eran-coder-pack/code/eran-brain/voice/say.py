"""say.py — CLI: the organism babbles toward a prototype from its own brain,
then writes what its mouth actually produced.

    python3 voice/say.py --target ah --gens 400

The wav is mouth.articulate() driven by whatever articulator posture
voice/babble.py's hill-climb found. Nothing is replayed, spliced, played
back, or hand-typed — no waveform bank is ever opened by this pipeline, and
nobody wrote a target formant into any file. The sidecar records the
articulator parameters, the generation count, the cosine similarity to the
target through the child's OWN frozen ear, and a plain-language provenance
line saying exactly what did and did not happen — the same honesty habit
voice/voice.py's echo-babble sidecar already keeps.

--target LABEL (default) is a CLI convenience: it asks the EXAMINER
(proof/say_judge.pick_target_prototype) which prototype index the organism's
own brain holds for that class. That is the ONLY place in this whole
pipeline a class name is used — voice/babble.py's own search loop never
receives one, only a plain vector. --target-proto N bypasses the examiner
entirely and is the fully organism-facing path.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
import time

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(ROOT, "body"))
sys.path.insert(0, os.path.join(ROOT, "proof"))
sys.path.insert(0, _HERE)

import genome                                     # noqa: E402
from brain import Brain                           # noqa: E402
from chemistry import Chemistry                   # noqa: E402
from ears import Ears, write_wav                  # noqa: E402
import babble                                      # noqa: E402
import mouth                                       # noqa: E402


def resolve_target(brain, ears, target, target_proto, train_dir=None):
    """--target-proto N: direct, no label ever touches this. --target LABEL:
    the one CLI-level import of the examiner, to turn a class name into a
    plain prototype index."""
    if target_proto is not None:
        return int(target_proto), None
    import say_judge          # the only label-aware import in this file
    idx = say_judge.pick_target_prototype(brain, ears, target, train_dir=train_dir)
    return idx, target


def main(argv=None):
    ap = argparse.ArgumentParser(description="babble toward a brain "
                                              "prototype, then say it")
    ap.add_argument("--target", default="ah",
                    help="class name the EXAMINER uses to find a prototype "
                         "(CLI convenience only; babble.py never sees it)")
    ap.add_argument("--target-proto", type=int, default=None,
                    help="direct prototype index — bypasses the examiner "
                         "entirely, no label involved")
    ap.add_argument("--gens", type=int, default=400)
    ap.add_argument("--lam", type=int, default=6)
    ap.add_argument("--seconds", type=float, default=0.32)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--brain-file", default=None)
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--no-chemistry", action="store_true")
    a = ap.parse_args(argv)

    ears = Ears()
    brain_path = a.brain_file or genome.BRAIN_FILE
    if not os.path.exists(brain_path):
        print(f"[say] no brain at {brain_path} — the organism has not lived yet.")
        return 1
    brain = Brain.load(brain_path)
    if not brain.protos:
        print("[say] the brain has no prototypes yet.")
        return 1

    idx, label_used = resolve_target(brain, ears, a.target, a.target_proto)
    if idx is None:
        print(f"[say] the organism has no prototype for '{a.target}' yet — "
              "it hasn't heard enough of that sound to have grown one.")
        return 1
    target_vec = np.asarray(brain.protos[idx]["vec"], dtype=np.float64)
    target_mass = brain.protos[idx]["mass"]

    chem = None if a.no_chemistry else Chemistry()
    seed = a.seed if a.seed is not None else genome.SEED
    log_path = os.path.join(genome.STATE_DIR, "babble.jsonl")
    os.makedirs(genome.STATE_DIR, exist_ok=True)

    print(f"[say] target: proto#{idx}"
          + (f" (examiner calls it '{label_used}', mass={target_mass:.1f})"
             if label_used else "")
          + f" | {a.gens} generations, lambda={a.lam}, {a.seconds}s")
    t0 = time.time()
    posture, sim, log = babble.babble(target_vec, ears, gens=a.gens, lam=a.lam,
                                      seconds=a.seconds, seed=seed,
                                      chemistry=chem, log_path=log_path)
    dt = time.time() - t0

    y = mouth.articulate(seconds=a.seconds, seed=seed, **posture)
    out_dir = a.out_dir or genome.OUTBOX_DIR
    os.makedirs(out_dir, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    safe_target = "".join(c for c in a.target if c.isalnum()) or "proto"
    wav_path = os.path.join(out_dir, f"say-{safe_target}-{ts}.wav")
    write_wav(wav_path, y)

    sidecar = {
        "mode": "say-v1 (mouth+babble): produced by the organism's OWN "
                "articulatory mouth, driven by articulator parameters its "
                "own babbling search found — NOT text-to-speech, NOT a "
                "replayed recording, NOT concatenated snippets. No waveform "
                "bank was ever read by voice/mouth.py or voice/babble.py.",
        "ts": ts,
        "target_prototype_index": idx,
        "target_label_used_for_lookup": label_used,
        "target_prototype_mass": round(float(target_mass), 3),
        "generations": a.gens,
        "lambda": a.lam,
        "final_cosine_sim_to_target_through_own_ear": round(sim, 5),
        "initial_cosine_sim": log[0]["best_sim"] if log else None,
        "articulator_params": {k: round(v, 4) for k, v in posture.items()},
        "seconds": a.seconds,
        "seed": seed,
        "search_seconds": round(dt, 1),
        "chemistry_used": chem is not None,
        "provenance": (
            "This wav was produced by voice/mouth.py's articulatory tube "
            "(numpy only, no file I/O — a mouth may not read files), driven "
            "by the articulator_params above. Those parameters were found "
            "by voice/babble.py's own (1+lambda) hill-climb against a "
            "percept the organism heard through its OWN frozen cochlea "
            "(body/ears.py, EAR_REPR=cochlea, Ears.utterance_from_samples — "
            "the identical code path a wav on disk would hit). The target "
            "was prototype #%d, already living in the organism's own brain "
            "(state/brain.json.gz) before this run started — nobody typed "
            "a target formant anywhere in this pipeline." % idx),
    }
    with open(wav_path.replace(".wav", ".json"), "w", encoding="utf-8") as f:
        json.dump(sidecar, f, indent=1, ensure_ascii=False)
    print(f"[say] wrote {wav_path}")
    print(f"[say] sim {sidecar['initial_cosine_sim']:.4f} -> {sim:.4f} "
          f"over {a.gens} generations ({dt:.1f}s search)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
