"""PROOF MIKO-02 -- the adapter was never an identity at step 0 (code revision 2026-09-06).

adapter.py's docstring promised "output == input at step 0". It was false: only proj_in was
zeroed, and every ResBlock's fc1/fc2 biases are randomly initialised, so blk(0) != 0. The
whole 09-03 adapter run therefore amounted to adding ONE constant vector to every frozen e5
embedding (|c| = 0.448 measured from adapter-v1.pt), and every "e5 + trained adapter" number
is zero-shot plus that offset.

FAILS against the 09-03 code (max|adapter(x) - x| ~ 0.4 at init, for every depth).
PASSES against the fix (exactly 0.0).

    python proof_MIKO-02.py [--dir <tree>]
"""
from __future__ import annotations

import argparse
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ap = argparse.ArgumentParser()
ap.add_argument("--dir", default=str(HERE))
TARGET = pathlib.Path(ap.parse_args().dir).resolve()
sys.path[:] = [p for p in sys.path if p and pathlib.Path(p).resolve() != HERE]
sys.path.insert(0, str(TARGET))

import torch                       # noqa: E402
import torch.nn.functional as F    # noqa: E402

from adapter import Adapter        # noqa: E402

checks: list[tuple[str, bool, str]] = []

TOL = 1e-6
torch.manual_seed(20260906)
x = F.normalize(torch.randn(16, 64), dim=-1)      # unit vectors, like real e5 output

for depth in (1, 2, 3):
    a = Adapter(d_in=64, d_out=64, depth=depth)
    a.eval()
    with torch.no_grad():
        ref = F.normalize(x, dim=-1)
        delta = float((a(x) - ref).abs().max())
        # the constant offset the old init actually added, for the record
        c = float((a(x) - ref).mean(0).norm())
    # TOL is float32 re-normalisation noise; the old init is 5 orders of magnitude above it.
    checks.append((f"Adapter(depth={depth}) == frozen backbone at step 0",
                   delta <= TOL,
                   f"max|adapter(x) - x| = {delta:.3e} (tol {TOL:.0e})   "
                   f"mean-offset norm |c| = {c:.4f}"))

# the residual branch itself must be exactly zero, not merely small
a = Adapter(d_in=64, d_out=64, depth=2)
with torch.no_grad():
    y = a.proj_in(x)
    for blk in a.blocks:
        y = blk(y)
branch = float(y.abs().max())
checks.append(("the whole residual branch is zero at init (not just proj_in)",
               branch == 0.0,
               f"max|blocks(proj_in(x))| = {branch:.6f}"))

# gradient must still flow -- a zeroed branch is useless if it cannot learn
a = Adapter(d_in=64, d_out=64, depth=2)
probe = torch.randn(64)
loss = (a(x) @ probe).sum()          # a real direction, not the constant ||a(x)||^2 = 1
loss.backward()
g_proj = float(a.proj_in.weight.grad.abs().max())
g_fc2 = float(a.blocks[-1].fc2.weight.grad.abs().max())
checks.append(("gradient still reaches proj_in and fc2 (the zeroing is not a dead branch)",
               g_proj > 1e-8 and g_fc2 > 1e-8,
               f"max|grad proj_in| = {g_proj:.3e}   max|grad blocks[-1].fc2| = {g_fc2:.3e}"))

src = (TARGET / "adapter_train.py").read_text(encoding="utf-8")
checks.append(("adapter_train.py asserts identity-at-init before training",
               "ADAPTER-NOT-IDENTITY-AT-INIT" in src,
               "assert present" if "ADAPTER-NOT-IDENTITY-AT-INIT" in src
               else "nothing checks it -- a random offset would be trained again"))

ok = all(c[1] for c in checks)
for name, good, detail in checks:
    print(f"  [{'PASS' if good else 'FAIL'}] {name}\n         {detail}")
print(f"PROOF MIKO-02: {'PASS' if ok else 'FAIL'}   (tree = {TARGET})")
sys.exit(0 if ok else 1)
