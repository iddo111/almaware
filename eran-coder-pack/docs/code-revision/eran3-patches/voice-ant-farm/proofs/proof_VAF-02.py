"""VAF-02 proof: the loop must SAY when its random-restart search is exhausted.

Over 2,940 cycle transitions on eran2 the colony leg (23,520 restarts) moved an
incumbent exactly twice, and every cycle still reported success. status.sh had
a flatness detector with a hand-picked `flat >= 8` that nothing ever ran.

The replacement threshold is DERIVED: the window is however many restarts this
ant actually performed in the last day. It reports and it may ask the loop to
wait longer; it never restarts, stops or signals anything.

FAILS on the pre-revision code, PASSES on the fixed code.
"""
import sys, tempfile, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import proof_common

code = proof_common.use_code(sys.argv)
import colony  # noqa: E402

checks = []
if not hasattr(colony, "search_status") or not hasattr(colony, "record_restart"):
    checks.append((
        "colony reports search exhaustion at all", False,
        "colony has no record_restart/search_status: 23,520 restarts, 2 promotions, "
        "and nothing in the code ever said so",
    ))
    raise SystemExit(proof_common.report("VAF-02", checks))

tmp = Path(tempfile.mkdtemp(prefix="vaf-proof-02-"))
state = tmp / "state"
now = time.time()

# 40 restarts in the last day, none better than the incumbent, none promoted.
for index in range(40):
    colony.record_restart(state, "ant-flat", {
        "seed": 7007 + index, "heldout_error_after": 0.95 + index * 1e-4,
        "incumbent_heldout_error": 0.8718, "promotion_eligible": False,
        "promotion_basis": "strict-heldout-improvement-over-incumbent",
    }, "colony", now=now - (86_400 * index / 40.0))
flat = colony.search_status(state, "ant-flat", now=now)

# Same shape, but one of the recent restarts actually beat the incumbent.
for index in range(40):
    promoted = index == 38
    colony.record_restart(state, "ant-live", {
        "seed": 7007 + index,
        "heldout_error_after": 0.80 if promoted else 0.95,
        "incumbent_heldout_error": 0.8718, "promotion_eligible": promoted,
        "promotion_basis": "strict-heldout-improvement-over-incumbent",
    }, "colony", now=now - (86_400 * index / 40.0))
live = colony.search_status(state, "ant-live", now=now)

# Half the restarts, spread over ten days: the window must shrink with the rate.
for index in range(40):
    colony.record_restart(state, "ant-slow", {
        "seed": 9001 + index, "heldout_error_after": 0.95,
        "incumbent_heldout_error": 0.8718, "promotion_eligible": False,
        "promotion_basis": "strict-heldout-improvement-over-incumbent",
    }, "colony", now=now - (864_000 * index / 40.0))
slow = colony.search_status(state, "ant-slow", now=now)

checks = [(
    "an exhausted search is named as exhausted",
    flat["search_exhausted"] is True,
    f"exhausted={flat['search_exhausted']} best={flat['best_in_window']:.4f} "
    f"incumbent={flat['incumbent_error']:.4f} since_promotion={flat['restarts_since_promotion']}",
), (
    "a search that is still finding things is NOT called exhausted",
    live["search_exhausted"] is False,
    f"exhausted={live['search_exhausted']} promotions_in_window={live['promotions_in_window']}",
), (
    "the window is derived from the run's own measured restart rate",
    flat["restarts_per_day_measured"] == 40 and slow["restarts_per_day_measured"] < 40
    and flat["window_restarts"] != slow["window_restarts"],
    f"fast lane {flat['restarts_per_day_measured']}/day -> window {flat['window_restarts']}; "
    f"slow lane {slow['restarts_per_day_measured']}/day -> window {slow['window_restarts']}",
), (
    "the verdict carries the numbers that justify it",
    flat["gap_best_minus_incumbent"] > 0 and flat["window_is_full"],
    f"gap={flat['gap_best_minus_incumbent']:.6f} window_is_full={flat['window_is_full']}",
)]

print(f"workspace: {tmp}")
raise SystemExit(proof_common.report("VAF-02", checks))
