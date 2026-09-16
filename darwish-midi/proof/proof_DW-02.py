# -*- coding: utf-8 -*-
"""proof_DW-02.py — the meal must be DRAWN, not argmaxed.

THE DEFECT (measured over 12,092 real meals):
    _pick_meal() returned ranked[0][1]. The winning shard's nutrition never fell
    (0.946 on each of its last ten servings after ~11,700 passes), so the
    "auto-curriculum" was a fixed point: 11,724 of 12,092 meals were
    '2012 - GoaTrance Retro Goa set by Dj Darwish.json' — 100.0% of every day
    from 08-22 to 09-06, and 683 M of the 687.9 M tokens ever eaten.

WHAT THIS PROVES, through the REAL Life._pick_meal:
    a stub appetite where one shard is always the argmax (exactly the measured
    situation). The old code eats it 100 times out of 100; the fixed code
    spreads over many shards, caps any one shard at DIET_DOMINANCE_CAP of the
    window, and still avoids the indigestible ones (nutrition leads, it no
    longer dictates).

    python3 proof_DW-02.py --mode old   -> FAIL
    python3 proof_DW-02.py              -> PASS
"""
import collections
import os
import random
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _rev20260906 as rev  # noqa: E402

MODE = rev.mode_from_argv()
TREE, SWAPPED = rev.enter(MODE)

sys.modules.setdefault("psy_synth", types.ModuleType("psy_synth"))
import genome                      # noqa: E402
from chemistry import Chemistry    # noqa: E402
from drives import Drives          # noqa: E402
import darwish_life as dl          # noqa: E402

MEALS = 100
GOA = "2012 - GoaTrance Retro Goa set by Dj Darwish.json"
JUNK = ["junk-%02d.json" % i for i in range(4)]          # indigestible shards

# the appetite the bird actually saw, frozen: one stable argmax, a long tail
RANKED = [(0.946, GOA)]
RANKED += [(0.940 - 0.008 * i, "shard-%02d.json" % i) for i in range(25)]
RANKED += [(0.25 - 0.03 * i, JUNK[i]) for i in range(4)]
RANKED.sort(reverse=True)
NAMES = [n for _, n in RANKED]

c = rev.Checks(__doc__.strip().splitlines()[0], MODE)
print("  tree=%s  swapped=%s" % (TREE, SWAPPED or "(none: this IS the tree)"))
print("  menu: %d shards, argmax = %s (%.3f)" % (len(NAMES), GOA[:38], 0.946))


def make_life():
    life = dl.Life.__new__(dl.Life)
    life.ablate = []
    life.beat = 0
    life.brain = types.SimpleNamespace(history=[], mass=0)
    life.ears = types.SimpleNamespace(train=list(NAMES))
    life.chem = Chemistry()
    life.drives = Drives()
    life.drives.probe_appetite = lambda brain, ears, names: list(RANKED)
    life._seq_idx = 0
    life._rng = random.Random(genome.SEED)
    life._recent = collections.deque(maxlen=getattr(genome, "MEAL_RECENT_EXCLUDE", 8))
    life._diet = collections.deque(maxlen=getattr(genome, "DIET_WINDOW", 200))
    return life


life = make_life()
eaten = []
for _ in range(MEALS):
    name = life._pick_meal()
    eaten.append(name)
    if hasattr(life, "_note_meal"):
        life._note_meal(name)
    life.beat += 1

counts = collections.Counter(eaten)
top_name, top_n = counts.most_common(1)[0]
junk_n = sum(counts.get(j, 0) for j in JUNK)
print("  %d meals -> %d distinct; top = %s x%d (%.0f%%); junk eaten %d"
      % (MEALS, len(counts), top_name[:38], top_n, 100.0 * top_n / MEALS, junk_n))

c.check("the diet is not one shard", len(counts) >= 20,
        "%d distinct shards in %d meals" % (len(counts), MEALS))
c.check("no shard owns the bird", top_n / MEALS <= 0.5,
        "top shard = %.0f%% of meals (cap %.0f%%)"
        % (100.0 * top_n / MEALS, 100.0 * getattr(genome, "DIET_DOMINANCE_CAP", 0.5)))
c.check("nutrition still leads (indigestible shards stay rare)",
        junk_n <= 0.05 * MEALS, "%d of %d meals were junk" % (junk_n, MEALS))
c.check("a shard is never repeated back-to-back",
        all(eaten[i] != eaten[i + 1] for i in range(len(eaten) - 1)))

# the fixed picker must still be a picker, not a shuffler: over many draws the
# most nutritious half of the menu must beat the least nutritious half.
good = {n for _, n in RANKED[:len(RANKED) // 2]}
share_good = sum(v for k, v in counts.items() if k in good) / MEALS
c.check("the nutritious half of the menu wins the majority of meals",
        share_good > 0.5, "%.0f%% of meals" % (100.0 * share_good))

# the collapse warning must exist and must be able to fire
c.check("Life._log_diet exists (diet histogram + collapse warning)",
        hasattr(dl.Life, "_log_diet"))

c.done()
