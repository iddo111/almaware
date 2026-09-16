"""PROOF ZIV-12 -- an empty query set raises instead of averaging in as nan

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

    python proof_ZIV-12.py            # the LIVE files  -> must PASS (exit 0)
    python proof_ZIV-12.py --old      # the .bak-rev-20260906 backups -> must FAIL (exit 1)

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
    print("== proof ZIV-12 against %s ==" % PF.which())

    import torch
    import torch.nn.functional as F
    c = PF.load(PF.src("close_loop.py"), "z12")
    cent = F.normalize(torch.randn(22, 16), dim=-1)
    q = torch.zeros(0, 16)
    qy = torch.zeros(0, dtype=torch.long)
    try:
        got = c.rank_acc(q, cent, qy)
    except Exception as e:                                           # noqa: BLE001
        print("raised: %s" % str(e).splitlines()[0])
        return PF.ok("an empty slice is an error, not a number -- the same shape as "
                     "ERAN's empty-menu starvation, caught here before it can average")
    return PF.bad("returned %r; letter_holdout averages that with np.mean, so a letter "
                  "with nothing held out poisons the headline to nan" % (got,))

if __name__ == "__main__":
    raise SystemExit(main())
