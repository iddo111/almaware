# -*- coding: utf-8 -*-
"""THE TOPOLOGY. שקלא וטריא as a shape, not as a prompt.

`D:\\CLAUDE\\quorum\\shakla.py` already runs the four moves — it asks an LLM,
in Hebrew, to write a קושיא and then a תירוץ. The form lives in the sentence.
Here the form lives in the weave, and every move is a piece of ALMA:

    ראיה   what each seat reads in the evidence — feature knots into that
           seat's own hidden knots, over that seat's own cords. Two seats,
           two independent readings of one page.
    טענה   `<seat>_arg`, a `sum` knot with a SELF-THREAD at delay 2. A position
           is not asserted once; it keeps being asserted, every round, at the
           same strength, until something stops it. The cycle IS the rounds.
    קושיא  `<seat>_gate` -> the OPPONENT's standing-pool, on a NEGATIVE cord.
           An attack is literally subtraction from where the other seat stands.
    תירוץ  the same spark -> its OWN standing-pool, positively. Speaking in
           your own defence is what keeps you standing.
    חזקה   both pools are SEEDED positive at beat 1. A position is presumed to
           stand until it is refuted; nobody has to earn the right to speak.
    דחייה  `<seat>_gate` is a `gate` whose `key` port is fed by its own
           standing-pool. ALMA's gate speaks only when its key sums ABOVE ZERO.
           So when a seat's standing falls to nothing, its gate still fires —
           and says NOTHING. It has conceded. And because it has gone silent,
           its opponent stops receiving קושיא and rises unopposed, while it
           keeps receiving and keeps falling. Concession is not a flag someone
           sets. It is a fixed point of the dynamics.
    מסקנה  two `fringe` knots at the hem recording the two standings, beat by
           beat. Who is left standing, by how much, and when the other folded.

WHAT IS GIVEN AND WHAT IS LEARNED — the honest line
---------------------------------------------------
GIVEN:     the form. Every cord drawn in `_structure()` below has `drift=0`:
           the gate plumbing, the self-thread, the sign of a קושיא, the חזקה.
           That is the שקלא וטריא itself, and it is not up for negotiation any
           more than `xor_pain.py` negotiates its thresholds.
LEARNED:   every cord in `_reading()`: feature -> hidden, and hidden -> טענה,
           for each seat separately. What each side SEES in the evidence.
NOT GIVEN: a single weight. They start random and small.
NOT GIVEN: any gradient. Nothing travels backwards; every delay is ≥ 1 beat.

THE BEAT SCHEDULE (verified by `trace()`, and it is worth checking by hand)
--------------------------------------------------------------------------
    b1   seeds land. feature knots and `one` fire; both stand-pools fire (חזקה)
    b2   hidden knots fire — those whose evidence crosses their threshold
    b3   each `_arg` fires: this seat's טענה, and it starts its own echo
    b4   ROUND 1. both gates fire: each speaks, or is silent because it stands
         at nothing
    b5   both pools take this round's קושיא and תירוץ and speak the new standing
    b6   ROUND 2 …and so on, one round every two beats, until the horizon.

The startup costs 3 beats and each round costs 2, so `beats=4+2*(R-1)` buys R
rounds. The default 14 is 6 rounds.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from alma import Loom, Weave
from alma.loom import Strand, Thread

from .encoding import SEAT_M, SEAT_Q, Argument

SEATS = (SEAT_M, SEAT_Q)

# --- the form. These are structure, not parameters to tune into an answer. ---
CHAZAKA = 1.0        # standing a position is granted before anyone speaks
AMIDA = 1.0          # Round 0 — the bare עמדה, asserted before any ראיה
KUSHIA = 1.0         # how much an attack takes off the opponent's standing
TIRUTZ = 0.5         # how much speaking in your own defence restores
ECHO = 2             # beats between one assertion of a position and the next
SPREAD = 0.6         # how far the hidden thresholds reach either side of zero

DEFAULT_BEATS = 14   # 6 rounds
DEFAULT_HIDDEN = 4   # reasons per seat
DEFAULT_DRIFT = 0.05


@dataclass
class Round:
    beat: int
    index: int
    m_spoke: bool
    q_spoke: bool
    stand_m: float
    stand_q: float


@dataclass
class Conclusion:
    """מסקנה — what the weave says when the beats run out."""
    winner: str                       # SEAT_M, SEAT_Q, or "תיקו"
    stand_m: float
    stand_q: float
    rounds: list[Round] = field(default_factory=list)
    conceded_m: int | None = None     # round index at which the seat went silent
    conceded_q: int | None = None
    machloket_stands: bool = False    # both still standing when the beats ran out

    def line(self, seat_m: str = "מתרץ", seat_q: str = "מקשן") -> str:
        """The one line a מסקנה has to end with.

        The seat names come from the Argument, so a syllogism ends in
        "הלכה כמתרץ" and a real dispute ends in "הלכה כבית הלל".
        """
        if self.winner == "תיקו":
            return "מסקנה: תיקו — שני הצדדים עומדים, והמחלוקת לא הוכרעה."
        who = seat_m if self.winner == SEAT_M else seat_q
        conceded = self.conceded_q if self.winner == SEAT_M else self.conceded_m
        if conceded is not None:
            return (f"מסקנה: הלכה כ{who} — "
                    f"בר-הפלוגתא נדחה בסבב {conceded} ומשם ואילך שתק.")
        return (f"מסקנה: הלכה כ{who} — "
                f"עמד בעוז {self.stand_m:+.2f} מול {self.stand_q:+.2f}.")


# ------------------------------------------------------------------ building

def _seat_knots(w: Weave, seat: str, hidden: int, thresholds: list[float]) -> None:
    for i in range(hidden):
        w.knot(f"{seat}_h{i}", verb="sum", trigger=f"rise {thresholds[i]}")
    w.knot(f"{seat}_arg", verb="sum", trigger="any")
    w.knot(f"{seat}_gate", verb="gate", trigger="count 2")
    w.knot(f"{seat}_stand", verb="pool", trigger="any")
    w.knot(f"say_{seat}", verb="fringe", trigger="any")


def _reading(w: Weave, seat: str, features: list[str], hidden: int,
             rng: random.Random, drift_in: float, drift_out: float,
             scale: float) -> None:
    """THE LEARNED PART. What this seat sees. Every weight random.

    The two layers carry SEPARATE drifts because they are learned by separate
    rules, and that split is the whole argument of `train.py`:

      `drift_out` (hidden -> טענה) is where the loom's three-factor rule is
        already correct. `xor_pain.py` measured this: at the OUTPUT knot,
        pain-and-pleasure is a proper reward-modulated perceptron.
      `drift_in`  (feature -> hidden) is where it is NOT. One global scalar
        verdict reaches every hidden cord with the same sign on the same beat,
        so nothing can tell h0 "you should have fired" while telling h1 the
        opposite. That is Minsky and Papert's objection, restated. Set this to
        0 and let node perturbation own the layer instead (train.py).
    """
    def cord(drift: float, delay: int = 1) -> Strand:
        return Strand(weight=rng.uniform(-scale, scale), delay=delay, drift=drift)

    for name in features:
        for i in range(hidden):
            w.threads.append(Thread(f"f_{name}", f"{seat}_h{i}", "in",
                                    [cord(drift_in)]))
    for i in range(hidden):
        # `one` is the seat's own leaning before it reads anything — a bias, and
        # a cord like any other, so it is learned like any other.
        w.threads.append(Thread("one", f"{seat}_h{i}", "in", [cord(drift_in)]))
        w.threads.append(Thread(f"{seat}_h{i}", f"{seat}_arg", "in",
                                [cord(drift_out)]))


def _structure(w: Weave, seat: str, other: str) -> None:
    """THE GIVEN PART. The dialectic itself. Every cord here has drift 0."""
    def fixed(weight: float, delay: int = 1) -> Strand:
        return Strand(weight=weight, delay=delay, drift=0.0)

    # ROUND 0 — עמדה. Found by running the weave: without this cord a seat whose
    # hidden knots all stayed below threshold had NOTHING in its `arg` tray, so
    # its gate never received an `in` spark, so it never spoke — and `conclude()`
    # read that silence as a דחייה. A seat was being recorded as having conceded
    # when in truth it had never been given a mouth. In the form, Round 0 is
    # exactly the seat stating its עמדה BEFORE any ראיה is brought, so the fix is
    # the form's own: every position is asserted, at a fixed strength, whether or
    # not the evidence moved it. What the hidden knots add on top is the ראיה.
    # Delay 2 puts it the same DISTANCE from `arg` as the path through the hidden
    # knots — `xor_pain.py` paid for that lesson once (its bias cord arrived a
    # beat early and decided the answer before any thinking got there).
    w.threads.append(Thread("one", f"{seat}_arg", "in", [fixed(AMIDA, 2)]))
    # a position keeps being asserted, once every ECHO beats, at its own strength
    w.threads.append(Thread(f"{seat}_arg", f"{seat}_arg", "in", [fixed(1.0, ECHO)]))
    # …into the gate, which lets it out only while the seat still stands
    w.threads.append(Thread(f"{seat}_arg", f"{seat}_gate", "in", [fixed(1.0)]))
    w.threads.append(Thread(f"{seat}_stand", f"{seat}_gate", "key", [fixed(1.0)]))
    # תירוץ into itself, קושיא into the opponent
    w.threads.append(Thread(f"{seat}_gate", f"{seat}_stand", "in", [fixed(TIRUTZ)]))
    w.threads.append(Thread(f"{seat}_gate", f"{other}_stand", "in", [fixed(-KUSHIA)]))
    # the hem
    w.threads.append(Thread(f"{seat}_stand", f"say_{seat}", "in", [fixed(1.0)]))


def build(features: list[str], seed: int = 0, hidden: int = DEFAULT_HIDDEN,
          drift_in: float = DEFAULT_DRIFT, drift_out: float = DEFAULT_DRIFT,
          beats: int = DEFAULT_BEATS, scale: float = 1.0,
          typical_present: int = 5) -> Weave:
    """The whole shape. `features` is every feature name the corpus can produce.

    `typical_present` is how many feature knots usually fire at once; the
    hidden thresholds are scaled by its square root so the same threshold
    spread works for a 16-feature corpus and a 40-feature one. That is
    arithmetic about the input, not a hint about the answer.
    """
    rng = random.Random(seed)
    w = Weave("shakla")
    for name in features:
        w.knot(f"f_{name}", verb="pass", trigger="any")
    w.knot("one", verb="pass", trigger="any")

    # A spread of thresholds gives the seat several different places to stand.
    # The weave is never told which reason is which; the verdict decides that.
    #
    # The spread straddles ZERO rather than sitting above it, and that was a fix,
    # not a preference. With all four thresholds positive, a typical seat had one
    # hidden knot fire out of four and often none at all — a seat with nothing to
    # read. Straddling zero puts the firing rate near half, which is what makes
    # SILENCE informative: in ALMA credit is carried by which knots stayed quiet
    # (see encoding.py), and a knot that never fires, or always does, carries none.
    span = scale * math.sqrt(max(1, typical_present))
    thresholds = [round(span * SPREAD * (2.0 * (i + 1) / (hidden + 1) - 1.0), 3)
                  for i in range(hidden)]

    for seat in SEATS:
        _seat_knots(w, seat, hidden, thresholds)
    for seat in SEATS:
        _reading(w, seat, features, hidden, rng, drift_in, drift_out, scale)
    for seat, other in ((SEAT_M, SEAT_Q), (SEAT_Q, SEAT_M)):
        _structure(w, seat, other)

    w.run_hint = beats
    return w


def learned_strands(w: Weave) -> list[Strand]:
    """Every strand, in the order `Result.learned` reports them."""
    return [st for t in w.threads for st in t.strands]


def hidden_input_strands(w: Weave, seat: str, i: int) -> list[Strand]:
    """Every cord landing on one hidden knot. Node perturbation needs these."""
    dst = f"{seat}_h{i}"
    return [st for t in w.threads if t.dst == dst for st in t.strands]


# ------------------------------------------------------------------- running

def seed_argument(w: Weave, arg: Argument) -> None:
    """Plant the evidence. Present features are seeded; absent ones stay silent."""
    w.seeds = []
    for name in arg.features:
        w.seed(f"f_{name}", 1.0, beat=1)
    w.seed("one", 1.0, beat=1)
    w.seed(f"{SEAT_M}_stand", CHAZAKA, beat=1)     # חזקה
    w.seed(f"{SEAT_Q}_stand", CHAZAKA, beat=1)


def conclude(result, beats: int) -> Conclusion:
    """Read the מסקנה off what the run actually did. No opinion enters here."""
    stands = {SEAT_M: [], SEAT_Q: []}
    for seat in SEATS:
        stands[seat] = list(result.fringes.get(f"say_{seat}", []))

    spoke = {SEAT_M: {}, SEAT_Q: {}}
    for f in result.fires:
        for seat in SEATS:
            if f.knot == f"{seat}_gate":
                spoke[seat][f.beat] = f.spoke is not None

    round_beats = sorted(set(spoke[SEAT_M]) | set(spoke[SEAT_Q]))
    rounds, conceded = [], {SEAT_M: None, SEAT_Q: None}
    for idx, b in enumerate(round_beats, start=1):
        sm, sq = spoke[SEAT_M].get(b, False), spoke[SEAT_Q].get(b, False)
        # The standing AFTER this round is the first one recorded past its beat;
        # for the last round the horizon cuts that off, so fall back to the last
        # standing on record. Reporting 0.00 there (as this did until it was run)
        # is not "no standing", it is "nothing was measured", and the two must
        # never print the same.
        after_m = next((v for bb, v in stands[SEAT_M] if bb > b),
                       stands[SEAT_M][-1][1] if stands[SEAT_M] else 0.0)
        after_q = next((v for bb, v in stands[SEAT_Q] if bb > b),
                       stands[SEAT_Q][-1][1] if stands[SEAT_Q] else 0.0)
        rounds.append(Round(b, idx, sm, sq, float(after_m), float(after_q)))
        for seat, said in ((SEAT_M, sm), (SEAT_Q, sq)):
            if not said and conceded[seat] is None:
                conceded[seat] = idx

    final_m = float(stands[SEAT_M][-1][1]) if stands[SEAT_M] else 0.0
    final_q = float(stands[SEAT_Q][-1][1]) if stands[SEAT_Q] else 0.0

    # WHO IS LEFT STANDING. A seat that conceded has lost, however the numbers
    # ended; otherwise the higher standing wins, and an exact tie is a תיקו.
    if conceded[SEAT_Q] is not None and conceded[SEAT_M] is None:
        winner = SEAT_M
    elif conceded[SEAT_M] is not None and conceded[SEAT_Q] is None:
        winner = SEAT_Q
    elif final_m > final_q:
        winner = SEAT_M
    elif final_q > final_m:
        winner = SEAT_Q
    else:
        winner = "תיקו"

    return Conclusion(
        winner=winner, stand_m=final_m, stand_q=final_q, rounds=rounds,
        conceded_m=conceded[SEAT_M], conceded_q=conceded[SEAT_Q],
        machloket_stands=(conceded[SEAT_M] is None and conceded[SEAT_Q] is None),
    )


def debate(loom: Loom, w: Weave, arg: Argument, beats: int = DEFAULT_BEATS,
           verdict=None) -> tuple[Conclusion, object]:
    """One full שקלא וטריא. Returns the מסקנה and the raw run."""
    seed_argument(w, arg)
    r = loom.run(w, beats=beats, verdict=verdict)
    return conclude(r, beats), r


def trace(arg: Argument, features: list[str], seed: int = 0,
          beats: int = DEFAULT_BEATS) -> str:
    """Beat by beat, in words. The check that the schedule above is real."""
    w = build(features, seed=seed, beats=beats)
    c, r = debate(Loom(), w, arg, beats=beats)
    out = [f"{arg.id}   {arg.text}", ""]
    by_beat: dict[int, list[str]] = {}
    for f in r.fires:
        if f.knot.startswith("f_"):
            continue
        said = "שותק" if f.spoke is None else f"{f.spoke:+.3f}"
        by_beat.setdefault(f.beat, []).append(f"{f.knot}={said}")
    for b in sorted(by_beat):
        out.append(f"  beat {b:2d}   " + "  ".join(by_beat[b]))
    out.append("")
    wm = max(len(arg.seat_m), len(arg.seat_q))
    for rd in c.rounds:
        out.append(f"  סבב {rd.index}  (beat {rd.beat:2d})   "
                   f"{arg.seat_m:{wm}s} {'דיבר' if rd.m_spoke else 'שתק '}   "
                   f"{arg.seat_q:{wm}s} {'דיבר' if rd.q_spoke else 'שתק '}   "
                   f"עמידה {rd.stand_m:+.2f} / {rd.stand_q:+.2f}")
    out.append("")
    out.append("  " + c.line(arg.seat_m, arg.seat_q))
    return "\n".join(out)


if __name__ == "__main__":
    from .encoding import encode_syllogism, syllogism_feature_names
    from .syllogism import Syllogism

    names = syllogism_feature_names("raw")
    for key, fig in (("AAA", 1), ("AAA", 2)):
        s = Syllogism(fig, key)
        print(trace(encode_syllogism(s, "raw"), names, seed=1))
        print("-" * 72)
