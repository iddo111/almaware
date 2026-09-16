"""PROOF MIKO-01 -- inverted contrastive temperature (code revision 2026-09-06).

FAILS against the 09-03 code (logit_scale() = 0.07 / 0.05, i.e. T instead of 1/T, so the
whole attainable InfoNCE window is 8.30-8.44 and the objective cannot shape anything).
PASSES against the fix (logit_scale() = 14.29 / 20.0, floor ~1e-4).

    python proof_MIKO-01.py                          # the fixed tree
    python proof_MIKO-01.py --dir <old-tree>         # the backed-up 09-03 tree
"""
from __future__ import annotations

import argparse
import math
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ap = argparse.ArgumentParser()
ap.add_argument("--dir", default=str(HERE), help="tree to test (default: this one)")
TARGET = pathlib.Path(ap.parse_args().dir).resolve()
sys.path[:] = [p for p in sys.path if p and pathlib.Path(p).resolve() != HERE]
sys.path.insert(0, str(TARGET))

import torch  # noqa: E402

checks: list[tuple[str, bool, str]] = []


def infonce_floor(scale: float, b: int = 48) -> float:
    """Best achievable train loss at this logit scale: cos(pos)=1, cos(neg)=0.

    train.py's loss = cross_entropy over (B, 2B) [positives + hard negatives] plus the
    symmetric (B, B) term -- exactly the two logs below.
    """
    return (math.log(1 + (2 * b - 1) * math.exp(-scale))
            + math.log(1 + (b - 1) * math.exp(-scale)))


CHANCE = math.log(96) + math.log(48)      # 8.4355 -- uniform logits, B = 48

from model import MikoBiEncoder  # noqa: E402
from adapter import Adapter      # noqa: E402

m = MikoBiEncoder(d=16, depth=1, vocab_size=1024)
m_scale = float(m.logit_scale().detach())
m_floor = infonce_floor(m_scale)
checks.append(("MikoBiEncoder.logit_scale() > 1 (1/T, not T)", m_scale > 1.0,
               f"logit_scale={m_scale:.4f}  (CLIP convention for T=0.07 is 14.2857)"))
checks.append(("from-scratch InfoNCE floor is reachable (< 0.01)", m_floor < 0.01,
               f"floor={m_floor:.4f}  chance={CHANCE:.4f}  window={CHANCE - m_floor:.4f}"))

a = Adapter(d_in=16, d_out=16, depth=1)
a_scale = float(a.logit_scale().detach())
a_floor = infonce_floor(a_scale)
checks.append(("Adapter.logit_scale() > 1 (1/T, not T)", a_scale > 1.0,
               f"logit_scale={a_scale:.4f}  (CLIP convention for T=0.05 is 20.0)"))
checks.append(("adapter InfoNCE floor is reachable (< 0.01)", a_floor < 0.01,
               f"floor={a_floor:.4f}  chance={CHANCE:.4f}"))

for f in ("train.py", "adapter_train.py"):
    src = (TARGET / f).read_text(encoding="utf-8")
    checks.append((f"{f} refuses an inverted temperature before training",
                   "INVERTED-TEMPERATURE" in src,
                   "assert on logit_scale() > 1.0 present" if "INVERTED-TEMPERATURE" in src
                   else "no such assert -- a scale of 0.07 would train silently again"))

# What the shipped checkpoints carry, for the record (not a pass condition: they are the
# 09-03 artefacts and stay wrong until a retrain on a fleet box).
for name in ("miko-v1.pt", "adapter-v1.pt"):
    p = TARGET / name
    if p.exists():
        try:
            sd = torch.load(p, map_location="cpu", weights_only=False)["model_state"]
            t = float(sd["temp"])
            print(f"[info] {name}: temp={t:.4f} -> exp(temp)={math.exp(t):.4f} "
                  f"(shipped 09-03 checkpoint; unchanged by this fix)")
        except Exception as e:                                   # pragma: no cover
            print(f"[info] {name}: could not read temp ({e})")

ok = all(c[1] for c in checks)
for name, good, detail in checks:
    print(f"  [{'PASS' if good else 'FAIL'}] {name}\n         {detail}")
print(f"PROOF MIKO-01: {'PASS' if ok else 'FAIL'}   (tree = {TARGET})")
sys.exit(0 if ok else 1)
