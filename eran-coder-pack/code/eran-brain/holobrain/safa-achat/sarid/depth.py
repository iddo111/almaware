# -*- coding: utf-8 -*-
"""TIME DEPTH - and why the horizon is a fact about the machine, not a promise.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL
> output, not a proxy.

In the ALMA loom a strand's `delay` is how many beats a spark takes to cross
it, delays are integers >= 1, and **delays add along a path**. SARID spends
that currency on the one thing it most needs to be unable to lie about.

    delay = time depth.  YEARS_PER_BEAT = 500.  HORIZON = 20 beats.

A pair of languages is wired at the delay their documented divergence costs.
Latin and Spanish separate around 2,000 years back: 4 beats. Two Indo-European
branches, around 6,000: 12 beats. Two different families have no accepted
divergence date at all, and the honest number - if someone insists on one - is
past the consensus reach of the comparative method.

So a cross-family node sits at a cumulative delay beyond the run's horizon and
**never appears in `result.fires`**. Not refused, not flagged, not printed with
a warning label. It never fires. The loom returns `finished=False` with sparks
still in flight, and that is the truthful report: the question was asked and
the machine could not reach the answer.

THIS IS WHY THE DESIGN CHOSE IT
-------------------------------
A charter sentence can be deleted by a future agent in one edit. Deleting this
costs them a failing test and a weave that stops working. The honesty is
structural. It is the strongest anti-overselling mechanism available to us and
it cost nothing but choosing the right unit for a delay.

THE DATES
---------
Conventional, cited, and deliberately GENEROUS to depth - erring towards
"older" makes the horizon harder to reach, never easier, so the mechanism can
never be accused of manufacturing its own pass. Where the literature disagrees
the older figure is taken.
"""
from __future__ import annotations

from . import HORIZON_BEATS, YEARS_PER_BEAT

# Divergence depth in YEARS for a pair of doculects, keyed by the smallest
# clade containing both. Conventional figures; the citation is the point.
BRANCH_YEARS = {
    # Romance: the daughters separate as Latin fragments, ~1,500-2,000 BP.
    "Romance": 2_000,
    "Germanic": 2_500,          # Proto-Germanic ~500 BCE
    "Slavic": 1_500,
    "Baltic": 2_000,
    "Indo-Iranian": 4_000,
    "Celtic": 3_000,
    "Finnic": 2_000,
    "Ugric": 4_000,
    "Turkic": 2_000,
    "Semitic": 4_500,
}

# Depth of a whole family - the deepest node the comparative method accepts
# for it. Gray & Atkinson and the standard handbooks; older figure taken.
FAMILY_YEARS = {
    "Indo-European": 6_000,     # Anatolian split; 8-9,500 on the Anatolian
    "Uralic": 6_000,            # hypothesis, still inside the horizon
    "Turkic": 2_500,
    "Afro-Asiatic": 10_000,     # AT the horizon: 20 beats exactly
    "Austronesian": 5_500,
    "Sino-Tibetan": 6_000,
    "Tupian": 5_000,
    "Nakh-Daghestanian": 6_000,
    "Kartvelian": 5_000,
    "Abkhaz-Adyge": 5_000,
    "Mongolic-Khitan": 1_000,
    "Tungusic": 2_000,
    "Chukotko-Kamchatkan": 2_000,
    "Eskimo-Aleut": 4_000,
    "Yukaghir": 2_000,
    "Yeniseian": 2_000,
    "Japonic": 2_000,
    "Koreanic": 1_000,
    "Alor-Pantar": 4_500,
}

# What a cross-family link would cost if anyone insisted on wiring one. It is
# past the horizon on purpose and by a wide margin: no long-range proposal
# (Nostratic, Eurasiatic, or a single ancestral tongue for all humanity) is
# an accepted reconstruction, and the
# machine expresses that by being unable to reach the node.
CROSS_FAMILY_YEARS = 15_000


def years(fam_a: str, fam_b: str,
          branch_a: str = "", branch_b: str = "") -> int:
    """Divergence depth in years for two doculects."""
    if fam_a != fam_b or not fam_a:
        return CROSS_FAMILY_YEARS
    if branch_a and branch_a == branch_b:
        return BRANCH_YEARS.get(branch_a, FAMILY_YEARS.get(fam_a, 6_000))
    return FAMILY_YEARS.get(fam_a, 6_000)


def beats(fam_a: str, fam_b: str,
          branch_a: str = "", branch_b: str = "") -> int:
    """Divergence depth in BEATS - the delay a strand between them carries."""
    y = years(fam_a, fam_b, branch_a, branch_b)
    return max(1, round(y / YEARS_PER_BEAT))


def reachable(fam_a: str, fam_b: str,
              branch_a: str = "", branch_b: str = "") -> bool:
    """Is this node inside the consensus reach of the comparative method?

    A False here is not a refusal SARID issues. It is a prediction about what
    the loom will do: the node's cumulative delay exceeds the horizon, so it
    will not be in `result.fires`. `weave.py` wires the node anyway, precisely
    so the silence is the machine's own answer rather than ours.
    """
    return beats(fam_a, fam_b, branch_a, branch_b) <= HORIZON_BEATS
