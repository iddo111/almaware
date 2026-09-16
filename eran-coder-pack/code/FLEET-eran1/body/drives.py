"""drives.py — energy and hunger. THIS is what makes learning autonomous.

Eating (processing audio) costs energy; learning PROGRESS feeds it — so the
organism is rewarded for getting better, not for chewing. Hunger ranks the
menu by Goldilocks novelty: not too known (empty calories), not too alien
(indigestible) — the MIKO curiosity rule. When energy is low and progress has
stalled, sleep pressure rises.

Embodies: hunger/satiety intrinsic drive (ALMA-LIVING-NEURON engine 3); the
organism is never spoon-fed — it chooses its own next meal.
"""
import numpy as np

import genome


class Drives:
    def __init__(self, state=None):
        self.E = genome.E_SET
        self.last_progress_beat = 0
        self.ablated = False      # --ablate hunger: first menu item, no ranking
        if state:
            self.E = float(state.get("E", genome.E_SET))
            self.last_progress_beat = int(state.get("last_progress_beat", 0))

    def to_state(self):
        return {"E": round(self.E, 4),
                "last_progress_beat": self.last_progress_beat}

    # ------------------------------------------------------------- appetite
    def choose(self, menu, brain, ears):
        """Pick the next meal from the school's menu by Goldilocks novelty.

        Probes each candidate WITHOUT learning (nearest-prototype only) and
        picks the one whose novelty sits closest to the Goldilocks band's
        middle. The menu items are opaque {'path': ...} records — the drives
        never see a label.
        """
        if not menu:
            return None
        if self.ablated:
            return menu[0]
        mid = 0.5 * (genome.GOLD_LO + genome.GOLD_HI)
        best, best_score = menu[0], -1e9
        for item in menu:
            try:
                vec = ears.utterance(item["path"])
            except (OSError, ValueError):
                continue
            _, sim, _ = brain.nearest(vec)
            novelty = 1.0 - sim
            if genome.GOLD_LO <= novelty <= genome.GOLD_HI:
                score = 1.0 - abs(novelty - mid)          # inside the band
            else:
                score = -abs(novelty - mid)               # outside: penalized
            if score > best_score:
                best, best_score = item, score
        return best

    # --------------------------------------------------------------- energy
    def eat_cost(self):
        self.E = max(0.0, self.E - genome.EAT_COST)

    def feed_progress(self, progress, beat):
        gain = genome.PROGRESS_FEED * progress
        if gain > 0.0005:
            self.last_progress_beat = beat
        self.E = min(1.0, self.E + gain)

    def tick(self):
        self.E = max(0.0, self.E - genome.TICK_COST)

    # ---------------------------------------------------------------- sleep
    def sleep_pressure(self, beat):
        """Low energy AND stalled progress -> time to sleep."""
        stalled = (beat - self.last_progress_beat) > genome.STALL_BEATS
        return self.E < genome.SLEEP_E_LINE and stalled

    def wake_refresh(self, beat=None):
        """Waking up clears the stall as well as the hunger.

        Measured 2026-08-21: without resetting the stall clock the child fell
        asleep again 4 beats after every waking (last_progress_beat frozen at
        2,127 while the beat counter passed 114,000) — it spent two hours
        napping instead of living, and its prototype count never moved. A
        child that just slept is not, by definition, stalled.
        """
        self.E = max(self.E, genome.E_SET)
        if beat is not None:
            self.last_progress_beat = int(beat)
