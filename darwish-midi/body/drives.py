"""drives.py — hunger/satiety. The bird chooses its own next meal.

Energy E in [0,1], set-point 0.6. Nutrition = surprise in the Goldilocks band:
too predictable = empty calories, too random = indigestible (the MIKO rule).
Appetite ranks candidate shards by expected nutrition -> auto-curriculum.

REVISION 2026-09-06 (DW-01, DW-02):
  * satiety was arithmetically unreachable — hunger fires below 0.4 and one meal
    lifts E by at most 0.15, so E topped out at 0.55 while singing needs 0.8.
    The bird ate 12,092 times in 16 days and sang once. Fixed with feeding
    hysteresis (should_eat/should_sing) + a boot gate that refuses a genome in
    which the satiety line cannot be reached.
  * the meal was a deterministic argmax over nutrition, and one shard's
    nutrition never fell, so the "auto-curriculum" was a fixed point: 11,724 of
    12,092 meals were the same GoaTrance track. choose_meal() samples instead.
"""
import math
import random

import genome


class SatietyUnreachable(RuntimeError):
    """The genome makes SATIETY_LINE arithmetically impossible to reach."""


def assert_satiety_reachable():
    """DW-01 boot gate. Returns the reachable E ceiling; raises if it is a lie.

    Without hysteresis the bird only eats below HUNGER_LINE and gains at most
    EAT_GAIN_MAX, so E can never exceed HUNGER_LINE + EAT_GAIN_MAX. If that
    ceiling is at or below SATIETY_LINE the bird can never sing, and everything
    downstream of singing — the critic, the trace payout, the father's taps,
    serotonin — is dark forever, with no exception and no log line. Refuse.
    """
    # getattr, not attribute access: if genome.py alone is rolled back to the
    # pre-revision file this must produce the REFUSAL below, not an
    # AttributeError that reads like an unrelated crash.
    gain = getattr(genome, "EAT_GAIN_MAX", 0.15)
    hysteresis = getattr(genome, "EAT_HYSTERESIS", False)
    ceiling = genome.HUNGER_LINE + gain
    if not hysteresis and ceiling <= genome.SATIETY_LINE:
        raise SatietyUnreachable(
            "genome: one meal lifts E to at most %.3f (HUNGER_LINE %.2f + "
            "EAT_GAIN_MAX %.2f) but SATIETY_LINE is %.2f — the bird can never "
            "sing. Set EAT_HYSTERESIS = True, or lower SATIETY_LINE."
            % (ceiling, genome.HUNGER_LINE, gain, genome.SATIETY_LINE))
    return ceiling


class Drives:
    def __init__(self, state=None):
        self.E = genome.E_SET
        self.feeding = False               # DW-01: inside a feeding bout?
        if state:
            self.E = state.get("E", genome.E_SET)
            self.feeding = bool(state.get("feeding", False))

    def to_state(self):
        return {"E": self.E, "feeding": self.feeding}

    @property
    def hungry(self):
        return self.E < genome.HUNGER_LINE

    @property
    def sated(self):
        return self.E > genome.SATIETY_LINE

    # ------------------------------------------------------- DW-01 hysteresis
    def should_eat(self):
        """Hunger WITH hysteresis (side effect: enters/leaves the feeding bout).

        Below HUNGER_LINE the bird starts a bout and keeps eating every beat
        until it crosses SATIETY_LINE. One meal cannot span the two lines
        (0.4 -> 0.8 needs 0.4 of energy, a meal gives <= 0.15), so without this
        the satiety branch is dead code — 1,678,853 live beats, 0 with E > 0.8.
        """
        if not getattr(genome, "EAT_HYSTERESIS", False):
            return self.hungry
        if self.feeding:
            if self.E >= genome.SATIETY_LINE:
                self.feeding = False
                return False
            return True
        if self.E < genome.HUNGER_LINE:
            self.feeding = True
            return True
        return False

    def should_sing(self):
        """Sated and not mid-bout. Paired with should_eat(); call it second."""
        return (not self.feeding) and self.E >= genome.SATIETY_LINE

    # ------------------------------------------------------------- nutrition
    def nutrition_of_bits(self, bits_list):
        """Fraction of tokens whose surprise fell in the Goldilocks band."""
        if not bits_list:
            return 0.0
        good = sum(1 for b in bits_list
                   if genome.GOLDILOCKS_LO <= b <= genome.GOLDILOCKS_HI)
        return good / len(bits_list)

    def probe_appetite(self, brain, ears, names):
        """Rank shards by expected nutrition, probing the first tokens of each
        WITHOUT learning (learn=False) and without touching brain history."""
        ranked = []
        for name in names:
            saved_hist = list(brain.history)
            bits = []
            for i, (tok, phase) in enumerate(ears.feed(name)):
                if i >= genome.APPETITE_PROBE:
                    break
                p = brain.p_of(tok, phase)
                bits.append(-math.log2(p))
                brain.history.append(tok)
                if len(brain.history) > genome.ORDER_MAX:
                    brain.history.pop(0)
            brain.history = saved_hist
            ranked.append((self.nutrition_of_bits(bits), name))
        ranked.sort(reverse=True)
        return ranked

    # ------------------------------------------------ DW-02 the meal is drawn
    def choose_meal(self, ranked, recent=(), counts=None, temperature=1.0,
                    rng=random):
        """Draw the next meal from `ranked` [(nutrition, name), ...].

        The old code returned ranked[0][1]. Nutrition of the winning shard never
        dropped (0.946 for its last ten of ~11,700 servings), so the argmax was a
        fixed point and the curriculum never moved. Here: drop the last few
        meals, drop any shard that already owns more than DIET_DOMINANCE_CAP of
        the diet window, then sample the rest softmax-weighted by nutrition at
        the mood temperature. Nutrition still leads; it no longer dictates.
        """
        if not ranked:
            return None
        recent_set = set(recent)
        counts = counts or {}
        total = sum(counts.values())

        def allowed(name):
            if name in recent_set:
                return False
            if (total >= getattr(genome, "DIET_WINDOW_MIN", 20)
                    and counts.get(name, 0) / total
                    > getattr(genome, "DIET_DOMINANCE_CAP", 0.5)):
                return False
            return True

        pool = [(n, nm) for n, nm in ranked if allowed(nm)]
        if not pool:                                   # everything excluded
            pool = [(n, nm) for n, nm in ranked if nm not in recent_set]
        if not pool:
            pool = list(ranked)
        t = max(0.15, float(temperature))
        best = max(n for n, _ in pool)
        beta = getattr(genome, "MEAL_BETA", 8.0)
        weights = [math.exp(beta * (n - best) / t) for n, _ in pool]
        total_w = sum(weights)
        if not (total_w > 0.0) or not math.isfinite(total_w):
            return pool[0][1]
        r = rng.random() * total_w
        acc = 0.0
        for w, (_, name) in zip(weights, pool):
            acc += w
            if r <= acc:
                return name
        return pool[-1][1]

    # ------------------------------------------------------------- energetics
    def eat(self, nutrition):
        self.E = min(1.0, self.E + getattr(genome, "EAT_GAIN_MAX", 0.15) * nutrition)

    def sing_cost(self):
        self.E = max(0.0, self.E - genome.SONG_COST)

    def tick(self):
        self.E = max(0.0, self.E - 0.001)
