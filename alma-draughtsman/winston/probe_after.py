"""After the A/B: does the fixed painter still paint somebody else?

The original diagnosis had one behavioural test that settled it -- shown a photograph it
had never seen, the pooled painter's painting was CLOSER to the corpus photograph whose
code was nearest than to the photograph in front of it. This runs that same test on both
trained checkpoints, on the SAME held-out photographs, so the before and after are in the
same units. A painter that describes must be nearest to what it was actually shown.

    python probe_after.py ab-pool/painter.pt ab-grid/painter.pt
"""
import os
import sys

import numpy as np
import torch
import torch.nn.functional as F

from winston import chroma, render
import winston2

DEV = torch.device("cuda")
ROOT = os.path.dirname(os.path.abspath(__file__))


def code(net, x):
    """A global descriptor for nearest-neighbour lookup. For the pooled net this IS the
    net's own bottleneck; for the grid net it is the same trunk pooled, used only as a
    neighbour index so the two are compared on identical footing."""
    see = net.see
    f = see(x.permute(0, 3, 1, 2))
    if f.dim() == 2:                      # pooled net: see() already flattened
        return f
    return F.adaptive_avg_pool2d(f, 1).flatten(1)


@torch.no_grad()
def main(ckpts):
    paths = winston2.images_in(os.path.join(ROOT, "trainset-iddo-alma-v2"))
    for cp in ckpts:
        ck = torch.load(cp, map_location=DEV, weights_only=False)
        size, strokes, arch = ck["size"], ck["strokes"], ck.get("arch", "pool")
        hold = set(ck.get("holdout", []))
        keep = [p for p in paths if os.path.basename(p) not in hold]
        held = [p for p in paths if os.path.basename(p) in hold]
        net = winston2.build(arch, strokes, tuple(ck.get("grids", (4, 8, 16)))).to(DEV).eval()
        net.load_state_dict(ck["net"])

        X = torch.as_tensor(np.stack([winston2.load(p, size) for p in keep]), device=DEV)
        Zc = torch.cat([code(net, X[i:i + 8]) for i in range(0, len(X), 8)])
        Zc = F.normalize(Zc, dim=1)

        print("\n=== %s   arch=%s  %d strokes @ %dpx ===" % (cp, arch, strokes, size))
        print("  on each HELD-OUT photograph: is the painting nearest to the photograph it")
        print("  was shown, or to the corpus photograph whose code is closest?")
        own = other = 0
        for hp in held + [os.path.join(ROOT, "sderot_src.jpg")]:
            xo = torch.as_tensor(winston2.load(hp, size)[None], device=DEV)
            j = int((F.normalize(code(net, xo), dim=1) @ Zc.T).argmax())
            yo = render(net(xo), size=size, chunk=25)
            d_own = float(F.mse_loss(yo, xo))
            d_oth = float(F.mse_loss(yo, X[j:j + 1]))
            own += d_own < d_oth
            other += d_own >= d_oth
            print("    %-34s painting->shown %.5f  painting->nearest-corpus %.5f  %s"
                  % (os.path.basename(hp)[:34], d_own, d_oth,
                     "ok" if d_own < d_oth else "<- PAINTS SOMEBODY ELSE"))
        print("  nearest to the photograph it was shown: %d/%d" % (own, own + other))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
