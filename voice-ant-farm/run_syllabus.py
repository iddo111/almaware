"""Train colonies on the combined human+syllable corpus and score them honestly.

Nothing here changes the learner. colony.train_colony / acoustic_units.train_ant do
all the learning exactly as before: four independent ants, four fixed seeds, one
private codebook each, Queen selection by held-out error, no merging, no sharing.

This module only (a) points the existing trainer at the combined corpus at three
codebook sizes, and (b) measures discrimination, which quantisation error cannot.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

import discrimination as probe
from acoustic_units import dataset, load_checkpoint
from colony import DEFAULT_ANTS, DEFAULT_SEEDS, train_colony


COMBINED = Path("corpus-combined")
HUMAN = Path("recordings")
STATE = Path("state-syllables")
UNIT_SIZES = (64, 128, 256)
CONTROL = "control-human-only-64"


def train_stage(units: int, out_dir: str | None = None, recordings: Path = COMBINED) -> dict:
    state = STATE / (out_dir or str(units))
    started = time.time()
    queen = train_colony(
        recordings, recordings / "manifest.json", state,
        ants=DEFAULT_ANTS, seeds=DEFAULT_SEEDS, units=units,
    )
    return {
        "units": units,
        "state": str(state),
        "seconds": round(time.time() - started, 1),
        "colony_sha256": queen["colony_sha256"],
        "selected_ant": queen["queen_selection"]["selected_ant"],
        "codebooks_merged": queen["codebooks_merged"],
        "ants": [
            {
                "ant": a["ant"], "seed": a["seed"],
                "heldout_error_before": a["heldout_error_before"],
                "heldout_error_after": a["heldout_error_after"],
                "evaluation_error_after": a["evaluation"]["error_after"],
                "checkpoint_sha256": a["checkpoint_sha256"],
            }
            for a in queen["ants"]
        ],
    }


def probe_stage() -> dict:
    labels = probe.load_labels(COMBINED)
    print("featurising corpus once ...", flush=True)
    train_items = probe.collect(COMBINED / "train", labels, "syllable")
    held_items = probe.collect(COMBINED / "heldout", labels, "syllable")
    word_items = probe.collect(COMBINED / "evaluation", labels, "word")
    print(f"  syllables train={len(train_items)} heldout={len(held_items)} "
          f"words={len(word_items)}", flush=True)

    raw_train, raw_held = probe.zscore(
        probe.raw_descriptor(train_items), probe.raw_descriptor(held_items)
    )
    reference = {
        "syllable_heldout": probe.nn_probe(
            raw_train, [i["label"] for i in train_items],
            raw_held, [i["label"] for i in held_items], "l2",
        ),
        "words_leave_one_base_out": probe.leave_one_base_out(
            word_items,
            probe.zscore(probe.raw_descriptor(word_items),
                         probe.raw_descriptor(word_items))[0],
            "l2",
        ),
        "note": "raw 14-dim ant features, no codebook: the information a perfect "
                "codebook could preserve at most",
    }

    y_train = [i["label"] for i in train_items]
    y_held = [i["label"] for i in held_items]

    def score(centers: np.ndarray) -> dict:
        hist_train = probe.unit_descriptor(train_items, centers)
        hist_held = probe.unit_descriptor(held_items, centers)
        hist_words = probe.unit_descriptor(word_items, centers)
        q_train, q_held = probe.zscore(
            probe.quantised_descriptor(train_items, centers),
            probe.quantised_descriptor(held_items, centers),
        )
        q_words = probe.quantised_descriptor(word_items, centers)
        return {
            "syllable_heldout": probe.nn_probe(
                hist_train, y_train, hist_held, y_held, "cosine"),
            "syllable_heldout_quantised_features": probe.nn_probe(
                q_train, y_train, q_held, y_held, "l2"),
            "words_leave_one_base_out": probe.leave_one_base_out(
                word_items, hist_words, "cosine"),
            "words_quantised_features": probe.leave_one_base_out(
                word_items, probe.zscore(q_words, q_words)[0], "l2"),
            "frame_agreement_heldout": probe.frame_agreement(held_items, centers),
        }

    colonies = {}
    for name in sorted(p.name for p in STATE.iterdir() if p.is_dir()):
        colony_dir = STATE / name
        ants = {}
        for ant in DEFAULT_ANTS:
            current = colony_dir / ant / "current.json"
            if not current.exists():
                continue
            checkpoint = load_checkpoint(current)
            centers = np.asarray(checkpoint["centers"], dtype=np.float32)
            t0 = time.time()
            ants[ant] = {
                "seed": checkpoint["seed"],
                "units": checkpoint["units"],
                "checkpoint_sha256": checkpoint["checkpoint_sha256"],
                "heldout_error_before": checkpoint["heldout_error_before"],
                "heldout_error_after": checkpoint["heldout_error_after"],
                "quantisation_error_by_source": probe.split_quantisation_error(
                    COMBINED / "heldout", labels, centers,
                    np.asarray(checkpoint["baseline_center"], dtype=np.float32),
                ),
                **score(centers),
                "probe_seconds": round(time.time() - t0, 1),
            }
            print(f"  {name}/{ant}: top1={ants[ant]['syllable_heldout']['top1']:.3f} "
                  f"words={ants[ant]['words_leave_one_base_out']['top1']:.3f}", flush=True)
        if ants:
            colonies[name] = ants

    # Control: the same codebook size, same seed, but never trained. This is
    # literally fit_codebook's round-zero initialisation (random real frames), so
    # any gap is what k-means learning contributed rather than what the grid gives.
    print("scoring untrained codebooks ...", flush=True)
    train_x, _ = dataset(COMBINED / "train")
    untrained = {}
    for units in sorted({a["units"] for c in colonies.values() for a in c.values()}):
        per_ant = {}
        for ant, seed in zip(DEFAULT_ANTS, DEFAULT_SEEDS):
            rng = np.random.default_rng(seed)
            init = train_x[rng.choice(len(train_x), units, replace=False)].copy()
            per_ant[ant] = {"seed": seed, "units": units, **score(init)}
            print(f"  untrained-{units}/{ant}: "
                  f"top1={per_ant[ant]['syllable_heldout']['top1']:.3f}", flush=True)
        untrained[str(units)] = per_ant

    return {
        "reference_no_codebook": reference,
        "untrained_codebook_control": untrained,
        "colonies": colonies,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=("train", "control", "probe"), required=True)
    parser.add_argument("--units", type=int)
    parser.add_argument("--out", default="reports")
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if args.stage == "train":
        result = train_stage(args.units)
        (out / f"train-{args.units}.json").write_text(json.dumps(result, indent=2))
    elif args.stage == "control":
        result = train_stage(64, CONTROL, HUMAN)
        (out / "train-control.json").write_text(json.dumps(result, indent=2))
    else:
        result = probe_stage()
        (out / "discrimination.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2)[:2000])


if __name__ == "__main__":
    main()
