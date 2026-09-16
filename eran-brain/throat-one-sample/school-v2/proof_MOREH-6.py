"""PROOF MOREH-6 — a crash is not a verdict.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

The defect: school-v2/ruler.judge() turned ANY exception during render or measurement into an ordinary
acoustic failure (`return False, ["render error ..."]`). A broken environment therefore scored as a bad
model, with no exception and no log line. In the shipped loo-results.json three of the copy floor's 24
"failures" are crashes (KeyError: gap_level_db, KeyError: gap, ValueError: Invalid number of FFT data
points (0)), so the published floor "copy 2/24" is part crash rate. On a box with no mouth the same
trap would silently score MOREH 0/24.

The fix: judge() returns ok=None for an error (None is falsy, so `if ok:` callers are unchanged),
moreh/ruler.py counts those in their own column and refuses to publish a summary when any exist, and
moreh/ruler.py refuses to import at all where gesture.mouth2 is None.

This PC has no mouth2, so the render path raises for real — no fault injection is needed.

    python proof_MOREH-6.py          # live ruler.py       -> must PASS
    python proof_MOREH-6.py --old    # .bak-rev-20260906   -> must FAIL
"""
import atexit
import importlib.util
import os
import shutil
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
MOREH = os.path.abspath(os.path.join(HERE, "..", "..", "holobrain", "moreh"))
OLD = "--old" in sys.argv
BAK = ".bak-rev-20260906"


def load(basename, name, old):
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    path = os.path.join(HERE, basename)
    if old:
        src = path + BAK
        path = os.path.join(HERE, "_probe_%s_%d.py" % (name, os.getpid()))
        shutil.copyfile(src, path)
        atexit.register(lambda p=path: os.path.exists(p) and os.remove(p))
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


def stub(name, **attrs):
    """the 09-02 family rulers are not mirrored on the PC; judge() crashes before it reaches them"""
    m = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[name] = m
    return m


def main():
    for n in ("lips", "tip", "back", "glottal", "verify_back"):
        stub(n)
    R = load("ruler.py", "v2ruler_under_test", OLD)
    import gesture as G
    print("ruler under test: %s" % ("ruler.py" + BAK if OLD else "ruler.py"))
    print("gesture.mouth2 on this box: %r  (so every render raises for real)" % (G.mouth2,))
    assert G.mouth2 is None, "this proof needs a box WITHOUT the mouth; run it on the PC"

    spec = dict(knots="AH", constr="seal", nasal=0, voice="on", release="gap", burst=1, pre=0,
                c_pos=0.65, c_area=0.0, velum=0.0, ten=0.6, voi=1.0, d_pre=0.0, d_cons=0.09,
                d_trans=0.015, d_gap=0.04, gap_pos=0.65, gap_area=0.3, gap_voi=0.0, gap_ten=0.6,
                d_bridge=0.0, d_vowel=0.6, glide=0.35, gain=6.0, f0=105.0, trans_voi=None)
    ok, fails, brief, y = R.judge("ba", spec)
    print("judge('ba', a legal spec) on a mouthless box -> ok=%r  fails=%s" % (ok, fails[:1]))
    assert fails and "error" in fails[0], "expected a render/measure error, got %s" % (fails[:1],)
    assert ok is not False, (
        "a CRASH came back as ok=False -- indistinguishable from a bad sound, so a broken box scores "
        "as a bad model and 'copy 2/24' is part crash rate")
    assert ok is None, "an error must be its own state (None), got %r" % (ok,)
    assert not ok, "None must stay falsy so `if ok:` callers are unchanged"
    print("an error is its own state, and still falsy: yes")

    # the consumer must count them separately and refuse to publish a number that hides them
    msrc = open(os.path.join(MOREH, "ruler.py" + (BAK if OLD else "")), encoding="utf-8").read()
    assert '"error": ok is None' in msrc, "moreh/ruler.py does not record error rows"
    assert "REFUSING to publish a summary" in msrc, "moreh/ruler.py still publishes a summary over errors"
    assert 'getattr(G, "mouth2", None) is None' in msrc, \
        "moreh/ruler.py would still run mouthless and score 0/24"
    print("moreh/ruler.py: error column, no summary over errors, import-time mouth check: yes")
    print("PROOF MOREH-6 PASSED")


try:
    main()
except Exception as e:
    print("PROOF MOREH-6 FAILED: %s: %s" % (type(e).__name__, e))
    sys.exit(1)
