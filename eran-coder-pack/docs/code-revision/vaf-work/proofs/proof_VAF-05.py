"""VAF-05 proof: consecutive tribal fires must speak DIFFERENT recordings.

speak() took sources[:utterances] - the first three train wavs in filename
order - at every fire round for 31 days (2,942 rounds on eran2). The other
recordings never crossed the fire.

FAILS on the pre-revision code, PASSES on the fixed code.
"""
import json, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import proof_common

code = proof_common.use_code(sys.argv)
import colony, fire  # noqa: E402

UNITS = 16
tmp = Path(tempfile.mkdtemp(prefix="vaf-proof-05-"))
recordings = proof_common.build_project(tmp, train=6)
state, fire_root = tmp / "state", tmp / "fire"
colony.train_colony(recordings, recordings / "manifest.json", state, units=UNITS)


def hold_round(number: int) -> None:
    (state / "round.json").write_text(
        json.dumps({"round": number, "lane": 1, "seed_stride": 1000, "search_lanes": 4}),
        encoding="utf-8",
    )


hold_round(0)
first = fire.run_fire_round(state, recordings, fire_root, round_id="20260906T000010Z")
hold_round(1)
second = fire.run_fire_round(state, recordings, fire_root, round_id="20260906T000020Z")

def spoken(manifest):
    return [entry["pcm_sha256"] for entry in manifest["producers"]["ant-a"]["files"]]

def named_sources(manifest):
    return [entry.get("source") for entry in manifest["producers"]["ant-a"]["files"]]

a, b = spoken(first), spoken(second)
checks = [(
    "two consecutive fire rounds synthesize from different recordings",
    set(a).isdisjoint(b),
    f"round0 utterance hashes {[h[:8] for h in a]} vs round1 {[h[:8] for h in b]}",
), (
    "the fire manifest names which recording each utterance came from",
    all(name for name in named_sources(second)),
    f"round1 sources = {named_sources(second)}",
)]

seen = set(named_sources(first)) | set(named_sources(second))
checks.append((
    "rotation reaches recordings the old window never touched",
    len([name for name in seen if name]) > 3,
    f"{len([n for n in seen if n])} distinct recordings crossed 2 fires "
    f"(old code: always the same 3)",
))

print(f"workspace: {tmp}")
raise SystemExit(proof_common.report("VAF-05", checks))
