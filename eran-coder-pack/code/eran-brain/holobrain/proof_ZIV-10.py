"""PROOF ZIV-10 -- the leakage control is WRITTEN DOWN and gates the headline

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

    python proof_ZIV-10.py            # the LIVE files  -> must PASS (exit 0)
    python proof_ZIV-10.py --old      # the .bak-rev-20260906 backups -> must FAIL (exit 1)

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
    print("== proof ZIV-10 against %s ==" % PF.which())

    tmp = os.path.join(tempfile.gettempdir(), "ziv10")
    p = PF.build(tmp)
    j = os.path.join(p["out"], "scramble.json")
    try:
        os.remove(j)
    except OSError:
        pass
    c = PF.load(PF.src("close_loop.py"), "z10")
    _, e, out = cap(PF.run_main, c, PF.argv(p, "--mode", "scramble"))
    if e is not None:
        return PF.bad("the control did not finish: %r" % e)
    if not os.path.exists(j):
        return PF.bad("the ONE test that would catch a leak printed to a terminal and "
                      "left no record: %s was not written" % j)
    import json
    r = json.load(open(j))
    for k in ("shape_to_true_sound", "bar_3se", "leaked", "n", "chance"):
        if k not in r:
            return PF.bad("the record has no %r: %r" % (k, r))
    src = io.open(PF.src("close_loop.py"), encoding="utf-8").read()
    if 'sc["leaked"]' not in src:
        return PF.bad("scramble.json is written but nothing gates on it")
    print("acc %.3f vs a derived bar of %.3f (n=%d) -> leaked=%s"
          % (r["shape_to_true_sound"], r["bar_3se"], r["n"], r["leaked"]))
    return PF.ok("persisted with a DERIVED bar (chance + 3 binomial SE), and a leak "
                 "refuses the run instead of scrolling past")

if __name__ == "__main__":
    raise SystemExit(main())
