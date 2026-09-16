"""PROOF ZIV-11 -- a missing WINSTON is a refusal, not a shorter report

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

    python proof_ZIV-11.py            # the LIVE files  -> must PASS (exit 0)
    python proof_ZIV-11.py --old      # the .bak-rev-20260906 backups -> must FAIL (exit 1)

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
    print("== proof ZIV-11 against %s ==" % PF.which())

    tmp = os.path.join(tempfile.gettempdir(), "ziv11")
    p = PF.build(tmp, hand=False)
    z = PF.load(PF.src("zivug.py"), "z11")
    rc, e, out = cap(PF.run_main, z, PF.argv(p))
    if e is None:
        return PF.bad("hand.pt is absent and the run finished (exit %r) with the whole "
                      "WINSTON claim silently missing from the report" % rc)
    if "hand.pt" not in str(e):
        return PF.bad("it failed, but not about the hand: %r" % e)
    p2 = PF.build(os.path.join(tempfile.gettempdir(), "ziv11b"), hand=True)
    rc2, e2, out2 = cap(PF.run_main, z, PF.argv(p2, "--no-hand"))
    if e2 is not None:
        return PF.bad("--no-hand did not work: %r" % e2)
    import json
    j = json.load(open(os.path.join(p2["out"], "zivug.json")))
    if not str(j.get("winston", "")).startswith("SKIPPED"):
        return PF.bad("a deliberate skip is recorded as %r, not as SKIPPED"
                      % j.get("winston"))
    print(str(e).splitlines()[0])
    return PF.ok("refuses when the organ is missing, and records SKIPPED (not null) "
                 "when it is left out on purpose")

if __name__ == "__main__":
    raise SystemExit(main())
