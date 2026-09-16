"""PROOF ZIV-06 -- the sheet is drawn from the RUN's reference glyphs

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

    python proof_ZIV-06.py            # the LIVE files  -> must PASS (exit 0)
    python proof_ZIV-06.py --old      # the .bak-rev-20260906 backups -> must FAIL (exit 1)

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
    print("== proof ZIV-06 against %s ==" % PF.which())

    npz = os.path.join(HERE, "state", "sound-drawings.npz")
    if not os.path.exists(npz):
        return PF.bad("no artifact to render: %s" % npz)
    dst = os.path.join(tempfile.gettempdir(), "ziv06-sheet.png")
    m = PF.load(PF.src("show_sound_drawings.py"), "z06")
    _, e, out = cap(m.main, npz, dst)
    if e is not None:
        return PF.bad("it crashed on the artifact it exists to render: %r" % e)
    if "run's own stored reference" not in out:
        return PF.bad("it rendered, but not from the run's own glyphs:\n%s" % out)
    if not os.path.exists(dst):
        return PF.bad("no sheet was written")
    print(out.strip().splitlines()[0])
    return PF.ok("renders the 2026-08-30 artifact against the glyphs THAT RUN stored, "
                 "not against whatever corpus is on disk today")

if __name__ == "__main__":
    raise SystemExit(main())
