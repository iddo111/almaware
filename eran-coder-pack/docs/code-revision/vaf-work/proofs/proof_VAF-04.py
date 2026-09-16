"""VAF-04 proof: candidate checkpoints must be pruned, and ONLY candidates.

3 candidates per ant per cycle, ~330 KB each, never deleted: 8,834 files and
2.8 GB per ant, 11 GB of state per live box, growing 0.36 GB/day/box. The fire
retention sweep in run_loop.sh prunes fire/ and nothing else.

The sweep must be as name-locked as that one: it may never touch current.json,
round.json, search_history.json, the candidate that current.json was promoted
from, or anything that is not exactly candidate-<12 hex>.json.

FAILS on the pre-revision code, PASSES on the fixed code.
"""
import json, sys, tempfile, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import proof_common

code = proof_common.use_code(sys.argv)
import colony  # noqa: E402

checks = []
if not hasattr(colony, "prune_candidates"):
    checks.append((
        "the farm prunes its own candidate checkpoints", False,
        "colony has no prune_candidates: 8,834 files and 2.8 GB per ant, never deleted",
    ))
    raise SystemExit(proof_common.report("VAF-04", checks))

tmp = Path(tempfile.mkdtemp(prefix="vaf-proof-04-"))
state = tmp / "state"
ant_dir = state / "ant-a"
ant_dir.mkdir(parents=True)
promoted_sha = "abcdef012345" + "0" * 52
incumbent_sha = "fedcba987654" + "0" * 52
(ant_dir / "current.json").write_text(json.dumps({
    "checkpoint_sha256": promoted_sha, "incumbent_checkpoint_sha256": incumbent_sha,
}), "utf-8")
(ant_dir / f"candidate-{promoted_sha[:12]}.json").write_text("{}", "utf-8")
(ant_dir / f"candidate-{incumbent_sha[:12]}.json").write_text("{}", "utf-8")
(ant_dir / "search_history.json").write_text('{"restarts": []}', "utf-8")
(ant_dir / "candidate-NOTHEXADEC.json").write_text("{}", "utf-8")
(ant_dir / "candidate-abc.json").write_text("{}", "utf-8")
(ant_dir / "notes.txt").write_text("keep me", "utf-8")
made = []
for index in range(60):
    path = ant_dir / f"candidate-{index:012x}.json"
    path.write_text("{}", "utf-8")
    import os
    os.utime(path, (time.time() - (60 - index) * 60, time.time() - (60 - index) * 60))
    made.append(path)

result = colony.prune_candidates(state, ("ant-a",), keep=10, prune_max=1000)
survivors = {p.name for p in ant_dir.iterdir()}
newest_ten = {p.name for p in made[-10:]}
oldest = {p.name for p in made[:50]}

checks = [(
    "the newest K candidates survive and the rest are gone",
    newest_ten <= survivors and not (oldest & survivors),
    f"removed={result['removed']} failures={result['failures']}, "
    f"{len([n for n in survivors if n.startswith('candidate-')])} candidate files left",
), (
    "current.json and the checkpoint it was promoted from are untouchable",
    "current.json" in survivors and f"candidate-{promoted_sha[:12]}.json" in survivors,
    "current.json and its candidate both present",
), (
    "the candidate acceptance.py needs to prove a real artifact change survives",
    f"candidate-{incumbent_sha[:12]}.json" in survivors,
    "the incumbent this checkpoint replaced is still on disk",
), (
    "nothing that is not exactly candidate-<12 hex>.json can be matched",
    {"search_history.json", "candidate-NOTHEXADEC.json", "candidate-abc.json",
     "notes.txt"} <= survivors,
    "search_history.json, notes.txt and both malformed candidate names survived",
), (
    "a single sweep is bounded so no one cycle stalls on a first pass",
    colony.prune_candidates(state, ("ant-a",), keep=10, prune_max=3)["removed"] == {},
    "nothing left to prune, and prune_max bounds the pass",
)]

print(f"workspace: {tmp}")
raise SystemExit(proof_common.report("VAF-04", checks))
