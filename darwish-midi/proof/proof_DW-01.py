# -*- coding: utf-8 -*-
"""proof_DW-01.py — satiety must be reachable, or the bird never sings.

THE DEFECT (measured over 1,678,809 real beats):
    eat() fires only while E < HUNGER_LINE (0.4) and adds at most 0.15, so E
    topped out at 0.5475 while singing needs E > SATIETY_LINE (0.8). The bird ate
    12,092 times in 16 days and sang ONCE — at beat 272, during --feed-all, when
    E had been driven to 1.0 by hand. Everything downstream of singing (critic,
    trace payout, the father's taps, serotonin) was dark for the entire life,
    with no exception and no log line.

WHAT THIS PROVES, with the REAL body/drives.py + body/genome.py:
    A. 200,000 beats of the real eat/sing policy: the old code never reaches the
       satiety line and never sings; the fixed code does both.
    B. the boot gate refuses a genome whose satiety line cannot be reached.
    C. the song cadence cap holds the fixed loop to SONG_MAX_PER_DAY.

    python3 proof_DW-01.py --mode old   -> FAIL   (the code that ran 16 days)
    python3 proof_DW-01.py              -> PASS   (the fix)
"""
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _rev20260906 as rev  # noqa: E402

MODE = rev.mode_from_argv()
TREE, SWAPPED = rev.enter(MODE)

import genome            # noqa: E402
import drives as drives_mod  # noqa: E402

NUTRITION = 0.946        # the measured nutrition of every meal the bird ever ate
BEATS = 200_000

c = rev.Checks(__doc__.strip().splitlines()[0], MODE)
print("  tree=%s  swapped=%s" % (TREE, SWAPPED or "(none: this IS the tree)"))


# ----------------------------------------------------------- A. the life policy
def simulate(beats=BEATS, nutrition=NUTRITION):
    """one_beat()'s eat/sing decision, nothing else, on the real Drives."""
    d = drives_mod.Drives()
    hyst = hasattr(d, "should_eat")
    max_e, songs, meals = d.E, 0, 0
    for _ in range(beats):
        if (d.should_eat() if hyst else d.hungry):
            d.eat(nutrition)
            meals += 1
        elif (d.should_sing() if hyst else d.sated):
            d.sing_cost()
            songs += 1
        d.tick()
        max_e = max(max_e, d.E)
    return max_e, songs, meals


max_e, songs, meals = simulate()
print("  %d beats at nutrition %.3f: maxE=%.4f  songs=%d  meals=%d"
      % (BEATS, NUTRITION, max_e, songs, meals))
c.check("E reaches the satiety line", max_e >= genome.SATIETY_LINE,
        "maxE=%.4f  SATIETY_LINE=%.2f" % (max_e, genome.SATIETY_LINE))
c.check("the bird sings", songs > 0, "%d songs in %d beats" % (songs, BEATS))
c.check("it still eats (singing did not replace feeding)", meals > 0,
        "%d meals" % meals)
c.check("song cost is paid from energy (no runaway)", max_e <= 1.0,
        "maxE=%.4f" % max_e)

# a leaner diet must not silently un-sing the bird
max_e2, songs2, _ = simulate(nutrition=0.60)
c.check("still sings on a leaner diet (nutrition 0.60)", songs2 > 0,
        "maxE=%.4f songs=%d" % (max_e2, songs2))


# ------------------------------------------------------------- B. the boot gate
gate = getattr(drives_mod, "assert_satiety_reachable", None)
c.check("a boot gate exists", gate is not None,
        "drives.assert_satiety_reachable")
if gate is not None:
    ok = True
    try:
        gate()
    except Exception as e:                                   # noqa: BLE001
        ok = False
        print("      gate refused the SHIPPED genome: %s" % e)
    c.check("the gate passes the shipped genome", ok)

    saved = genome.EAT_HYSTERESIS
    genome.EAT_HYSTERESIS = False           # the 16-day genome, without the fix
    refused = False
    try:
        gate()
    except Exception as e:                                   # noqa: BLE001
        refused = True
        print("      gate refused the pre-revision genome: %s" % str(e)[:140])
    genome.EAT_HYSTERESIS = saved
    c.check("the gate REFUSES a genome that can never be sated", refused,
            "HUNGER_LINE %.2f + EAT_GAIN_MAX %.2f <= SATIETY_LINE %.2f"
            % (genome.HUNGER_LINE, getattr(genome, "EAT_GAIN_MAX", 0.15),
               genome.SATIETY_LINE))


# --------------------------------------------------------- C. the cadence cap
sys.modules.setdefault("psy_synth", types.ModuleType("psy_synth"))
try:
    import darwish_life as dl                                # noqa: E402
except Exception as e:                                       # noqa: BLE001
    dl = None
    print("      (darwish_life not importable: %s)" % e)

if dl is not None and hasattr(dl.Life, "_song_allowed"):
    import datetime
    obj = types.SimpleNamespace(_song_gate={}, _songs=0)
    t = 1_757_000_000.0                       # a fixed clock: no wall-clock flake
    per_day, gaps, last = {}, [], None
    for _ in range(7 * 24 * 60):              # 7 simulated days, one probe/minute
        if dl.Life._song_allowed(obj, now=t):
            dl.Life._note_song(obj, now=t)
            day = datetime.date.fromtimestamp(t).isoformat()
            per_day[day] = per_day.get(day, 0) + 1
            if last is not None:
                gaps.append(t - last)
            last = t
        t += 60.0
    worst_day = max(per_day.values()) if per_day else 0
    print("      cadence: %d songs over 7 simulated days, busiest day %d, "
          "min gap %.0f s" % (sum(per_day.values()), worst_day,
                              min(gaps) if gaps else 0))
    c.check("no calendar day exceeds the song cap",
            worst_day <= genome.SONG_MAX_PER_DAY,
            "busiest day %d vs cap %d" % (worst_day, genome.SONG_MAX_PER_DAY))
    c.check("songs are never closer than the minimum interval",
            bool(gaps) and min(gaps) >= genome.SONG_MIN_INTERVAL_S,
            "min gap %.0f s >= %d s"
            % (min(gaps) if gaps else 0, genome.SONG_MIN_INTERVAL_S))
    c.check("the cap is what holds the loop back, not the drives",
            songs / max(1, sum(per_day.values())) > 1.0,
            "%d songs wanted in %d beats (~%.0f/day at 2.75 beats/s) vs %d/day "
            "allowed" % (songs, BEATS, songs / (BEATS / 2.75 / 86400.0),
                         worst_day))
    c.check("cadence cap does not mute the bird", sum(per_day.values()) > 0,
            "%d songs allowed in 7 simulated days" % sum(per_day.values()))
else:
    c.check("Life._song_allowed exists (song cadence cap)", False,
            "no cadence cap in this tree")

c.done()
