"""PROOF ZIV-07 -- nt_xent stops pushing a syllable away from itself

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

    python proof_ZIV-07.py            # the LIVE files  -> must PASS (exit 0)
    python proof_ZIV-07.py --old      # the .bak-rev-20260906 backups -> must FAIL (exit 1)

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
    print("== proof ZIV-07 against %s ==" % PF.which())

    import torch
    import torch.nn.functional as F
    m = PF.load(PF.src("zivug.py"), "z07")
    torch.manual_seed(0)
    n, d = 64, 16
    lab = torch.randint(0, 4, (n,))                  # 4 classes, 64 anchors: many collide
    a = F.normalize(torch.randn(n, d), dim=-1)
    b = F.normalize(torch.randn(n, d), dim=-1)
    try:
        with_lab = float(m.nt_xent(a, b, labels=lab))
    except TypeError as e:
        return PF.bad("nt_xent takes no labels (%s) -- every anchor is pushed away from "
                      "~11.6 clips of its OWN syllable, measured, at batch 128 over 22" % e)
    plain = float(m.nt_xent(a, b))
    # the reference: same loss with same-class non-positives removed by hand
    z = torch.cat([a, b])
    sim = (z @ z.T) / 0.12
    sim.fill_diagonal_(-1e4)
    tgt = torch.cat([torch.arange(n, 2 * n), torch.arange(0, n)])
    l2 = torch.cat([lab, lab])
    same = l2[:, None] == l2[None, :]
    pos = torch.zeros_like(same)
    pos[torch.arange(2 * n), tgt] = True
    ref = float(F.cross_entropy(sim.masked_fill(same & ~pos, -1e4), tgt))
    if abs(with_lab - ref) > 1e-5:
        return PF.bad("masked loss %.6f does not match the reference %.6f"
                      % (with_lab, ref))
    if abs(with_lab - plain) < 1e-6:
        return PF.bad("labels changed nothing -- the mask is not being applied")
    src = io.open(PF.src("zivug.py"), encoding="utf-8").read()
    if "labels=want" not in src or "labels=s_of" not in src:
        return PF.bad("nt_xent can mask but the two call sites do not pass their labels")
    print("plain %.4f -> masked %.4f (reference %.4f)" % (plain, with_lab, ref))
    return PF.ok("same-class negatives are out of the denominator and both call sites "
                 "pass the labels they already hold")

if __name__ == "__main__":
    raise SystemExit(main())
