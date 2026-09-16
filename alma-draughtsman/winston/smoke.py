"""Smoke test: the grid painter must be shaped right, finite, and -- the load-bearing
claim -- must land its strokes where the picture is, not where a global code says."""
import torch
import winston
import winston2

n = winston2.PainterGrid(800)
print("pyramid", n.plan, "-> total", sum(g * g * k for g, k in n.plan), "kept", n.n)
x = torch.randn(2, 128, 128, 3)
p = n(x)
print("out", tuple(p.shape), "finite", bool(torch.isfinite(p).all()))
xy, w, col = winston.decode(p)
print("anchor x range %.3f..%.3f  y %.3f..%.3f"
      % (float(xy[:, :, 0, 0].min()), float(xy[:, :, 0, 0].max()),
         float(xy[:, :, 0, 1].min()), float(xy[:, :, 0, 1].max())))

# THE test of the anchoring algebra: with the head output at zero, every stroke must sit
# EXACTLY on its own cell centre after decode()'s tanh. If atanh/tanh do not cancel, the
# whole spatial grounding is a lie and this prints a large number.
with torch.no_grad():
    for h in n.heads:
        h.weight.zero_()
    xy0, _, _ = winston.decode(n(x))
    err = (xy0[0, :, 0] - n.cell).abs().max()
print("anchor == cell centre when the head says nothing: max error %.2e" % float(err))

pg = sum(q.numel() for q in winston2.PainterGrid(800).parameters())
pp = sum(q.numel() for q in winston.Painter(800).parameters())
print("params: grid %.3fM   pool %.3fM   (grid is %.2fx smaller)" % (pg / 1e6, pp / 1e6, pp / pg))
print("images_in finds %d" % len(winston2.images_in("trainset-iddo-alma-v2")))

# coverage: after truncation, how many cells of each grid have no stroke at all?
m = winston2.PainterGrid(800)
o = 0
for g, k in m.plan:
    tot = g * g * k
    take = max(0, min(tot, m.n - o))
    got = m.cell[o:o + take]
    cs = set(map(tuple, (((got + 1) / 2 * g).floor().clamp(0, g - 1)).int().tolist()))
    print("grid %2d: %4d/%4d strokes kept, cells covered %3d/%3d" % (g, take, tot, len(cs), g * g))
    o += take
