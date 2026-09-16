"""PROOF ZIV-09 -- retrieval RAISES on a missing class instead of shifting the rows

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

    python proof_ZIV-09.py            # the LIVE files  -> must PASS (exit 0)
    python proof_ZIV-09.py --old      # the .bak-rev-20260906 backups -> must FAIL (exit 1)

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
    print("== proof ZIV-09 against %s ==" % PF.which())

    import inspect
    import torch
    import torch.nn.functional as F
    m = PF.load(PF.src("zivug.py"), "z09")
    sig = inspect.signature(m.retrieval)
    torch.manual_seed(0)
    d = 8
    base = F.normalize(torch.randn(4, d), dim=-1)
    ky = torch.tensor([0, 0, 1, 1, 3, 3])             # class 2 is ABSENT
    keys = F.normalize(base[ky] + 0.01 * torch.randn(6, d), dim=-1)
    q = keys[4:6]
    qy = torch.tensor([3, 3])
    args = [q, keys, qy, ky] + ([4] if len(sig.parameters) >= 5 else [])
    try:
        got = m.retrieval(*args)
    except AssertionError as e:
        print("raised: %s" % e)
        return PF.ok("a class with no keys is an error, not a quietly wrong number")
    return PF.bad("returned %.3f (correct is 1.000) with class 2 absent -- no exception, "
                  "no warning, every row after the gap scored against the wrong class"
                  % got)

if __name__ == "__main__":
    raise SystemExit(main())
