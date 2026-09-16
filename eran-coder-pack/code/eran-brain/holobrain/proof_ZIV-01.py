"""PROOF ZIV-01 -- the stale eye checkpoint is NAMED, not a bare size mismatch

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

    python proof_ZIV-01.py            # the LIVE files  -> must PASS (exit 0)
    python proof_ZIV-01.py --old      # the .bak-rev-20260906 backups -> must FAIL (exit 1)

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
    print("== proof ZIV-01 against %s ==" % PF.which())

    tmp = os.path.join(tempfile.gettempdir(), "ziv01")
    m = PF.load(PF.src("zivug.py"), "z01")
    # the REAL eye.pt and the REAL letters.npz -- the pair that has been broken since
    # 2026-08-31 and said nothing about it.
    args = ["--steps", "1", "--out", tmp, "--device", "cpu", "--i-know-this-is-the-PC"]
    _, e, _out = cap(PF.run_main, m, args)
    if e is None:
        return PF.bad("it RAN. The eye and the corpus are supposed to be incompatible; "
                      "this proof is meaningless unless one of them changed.")
    msg = str(e)
    if "size mismatch" in msg and "proj.weight" in msg:
        return PF.bad("bare torch traceback, nothing said which file moved:\n  %s"
                      % msg.splitlines()[0][:160])
    for need in ("eye.pt", "letters.npz", "2026-08-30", "2026-08-31", "CH=3"):
        if need not in msg:
            return PF.bad("the refusal does not mention %r:\n%s" % (need, msg[:400]))
    print(msg.splitlines()[0])
    return PF.ok("refused by name, with both files and both mtimes, before load_state_dict")

if __name__ == "__main__":
    raise SystemExit(main())
