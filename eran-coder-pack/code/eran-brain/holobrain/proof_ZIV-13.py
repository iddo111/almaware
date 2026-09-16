"""PROOF ZIV-13 -- the two scripts nezer.py COPIES now carry nezer.py's own PC guard

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

    python proof_ZIV-13.py            # the LIVE files  -> must PASS (exit 0)
    python proof_ZIV-13.py --old      # the .bak-rev-20260906 backups -> must FAIL (exit 1)

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
    print("== proof ZIV-13 against %s ==" % PF.which())

    import platform
    host = platform.node().split(".")[0].lower()
    fleet = ("eran2", "eran3", "eran4", "edgexpert-")
    if any(host == f or host.startswith(f) for f in fleet):
        return PF.bad("this proof only means something off the fleet; this box is %r"
                      % host)
    tmp = os.path.join(tempfile.gettempdir(), "ziv13")
    p = PF.build(tmp, hand=False)
    args = [x for x in PF.argv(p) if x != "--i-know-this-is-the-PC"]
    for name, mode in (("zivug.py", []),
                       ("close_loop.py", ["--mode", "scramble"])):
        m = PF.load(PF.src(name), "z13" + name[:3])
        rc, e, out = cap(PF.run_main, m, args + mode)
        if e is None:
            return PF.bad("%s TRAINED on %s without being asked twice (exit %r). "
                          "--device already resolves to cpu here, so the default was "
                          "the failure mode, not a protection." % (name, host, rc))
        if "not on the fleet" not in str(e):
            return PF.bad("%s failed for another reason: %r" % (name, e))
    print("both refused on %s; --i-know-this-is-the-PC is the only way through" % host)
    return PF.ok("refused by hostname in both entry points, as nezer.py already did")

if __name__ == "__main__":
    raise SystemExit(main())
