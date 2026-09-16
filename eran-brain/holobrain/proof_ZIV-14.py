"""PROOF ZIV-14 -- 'the encoder never saw them' is only said when the checkpoint says it

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

    python proof_ZIV-14.py            # the LIVE files  -> must PASS (exit 0)
    python proof_ZIV-14.py --old      # the .bak-rev-20260906 backups -> must FAIL (exit 1)

The proof runs the CODE, not the live process: this chain has no service, no port and no
scheduler, so there is nothing running to disturb. Where the real corpus cannot be used
(eye.pt is a grayscale encoder against a colour corpus -- that IS ZIV-01) the run happens
inside proof_fixture.py's tiny matching world.
"""
import io
import os
import sys
import tempfile
import contextlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import proof_fixture as PF                                           # noqa: E402


def cap(fn, *a, **k):
    """Run fn, returning (result, exception, stdout)."""
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            return fn(*a, **k), None, buf.getvalue()
    except BaseException as e:                                       # noqa: BLE001
        return None, e, buf.getvalue()


def main():
    print("== proof ZIV-14 against %s ==" % PF.which())

    tmp = os.path.join(tempfile.gettempdir(), "ziv14")
    p = PF.build(tmp, holdout_in_eye=None, hand=False)             # eye.pt records NO holdout
    z = PF.load(PF.src("zivug.py"), "z14")
    _, e, out = cap(PF.run_main, z, PF.argv(p, "--no-hand"))
    if e is not None:
        return PF.bad("zivug did not finish: %r" % e)
    if "UNKNOWN" not in out or "ENCODER" not in out:
        return PF.bad("a checkpoint with no holdout field produced no UNKNOWN anywhere "
                      "in the report -- the claim is made regardless")
    p2 = PF.build(os.path.join(tempfile.gettempdir(), "ziv14b"), holdout_in_eye=1, hand=False)
    _, e2, out2 = cap(PF.run_main, z, PF.argv(p2, "--no-hand"))
    if e2 is not None:
        return PF.bad("second run failed: %r" % e2)
    if "1 faces, recorded in the checkpoint" not in out2:
        return PF.bad("a checkpoint that DOES record its holdout is not believed either")
    ey = PF.load(PF.src("eye.py"), "z14eye")
    if not hasattr(ey, "_fingerprint"):
        return PF.bad("eye.py writes no corpus fingerprint, so the next eye.pt will be "
                      "as uncheckable as this one")
    fp = ey._fingerprint(p["letters"])
    if "sha256_first_mb" not in fp or "shape" not in fp:
        return PF.bad("the fingerprint is empty: %r" % fp)
    esrc = io.open(PF.src("eye.py"), encoding="utf-8").read()
    if '"holdout": int(a.holdout)' not in esrc or '"corpus": _fingerprint' not in esrc:
        return PF.bad("the fingerprint exists but is not saved into eye.pt")
    print([l for l in out.splitlines() if "ENCODER" in l][0].strip())
    return PF.ok("UNKNOWN when the checkpoint is silent, the recorded number when it is "
                 "not, and eye.py now writes holdout + corpus fingerprint into eye.pt")

if __name__ == "__main__":
    raise SystemExit(main())
