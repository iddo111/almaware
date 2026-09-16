# -*- coding: utf-8 -*-
"""THE VOICES - the numerics, living inside spells, closed over ONE Round.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL
> output, not a proxy.

The WINSTON pattern, kept exactly (winston/brushes.py is the model): the weave
in `weave.py` is pure loom semantics, and every array, alignment and
correspondence table lives in the host `Round` object that these closures see.
A spark stays a scalar all the way through. Nothing is smuggled down a cord.

A spell receives only `tray["in"]` - the loom hands it a tuple of floats and
takes back one float or None. `None` is silence, exactly like a shut gate.

WHAT EACH VOICE ACTUALLY COMPUTES
---------------------------------
`tally_a_b`   the number of sound correspondences between two languages that
              recur across DISTINCT concepts and survive the permutation null
              at p < 0.01. Recurrence across distinct meanings is the whole
              comparative method in one sentence: one lookalike is chance, the
              same correspondence in fifteen unrelated meanings is a law.
              Answers None when the pair shares too few concepts to test -
              refusing to answer is a first-class result here.

`sig_a_b`     the permutation z-score. KEY MATERIAL ONLY: it opens or shuts the
              pair's gate and never becomes evidence itself.

`exam_*`      the four ruler numbers, recomputed every round on the round's own
              canon, so Gate 1 re-passes NOW rather than once at the start.

`gain`        held-out improvement over the last KEPT round. This is the only
              number merit hangs on.
"""
from __future__ import annotations

import math
import random
import statistics
from collections import defaultdict

from . import sca

MIN_CONCEPTS = 60          # below this a pair cannot be tested, and says so
P_THRESHOLD = 0.01
N_PERM = 200               # permutations per pair; 200 gives p resolution 0.005
MIN_RECUR = 3              # a correspondence must appear in >= 3 DISTINCT concepts
# A pair must receive evidence from BOTH its lineages before it may be
# examined. Doculect masses are scaled so the median doculect carries 1.0, so
# two awake lineages deliver about 2.0 and one delivers about 1.0: this line
# sits between them on purpose. You cannot establish a sound correspondence
# from one language, and now the weave cannot either - starve either side and
# the pair sleeps.
THETA_PAIR = 1.5
LAW_BONUS = 0.35           # how much an established law is worth to a score


# ------------------------------------------------------- correspondence mining

def correspondences(pairs) -> dict:
    """Align every shared concept; count each column across DISTINCT concepts.

    `pairs` is [(concept, segments_a, segments_b)]. Returns
    {(class_a, class_b): set(concepts)}. Counting CONCEPTS, not columns, is
    deliberate: ten occurrences of p:b inside one word is one piece of
    evidence, not ten.
    """
    table = defaultdict(set)
    for concept, sa, sb in pairs:
        _, cols = sca.align(sa, sb)
        for ca, cb in cols:
            if ca == "-" or cb == "-":
                continue
            if ca == "?" or cb == "?":
                continue
            table[(ca, cb)].add(concept)
    return table


def _observed(pairs) -> float:
    """THE STATISTIC: how far the correspondences exceed what chance predicts.

    NOT the number of distinct recurring correspondences. That was the first
    version and the null model killed it on sight: with 90 concepts, random
    meaning-pairings produce MANY class-pairs that each reach three concepts,
    so the shuffled control scored 46 against the true signal's 13. Counting
    types rewards diversity, and chance is diverse; descent is CONCENTRATED.

    What descent actually looks like is a few correspondences carrying far more
    mass than independence allows - Latin p : Spanish b in fifty meanings, not
    fifty correspondences in three meanings each. So the statistic is the
    chi-square excess of the over-represented, recurring cells:

        for each aligned class pair (x, y) with count n >= MIN_RECUR
            expected = marginal(x) * marginal(y) / total
            add (n - expected)^2 / expected   when n > expected

    Under the permutation null the cells sit at their marginals and this goes
    to nearly zero. Under real descent a handful of cells dominate it. It is
    the same quantity LexStat's correspondence scoring is built on.
    """
    table = correspondences(pairs)
    counts = {k: len(v) for k, v in table.items()}
    total = sum(counts.values())
    if not total:
        return 0.0
    marg_a, marg_b = defaultdict(int), defaultdict(int)
    for (x, y), n in counts.items():
        marg_a[x] += n
        marg_b[y] += n
    stat = 0.0
    for (x, y), n in counts.items():
        if n < MIN_RECUR:
            continue
        exp = marg_a[x] * marg_b[y] / total
        if exp > 0 and n > exp:
            stat += (n - exp) ** 2 / exp
    return stat


def n_laws(pairs) -> int:
    """How many correspondences recur across >= MIN_RECUR distinct concepts.

    Reported and written to the canon; NEVER used as the significance test -
    see _observed for why that distinction had to be made.
    """
    return sum(1 for _, cs in correspondences(pairs).items()
               if len(cs) >= MIN_RECUR)


def permutation_test(pairs, n_perm: int = N_PERM, seed: int = 0):
    """THE NULL MODEL. Returns (observed, p, z, null_mean, null_sd).

    The meaning link is destroyed and nothing else is: same two languages, same
    inventories, same phonotactics, same number of comparisons. Whatever the
    method scores here is what it would have scored on noise.

    This function is the difference between SARID and Ruhlen, and the charter
    says so in those words. It is not an optional extra pass.
    """
    # THE FLOOR-EFFECT GUARD, and it caught a live one on round 0.
    #
    # A permutation p-value cannot go below 1/(n_perm+1). With n_perm=60 the
    # smallest achievable p is 0.0164, which is ABOVE P_THRESHOLD=0.01 - so on
    # the first real round NO pair could reach significance no matter how
    # strong its evidence, and the round wrote 0 laws while reporting success.
    # That is the first nezer's frozen 0.431 gate exactly: a threshold outside
    # the statistic's reachable range. Refuse loudly instead of returning a
    # number that can only ever mean "no".
    if n_perm + 1 < 1.0 / P_THRESHOLD:
        raise ValueError(
            "permutation floor effect: %d permutations can never produce "
            "p < %g (the smallest reachable p is %.4f). Raise --perm to at "
            "least %d, or this test can only ever say no."
            % (n_perm, P_THRESHOLD, 1.0 / (n_perm + 1),
               int(round(1.0 / P_THRESHOLD))))
    obs = _observed(pairs)
    rnd = random.Random(seed)
    rb = [p[2] for p in pairs]
    null = []
    for _ in range(n_perm):
        rnd.shuffle(rb)
        null.append(_observed([(pairs[i][0], pairs[i][1], rb[i])
                               for i in range(len(pairs))]))
    mu = statistics.fmean(null) if null else 0.0
    sd = statistics.pstdev(null) if len(null) > 1 else 0.0
    p = (sum(1 for v in null if v >= obs) + 1) / (len(null) + 1)
    z = ((obs - mu) / sd) if sd > 0 else (float("inf") if obs > mu else 0.0)
    return obs, p, z, mu, sd


# ------------------------------------------------------------------ the round

class Round:
    """Everything one round of SARID knows. The spells close over this."""

    def __init__(self, corpus, fit_langs, held_out_family: str,
                 seed: int = 1933, n_perm: int = N_PERM):
        self.corpus = corpus
        self.fit_langs = tuple(fit_langs)
        self.held_out = held_out_family
        self.seed = int(seed)
        self.n_perm = int(n_perm)
        # filled in as the weave runs
        self.tallies: dict = {}          # (a,b) -> (obs, p, z)
        self.laws: dict = {}             # (a,b) -> [(corr, n_concepts)]
        self.starved: set = set()        # pairs whose lineage stopped waking
        self.exams: dict = {}
        self.notes: list = []

    # -- the pair voices ---------------------------------------------------

    def tally(self, a: str, b: str):
        """One pair's evidence, or None when it cannot honestly be tested.

        THE ARRIVING SPARK IS LOAD-BEARING, and this is the mechanism the spec
        calls "a failed hypothesis dies of starvation, not of a rule forbidding
        it". `ins` carries the evidence that reached this pair along its own
        lineage's cords. If a lineage's strands have thinned below THETA_PAIR -
        because its laws kept failing, and 4:1 drift kept charging them - the
        pair is never examined again. Pruning is a run-time weave event.

        A spell that ignored `ins` would make the weave decoration. The facade
        test in tests/test_sarid.py exists to catch exactly that, and it caught
        it here on the first run.
        """
        def voice(ins):
            arriving = sum(ins)
            if arriving < THETA_PAIR:
                self.tallies[(a, b)] = (0, 1.0, 0.0, 0)
                self.starved.add((a, b))
                return None                      # starved: the lineage sleeps
            pairs = self.corpus.shared(a, b)
            if len(pairs) < MIN_CONCEPTS:
                self.tallies[(a, b)] = (0, 1.0, 0.0, len(pairs))
                return None                      # refusing to answer IS a result
            obs, p, z, _, _ = permutation_test(pairs, self.n_perm, self.seed)
            nl = n_laws(pairs)
            self.tallies[(a, b)] = (nl, p, z, len(pairs))
            if p < P_THRESHOLD:
                tab = correspondences(pairs)
                self.laws[(a, b)] = sorted(
                    ((c, len(cs)) for c, cs in tab.items()
                     if len(cs) >= MIN_RECUR),
                    key=lambda t: -t[1])
            return float(nl)
        return voice

    def sig(self, a: str, b: str):
        """The z-score. Key material: it opens the gate, it is never evidence."""
        def voice(_ins):
            t = self.tallies.get((a, b))
            if not t:
                return None
            obs, p, z, n = t
            if p >= P_THRESHOLD:
                return None                      # shut the gate, silently
            return float(min(z, 50.0)) if math.isfinite(z) else 50.0
        return voice

    # -- the exams ---------------------------------------------------------

    def _established(self) -> set:
        """Every correspondence this round actually established, as a set.

        This is the round's canon in the only form a score needs: which (class,
        class) columns earned the right to count as evidence.
        """
        out = set()
        for laws in self.laws.values():
            for corr, _n in laws:
                out.add(corr)
        return out

    def _pair_score(self, a: str, b: str) -> float:
        """How related two languages look, GIVEN THE LAWS THIS ROUND ESTABLISHED.

        Two terms, and the second is why the weave is not decoration:

          base   sound-class alignment similarity - what any aligner would say
          bonus  the fraction of this pair's aligned columns that are
                 correspondences the round ESTABLISHED, times LAW_BONUS

        The bonus is the comparative method's actual claim: a p:b match means
        much more between two languages where p:b has been shown to recur
        across many distinct meanings than between two where it has not. It is
        the same idea LexStat implements as pair-specific scoring.

        And it is what makes the exams depend on the weave. Starve the evidence
        cords, no laws get established, the bonus goes to zero and every exam
        number moves. The facade test asserts exactly that, and before this
        term existed the test failed - correctly, because the spells were
        recomputing from the corpus and ignoring what the loom delivered.
        """
        pairs = self.corpus.shared(a, b)
        if not pairs:
            return 0.0
        est = self._established()
        base = statistics.fmean([sca.similarity(sa, sb)
                                 for _, sa, sb in pairs])
        if not est:
            return base
        hit = tot = 0
        for _, sa, sb in pairs:
            _, cols = sca.align(sa, sb)
            for ca, cb in cols:
                if ca in ("-", "?") or cb in ("-", "?"):
                    continue
                tot += 1
                if (ca, cb) in est:
                    hit += 1
        bonus = (hit / tot) if tot else 0.0
        return base + LAW_BONUS * bonus

    def exam_ceiling(self, related_pairs):
        """Documented DESCENT must score high. The answer is known in advance."""
        def voice(_ins):
            vals = [self._pair_score(a, b) for a, b in related_pairs]
            v = statistics.fmean(vals) if vals else 0.0
            self.exams["ceiling"] = v
            return v
        return voice

    def exam_floor(self, unrelated_pairs):
        """Documented NON-relatedness must score low."""
        def voice(_ins):
            vals = [self._pair_score(a, b) for a, b in unrelated_pairs]
            v = statistics.fmean(vals) if vals else 0.0
            self.exams["floor"] = v
            return v
        return voice

    def exam_shuffle(self, a: str, b: str, draws: int = 60):
        """The null: the same pair with meaning destroyed."""
        def voice(_ins):
            vals = []
            for k in range(draws):
                ps = self.corpus.shuffled_against(a, b, seed=self.seed + k)
                if ps:
                    vals.append(statistics.fmean(
                        [sca.similarity(sa, sb) for _, sa, sb in ps]))
            v = statistics.fmean(vals) if vals else 0.0
            self.exams["shuffle"] = v
            self.exams["shuffle_sd"] = (statistics.pstdev(vals)
                                        if len(vals) > 1 else 0.0)
            return v
        return voice

    def exam_holdout(self, within_pairs, across_pairs):
        """THE LEARNING CRITERION - and the only number merit may hang on.

        Every language here belongs to a family the fitting knots never saw.
        The question is not "does the canon fit?" but "does it survive?": can
        laws learned without this family still tell its own related pairs from
        its unrelated ones?

        The number is a discrimination AUC over documented family membership -
        ground truth from Glottolog, which is a documented classification, not
        an automatic judgement. A ruler scored against automatic judgements is
        a ruler measuring itself, and Gate 0 refuses that outright.
        """
        def voice(_ins):
            within = [self._pair_score(a, b) for a, b in within_pairs]
            across = [self._pair_score(a, b) for a, b in across_pairs]
            if not within or not across:
                self.exams["holdout"] = 0.0
                return None
            n_ok = sum(1 for w in within for x in across if w > x)
            n_tie = sum(1 for w in within for x in across if w == x)
            auc = (n_ok + 0.5 * n_tie) / (len(within) * len(across))
            self.exams["holdout"] = auc
            self.exams["holdout_within"] = statistics.fmean(within)
            self.exams["holdout_across"] = statistics.fmean(across)
            self.exams["holdout_n"] = (len(within), len(across))
            return float(auc)
        return voice

    def gain_over(self, last_kept: float, eps: float):
        """Held-out improvement over the last KEPT round. ALWAYS answers.

        IT MUST ALWAYS ANSWER, and that is not a detail - it is the fix for the
        drift trap, found by the canary on this build's first test run.

        loom.py's LEARN thickens a cord when its spark LANDED and the
        destination FIRED, and thins it when the spark landed and the
        destination stayed silent. A cord whose spark never lands is never
        judged at all. So if this voice went silent on a bad round, the merit
        cord would simply not be charged, and merit could only ever rise.

        Answering the raw gain - negative when the round got worse - makes the
        spark always land in `keep`, which is a `sum` knot with `trigger="rise
        eps"`: it fires only on real improvement. Thicken on improvement, thin
        on failure, at ALMA's own 4:1. That is WINSTON's `w_###` pattern, and
        it is the placement the canary is there to defend.
        """
        def voice(_ins):
            h = self.exams.get("holdout")
            if h is None:
                self.exams["gain"] = -1.0
                return -1.0            # a round with no exam is a failed round
            d = h - last_kept
            self.exams["gain"] = d
            return float(d)
        return voice

    def settle(self):
        """Commit: how many laws the round wrote down."""
        def voice(_ins):
            n = sum(len(v) for v in self.laws.values())
            self.exams["settled"] = n
            return float(n)
        return voice
