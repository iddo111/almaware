"""PROOF ZIV-02 -- a headline whose falsifiers never ran is STAMPED

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

    python proof_ZIV-02.py            # the LIVE files  -> must PASS (exit 0)
    python proof_ZIV-02.py --old      # the .bak-rev-20260906 backups -> must FAIL (exit 1)

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
    print("== proof ZIV-02 against %s ==" % PF.which())

    m = PF.load(PF.src("close_loop.py"), "z02")
    if not hasattr(m, "falsification_stamp"):
        return PF.bad("no falsification_stamp(): the headline is printed clean whether "
                      "or not letterout/pairout/scramble have ever been run")
    empty = os.path.join(tempfile.gettempdir(), "ziv02-empty")
    full = os.path.join(tempfile.gettempdir(), "ziv02-full")
    os.makedirs(empty, exist_ok=True)
    os.makedirs(full, exist_ok=True)
    for f, _ in m.FALSIFIERS:
        open(os.path.join(full, f), "w").write("{}")
    s_empty, s_full = m.falsification_stamp(empty), m.falsification_stamp(full)
    if "UNFALSIFIED" not in s_empty:
        return PF.bad("no stamp with every falsifier missing: %r" % s_empty)
    if s_full != "":
        return PF.bad("still stamped when all three exist: %r" % s_full)
    src = io.open(PF.src("close_loop.py"), encoding="utf-8").read()
    if "falsification_stamp(a.out)" not in src:
        return PF.bad("falsification_stamp exists but nothing calls it at the headline")
    print(s_empty.strip())
    return PF.ok("stamped when the falsifiers are missing, clean when they exist, and "
                 "wired into the SHAPE->SOUND print")

if __name__ == "__main__":
    raise SystemExit(main())
