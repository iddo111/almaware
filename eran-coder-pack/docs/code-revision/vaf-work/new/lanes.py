"""Read-only cross-lane comparator for the voice ant farm (VAF-09).

SEARCH_LANES splits the seed space across nodes so the boxes do not recompute
identical colonies - and then nothing ever collects the result. eran2 has been
holding a 0.8692 incumbent while eran3 holds a 0.8439 on the SAME held-out set,
and neither box has ever known. This names the fleet best.

It compares and prints. It never promotes, never copies a checkpoint and never
writes a byte - promotion across nodes must stay a deliberate, logged act, and
a checkpoint moved between boxes must first pass the VAF-03 realness guard.

    python3 lanes.py --lane local=state --lane eran3=eran3:voice-ant-farm/state
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


def read_queen(location: str) -> dict:
    """Read one lane's queen manifest, locally or over ssh (read-only `cat`)."""
    if ":" in location and not Path(location).exists():
        host, _, remote = location.partition(":")
        path = f"{remote.rstrip('/')}/queen/current.json"
        raw = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", host, "cat", "--", path],
            capture_output=True, text=True, timeout=60, check=True,
        ).stdout
        return json.loads(raw)
    return json.loads((Path(location) / "queen" / "current.json").read_text(encoding="utf-8"))


def lane_summary(name: str, location: str) -> dict:
    try:
        queen = read_queen(location)
    except Exception as exc:
        return {"lane": name, "location": location, "error": f"{type(exc).__name__}: {exc}"}
    ants = queen.get("ants") or []
    if not ants:
        return {"lane": name, "location": location, "error": "queen has no ants"}
    best = min(ants, key=lambda ant: ant["heldout_error_after"])
    # The queen records no held-out hashes, so the corpus manifest hash plus
    # the experiment namespace are what make two lanes' numbers the same number.
    evaluation = (best.get("evaluation") or {}).get("evaluation_audio_hashes")
    return {
        "lane": name,
        "location": location,
        "experiment_namespace": queen.get("experiment_namespace"),
        "corpus_manifest_sha256": queen.get("corpus_manifest_sha256"),
        "best_ant": best["ant"],
        "best_heldout_error_after": best["heldout_error_after"],
        "best_checkpoint_sha256": best["checkpoint_sha256"],
        "ants": {ant["ant"]: ant["heldout_error_after"] for ant in ants},
        "ants_skipped": queen.get("ants_skipped", []),
        "evaluation_audio_hashes": sorted(evaluation) if evaluation else None,
    }


def compare(lanes: list[tuple[str, str]]) -> dict:
    summaries = [lane_summary(name, location) for name, location in lanes]
    usable = [item for item in summaries if "error" not in item]
    namespaces = {item["experiment_namespace"] for item in usable}
    corpora = {item["corpus_manifest_sha256"] for item in usable}
    comparable = len(namespaces) <= 1 and len(corpora) <= 1
    result = {
        "lanes": summaries,
        "unreadable_lanes": [item["lane"] for item in summaries if "error" in item],
        "comparable": comparable,
        "why_not_comparable": None if comparable else (
            "lanes disagree on experiment_namespace or corpus_manifest_sha256; "
            "their held-out errors are not the same number"
        ),
        "claim_limit": "read-only comparison; no checkpoint is promoted across nodes",
    }
    if usable and comparable:
        winner = min(usable, key=lambda item: item["best_heldout_error_after"])
        result["fleet_best"] = {
            "lane": winner["lane"],
            "ant": winner["best_ant"],
            "heldout_error_after": winner["best_heldout_error_after"],
            "checkpoint_sha256": winner["best_checkpoint_sha256"],
        }
        result["gap_to_fleet_best"] = {
            item["lane"]: round(
                item["best_heldout_error_after"] - winner["best_heldout_error_after"], 9
            )
            for item in usable
        }
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--lane", action="append", required=True,
        help="NAME=LOCATION, where LOCATION is a state dir or host:state-dir",
    )
    args = parser.parse_args()
    lanes = []
    for raw in args.lane:
        name, _, location = raw.partition("=")
        lanes.append((name, location or name))
    print(json.dumps(compare(lanes), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
