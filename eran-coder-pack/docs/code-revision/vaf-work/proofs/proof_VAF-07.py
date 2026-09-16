"""VAF-07 proof: an ant that drops out of a colony round must be NAMED.

`if not current_path.exists(): continue` dropped an ant from the round with no
log line, no counter and no warning; the Queen then "selected" from whatever
was left and the cycle reported success. Only the fully-empty case raised.
This is the ERAN starvation shape one degree softer - it cannot silence the
whole colony, but it can silence three quarters of it invisibly.

FAILS on the pre-revision code, PASSES on the fixed code.
"""
import sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import proof_common

code = proof_common.use_code(sys.argv)
import colony  # noqa: E402

UNITS = 16
tmp = Path(tempfile.mkdtemp(prefix="vaf-proof-07-"))
recordings = proof_common.build_project(tmp, train=6)
manifest = recordings / "manifest.json"

real_train_ant = colony.train_ant
missing = {"ant-b"}


def vanishing_train_ant(*args, **kwargs):
    result = real_train_ant(*args, **kwargs)
    ant, state = args[3], Path(args[2])
    if ant in missing:
        (state / ant / "current.json").unlink(missing_ok=True)
    return result


colony.train_ant = vanishing_train_ant
queen = colony.train_colony(recordings, manifest, tmp / "state-one", units=UNITS)
present = [entry["ant"] for entry in queen["ants"]]

checks = [(
    "a silently dropped ant is named in the Queen manifest",
    queen.get("ants_skipped") == ["ant-b"],
    f"ants_skipped={queen.get('ants_skipped')!r} (old code records nothing at all)",
), (
    "the manifest carries expected-vs-present, not just the survivors",
    len(queen.get("ants_expected") or []) == 4 and queen.get("ants_present") == present,
    f"expected={queen.get('ants_expected')} present={queen.get('ants_present')}",
)]

missing = {"ant-b", "ant-c", "ant-d"}
try:
    colony.train_colony(recordings, manifest, tmp / "state-two", units=UNITS)
    checks.append((
        "a one-ant colony is refused instead of reported as a success",
        False, "train_colony returned a 'colony' of one ant and called it a round",
    ))
except ValueError as exc:
    checks.append((
        "a one-ant colony is refused instead of reported as a success",
        "too small" in str(exc), f"refused: {exc}",
    ))

print(f"workspace: {tmp}")
raise SystemExit(proof_common.report("VAF-07", checks))
