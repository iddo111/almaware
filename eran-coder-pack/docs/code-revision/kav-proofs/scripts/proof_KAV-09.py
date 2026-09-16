"""KAV-09 proof — a question the grammar cannot reach costs the model instead of shrinking the denominator

Run: python proofs/proof_KAV-09.py old   -> must FAIL (exit 1)
     python proofs/proof_KAV-09.py new   -> must PASS (exit 0)
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _harness


def check(organ):

    import mesh, joiner
    tris = mesh.prism(mesh.regular(12, 0.6), mesh.regular(12, 0.6), 0, 2.0)
    table, faces = mesh.table_and_faces(tris)
    steps = sum(1 for _ in joiner.walk(table.astype(float), faces))
    d = list(joiner.step_of.__defaults__)
    d[0] = 4                       # NEAR = 4: most true corners fall outside the reach
    joiner.step_of.__defaults__ = tuple(d)
    sc = joiner.score({"m": joiner.MirrorFloor()}, [("drum12", tris)])
    print(f"    the truth's walk asks {steps} questions; NEAR=4 puts "
          f"{sc['beyond_reach']} of them beyond reach")
    print(f"    scored denominator = {sc['frames']}, accuracy {sc['accuracy']['m']:.4f}")
    assert sc["beyond_reach"] > 0, "the probe did not make any question unreachable"
    assert sc["frames"] == steps, (
        "beyond-reach questions are dropped from the DENOMINATOR (%d scored of %d "
        "asked), so accuracy goes UP as the grammar's reach gets WORSE"
        % (sc["frames"], steps))


_harness.run(check)
