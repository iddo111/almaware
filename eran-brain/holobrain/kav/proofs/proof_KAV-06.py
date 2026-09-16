"""KAV-06 proof — gate 1's verdict reads the SEEN row, and its floor is computed on the set it judges

Run: python proofs/proof_KAV-06.py old   -> must FAIL (exit 1)
     python proofs/proof_KAV-06.py new   -> must PASS (exit 0)
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _harness


def check(organ):

    import ruler
    def row(kav, floor, err_kav=1.0, err_floor=9.0):
        names = ("KAV",) + getattr(ruler, "FLOORS",
                                   ("FLOOR_common", "FLOOR_common_train",
                                    "FLOOR_repeat", "FLOOR_phase"))
        acc = {n: floor for n in names}
        acc["KAV"] = kav
        err = {n: err_floor for n in names}
        err["KAV"] = err_kav
        return {"frames": 100, "accuracy": acc, "mean_abs_error": err,
                "hits": {n: 0 for n in names},
                "floors_used": {"common": 0, "per_phase": [0, 0, 0]},
                "by_shape": {"one": {"frames": 100, "share_of_set": 1.0,
                                     "accuracy": acc}}}
    # a model that LOSES to a constant on its own training data and wins on the sealed
    # set -- exactly what was measured on 2026-09-06 (seen 0.0601 vs 0.2093).
    r = {"seen": row(0.06, 0.21), "sealed": row(0.30, 0.05)}
    ok, lines = ruler.verdict(r)
    for ln in lines[:6]:
        print("   ", ln)
    assert not ok, ("gate 1 PASSED for a model that is 3.5x worse than a constant on "
                    "its own training data — verdict() never looks at r['seen'], which "
                    "measure() has always returned")
    src = __import__("inspect").getsource(ruler.score)
    assert "_constant_floors" in src, ("the floor is still the TRAIN set's most-common "
                                       "token applied to a set where it is rare")


_harness.run(check)
