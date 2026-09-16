"""Does the spatial information die at AdaptiveAvgPool2d(1)?  A matched-budget test.

THE HYPOTHESIS (2026-09-05): Painter.see ends in a global average pool, so the whole
image becomes ONE 256-d vector with zero spatial layout, and an MLP expands that to
strokes*16 numbers. 256 numbers is plenty to INDEX one of 93 photographs and far too
few to DESCRIBE a new one.

THE TEST, and why it is fair. Take the trained trunk's last feature map F (256 x G x G).
Read it out three ways, EACH GIVING EXACTLY 256 NUMBERS:

    z_glob   256 channels, pooled to 1x1     <- what the net actually uses
    z_2x2     64 channels, pooled to 2x2
    z_4x4     16 channels, pooled to 4x4

Same budget every time; only the trade of channels for LAYOUT changes. Then ask each
one to predict an 8x8x3 thumbnail of its own input under leave-one-out ridge across the
93 corpus photos -- LOO, so this measures DESCRIPTION (does the code transfer to a
picture the probe never saw) and not memorisation. If R^2 rises as the budget is spent
on layout instead of channels, the pool is where the description dies, and it is not a
question of how many numbers the bottleneck has.

Test C is behavioural, on the painter itself: for an unseen photograph, is the painting
it makes closer to that photograph, or to the corpus photograph whose code is nearest?
A painter DESCRIBES. An index paints somebody else.
"""
import glob, os, sys
import numpy as np
import torch, torch.nn.functional as F

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from winston import Painter, load, render, chroma, floors, busy_error, detail, POINTS

DEV = torch.device("cuda")
ROOT = os.path.dirname(os.path.abspath(__file__))
SIZE = 256


def trunk_map(net, x):
    """The feature map JUST BEFORE the pool. see[:-2] drops AdaptiveAvgPool2d+Flatten."""
    return net.see[:-2](x.permute(0, 3, 1, 2))


def loo_ridge_r2(Z, Y, lams=(1e-3, 1e-2, 1e-1, 1.0, 10.0, 100.0, 1e3, 1e4)):
    """Leave-one-out R^2 of ridge Z->Y, best lambda reported. Closed form via the hat
    matrix: LOO residual = residual / (1 - h_ii), no refitting."""
    n = Z.shape[0]
    Z = (Z - Z.mean(0)) / (Z.std(0) + 1e-8)
    Z = np.concatenate([Z, np.ones((n, 1))], 1)
    Ym = Y - Y.mean(0)
    best = (-9e9, None)
    G = Z @ Z.T
    for lam in lams:
        # dual ridge: H = Z(Z'Z+lam I)^-1 Z' = G(G+lam I)^-1
        A = np.linalg.solve(G + lam * np.eye(n), np.stack([G, Ym.T @ np.eye(n)][0:1])[0]) if False else None
        Ginv = np.linalg.inv(G + lam * np.eye(n))
        H = G @ Ginv
        pred = H @ Ym
        h = np.clip(np.diag(H), 0, 1 - 1e-6)
        loo = Ym - (Ym - pred) / (1 - h)[:, None]
        r2 = 1 - ((Ym - loo) ** 2).sum() / (Ym ** 2).sum()
        if r2 > best[0]:
            best = (r2, lam)
    return best


def readout(Fmap, chans, grid, order):
    """chans highest-variance channels, average-pooled to grid x grid. chans*grid^2 numbers."""
    sel = Fmap[:, order[:chans]]
    return F.adaptive_avg_pool2d(sel, grid).flatten(1).cpu().numpy().astype(np.float64)


def main():
    ck = torch.load(os.path.join(ROOT, "forever-v2/painter.pt"), map_location=DEV,
                    weights_only=False)
    strokes = ck.get("strokes", 800)
    net = Painter(strokes).to(DEV).eval()
    net.load_state_dict(ck["net"])
    print("checkpoint: %d strokes, trained at size %s" % (strokes, ck.get("size")))

    paths = sorted(sum((glob.glob(os.path.join(ROOT, "trainset-iddo-alma-v2", "**", e),
                                  recursive=True) for e in ("*.jpg", "*.jpeg", "*.png")), []))
    print("corpus: %d photographs" % len(paths))
    X = torch.as_tensor(np.stack([load(p, SIZE) for p in paths]), device=DEV)

    with torch.no_grad():
        Fmap = torch.cat([trunk_map(net, X[i:i + 8]) for i in range(0, len(X), 8)])
    print("feature map before the pool: %s  (%d numbers)  -> pool gives %d"
          % (tuple(Fmap.shape[1:]), int(np.prod(Fmap.shape[1:])), Fmap.shape[1]))

    var = Fmap.var(dim=(0, 2, 3))
    order = torch.argsort(var, descending=True).cpu().numpy()

    thumb = F.adaptive_avg_pool2d(X.permute(0, 3, 1, 2), 8).flatten(1).cpu().numpy().astype(np.float64)

    print("\n=== TEST A/B: 256 numbers, spent three ways. LOO R^2 predicting an 8x8 thumbnail ===")
    print("  (LOO = leave-one-out across the 93, so this is DESCRIPTION, not memorisation)")
    rows = [("z_glob  256ch x 1x1  <- WHAT THE NET USES", 256, 1),
            ("z_2x2    64ch x 2x2", 64, 2),
            ("z_4x4    16ch x 4x4", 16, 4),
            ("z_8x8     4ch x 8x8", 4, 8)]
    for name, c, g in rows:
        if c > Fmap.shape[1] or g > Fmap.shape[-1]:
            continue
        Z = readout(Fmap, c, g, order)
        r2, lam = loo_ridge_r2(Z, thumb)
        print("  %-42s dims %4d   LOO R^2 %+.4f  (lam %g)" % (name, Z.shape[1], r2, lam))

    # a full-map control, unmatched budget, for reference only
    Zfull = Fmap.flatten(1).cpu().numpy().astype(np.float64)
    r2, lam = loo_ridge_r2(Zfull, thumb)
    print("  %-42s dims %4d   LOO R^2 %+.4f  (lam %g)  <- reference, unmatched budget"
          % ("FULL map (no pool at all)", Zfull.shape[1], r2, lam))

    print("\n=== TEST D: is the pooled code an INDEX? ===")
    Zg = readout(Fmap, 256, 1, order)
    Zn = Zg / (np.linalg.norm(Zg, axis=1, keepdims=True) + 1e-9)
    C = Zn @ Zn.T
    np.fill_diagonal(C, -9)
    print("  mean cosine to nearest other corpus code: %.4f   (1.0 = identical, 0 = orthogonal)"
          % C.max(1).mean())
    np.fill_diagonal(C, np.nan)
    print("  mean cosine to ALL other corpus codes:    %.4f" % np.nanmean(C))

    print("\n=== TEST C: on an UNSEEN photograph, whose picture does it paint? ===")
    outs = [os.path.join(ROOT, "sderot_src.jpg")]
    blank_all, blur_all, side = floors(X, strokes, SIZE)
    for op in outs:
        xo = torch.as_tensor(load(op, SIZE)[None], device=DEV)
        with torch.no_grad():
            zo = F.adaptive_avg_pool2d(trunk_map(net, xo), 1).flatten(1)
            zc = F.adaptive_avg_pool2d(Fmap, 1).flatten(1)
            sim = F.normalize(zo, dim=1) @ F.normalize(zc, dim=1).T
            j = int(sim.argmax())
            yo = render(net(xo), size=SIZE, chunk=16)
            yj = render(net(X[j:j + 1]), size=SIZE, chunk=16)
        b, bl, _ = floors(xo, strokes, SIZE)
        print("  %s" % os.path.basename(op))
        print("    nearest corpus code: #%d %s  (cos %.4f)"
              % (j, os.path.basename(paths[j]), float(sim.max())))
        print("    BLANK %.5f | PAINTER %.5f | BLUR %.5f"
              % (b, float(F.mse_loss(yo, xo)), bl))
        print("    mse( painting , THE UNSEEN PHOTO )      %.5f" % float(F.mse_loss(yo, xo)))
        print("    mse( painting , nearest corpus photo )  %.5f" % float(F.mse_loss(yo, X[j:j+1])))
        print("    mse( painting , the painting it makes of that corpus photo ) %.5f"
              % float(F.mse_loss(yo, yj)))
        print("    mse( THE UNSEEN PHOTO , nearest corpus photo ) %.5f"
              % float(F.mse_loss(xo, X[j:j+1])))
        print("    chroma: source %.3f painted %.3f (x%.2f)"
              % (chroma(xo), chroma(yo), chroma(yo) / max(chroma(xo), 1e-3)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
