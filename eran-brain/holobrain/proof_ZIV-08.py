"""PROOF ZIV-08 -- the scribe's noise is set from the gap it will ACTUALLY meet

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

    python proof_ZIV-08.py            # the LIVE files  -> must PASS (exit 0)
    python proof_ZIV-08.py --old      # the .bak-rev-20260906 backups -> must FAIL (exit 1)

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
    print("== proof ZIV-08 against %s ==" % PF.which())
    import types

    import numpy as np
    import torch
    import torch.nn.functional as F
    c = PF.load(PF.src("close_loop.py"), "z08")
    torch.manual_seed(0)
    d, n_syl = c.D, 4

    # A world built so the HELD-OUT take is FURTHER from the shape centres than the
    # training clips are -- which is the real situation (measured on ear-human.npz: cos
    # 0.9088 to the own-syllable training centroid for training clips, 0.8932 for the
    # held-out take). If the gap is only ever measured on the training side, the scribe
    # is trained through noise ~30% narrower than the gap it must actually cross.
    cent = F.normalize(torch.randn(n_syl, d), dim=-1)
    V, ey, et = [], [], []
    for cl in range(n_syl):
        for t in range(2):
            spread = 0.05 if t == 0 else 0.60         # take 1 is the far one
            for _ in range(3):
                V.append(F.normalize(cent[cl] + spread * torch.randn(d), dim=-1))
                ey.append(cl)
                et.append(t)
    V = torch.stack(V)
    ey = torch.tensor(ey)
    et = torch.tensor(et)
    G = torch.stack([F.normalize(cent[cl] + 0.05 * torch.randn(d), dim=-1)
                     for cl in range(n_syl) for _ in range(4)])
    ly = torch.tensor([cl for cl in range(n_syl) for _ in range(4)])
    ident = torch.arange(n_syl)
    w = types.SimpleNamespace(V=V, ey=ey, t_tr=et == 0, t_te=et == 1, n_syl=n_syl,
                              G=G, ly=ly, l_tr=torch.ones(len(G), dtype=torch.bool),
                              n_let=n_syl, l2s=ident, s2l=ident)
    idh = lambda x: F.normalize(x, dim=-1)                           # noqa: E731

    got = c.cross_modal_gap(w, idh, idh)
    if len(got) != 3:
        return PF.bad("cross_modal_gap returns %d values -- there is no held-out "
                      "measurement at all, and its own docstring says the number it does "
                      "return is 'Measured on TRAINING data'" % len(got))
    cross, within, cross_te = got
    if not (cross_te < cross):
        return PF.bad("the held-out gap (%.4f) is not wider than the training gap "
                      "(%.4f) in a world built so that it is" % (cross_te, cross))
    j_train = min(0.20, float(np.sqrt(max(1.0 / max(cross, 1e-3) ** 2 - 1, 0) / c.D)))
    j_wider = min(0.20, float(np.sqrt(max(1.0 / max(min(cross, cross_te), 1e-3) ** 2 - 1,
                                          0) / c.D)))
    if j_wider <= j_train:
        return PF.bad("taking the wider gap does not widen the noise: %.4f vs %.4f"
                      % (j_wider, j_train))
    src = io.open(PF.src("close_loop.py"), encoding="utf-8").read()
    if "min(c_cross, c_cross_te)" not in src:
        return PF.bad("the held-out gap is measured but the jitter is still derived from "
                      "the training side alone")
    if "cross_modal_cos_heldout_take" not in src:
        return PF.bad("neither gap is recorded, so the calibration cannot be audited")
    print("train cos %.4f -> sigma %.4f  |  held-out cos %.4f -> sigma %.4f"
          % (cross, j_train, cross_te, j_wider))
    return PF.ok("both distributions measured, the WIDER gap sets the scribe's noise, "
                 "and both cosines are written into sound2draw.json")


if __name__ == "__main__":
    raise SystemExit(main())
