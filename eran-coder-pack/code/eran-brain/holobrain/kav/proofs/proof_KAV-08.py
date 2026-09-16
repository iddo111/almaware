"""KAV-08 proof — closure says whether a shape was cut off by the budget or left open

Run: python proofs/proof_KAV-08.py old   -> must FAIL (exit 1)
     python proofs/proof_KAV-08.py new   -> must PASS (exit 0)
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _harness


def check(organ):

    import mesh, joiner
    corpus = [("drum8", mesh.prism(mesh.regular(8, 0.8), mesh.regular(8, 0.8), 0, 0.5))]
    c = joiner.closure(joiner.MirrorFloor(), corpus)
    s = c["shapes"][0]
    print("    keys:", sorted(s.keys()))
    for k in ("made", "front_left", "budget", "status", "cut_off"):
        assert k in s, (f"closure() throws away {k!r}: grow_report has always returned "
                        f"made and front_left, so a shape CUT OFF by the budget with "
                        f"its front still open is reported identically to one the "
                        f"learner genuinely left open")
    print(f"    {s['name']}: budget {s['budget']} made {s['made']} front_left "
          f"{s['front_left']} -> {s['status']}")
    assert isinstance(s["status"], str) and s["status"]
    import inspect
    assert "budget_scale" in inspect.signature(joiner.closure).parameters, \
        "the budget cannot be lifted as a diagnostic, so 'would it ever close?' " \
        "cannot be asked"


_harness.run(check)
