"""VAF-08 proof: the acceptance gate must run inside the loop, not once in August.

state/acceptance-current.json was written on 2026-08-02 22:47 with overall
PARTIAL and never again; nothing in run_loop.sh, train_loop.sh, colony.py or
fire.py mentions acceptance.py. A gate that has never refused anything is not
demonstrated.

The cadence is DERIVED from the loop's own sleep (one day of cycles), and the
gate only reports: it can refuse loudly, it can never stop or restart anything,
and a crash inside it must not take the training cycle with it.

FAILS on the pre-revision code, PASSES on the fixed code.
"""
import json, os, sys, tempfile, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import proof_common

code = proof_common.use_code(sys.argv)
import colony, fire  # noqa: E402

checks = []
if not hasattr(fire, "maybe_run_acceptance"):
    checks.append((
        "the loop runs its own acceptance gate", False,
        "fire.py has no acceptance gate: the last verdict is from 2026-08-02 22:47",
    ))
    raise SystemExit(proof_common.report("VAF-08", checks))

UNITS = 16
tmp = Path(tempfile.mkdtemp(prefix="vaf-proof-08-"))
recordings = proof_common.build_project(tmp, train=6)
state = tmp / "state"
colony.train_colony(recordings, recordings / "manifest.json", state, units=UNITS)

skipped = fire.maybe_run_acceptance(tmp, state, every=5)
verdict = fire.maybe_run_acceptance(tmp, state, every=1)
report_path = state / "acceptance-current.json"

checks = [(
    "the gate runs on a cadence instead of once, and says when it is waiting",
    skipped["ran"] is False and skipped["cycles_since_run"] == 1,
    f"cycle 1 of every {skipped['every']}: ran={skipped['ran']}",
), (
    "when it runs it produces a real verdict with per-layer statuses",
    verdict["ran"] is True and "overall" in verdict
    and "2_acoustic_learner" in verdict.get("layers", {}),
    f"overall={verdict.get('overall')} layers={json.dumps(verdict.get('layers'))}",
), (
    "the verdict is written where status.sh and the next reader can find it",
    report_path.exists() and time.time() - report_path.stat().st_mtime < 120,
    f"{report_path.name} refreshed {time.time() - report_path.stat().st_mtime:.1f}s ago",
), (
    "the gate can actually refuse - layer 2 is not VERIFIED and that is reported",
    verdict["layers"]["2_acoustic_learner"] != "VERIFIED",
    f"2_acoustic_learner={verdict['layers']['2_acoustic_learner']} "
    "(the boundary/repeatability evidence has never been produced)",
)]

broken = tmp / "no-such-project"
crash = fire.maybe_run_acceptance(broken, state, every=1)
checks.append((
    "a gate that crashes reports the crash and does not take the cycle with it",
    crash.get("ran") is True and "error" in crash,
    f"error={crash.get('error', '')[:80]}",
))

print(f"workspace: {tmp}")
raise SystemExit(proof_common.report("VAF-08", checks))
