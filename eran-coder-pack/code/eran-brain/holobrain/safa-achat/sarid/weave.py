# -*- coding: utf-8 -*-
"""THE ANATOMY - SARID as a real ALMA weave, in comparative-method vocabulary.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL
> output, not a proxy.

לזכרה של עלמה ז״ל. This is the organ itself: the comparative method AS loom
semantics, not a loom standing guard over a pile of numpy. What each piece of
the weave IS, with no metaphor debt - the WINSTON easel's own standard:

  a strand IS a sound change   `bearing` carries the rule as text ("p > b / V_V"),
                               `weight` is its regularity - how much of the
                               lineage's evidence it carries - and `tint` names
                               its kind (lenition, assimilation, loan, chance).
  a delay IS time depth        500 years per beat. Delays ADD along a path, so
                               a node's age is its distance from the seed. This
                               is not decoration: it is what makes the horizon
                               real (see depth.py).
  the horizon IS the consensus 10,000 years = 20 beats. A cross-family node sits
                               past it and NEVER FIRES. Not refused - unreached.
                               The loom returns finished=False with sparks still
                               in flight, which is the truthful report.
  a pair's gate IS a verdict   `law_a_b` opens only when the permutation z-score
                               says the correspondences beat their own null.
                               p >= 0.01 shuts it, silently.
  holdout IS topology          no cord runs from a held-out family's knot to any
                               fitting knot. The 08-21 session-leak scar closed
                               by construction: a leak is a graph error that a
                               test can assert on, not a statistics mistake
                               nobody notices.
  keep/revert                  REVERT IS THE DEFAULT. `keep` is a gate keyed on
                               `sep` whose `in` is the held-out gain; it fires
                               with a value only on vetted improvement. A round
                               that does not improve on a family it never saw
                               dies, and nothing needs undoing because its laws
                               were never committed.
  merit                        `drift = 0.4` on the keep->canon cord and NOWHERE
                               ELSE. See THE DRIFT TRAP below - this placement
                               is the whole defence.
  the alarm                    a gate keyed on -sep: it FIRES when the ruler
                               failed this round. The blind-ruler law as
                               structure rather than a printed warning.

THE DRIFT TRAP, designed around and canaried
--------------------------------------------
loom.py's LEARN step computes `fired_now = {f.knot for f in fires if f.beat ==
beat}`, and `fires` INCLUDES SILENT FIRES - a shut gate and a None-answering
spell both append `Fire(beat, name, None)`. So a cord feeding a knot that
REFUSED still thickens, if merit hangs on that knot.

Merit therefore hangs on `keep` alone: a gate downstream of every exam, keyed
by `sep`, whose `in` is the held-out gain. It fires with a value only on vetted
improvement. tests/test_sarid.py forces every exam to refuse and asserts every
merit cord comes back THINNER - copied from WINSTON's canary, because this trap
has already cost this workspace a debugging cycle once.

THE 4:1 EPISTEMICS ARE ALMA'S OWN CONSTANT
------------------------------------------
loom.py LEARN: `w += drift if dst in fired_now else -drift * 0.25`. One survival
is worth four failures. From weight 1.0, five consecutive refutations reach
THETA_DECANON and the law leaves the canon. That asymmetry is not a
hyperparameter we chose - it is the language's, and it happens to be the right
epistemics for a sound law: laws are hard to establish and one clean
counterexample matters more than one more confirmation.

API TRAPS OBEYED (each one costs a debugging cycle if ignored)
--------------------------------------------------------------
 1. a `fringe` knot may NOT have outgoing threads. Every measurement is a
    `spell` knot with a `fringe` TWIN hanging off it.
 2. `trigger` sums the WHOLE tray, key port included. Therefore every gate
    keeps `trigger="any"`. Never `rise` on a gate.
 3. a spell receives only `tray["in"]`.
 4. `gate` opens on `key > 0` STRICTLY. An exactly-zero key is a shut gate.
 5. knot names may not be reserved words.
 6. a knot fires on EVERY beat its tray is non-empty and its trigger met - so
    once-per-round exams get a refractory self-strand of -1e6, WINSTON's own
    trick: its own fire drives its tray far negative, so it fires once.
 7. `Result.learned` is None unless some strand has drift != 0.
 8. `sep`'s floor input arrives NEGATED (Strand(weight=-1.0)), so the tray sums
    to ceiling - floor.
"""
from __future__ import annotations

import os
import sys

_ALMA = os.environ.get("ALMA_HOME", "D:/CLAUDE/alma-language")
for _p in (_ALMA, "/home/eran3/sarid/alma-language",
           "/home/eran4/sarid/alma-language"):
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)

from alma import Loom, Strand, Weave, spells                    # noqa: E402

from . import HORIZON_BEATS                                     # noqa: E402
from . import depth                                             # noqa: E402
from .voices import Round                                       # noqa: E402

BIG_INHIBIT = -1e6         # the refractory self-strand: a knot that fires once
MERIT_FLOOR = 0.0          # a law may starve to nothing...
MERIT_CEIL = 4.0           # ...and may never eat the weave
DRIFT = 0.4                # on keep->canon and nowhere else
THETA_DATA = 0.5           # a doculect must bring this much evidence to speak
THETA_DECANON = 0.5        # below this a law leaves the canon
MARGIN = 0.15              # the separation `sep` must reach
EPS = 0.005                # held-out improvement required to KEEP a round


def _safe(name: str) -> str:
    """Knot names: no reserved words, no punctuation the transcript would eat."""
    return "".join(ch if (ch.isalnum() or ch == "_") else "_" for ch in name)


class Anatomy:
    """Builds SARID's weave over one Round, and runs it.

    The weave is rebuilt every round with the current canon weights, exactly as
    WINSTON's Easel rebuilds with the current opacities. The weave stays pure;
    the loom learns on its own copy and hands the weights back in
    `Result.learned`; writing them into the next round's weave is the author's
    choice, not a side effect.
    """

    def __init__(self, rnd: Round, ceiling_pairs, floor_pairs,
                 holdout_within, holdout_across, shuffle_pair=("lat", "spa"),
                 canon_weight=None, last_kept: float = 0.0,
                 name: str = "sarid"):
        self.r = rnd
        self.ceiling_pairs = list(ceiling_pairs)
        self.floor_pairs = list(floor_pairs)
        self.holdout_within = list(holdout_within)
        self.holdout_across = list(holdout_across)
        self.shuffle_pair = shuffle_pair
        self.last_kept = float(last_kept)
        self.canon_weight = dict(canon_weight or {})
        self.name = name
        self._merit_slot = None
        self._pairs = self._fit_pairs()
        self.horizon = self._schedule()

    # -- which pairs the fitting knots may see -----------------------------

    def _fit_pairs(self):
        """Every WITHIN-FAMILY pair among the FIT languages, and no other.

        Held-out languages are absent from this list by construction. That is
        graft G-b: the holdout is a property of the GRAPH, and
        `test_holdout_is_topology` asserts no path exists.
        """
        c = self.r.corpus
        out = []
        langs = [lg for lg in self.r.fit_langs
                 if c.family_of(lg) != self.r.held_out]
        for i, a in enumerate(langs):
            for b in langs[i + 1:]:
                fa, fb = c.family_of(a), c.family_of(b)
                if not fa or fa != fb:
                    continue                    # cross-family: past the horizon
                out.append((a, b))
        return out

    def _schedule(self) -> int:
        """The horizon: deep enough for every reachable node, and no deeper."""
        c = self.r.corpus
        deepest = 1
        for a, b in self._pairs:
            deepest = max(deepest, depth.beats(c.family_of(a), c.family_of(b)))
        # look(1) -> d_(1) -> tally(depth) -> sig(1) -> law(2) -> census(1)
        # -> exams(2) -> sep(1) -> keep(2) -> settle/canon(2) -> ledger(1)
        return 1 + 1 + deepest + 1 + 2 + 1 + 2 + 1 + 2 + 2 + 2

    # -- the weave ---------------------------------------------------------

    def weave(self) -> Weave:
        w = Weave(self.name)
        c = self.r.corpus
        n_strands = 0

        def cord(src, dst, port="in", strands=None):
            nonlocal n_strands
            ss = strands or [Strand()]
            w.thread(src, dst, port, ss)
            first = n_strands
            n_strands += len(ss)
            return first

        # ---- the corpus enters
        w.knot("look", verb="pass")

        # ---- one knot per doculect: its evidence mass
        used = sorted({lg for p in self._pairs for lg in p})
        # Evidence mass is RELATIVE TO THIS DATASET, not to a hard constant.
        # It was /500.0 until the toy corpus caught it: a 20-concept doculect
        # scored 0.04, never crossed THETA_DATA, and the entire discovery half
        # of the weave sat silent while the exams still answered off the
        # patience strand. The weave looked alive and was not. Scaling to the
        # median doculect makes "enough evidence to speak" mean the same thing
        # on a 20-concept toy and a 1,016-concept database.
        counts = sorted(len(c.by_lang(lg)) for lg in used) or [1]
        scale = float(counts[len(counts) // 2]) or 1.0
        for lg in used:
            k = "d_" + _safe(lg)
            w.knot(k, verb="sum", trigger="rise %g" % THETA_DATA)
            mass = min(4.0, len(c.by_lang(lg)) / scale)
            cord("look", k, strands=[Strand(weight=mass, delay=1,
                                            tint="evidence", bearing=lg)])

        # ---- one triple per pair: tally -> sig -> law
        law_knots = []
        for a, b in self._pairs:
            sa, sb = _safe(a), _safe(b)
            tally, sig, law = "tally_%s_%s" % (sa, sb), \
                              "sig_%s_%s" % (sa, sb), "law_%s_%s" % (sa, sb)
            d = depth.beats(c.family_of(a), c.family_of(b))
            spells.teach("t_%s_%s" % (sa, sb), self.r.tally(a, b), replace=True)
            spells.teach("z_%s_%s" % (sa, sb), self.r.sig(a, b), replace=True)
            w.knot(tally, verb="spell", spell="t_%s_%s" % (sa, sb))
            w.knot(sig, verb="spell", spell="z_%s_%s" % (sa, sb))
            w.knot(law, verb="gate")            # trap 2: gates keep trigger any
            # DELAY IS TIME DEPTH. A cross-family pair would sit past the
            # horizon here and simply never arrive.
            wt = self.canon_weight.get((a, b), 1.0)
            cord("d_" + sa, tally, strands=[Strand(weight=wt, delay=d,
                                                   tint="descent")])
            cord("d_" + sb, tally, strands=[Strand(weight=wt, delay=d,
                                                   tint="descent")])
            cord(tally, sig, strands=[Strand(delay=1)])
            # trap: key must land BEFORE the value it judges
            cord(sig, law, port="key", strands=[Strand(delay=1)])
            cord(tally, law, port="in", strands=[Strand(delay=2)])
            law_knots.append(law)

        # ---- the census: fires ONCE, when the laws are in (or patience comes)
        t_census = max(1.0, 0.5 * len(law_knots))
        w.knot("census", verb="sum", trigger="rise %g" % t_census)
        for lk in law_knots:
            cord(lk, "census", strands=[Strand(weight=1.0, delay=1,
                                               tint="evidence")])
        # the mercy strand: patience, so a round where every gate shut still
        # reaches its exam and REPORTS the failure instead of hanging
        cord("look", "census",
             strands=[Strand(weight=t_census,
                             delay=max(2, self.horizon - 9), tint="patience")])
        # trap 6: refractory - its own fire drives the tray far negative
        cord("census", "census", strands=[Strand(weight=BIG_INHIBIT, delay=1)])

        # ---- the exams: a spell knot each, with a FRINGE TWIN (trap 1)
        exams = (
            ("ceiling", self.r.exam_ceiling(self.ceiling_pairs)),
            ("floor", self.r.exam_floor(self.floor_pairs)),
            ("shuffle", self.r.exam_shuffle(*self.shuffle_pair)),
            ("holdout", self.r.exam_holdout(self.holdout_within,
                                            self.holdout_across)),
        )
        for tag, fn in exams:
            spells.teach("x_" + tag, fn, replace=True)
            w.knot("m_" + tag, verb="spell", spell="x_" + tag)
            w.knot("f_" + tag, verb="fringe")          # the ledger twin
            cord("census", "m_" + tag, strands=[Strand(delay=1)])
            cord("m_" + tag, "f_" + tag, strands=[Strand(delay=1)])

        # ---- sep = ceiling - floor  (trap 8: the floor arrives NEGATED)
        w.knot("sep", verb="sum", trigger="rise %g" % MARGIN)
        cord("m_ceiling", "sep", strands=[Strand(weight=1.0, delay=1)])
        cord("m_floor", "sep", strands=[Strand(weight=-1.0, delay=1)])

        # ---- the alarm: fires when the ruler FAILED this round
        w.knot("alarm", verb="gate", trigger="count 2", bias=1.0)
        w.knot("f_alarm", verb="fringe")
        cord("m_ceiling", "alarm", port="key",
             strands=[Strand(weight=-1.0, delay=1)])
        cord("m_floor", "alarm", port="key",
             strands=[Strand(weight=1.0, delay=1)])
        cord("census", "alarm", strands=[Strand(weight=0.0, delay=3)])
        cord("alarm", "f_alarm", strands=[Strand(delay=1)])

        # ---- keep: the ONE knot merit hangs on.
        #
        # THE PLACEMENT IS THE WHOLE DEFENCE, and the canary proved it on this
        # build's first run: `keep` was a GATE, and a gate whose key opens but
        # whose `in` tray is empty returns 0.0 - a REAL fire, not silence. So a
        # round where every exam refused still thickened the merit cord, to
        # 1.4000. Exactly the trap loom.py's LEARN sets.
        #
        # The fix is WINSTON's `w_###` pattern: `gain` ALWAYS speaks (it
        # answers a negative number on a bad round), so its spark always LANDS
        # in `keep`; and `keep` is a `sum` with `trigger="rise eps"`, so it
        # FIRES only on real improvement. Landed-and-fired thickens,
        # landed-and-silent thins, at ALMA's own 4:1.
        spells.teach("g_gain", self.r.gain_over(self.last_kept, EPS),
                     replace=True)
        w.knot("gain", verb="spell", spell="g_gain")
        w.knot("keep", verb="sum", trigger="rise %g" % EPS)
        cord("m_holdout", "gain", strands=[Strand(delay=1)])
        self._merit_slot = cord("gain", "keep", strands=[Strand(
            weight=1.0, delay=1, drift=DRIFT,
            floor=MERIT_FLOOR, ceil=MERIT_CEIL, tint="merit",
            bearing="what survives a family it had never seen")])

        # ---- commit: the ruler must ALSO have separated, this round, now.
        #
        # `count 2`, not `any`: a gate with trigger "any" fires on the KEY
        # ALONE, returning `ins + bias` = 0.0 with an empty `in` tray - a real
        # fire, and this weave did exactly that on its first debug run, so
        # `canon` and `settle` both spoke on a round where `keep` had stayed
        # silent. Requiring two sparks makes the gate mean what it reads like.
        # (WINSTON's `alarm` and `show` gates carry the same `count 2` for the
        # same reason - trap 2 in this file's header.)
        w.knot("commit", verb="gate", trigger="count 2")
        cord("sep", "commit", port="key", strands=[Strand(delay=2)])
        cord("keep", "commit", port="in", strands=[Strand(delay=1)])

        # ---- the canon
        w.knot("canon", verb="pool")
        cord("commit", "canon", strands=[Strand(delay=1)])
        spells.teach("s_settle", self.r.settle(), replace=True)
        w.knot("settle", verb="spell", spell="s_settle")
        cord("commit", "settle", strands=[Strand(delay=1)])

        # ---- the ledger: the only exit
        w.knot("ledger", verb="fringe")
        cord("canon", "ledger", strands=[Strand(delay=1)])
        w.knot("f_settled", verb="fringe")
        cord("settle", "f_settled", strands=[Strand(delay=1)])

        w.seed("look", 1.0, beat=1)
        w.run_hint = self.horizon
        return w

    # -- one round ---------------------------------------------------------

    def run(self):
        w = self.weave()
        w.validate()
        res = Loom().run(w, self.horizon)
        fr = {k: res.fringe(k) for k in
              ("f_ceiling", "f_floor", "f_shuffle", "f_holdout",
               "f_alarm", "ledger", "f_settled")}
        return res, fr, w

    def merit(self, res):
        """The merit cord's weight after the round. Thicker = the round kept."""
        if res.learned is None or self._merit_slot is None:
            return None
        return res.learned[self._merit_slot]
