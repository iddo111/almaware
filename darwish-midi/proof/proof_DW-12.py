# -*- coding: utf-8 -*-
"""proof_DW-12.py — the brain-file cap must actually be enforced, and out loud.

THE DEFECT (code reading):
    Brain.save() wrote the gzip and then

        if mb > genome.FILE_MAX_MB:
            self._prune_weakest()

    but _prune_weakest() only looped `while self.mass > MASS_MAX * 0.95`. So
    whenever the FILE was over its cap while mass sat under that line, the guard
    was a silent no-op: nothing pruned, nothing logged, the cap not enforced.
    (Live today: brain.json.gz is 27.25 MB against a 32 MB cap with mass at
    1,954,803 of 2,000,000 — the no-op path is one growth spurt away.)

WHAT THIS PROVES, with the REAL body/brain.py:
    a brain whose FILE is over the cap while its MASS is far below the prune
    line. Old: the file stays over the cap, mass unchanged, not one log line.
    Fixed: it prunes toward the size, says so with before/after numbers, and the
    file ends under the cap.

    python3 proof_DW-12.py --mode old   -> FAIL
    python3 proof_DW-12.py              -> PASS
"""
import os
import random
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _rev20260906 as rev  # noqa: E402

MODE = rev.mode_from_argv()
TREE, SWAPPED = rev.enter(MODE)

import genome            # noqa: E402
from brain import Brain  # noqa: E402

c = rev.Checks(__doc__.strip().splitlines()[0], MODE)
print("  tree=%s  swapped=%s" % (TREE, SWAPPED or "(none: this IS the tree)"))

SANDBOX = tempfile.mkdtemp(prefix="dw-rev-brain-")
PATH = os.path.join(SANDBOX, "brain.json.gz")

rng = random.Random(20260906)
b = Brain()
for cell in range(1200):
    key = "%d|%d,%d" % (1 + cell % 4, cell, rng.randrange(104))
    row = {}
    for _ in range(12):
        row[str(rng.randrange(genome.VOCAB))] = round(
            genome.W_MIN + rng.random() * 8.0, 6)
    b.w[key] = row
    b.n[key] = rng.randrange(3, 400)
    b.mass += len(row)

LOG = []
try:
    b.save(PATH, log=LOG.append)          # the fixed signature
except TypeError:
    b.save(PATH)                          # the old signature: no log at all
size0 = os.path.getsize(PATH) / 1e6
mass0 = b.mass
print("  seeded brain: mass=%d  file=%.3f MB  (MASS_MAX*0.95=%d)"
      % (mass0, size0, int(genome.MASS_MAX * 0.95)))

# make the FILE oversized while the MASS stays far under the prune line — the
# exact shape the old guard could not see
genome.FILE_MAX_MB = round(size0 / 3.0, 4)
print("  cap set to %.4f MB; mass %d is %.2f%% of the prune line"
      % (genome.FILE_MAX_MB, mass0, 100.0 * mass0 / (genome.MASS_MAX * 0.95)))

LOG[:] = []
try:
    b.save(PATH, log=LOG.append)
except TypeError:
    b.save(PATH)
size1 = os.path.getsize(PATH) / 1e6
print("  after save: mass %d -> %d, file %.3f -> %.3f MB, %d log lines"
      % (mass0, b.mass, size0, size1, len(LOG)))
for line in LOG[:4]:
    print("      %s" % line)

c.check("mass is far below the prune line (the no-op case)",
        mass0 < genome.MASS_MAX * 0.95)
c.check("the file cap is enforced", size1 <= genome.FILE_MAX_MB,
        "%.4f MB vs cap %.4f MB" % (size1, genome.FILE_MAX_MB))
c.check("pruning actually happened", b.mass < mass0,
        "mass %d -> %d" % (mass0, b.mass))
c.check("the prune is logged, not silent", len(LOG) >= 1,
        "%d log lines" % len(LOG))
c.check("the brain is not wiped out", b.mass > 0, "mass=%d" % b.mass)

# a brain under the cap must be left completely alone
genome.FILE_MAX_MB = 32
LOG[:] = []
mass_before = b.mass
try:
    b.save(PATH, log=LOG.append)
except TypeError:
    b.save(PATH)
c.check("a brain under the cap is untouched and silent",
        b.mass == mass_before and not LOG,
        "mass=%d, %d log lines" % (b.mass, len(LOG)))

# and the prune loop must terminate even with nothing left to cut
b2 = Brain()
b2.mass = 5000                      # a mass counter that lies (nothing in w)
if "target_mass" in getattr(b2._prune_weakest, "__code__").co_varnames:
    b2._prune_weakest(target_mass=0)
    c.check("the prune loop terminates on an empty brain", True, "mass=%d" % b2.mass)
else:
    c.check("_prune_weakest takes a size target", False, "old signature")

c.done()
