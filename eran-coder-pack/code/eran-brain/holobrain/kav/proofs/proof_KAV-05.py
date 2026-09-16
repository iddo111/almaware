"""KAV-05 proof — intact_only refuses an all-broken corpus instead of handing it back

Run: python proofs/proof_KAV-05.py old   -> must FAIL (exit 1)
     python proofs/proof_KAV-05.py new   -> must PASS (exit 0)
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _harness


def check(organ):

    import mesh, joiner
    corpus = mesh.our_corpus()
    broken = [(n, t) for n, t in corpus if mesh.dropped_by_grid(t) > 0]
    print(f"    feeding intact_only only the {len(broken)} grid-broken shapes: "
          f"{[n for n, _ in broken]}")
    try:
        got = joiner.intact_only(broken)
    except ValueError as e:
        print(f"    refused: {e}")
        return
    raise AssertionError(
        "intact_only returned %d shapes -> %r. A filter that can exclude everything "
        "and then quietly hands back the very shapes it was written to exclude is "
        "ERAN's empty-menu shape: no exception, no log line, a plausible accuracy out "
        "the far end." % (len(got), [n for n, _ in got]))


_harness.run(check)
