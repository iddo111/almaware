"""KAV-10 proof — no refuted ruler can print a green gate from inside the organ

Run: python proofs/proof_KAV-10.py old   -> must FAIL (exit 1)
     python proofs/proof_KAV-10.py new   -> must PASS (exit 0)
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _harness


def check(organ):

    import io, subprocess, sys as _s
    bad = []
    for fn in sorted(os.listdir(organ)):
        if not fn.endswith(".py"):
            continue
        src = io.open(os.path.join(organ, fn), encoding="utf-8").read()
        if 'if __name__ == "__main__":' not in src:
            continue
        tail = src.split('if __name__ == "__main__":', 1)[1]
        refuted = ('c["watertight"] == c["tried"]' in src
                   or "c['watertight'] == c['tried']" in src)
        if refuted and "raise SystemExit" not in tail:
            bad.append(fn)
    print(f"    runnable modules in the organ dir: "
          f"{[f for f in os.listdir(organ) if f.endswith('.py')]}")
    assert not bad, (
        "%r sits in the organ's own directory and its __main__ still prints a PASSING "
        "gate 2 by the standard this project explicitly refuted (watertight only, no "
        "face count, no volume). Measured 2026-09-06 with the live ruler: the "
        "close-the-hole floor is 3/3 watertight at volume x0.167-0.300 and 0/3 right "
        "solids." % (bad,))
    leg = os.path.join(organ, "legacy")
    assert os.path.isdir(leg) and os.path.exists(os.path.join(leg, "README.md")), \
        "the retired rulers have nowhere to be, and no note saying what they measured"
    print(f"    legacy/: {sorted(os.listdir(leg))}")


_harness.run(check)
