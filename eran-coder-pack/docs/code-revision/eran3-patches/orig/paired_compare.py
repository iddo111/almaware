#!/usr/bin/env python3
"""Paired old-vs-new comparison on the EXACT SAME sequences.

Both runs start at dom_cursor=0/rep_cursor=0, and MixedLoader decides
domain-vs-replay purely from the GLOBAL sequence index, so after k optimiser
steps a run has consumed sequences [0, k*block_size) whatever block_size is.
New step k therefore covers the same set as old step 16k (128 vs 8 per step).
Grouping and within-block order differ; the SET does not. So the two means are
computed over identical data and the only differences are the weights (base vs
base+1017 steps) and the batch size.
"""
import re, math, sys, statistics as st

old, new = [], []
for line in open("train.out", errors="replace"):
    m = re.search(r"step (\d+)/(\d+) loss ([0-9.]+) gnorm ([0-9.]+)", line)
    if not m:
        continue
    s, t = int(m.group(1)), int(m.group(2))
    rec = (s, float(m.group(3)), float(m.group(4)))
    (old if t == 8000 else new).append(rec)

n = len(new)
if n == 0:
    sys.exit("no steps from the new run yet")
j = 16 * n
o = [x[1] for x in old if x[0] <= j]
nn = [x[1] for x in new]

def stat(v):
    return (st.mean(v), st.stdev(v)/math.sqrt(len(v)) if len(v) > 1 else float("nan"))

mo, so = stat(o)
mn, sn = stat(nn)
print(f"IDENTICAL DATA: global sequences 0..{128*n-1}  "
      f"({128*n} sequences = {128*n*4096/1e6:.1f}M tokens)")
print(f"  OLD run  base weights,     batch   8, steps 1-{j:<5} mean {mo:.4f} +/- {so:.4f}  n={len(o)}")
print(f"  NEW run  step-1017 weights, batch 128, steps 1-{n:<5} mean {mn:.4f} +/- {sn:.4f}  n={len(nn)}")
d = mn - mo
sd = math.sqrt(so**2 + sn**2)
print(f"  difference {d:+.4f} +/- {sd:.4f}  ({d/sd:+.2f} sigma)")
go = [x[2] for x in old if x[0] <= j]
gn = [x[2] for x in new]
print()
print(f"  gnorm  old {st.mean(go):.3f}  new {st.mean(gn):.3f}   (clip = 1.0)")
if len(o) > 1:
    print(f"  per-step loss sd  old {st.stdev(o):.4f}", end="")
if len(nn) > 2:
    print(f"   new (excl. step 1) {st.stdev(nn[1:]):.4f}")
else:
    print()
