#!/usr/bin/env python3
"""Block-mean loss table from a train.out log.

WHY BLOCKS. Single-step loss is a sample of a handful of 4096-token windows,
and windows differ enormously in intrinsic difficulty (a Kconfig file vs a
StackExchange answer). In the mb=1 x accum=8 run the per-step sd was 0.35 on a
value of ~1.41, so ANY two-point read -- "step 100 was 1.38, step 1000 is 1.35,
it is learning" -- is noise. That is exactly how 14 hours of a flat run went
unnoticed. Only the mean of a block, quoted with its own standard error, says
anything.

  sd_blockmean = sd_step / sqrt(steps_per_block)

Usage: loss_blocks.py <train.out> [block] [--since STEP] [--max-steps N]
"""
import re, sys, math, statistics as st

path = sys.argv[1]
block = int(sys.argv[2]) if len(sys.argv) > 2 and not sys.argv[2].startswith("-") else 50
since = 0
maxst = None
for i, a in enumerate(sys.argv):
    if a == "--since":  since = int(sys.argv[i+1])
    if a == "--max-steps": maxst = int(sys.argv[i+1])

pat = re.compile(r"step (\d+)/(\d+) loss ([0-9.]+) gnorm ([0-9.naif]+) lr ([0-9.e+-]+) "
                 r"(\d+) tok/s")
rows = []
for line in open(path, encoding="utf-8", errors="replace"):
    m = pat.search(line)
    if not m:
        continue
    step, total, loss, gn, lr, tps = m.groups()
    step, total = int(step), int(total)
    if maxst is not None and total != maxst:
        continue
    if step < since:
        continue
    rows.append((step, float(loss), float(gn), float(lr), int(tps)))
rows.sort()
if not rows:
    sys.exit("no matching step lines")

losses = [r[1] for r in rows]
sd_step = st.stdev(losses) if len(losses) > 1 else float("nan")
print(f"{len(rows)} steps, {rows[0][0]}..{rows[-1][0]} | per-step loss sd {sd_step:.4f}")
print(f"{'block':>13} {'n':>4} {'mean':>8} {'se':>7} {'sd':>7} {'gnorm':>7} "
      f"{'lr':>10} {'tok/s':>7}")
prev = None
for b0 in range(rows[0][0] - (rows[0][0] % block), rows[-1][0] + 1, block):
    chunk = [r for r in rows if b0 < r[0] <= b0 + block]
    if not chunk:
        continue
    ls = [c[1] for c in chunk]
    mean = sum(ls) / len(ls)
    sd = st.stdev(ls) if len(ls) > 1 else float("nan")
    se = sd / math.sqrt(len(ls)) if len(ls) > 1 else float("nan")
    d = "" if prev is None else f"  delta {mean-prev:+.4f}"
    print(f"{b0+1:>6}-{b0+block:<6} {len(chunk):>4} {mean:>8.4f} {se:>7.4f} {sd:>7.4f} "
          f"{sum(c[2] for c in chunk)/len(chunk):>7.3f} "
          f"{sum(c[3] for c in chunk)/len(chunk):>10.3e} "
          f"{sum(c[4] for c in chunk)/len(chunk):>7.0f}{d}")
    prev = mean

# ---- OLS trend: the verdict, stated as a number with an uncertainty --------
# "delta between two blocks" is still a two-point read, just of noisier points.
# Fit loss ~ a + b*step over EVERY step and report b with its standard error.
# If |b| < 2*se(b) the run is flat and no amount of staring at the block table
# changes that.
xs = [float(r[0]) for r in rows]
ys = [float(r[1]) for r in rows]
n = len(xs)
if n > 2:
    mx, my = sum(xs)/n, sum(ys)/n
    sxx = sum((x-mx)**2 for x in xs)
    sxy = sum((x-mx)*(y-my) for x, y in zip(xs, ys))
    b = sxy/sxx
    a = my - b*mx
    resid = [y - (a + b*x) for x, y in zip(xs, ys)]
    s2 = sum(r*r for r in resid)/(n-2)
    se_b = math.sqrt(s2/sxx)
    per1k, se1k = b*1000, se_b*1000
    print()
    print(f"OLS over all {n} steps: slope = {per1k:+.4f} +/- {se1k:.4f} loss per 1000 steps "
          f"(1 se); residual sd {math.sqrt(s2):.4f}")
    t = per1k/se1k if se1k else float("nan")
    # POWER FIRST. "flat" and "cannot tell" are different answers and only one
    # of them is a finding. A run that is really learning should shed roughly
    # 0.1-0.3 loss over its full schedule, i.e. a slope of order 0.1 per 1000
    # steps. If our own standard error is bigger than that, the fit cannot see
    # such a slope even if it is there, and calling that "FLAT" is a lie.
    INTERESTING = 0.10           # loss per 1000 steps
    if se1k > INTERESTING:
        need = int(n * (se1k / INTERESTING) ** (2.0/3.0)) + 1
        print(f"  UNDERPOWERED: se {se1k:.3f} > {INTERESTING} per 1000 steps, so a "
              f"real slope would be invisible here.")
        print(f"  VERDICT = UNKNOWN, not flat. Need roughly {need} steps at this "
              f"noise level (sd {math.sqrt(s2):.4f}) to resolve it.")
        raise SystemExit(0)
    print(f"  t = {t:+.2f}  ->  ", end="")
    if t < -2:
        print(f"FALLING. Over the {int(xs[-1]-xs[0])} steps measured the fit drops "
              f"{-b*(xs[-1]-xs[0]):.4f}.")
    elif t > 2:
        print("RISING -- the loss is going the wrong way.")
    else:
        print("FLAT. Slope is within 2 se of zero: no detectable learning.")
