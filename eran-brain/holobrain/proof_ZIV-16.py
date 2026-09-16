"""PROOF ZIV-16 -- the hand's one channel reaches the colour eye at all

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

    python proof_ZIV-16.py            # the LIVE files  -> must PASS (exit 0)
    python proof_ZIV-16.py --old      # the .bak-rev-20260906 backups -> must FAIL (exit 1)

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
    print("== proof ZIV-16 against %s ==" % PF.which())

    tmp = os.path.join(tempfile.gettempdir(), "ziv16")
    p = PF.build(tmp, hand=True)
    z = PF.load(PF.src("zivug.py"), "z16")
    rc, e, out = cap(PF.run_main, z, PF.argv(p))
    if e is not None:
        if "permute" in str(e) or "dim" in str(e):
            return PF.bad("the loop does not close -- ink() draws one channel, the eye "
                          "reads CH: %s" % str(e).splitlines()[-1][:150])
        return PF.bad("zivug did not finish: %r" % e)
    if "WINSTON DRAWS" not in out:
        return PF.bad("no WINSTON leg in the report at all")
    print([l for l in out.splitlines() if "WINSTON DRAWS" in l][0].strip())
    return PF.ok("ink() -> ink_to_eye() -> the colour eye: the loop closes end to end "
                 "again, which no retrain of eye.pt would have fixed on its own")

if __name__ == "__main__":
    raise SystemExit(main())
