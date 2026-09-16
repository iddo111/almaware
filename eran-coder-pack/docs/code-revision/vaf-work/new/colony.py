"""Independent acoustic ants with held-out Queen selection and no codebook merge."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import socket
import time
from pathlib import Path

from acoustic_units import evaluate_checkpoint, load_checkpoint, train_ant, write_json_atomic
from corpus import validate_manifest


COLONY_FORMAT = 1
DEFAULT_ANTS = ("ant-a", "ant-b", "ant-c", "ant-d")
DEFAULT_SEEDS = (7007, 7019, 7039, 7057)
# Seeds move by SEED_STRIDE per round. The stride exceeds the spread of
# DEFAULT_SEEDS, so two ants can never land on the same seed in any round.
SEED_STRIDE = 1000
# Each node searches its own lane of the global seed sequence, so four nodes
# do four times the search instead of recomputing identical colonies.
SEARCH_LANES = 4
# VAF-07: a colony of one ant cannot hold a fire and its Queen "selection" is
# meaningless. Fewer than this many surviving ants is a refusal, not a round.
MIN_SURVIVING_ANTS = 2
# VAF-02: the search-exhaustion window is DERIVED from the loop's own measured
# restart rate (how many restarts this ant actually did in the last day), never
# from a hand-picked cycle count. These two only bound that derivation.
SEARCH_WINDOW_SECONDS = 86_400.0
SEARCH_WINDOW_MIN_RESTARTS = 20
SEARCH_HISTORY_MAX = 600
# VAF-04: 3 candidate checkpoints per ant per cycle were written and never
# deleted - 8,834 files and 2.8 GB per ant, 11 GB of state per box. The name
# pattern is locked exactly the way run_loop.sh locks fire round IDs, so
# current.json, round.json and search_history.json can never match it.
CANDIDATE_NAME = re.compile(r"^candidate-[0-9a-f]{12}\.json$")
CANDIDATE_KEEP_MIN = 10
CANDIDATE_KEEP_DEFAULT = 200
CANDIDATE_PRUNE_MAX_DEFAULT = 2000


def node_lane() -> int:
    """Which disjoint slice of the seed sequence this machine explores."""
    raw = os.environ.get("VAF_NODE_LANE", "").strip()
    if raw:
        return int(raw) % SEARCH_LANES
    host = socket.gethostname().encode()
    return int(hashlib.sha256(host).hexdigest(), 16) % SEARCH_LANES


def next_round(state: Path) -> int:
    """Monotonic per-node round counter, persisted beside the colony state."""
    path = Path(state) / "round.json"
    previous = -1
    if path.exists():
        try:
            previous = int(json.loads(path.read_text(encoding="utf-8"))["round"])
        except (ValueError, TypeError, KeyError, json.JSONDecodeError):
            previous = -1
    round_n = previous + 1
    Path(state).mkdir(parents=True, exist_ok=True)
    write_json_atomic(path, {
        "round": round_n,
        "lane": node_lane(),
        "seed_stride": SEED_STRIDE,
        "search_lanes": SEARCH_LANES,
    })
    return round_n


def current_round(state: Path) -> int:
    """Read the round counter WITHOUT advancing it (VAF-05 needs the number)."""
    path = Path(state) / "round.json"
    if not path.exists():
        return 0
    try:
        return int(json.loads(path.read_text(encoding="utf-8"))["round"])
    except (ValueError, TypeError, KeyError, json.JSONDecodeError, OSError):
        return 0


def record_restart(
    state: Path, ant: str, candidate: dict, leg: str, now: float | None = None,
) -> None:
    """Append one random restart to this ant's rolling search history.

    VAF-02: the colony leg moved an incumbent 2 times in 23,520 restarts and
    reported success every time. Nothing recorded that. This does.
    """
    path = Path(state) / ant / "search_history.json"
    history = []
    if path.exists():
        try:
            history = json.loads(path.read_text(encoding="utf-8")).get("restarts", [])
        except (ValueError, json.JSONDecodeError, OSError):
            history = []
    history.append({
        "t": float(now if now is not None else time.time()),
        "leg": leg,
        "seed": candidate.get("seed"),
        "error": candidate.get("heldout_error_after"),
        "incumbent_error": candidate.get("incumbent_heldout_error"),
        "promoted": bool(candidate.get("promotion_eligible")),
        "promotion_basis": candidate.get("promotion_basis"),
    })
    write_json_atomic(path, {"restarts": history[-SEARCH_HISTORY_MAX:]})


def search_status(state: Path, ant: str, leg: str = "colony", now: float | None = None) -> dict:
    """Is this ant's random-restart search still finding anything?

    The window is the number of restarts this ant actually performed in the
    last SEARCH_WINDOW_SECONDS - i.e. derived from the run's own rate - and
    never a hand-picked constant. Reports only; changes nothing.
    """
    now = time.time() if now is None else now
    path = Path(state) / ant / "search_history.json"
    restarts = []
    if path.exists():
        try:
            restarts = json.loads(path.read_text(encoding="utf-8")).get("restarts", [])
        except (ValueError, json.JSONDecodeError, OSError):
            restarts = []
    restarts = [r for r in restarts if r.get("leg") == leg and r.get("error") is not None]
    recent = [r for r in restarts if now - float(r.get("t", 0.0)) <= SEARCH_WINDOW_SECONDS]
    window = max(len(recent), SEARCH_WINDOW_MIN_RESTARTS)
    sample = restarts[-window:]
    promotions = sum(1 for r in sample if r.get("promoted"))
    since = 0
    for restart in reversed(restarts):
        if restart.get("promoted"):
            break
        since += 1
    incumbent = None
    for restart in reversed(sample):
        if restart.get("incumbent_error") is not None:
            incumbent = float(restart["incumbent_error"])
            break
    best = min((float(r["error"]) for r in sample), default=None)
    enough = len(sample) >= window
    exhausted = bool(
        enough and promotions == 0
        and best is not None and incumbent is not None and best >= incumbent
    )
    return {
        "ant": ant,
        "leg": leg,
        "restarts_recorded": len(restarts),
        "restarts_per_day_measured": len(recent),
        "window_restarts": window,
        "window_is_full": enough,
        "promotions_in_window": promotions,
        "restarts_since_promotion": since,
        "best_in_window": best,
        "incumbent_error": incumbent,
        "gap_best_minus_incumbent": (
            None if best is None or incumbent is None else best - incumbent
        ),
        "search_exhausted": exhausted,
    }


def prune_candidates(
    state: Path, ants: tuple[str, ...] = DEFAULT_ANTS + ("queen",),
    keep: int | None = None, prune_max: int | None = None,
) -> dict:
    """Keep current.json plus the newest `keep` candidates per ant.

    Deletes nothing it cannot name: only files matching CANDIDATE_NAME, only
    inside state/<ant>/, never the candidate that current.json was promoted
    from, and at most `prune_max` per ant per cycle so no single cycle stalls
    on a first sweep of 8,800 files. Any OSError is counted, never raised -
    a retention sweep must not be able to break a training cycle.
    """
    keep = int(os.environ.get("VAF_CANDIDATE_KEEP", CANDIDATE_KEEP_DEFAULT)) if keep is None else int(keep)
    keep = max(keep, CANDIDATE_KEEP_MIN)
    prune_max = (
        int(os.environ.get("VAF_CANDIDATE_PRUNE_MAX", CANDIDATE_PRUNE_MAX_DEFAULT))
        if prune_max is None else int(prune_max)
    )
    removed = {}
    failures = 0
    for ant in ants:
        folder = Path(state) / ant
        if not folder.is_dir():
            continue
        protected = set()
        current = folder / "current.json"
        if current.exists():
            try:
                promoted = json.loads(current.read_text(encoding="utf-8"))
                # acceptance.py proves a real artifact change by checking that
                # the candidate the incumbent was promoted FROM still exists.
                # Retention must never delete that evidence.
                for key in ("checkpoint_sha256", "colony_sha256",
                            "incumbent_checkpoint_sha256"):
                    sha = promoted.get(key)
                    if sha:
                        protected.add(f"candidate-{sha[:12]}.json")
            except (ValueError, json.JSONDecodeError, OSError):
                pass
        candidates = []
        for path in folder.iterdir():
            if not path.is_file() or not CANDIDATE_NAME.match(path.name):
                continue
            if path.name in protected:
                continue
            try:
                candidates.append((path.stat().st_mtime, path))
            except OSError:
                failures += 1
        candidates.sort(key=lambda item: item[0], reverse=True)
        stale = [path for _mtime, path in candidates[keep:]][:prune_max]
        count = 0
        for path in stale:
            try:
                path.unlink()
                count += 1
            except OSError:
                failures += 1
        if count:
            removed[ant] = count
    return {"kept_per_ant": keep, "removed": removed, "failures": failures}


def round_seeds(round_n: int, lane: int | None = None) -> tuple[int, ...]:
    """Random-restart seeds: a fresh k-means basin per ant, per round, per node.

    fit_codebook is a pure function of (data, seed). With a constant seed the
    colony recomputes one answer forever. Advancing the seed each round turns
    the loop into random-restart hill climbing; the existing strict held-out
    promotion guard in train_ant is what keeps only genuine improvements.
    """
    lane = node_lane() if lane is None else lane
    step = (round_n * SEARCH_LANES + lane) * SEED_STRIDE
    return tuple(base + step for base in DEFAULT_SEEDS)


def colony_digest(manifest: dict) -> str:
    payload = {k: v for k, v in manifest.items() if k != "colony_sha256"}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def train_colony(
    recordings: Path, corpus_manifest: Path, state: Path,
    ants: tuple[str, ...] = DEFAULT_ANTS, seeds: tuple[int, ...] | None = None,
    units: int = 64,
) -> dict:
    if seeds is None:
        seeds = round_seeds(next_round(Path(state)))
    if len(ants) != len(seeds) or len(set(ants)) != len(ants):
        raise ValueError("ants and unique seeds must have the same length")
    if len(set(seeds)) != len(seeds):
        raise ValueError("every ant requires an independent random seed")
    corpus = validate_manifest(corpus_manifest, recordings)
    sessions = {
        split: sorted({
            entry["session_id"] for entry in corpus["entries"] if entry["split"] == split
        })
        for split in ("train", "heldout", "evaluation")
    }
    corpus_provenance = {
        "manifest_sha256": corpus["manifest_sha256"],
        "sample_rates": corpus["sample_rates"],
        "speaker_ids": sorted({entry["speaker_id"] for entry in corpus["entries"]}),
        "sessions": sessions,
    }
    train_folder = recordings / "train"
    heldout_folder = recordings / "heldout"
    evaluation_folder = recordings / "evaluation"
    # VAF-03: the manifest is the authority on which decoded PCM is real human
    # audio. Anything else reaching an exemplar slot is synthetic.
    real_train_pcm_hashes = sorted({
        entry["pcm_sha256"] for entry in corpus["entries"] if entry["split"] == "train"
    })
    results = []
    skipped = []
    for ant, seed in zip(ants, seeds):
        candidate_checkpoint, _candidate = train_ant(
            train_folder, heldout_folder, state, ant, units, seed, corpus_provenance,
            exemplar_folder=train_folder, real_pcm_hashes=set(real_train_pcm_hashes),
        )
        record_restart(state, ant, candidate_checkpoint, "colony")
        current_path = state / ant / "current.json"
        if not current_path.exists():
            # VAF-07: a missing ant used to vanish from the round with no log
            # line, no counter and no warning, and the cycle still reported
            # success. Name it instead of swallowing it.
            skipped.append(ant)
            continue
        checkpoint = load_checkpoint(current_path)
        evaluation = evaluate_checkpoint(checkpoint, evaluation_folder)
        results.append({
            "ant": ant,
            "seed": checkpoint["seed"],
            "checkpoint": str(
                (state / ant / f"candidate-{checkpoint['checkpoint_sha256'][:12]}.json")
                .relative_to(state).as_posix()
            ),
            "checkpoint_sha256": checkpoint["checkpoint_sha256"],
            "heldout_error_before": checkpoint["heldout_error_before"],
            "heldout_error_after": checkpoint["heldout_error_after"],
            "improved_over_baseline": checkpoint["improved_over_baseline"],
            "evaluation": evaluation,
        })
    if not results:
        raise ValueError("no ant has a promoted current checkpoint")
    if len(results) < MIN_SURVIVING_ANTS:
        raise ValueError(
            f"colony too small to be a colony: {len(results)} of {len(ants)} ants present, "
            f"missing {sorted(skipped)}"
        )
    experiment_namespaces = {
        load_checkpoint(state / result["checkpoint"])["experiment_namespace"]
        for result in results
    }
    if len(experiment_namespaces) != 1:
        raise ValueError("Queen cannot compare ants from different feature/unit experiments")
    winner = min(results, key=lambda result: result["heldout_error_after"])
    queen = {
        "format_version": COLONY_FORMAT,
        "architecture": "independent-waveform-acoustic-colony",
        "corpus_manifest_sha256": corpus["manifest_sha256"],
        "experiment_namespace": next(iter(experiment_namespaces)),
        "ants": results,
        "ants_expected": list(ants),
        "ants_present": [result["ant"] for result in results],
        "ants_skipped": sorted(skipped),
        # VAF-03: published so the fire retrain can refuse a checkpoint whose
        # waveform exemplars came from synthesized audio.
        "real_train_pcm_hashes": real_train_pcm_hashes,
        "queen_selection": {
            "selected_ant": winner["ant"],
            "selected_checkpoint_sha256": winner["checkpoint_sha256"],
            "criterion": "minimum-heldout-quantization-error",
            "evaluation_was_not_used_for_selection": True,
        },
        "codebooks_merged": False,
        "unit_namespace": "checkpoint_sha256:unit_id",
        "claim_limit": "acoustic candidates and learned-exemplar reconstruction only",
    }
    queen["colony_sha256"] = colony_digest(queen)
    queen_state = state / "queen"
    queen_state.mkdir(parents=True, exist_ok=True)
    candidate = queen_state / f"candidate-{queen['colony_sha256'][:12]}.json"
    write_json_atomic(candidate, queen)
    current = queen_state / "current.json"
    existing = json.loads(current.read_text(encoding="utf-8")) if current.exists() else None
    if not existing or existing.get("colony_sha256") != queen["colony_sha256"]:
        write_json_atomic(current, queen)
    return queen


def train_command(args) -> None:
    queen = train_colony(
        Path(args.recordings), Path(args.manifest), Path(args.state),
        units=args.units,
    )
    round_state = Path(args.state) / "round.json"
    round_info = json.loads(round_state.read_text(encoding="utf-8")) if round_state.exists() else {}
    print(json.dumps({
        "round": round_info.get("round"),
        "lane": round_info.get("lane"),
        "ants_expected": queen["ants_expected"],
        "ants_present": queen["ants_present"],
        "ants_skipped": queen["ants_skipped"],
        "search_exhausted": [
            ant for ant in queen["ants_present"]
            if search_status(Path(args.state), ant)["search_exhausted"]
        ],
        "seeds_tried": list(round_seeds(round_info["round"], round_info["lane"]))
        if "round" in round_info else None,
        "seeds_holding_current": [ant["seed"] for ant in queen["ants"]],
        "heldout_error_after": {ant["ant"]: ant["heldout_error_after"] for ant in queen["ants"]},
        "colony_sha256": queen["colony_sha256"],
        "selected_ant": queen["queen_selection"]["selected_ant"],
        "selected_checkpoint_sha256": queen["queen_selection"]["selected_checkpoint_sha256"],
        "codebooks_merged": queen["codebooks_merged"],
        "claim_limit": queen["claim_limit"],
    }))


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(required=True)
    train = commands.add_parser("train")
    train.add_argument("--recordings", required=True)
    train.add_argument("--manifest", required=True)
    train.add_argument("--state", default="state")
    train.add_argument("--units", type=int, default=64)
    train.set_defaults(fn=train_command)
    args = parser.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
