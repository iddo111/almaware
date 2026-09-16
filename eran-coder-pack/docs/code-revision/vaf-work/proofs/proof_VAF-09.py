"""VAF-09 proof: something must compare the lanes.

SEARCH_LANES splits the seed space so eran2 and eran3 do not recompute
identical colonies - and then nothing ever collects the result. eran3's best
ant is 0.8439 and eran2's is 0.8692 on the SAME held-out set, and neither box
has ever known. The comparator reads; it never promotes and never writes.

FAILS on the pre-revision code, PASSES on the fixed code.
"""
import json, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import proof_common

code = proof_common.use_code(sys.argv)
checks = []
if not (code / "lanes.py").exists():
    checks.append((
        "a cross-lane comparator exists", False,
        "no lanes.py: two boxes, two answers, and no code path that compares them",
    ))
    raise SystemExit(proof_common.report("VAF-09", checks))
import lanes  # noqa: E402

tmp = Path(tempfile.mkdtemp(prefix="vaf-proof-09-"))


def queen(path: Path, namespace: str, corpus: str, errors: dict) -> None:
    (path / "queen").mkdir(parents=True)
    (path / "queen" / "current.json").write_text(json.dumps({
        "experiment_namespace": namespace,
        "corpus_manifest_sha256": corpus,
        "ants": [
            {"ant": ant, "heldout_error_after": value,
             "checkpoint_sha256": f"{ant}-sha", "evaluation": {}}
            for ant, value in errors.items()
        ],
    }), encoding="utf-8")


queen(tmp / "lane1", "92fd88c8", "corpus-1",
      {"ant-a": 0.8718, "ant-b": 0.8692, "ant-c": 0.8767, "ant-d": 0.8715})
queen(tmp / "lane2", "92fd88c8", "corpus-1",
      {"ant-a": 0.8507, "ant-b": 0.8445, "ant-c": 0.8439, "ant-d": 0.8525})
queen(tmp / "lane3", "OTHER-NAMESPACE", "corpus-2", {"ant-a": 0.10})

result = lanes.compare([("eran2", str(tmp / "lane1")), ("eran3", str(tmp / "lane2"))])
mixed = lanes.compare([("eran2", str(tmp / "lane1")), ("eran4", str(tmp / "lane3"))])
absent = lanes.compare([("eran2", str(tmp / "lane1")), ("gone", str(tmp / "nope"))])

checks = [(
    "the fleet best across lanes is named",
    result["fleet_best"]["lane"] == "eran3" and result["fleet_best"]["ant"] == "ant-c",
    f"fleet best = {result['fleet_best']['lane']}/{result['fleet_best']['ant']} "
    f"@ {result['fleet_best']['heldout_error_after']}",
), (
    "the per-lane gap is reported so the cost of not comparing is visible",
    round(result["gap_to_fleet_best"]["eran2"], 4) == 0.0253,
    f"gaps = {result['gap_to_fleet_best']}",
), (
    "lanes running a different experiment are refused, not silently ranked",
    mixed["comparable"] is False and "fleet_best" not in mixed,
    f"comparable={mixed['comparable']}: {mixed['why_not_comparable']}",
), (
    "an unreachable lane is named instead of dropped",
    absent["unreadable_lanes"] == ["gone"],
    f"unreadable={absent['unreadable_lanes']}",
), (
    "the comparator promotes nothing",
    result["claim_limit"].startswith("read-only"), result["claim_limit"],
)]

print(f"workspace: {tmp}")
raise SystemExit(proof_common.report("VAF-09", checks))
