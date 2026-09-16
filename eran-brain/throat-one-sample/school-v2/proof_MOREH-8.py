"""PROOF MOREH-8 — clean() must record what it rewrote, and must not fake a mouth it does not have.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

The defect (gesture.clean):
  * an out-of-vocabulary decision was silently rewritten to the FIRST class — "AH" for knots, "seal"
    for constr, "plain" for release — so a malformed or off-box prediction became a plausible-looking
    sealed AH syllable that the judge then scored as if it were the model's real answer;
  * where mouth2 is missing (every run on the PC) knots I and U were silently rewritten to AH. `ya` is
    the one syllable whose true knots is I, so on the PC its prediction was judged as a different sound
    with no record in the spec, the fails list, or loo-results.json.

The fix: clean(spec, report=True) returns (spec, coercions) and moreh/ruler.py writes them into the LOO
JSON; the mouthless I/U branch raises instead of substituting.

    python proof_MOREH-8.py          # live gesture.py     -> must PASS
    python proof_MOREH-8.py --old    # .bak-rev-20260906   -> must FAIL
"""
import atexit
import importlib.util
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MOREH = os.path.abspath(os.path.join(HERE, "..", "..", "holobrain", "moreh"))
OLD = "--old" in sys.argv
BAK = ".bak-rev-20260906"


def load(basename, name, old):
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    path = os.path.join(HERE, basename)
    if old:
        path = os.path.join(HERE, "_probe_%s_%d.py" % (name, os.getpid()))
        shutil.copyfile(os.path.join(HERE, basename + BAK), path)
        atexit.register(lambda p=path: os.path.exists(p) and os.remove(p))
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


BASE = dict(knots="AH", constr="seal", nasal=0, voice="on", release="gap", burst=1, pre=0,
            c_pos=0.65, c_area=0.0, velum=0.0, ten=0.6, voi=1.0, d_pre=0.0, d_cons=0.09,
            d_trans=0.015, d_gap=0.04, gap_pos=0.65, gap_area=0.3, gap_voi=0.0, gap_ten=0.6,
            d_bridge=0.0, d_vowel=0.6, glide=0.35, gain=6.0, f0=105.0, trans_voi=None)


def main():
    G = load("gesture.py", "gesture_under_test", OLD)
    print("gesture under test: %s   mouth2=%r  KI=%r"
          % ("gesture.py" + BAK if OLD else "gesture.py", G.mouth2, G.KI))
    assert G.KI is None, "this proof needs a box WITHOUT the mouth; run it on the PC"

    # 1. an out-of-vocabulary decision must be reported, not swallowed
    bad = dict(BASE, constr="BOGUS", release="ALSO-BOGUS")
    try:
        s, coerced = G.clean(dict(bad), report=True)
    except TypeError as e:
        raise AssertionError("clean() cannot report its rewrites (%s): an illegal prediction becomes a "
                             "sealed plain syllable with nothing on the record" % e)
    print("clean(constr='BOGUS', release='ALSO-BOGUS') -> %s ; coercions=%s"
          % ({k: s[k] for k in ("constr", "release")}, coerced))
    assert len(coerced) == 2, coerced
    assert {c["key"] for c in coerced} == {"constr", "release"}
    assert s["constr"] == "seal" and s["release"] == "plain"
    # and the default call must still return a plain dict, so every existing caller is unchanged
    assert isinstance(G.clean(dict(BASE)), dict), "clean() broke its old single-value contract"
    print("clean(...) without report= still returns a bare dict: yes")

    # 2. a box with no mouth must refuse, not substitute AH for ya's I
    try:
        out = G.clean(dict(BASE, knots="I"))
        raise AssertionError("knots='I' was silently rewritten to %r on a box with no mouth: `ya` would "
                             "be judged as a different sound with no record anywhere" % out["knots"])
    except RuntimeError as e:
        print("knots='I' with no mouth raises: %s" % str(e)[:80])

    # 3. the consumer must keep the record
    msrc = open(os.path.join(MOREH, "ruler.py" + (BAK if OLD else "")), encoding="utf-8").read()
    assert "report=True" in msrc and "coercions" in msrc, \
        "moreh/ruler.py does not record the coercions in the LOO JSON"
    print("moreh/ruler.py writes the coercions into the LOO JSON: yes")
    print("PROOF MOREH-8 PASSED")


try:
    main()
except Exception as e:
    print("PROOF MOREH-8 FAILED: %s: %s" % (type(e).__name__, e))
    sys.exit(1)
