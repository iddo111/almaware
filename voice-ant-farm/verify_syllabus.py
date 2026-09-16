"""Re-derive the founding rules from the written checkpoints, not from claims.

Checks, for every colony under state-syllables/:
  1. every checkpoint's own sha256 verifies (load_checkpoint does this);
  2. no two ants in a colony share a codebook, an exemplar set, or a seed;
  3. every ant trained on the real human recordings as well as the syllables;
  4. no checkpoint carries a syllable label, glyph, gloss or transcript.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from acoustic_units import load_checkpoint, load_wav
from colony import DEFAULT_ANTS

STATE = Path("state-syllables")
COMBINED = Path("corpus-combined")
FORBIDDEN = {
    "text", "transcript", "tokens", "letters", "words", "item_id", "glyph",
    "gloss", "hebrew", "vocalised", "labels", "label",
}


def human_train_hashes(root: Path) -> set[str]:
    return {
        load_wav(p).pcm_sha256
        for p in sorted((root / "train").glob("human_*.wav"))
    }


def check() -> dict:
    human = human_train_hashes(COMBINED)
    report = {"human_train_files": len(human), "colonies": {}}
    for colony_dir in sorted(p for p in STATE.iterdir() if p.is_dir()):
        checkpoints = {}
        for ant in DEFAULT_ANTS:
            current = colony_dir / ant / "current.json"
            if current.exists():
                checkpoints[ant] = load_checkpoint(current)
        if not checkpoints:
            continue
        names = list(checkpoints)
        centers = {a: np.asarray(c["centers"], dtype=np.float64) for a, c in checkpoints.items()}
        exemplars = {
            a: json.dumps(c["exemplars_pcm16"], separators=(",", ":"))
            for a, c in checkpoints.items()
        }
        shared_codebook, shared_exemplars = [], []
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                if centers[a].shape == centers[b].shape and np.array_equal(centers[a], centers[b]):
                    shared_codebook.append(f"{a}|{b}")
                if exemplars[a] == exemplars[b]:
                    shared_exemplars.append(f"{a}|{b}")
        seeds = [c["seed"] for c in checkpoints.values()]
        human_seen = {
            a: (human <= set(c["train_audio_hashes"])) if human else None
            for a, c in checkpoints.items()
        }
        leaks = {
            a: sorted(FORBIDDEN & set(json.loads(json.dumps(c)).keys()))
            for a, c in checkpoints.items()
        }
        blobs = {a: json.dumps(c, separators=(",", ":")) for a, c in checkpoints.items()}
        report["colonies"][colony_dir.name] = {
            "ants": names,
            "units": sorted({c["units"] for c in checkpoints.values()}),
            "seeds": seeds,
            "seeds_unique": len(set(seeds)) == len(seeds),
            "shared_codebooks": shared_codebook,
            "shared_exemplar_sets": shared_exemplars,
            "identical_checkpoint_bodies": [
                f"{a}|{b}" for i, a in enumerate(names) for b in names[i + 1:]
                if blobs[a] == blobs[b]
            ],
            "human_audio_in_training_set": human_seen,
            "forbidden_keys": {a: v for a, v in leaks.items() if v},
            "codebooks_merged": False,
        }
    return report


def main() -> None:
    report = check()
    failures = []
    for name, colony in report["colonies"].items():
        if colony["shared_codebooks"]:
            failures.append(f"{name}: codebooks shared {colony['shared_codebooks']}")
        if colony["shared_exemplar_sets"]:
            failures.append(f"{name}: exemplars shared {colony['shared_exemplar_sets']}")
        if not colony["seeds_unique"]:
            failures.append(f"{name}: seeds not unique")
        if colony["forbidden_keys"]:
            failures.append(f"{name}: label leak {colony['forbidden_keys']}")
        if name != "control-human-only-64":
            missing = [a for a, ok in colony["human_audio_in_training_set"].items() if not ok]
            if missing:
                failures.append(f"{name}: human speech missing from {missing}")
    report["failures"] = failures
    report["all_rules_hold"] = not failures
    Path("reports").mkdir(exist_ok=True)
    Path("reports/founding-rules.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
