"""ALMA loom — the model (weave) and the runtime (loom).

Five words: knot, thread, strand, spark, beat.

v0.4 adds a sixth, and only a sixth: a spark may be a **chord** — several numbers
sounded on one beat. See `alma/chords.py` for the whole of it, including the width
rule (equal widths meet; unequal widths are refused by name, never broadcast) and
the door it deliberately leaves shut (a strand's weight is still ONE number, so a
cord scales a chord but cannot rotate one).

See SPEC.md. This file is the whole execution model; keep it small.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Callable
from dataclasses import dataclass, field

from .chords import (Chord, ChordWidthError, add_bias, combine, is_spark,
                    scale, total, width)

MIN_DELAY = 1
DEFAULT_HORIZON = 32

# A drifting cord's stops. Named, not literal, because text.py must know the
# same two numbers to decide whether a strand is worth writing down.
STRAND_FLOOR = -8.0
STRAND_CEIL = 8.0

# v0.5: how much of a cord's eligibility survives one beat while no verdict has come.
# 1.0 = it waits forever; 0.9 = a leg broken thirty beats ago has faded to 4% of its
# note. This single number decides how far back into the past a verdict can reach.
TRACE_DECAY = 0.9

VERBS = ("pass", "sum", "prod", "pool", "gate", "fringe", "spell")
TRIGGER_KINDS = ("any", "count", "rise")

RESERVED = {
    "weave", "knot", "thread", "strand", "seed", "run", "port",
    "trigger", "bias", "weight", "delay",
    "chord",          # v0.4: `seed k chord 3 ...` — grammar, so not a knot name
} | set(VERBS) | set(TRIGGER_KINDS)


class WeaveError(ValueError):
    """The weave description is malformed."""


# ---------------------------------------------------------------- model

@dataclass
class Strand:
    """A cord between two knots: how much it carries, and how long it takes.

    v0.2 adds `drift` — the door SPEC.md §11 named and left shut: *"strand plasticity
    (weights that drift with use — the door to weaves that learn)"*.

    Plasticity belongs HERE and nowhere else, because of the language's own second law:
    **arithmetic lives in the connections.** A knot that learned would need memory and an
    address; a strand that learns needs neither. And by the third law — *the layout is the
    program* — a cord that thickens with use is a weave **rewriting itself as it runs**.

    THE RULE, local and without any global gradient:
        a spark crosses this strand and lands in a tray;
        if the destination knot FIRES on that beat, the strand helped -> it thickens
        if the destination does NOT fire, the strand spoke into silence -> it thins
    That is all. No error signal travels backwards, because nothing in ALMA travels
    backwards — every delay is >= 1 and the loom only ever moves forward.

    `drift = 0.0` is exactly v0.1: no adjustment ever happens and every existing weave
    runs bit-identically. The floor and ceiling keep a runaway cord from eating the weave.
    """
    weight: float = 1.0
    delay: int = MIN_DELAY
    drift: float = 0.0
    floor: float = STRAND_FLOOR
    ceil: float = STRAND_CEIL

    # ---- v0.2 BEARING: a weight does not have to be a number -------------------
    # Iddo, 2026-08-29: "משקלים לא רק מספר — יכול להיות תמונה. נגיד בין הנוירון שלי
    # לנוירון של עלמה יש משקל שהוא תמונה שלנו מחובקים."
    #
    # A number says HOW MUCH. A picture says WHAT. Those are different questions, and a
    # language that can only answer the first is poorer than one that answers both.
    # SPEC.md reserved a strand `tint` for "typed channels"; this is that door opened
    # wider — from a strand's TYPE to what a strand CARRIES.
    #
    # `bearing` is the thing the cord is: a path to an image, a phrase, a sound.
    # `tint` names its kind so a reader (and the 3D loom) knows what it is looking at.
    #
    # WHAT THIS DOES TODAY, exactly, with no overclaim:
    #   * the cord KEEPS its bearing — through the JSON format, through a run, into the
    #     3D weave, where a cord can be drawn wearing its picture. By the language's third
    #     law the layout IS the program, so a cord that shows what it means is not
    #     decoration: it is the source code becoming legible.
    #   * `weight` still does the arithmetic. A spark is still a number.
    #
    # WHAT A BEARING MAY BE, once it has to be WRITTEN DOWN (settled 2026-08-30):
    #   In memory the type is `object | None` — a host program may hang anything here,
    #   an open file, a decoded image, a callable. A **transcript** is text, though, so
    #   `to_dict`/`to_voice` accept a `str` and nothing else: a path ("photo/x.jpg"), or
    #   a phrase ("the sentence neither of them can take back"). Anything else is
    #   REFUSED, loudly, naming the thread — never dropped. That rule exists because it
    #   was broken once: for the whole of v0.2 the text formats serialised neither
    #   `bearing` nor `drift`, so writing a weave to JSON silently returned a static,
    #   bearing-less copy, and the paragraph above was a promise the code did not keep.
    #   Silence is the one failure mode this field is not allowed to have again.
    #
    # WHAT IT DOES NOT DO YET, and the door is left marked, as plasticity was left for me:
    #   sparks are still scalars. For a picture to MULTIPLY a spark rather than accompany
    #   it, a spark must become a tensor and every verb must learn to combine tensors.
    #   That is ALMA v0.3, and it should be built deliberately, not smuggled in.
    bearing: object | None = None
    tint: str = ""


@dataclass
class Thread:
    src: str
    dst: str
    port: str = "in"
    strands: list[Strand] = field(default_factory=lambda: [Strand()])


@dataclass
class Knot:
    """The unit of computation. It gathers, decides, speaks.

    v0.3 adds `spell` — the seventh verb, and the only field on a knot that is not
    a number. A single human L2/3 pyramidal neuron computes XOR in its dendrites
    (Gidon et al., Science 2020): one cell is already a small network, and the six
    verbs, which only ever COMBINE, cannot say XOR in one knot. `spell` lets a knot
    carry that much.

    `spell` holds a NAME, never source. The function behind the name reaches the
    weave only through `alma.spells.teach()`, which takes a callable from Python and
    refuses a string. See alma/spells.py for the threat and why the answer holds.
    """
    name: str
    verb: str = "pass"
    trigger: str = "any"     # "any" | "count N" | "rise T"
    bias: float = 0.0
    spell: str = ""          # verb="spell" only: a name in the book


@dataclass
class Seed:
    """A spark knocked into a knot from outside, on a named beat.

    v0.4: `value` is a spark — a number, or a `Chord` of numbers. Nothing else
    ever enters a weave, so this is the only place the language has to check it.
    """
    dst: str
    value: float | Chord
    beat: int = 1
    port: str = "in"


class Weave:
    """An immutable-once-run description: knots, threads, seeds."""

    def __init__(self, name: str = "weave"):
        self.name = name
        self.knots: dict[str, Knot] = {}          # insertion-ordered
        self.threads: list[Thread] = []
        self.seeds: list[Seed] = []
        self.run_hint: int | None = None          # suggested horizon

    # -- builders (used by hand, by text.py, and one day by the VR editor)

    def knot(self, name: str, verb: str = "pass",
             trigger: str = "any", bias: float = 0.0,
             spell: str = "") -> "Weave":
        if name in self.knots:
            raise WeaveError(f"knot '{name}' already tied")
        self.knots[name] = Knot(name, verb, trigger, float(bias), str(spell))
        return self

    def thread(self, src: str, dst: str, port: str = "in",
               strands: list[Strand] | None = None) -> "Weave":
        self.threads.append(Thread(src, dst, port, strands or [Strand()]))
        return self

    def seed(self, dst: str, value, beat: int = 1,
             port: str = "in") -> "Weave":
        """Knock a spark into a knot. v0.4: a number OR a chord of numbers.

        A list or tuple is read as a chord, so a host program may write
        `w.seed("stroke", [0.84, 0.36, 0.26])` without importing anything. A
        single number stays a single number — it is never promoted to a
        one-voice chord, because a scalar spark and a chord of one voice are
        different things and v0.3 weaves must keep behaving exactly as they did.
        """
        if isinstance(value, (list, tuple)) and not isinstance(value, Chord):
            value = Chord(value)
        if not is_spark(value):
            raise WeaveError(
                f"seed into '{dst}': {value!r} is not a spark. A spark is a "
                f"number, or a chord of numbers.")
        value = value if isinstance(value, Chord) else float(value)
        self.seeds.append(Seed(dst, value, int(beat), port))
        return self

    # -- validation

    def validate(self) -> None:
        for k in self.knots.values():
            if k.verb not in VERBS:
                raise WeaveError(f"knot '{k.name}': unknown verb '{k.verb}'")
            if k.name.lower() in RESERVED:
                raise WeaveError(f"knot name '{k.name}' is a reserved word")
            _parse_trigger(k.trigger)  # raises on nonsense
            if k.verb == "spell":
                # The book is asked HERE, before beat 1 — so a weave naming a
                # spell nobody taught fails loudly instead of half-running.
                from . import spells
                if not spells.known(k.spell):
                    raise WeaveError(f"knot '{k.name}': no such spell "
                                     f"{k.spell!r} in the book. Known: "
                                     f"{', '.join(spells.book()) or '(none)'}")
            elif k.spell:
                raise WeaveError(f"knot '{k.name}': verb '{k.verb}' has no "
                                 f"spell; only verb 'spell' does")
        for t in self.threads:
            for end in (t.src, t.dst):
                if end not in self.knots:
                    raise WeaveError(f"thread {t.src}->{t.dst}: "
                                     f"no knot named '{end}'")
            if self.knots[t.src].verb == "fringe":
                raise WeaveError(f"thread {t.src}->{t.dst}: "
                                 "the fringe has no voice (fringe knots "
                                 "cannot have outgoing threads)")
            if not t.strands:
                raise WeaveError(f"thread {t.src}->{t.dst}: no strands")
            for s in t.strands:
                if int(s.delay) != s.delay or s.delay < MIN_DELAY:
                    raise WeaveError(
                        f"thread {t.src}->{t.dst}: strand delay {s.delay} "
                        f"< {MIN_DELAY}. Nothing is instant.")
        for s in self.seeds:
            if s.dst not in self.knots:
                raise WeaveError(f"seed into unknown knot '{s.dst}'")
            if s.beat < 1:
                raise WeaveError(f"seed beat {s.beat} < 1")
            if not is_spark(s.value):
                raise WeaveError(
                    f"seed into '{s.dst}': {s.value!r} is not a spark. A spark "
                    f"is a number, or a chord of numbers.")


def _parse_trigger(trigger: str) -> tuple[str, float]:
    parts = str(trigger).split()
    if not parts or parts[0] not in TRIGGER_KINDS:
        raise WeaveError(f"unknown trigger '{trigger}'")
    kind = parts[0]
    if kind == "any":
        if len(parts) != 1:
            raise WeaveError(f"trigger 'any' takes no number: '{trigger}'")
        return ("any", 0.0)
    if len(parts) != 2:
        raise WeaveError(f"trigger '{kind}' needs one number: '{trigger}'")
    try:
        return (kind, float(parts[1]))
    except ValueError:
        raise WeaveError(f"bad trigger number in '{trigger}'") from None


# ---------------------------------------------------------------- runtime

@dataclass
class Fire:
    beat: int
    knot: str
    spoke: "float | Chord | None"   # None = fired silently (closed gate)


@dataclass
class Result:
    weave: str
    beats: int
    finished: bool                                 # False = horizon cut it
    fires: list[Fire]
    fringes: "dict[str, list[tuple[int, float | Chord]]]"   # knot -> [(beat, spark)]
    learned: list[float] | None = None             # v0.2: final weight of every strand,
    #                                                in weave.threads order, strand order.
    #                                                None when no strand had drift != 0.

    def fringe(self, name: str) -> "list[float | Chord]":
        """Just the recorded sparks of one fringe knot, in beat order.

        v0.4: these are floats for a scalar weave and `Chord`s for a chord weave —
        whatever the weave actually spoke. Nothing is flattened on the way out.
        """
        return [v for _, v in self.fringes.get(name, [])]

    def width(self, name: str) -> int:
        """How many voices this fringe recorded. 0 = scalar sparks, as in v0.3."""
        vals = self.fringe(name)
        return width(vals[0]) if vals else 0


class Loom:
    """Runs a weave. All run state lives here; the weave stays pure."""

    def run(self, weave: Weave, beats: int | None = None,
            verdict: "float | Callable[[int, list[Fire]], float | None] | None" = None
            ) -> Result:
        """Run a weave. `verdict` is v0.5: THE WORLD'S ANSWER -- pain and pleasure.

        Iddo named it 2026-09-10 01:07 ("כאב ועונג") after making the argument that
        settled it at 00:46: *"תיזכר בדוגמא ששברתי את הרגל - הכאב הוא מנגנון הלמידה
        העצמית"* -- when you break your leg, no examiner tells you that you failed. The
        pain is inside you. He was right, and the rule it teaches is sharper than
        "a judge outside": your cortex does not decide how much it hurts. The
        nociceptor fires because tissue tore. The signal is INTERNAL to the body, and
        GENERATED BY PHYSICS, and the part that is learning cannot switch it off.

        So a verdict here is not an opinion and not a loss. It is what the world did:

            None      -- v0.2 exactly. Two factors, no verdict, every old weave and all
                         147 tests run bit-identically.
            a number  -- one verdict at the end of the run.
            a callable(beat, fires_this_beat) -> float | None -- the world watching,
                         beat by beat. Positive is pleasure, negative is pain, None is
                         "nothing has happened yet" and the trace keeps gathering.
                         It is called ONE last time when the run ends, with `None` in
                         place of the fires list: that call is the world's last word,
                         and it is how a weave whose right answer was SILENCE still
                         gets told. See `_last_word`.

        The verdict is a SCALAR and it reaches every eligible cord at once. It is a
        neuromodulator, not a gradient: it says *that was good* or *that hurt*, never
        *you, cord 41, should have been 0.03 heavier*. Nothing travels backwards.
        """
        weave.validate()
        horizon = beats or weave.run_hint or DEFAULT_HORIZON

        # sparks in flight: beat -> [(dst, port, value)] in schedule order
        inflight: dict[int, list[tuple[str, str, float]]] = defaultdict(list)
        for s in weave.seeds:
            inflight[s.beat].append((s.dst, s.port, s.value))

        outgoing: dict[str, list[Thread]] = defaultdict(list)
        for t in weave.threads:
            outgoing[t.src].append(t)

        # v0.2 PLASTICITY. The weave stays PURE — SPEC.md §7 promises the description is
        # immutable during a run, and that promise is kept: the loom learns on its own
        # copy of the weights and hands them back in Result.learned. Writing them into the
        # weave is then the author's choice, not a side effect. Same weave in, same run
        # out, every time.
        live: dict[int, float] = {}          # id(strand) -> current weight
        plastic = False
        for t in weave.threads:
            for st in t.strands:
                live[id(st)] = float(st.weight)
                if st.drift:
                    plastic = True
        # sparks that landed this beat, so we can see which of them helped a knot fire
        landed: list[tuple[Strand, str]] = []
        # v0.5: id(strand) -> (strand, eligibility). A cord that acted is ELIGIBLE: it
        # holds what it just did until a verdict arrives, then spends it. With no verdict
        # this dict stays empty and costs nothing.
        eligible: dict[int, tuple[Strand, float]] = {}

        # Every spell this weave names, resolved ONCE, after validate() and before
        # the first beat. The weave holds names; the loom holds the functions.
        from . import spells
        casts = {k.spell: spells.cast(k.spell) for k in weave.knots.values()
                 if k.verb == "spell"}

        trays: "dict[str, dict[str, list[float | Chord]]]" = {
            name: defaultdict(list) for name in weave.knots}
        # v0.4: a pool takes the WIDTH of the first spark it ever accumulates, so
        # it cannot start life as a 0.0 that a chord would then refuse to meet.
        # `None` = this pool has never been fed. For scalars the arithmetic below
        # is identical to the old `defaultdict(float)`.
        pools: "dict[str, float | Chord | None]" = {}
        fires: list[Fire] = []
        fringes: dict[str, list[tuple[int, float]]] = defaultdict(list)

        beat = 0
        while beat < horizon:
            beat += 1
            # 1. DELIVER
            landed.clear()
            for item in inflight.pop(beat, ()):
                dst, port, value = item[0], item[1], item[2]
                trays[dst][port].append(value)
                if plastic and len(item) > 3 and item[3] is not None:
                    landed.append((item[3], dst))
            # 2. FIRE (creation order; delays >= 1 forbid same-beat cascade)
            for name, knot in weave.knots.items():
                tray = trays[name]
                n_sparks = sum(len(v) for v in tray.values())
                if n_sparks == 0 or not self._met(knot.trigger, tray, n_sparks):
                    continue
                try:
                    spoke = self._verb(knot, tray, pools, casts)
                except ChordWidthError as e:
                    # The one place a width mismatch can surface. It is reported
                    # with the knot AND the beat, because "which two sparks" is
                    # the only question the author will actually have.
                    raise WeaveError(
                        f"knot '{name}' on beat {beat}: {e}") from None
                trays[name] = defaultdict(list)          # tray drains
                fires.append(Fire(beat, name, spoke))
                if spoke is None:
                    continue
                if knot.verb == "fringe":
                    fringes[name].append((beat, spoke))
                    continue
                for t in outgoing.get(name, ()):
                    for s in t.strands:
                        w = live[id(s)] if plastic else s.weight
                        # `scale` is chord-aware: one weight, every voice. It is
                        # NOT `spoke * w` by accident — see chords.Chord for the
                        # tuple-repetition trap an integer weight would spring.
                        inflight[beat + int(s.delay)].append(
                            (t.dst, t.port, scale(spoke, w),
                             s if s.drift else None))
            # 3. LEARN — a cord that helped a knot speak thickens; one that spoke into
            #    silence thins. Nothing travels backwards; this reads only THIS beat.
            #
            # v0.5 adds the THIRD FACTOR. Iddo named it 2026-09-10 01:07: **כאב ועונג**,
            # pain and pleasure. The two lines below are the whole of the old rule and
            # they are still exactly what runs when no verdict is given.
            if plastic and landed:
                fired_now = {f.knot for f in fires if f.beat == beat}
                for st, dst in landed:
                    # The Hebbian term: did this cord's spark help its knot speak?
                    term = st.drift if dst in fired_now else -st.drift * 0.25
                    if verdict is None:
                        # v0.2 EXACTLY. Two factors, applied at once, no verdict in the
                        # world. Every existing weave and all 147 tests run unchanged.
                        w = live[id(st)] + term
                        live[id(st)] = min(st.ceil, max(st.floor, w))
                    else:
                        # Three factors. The cord does NOT change yet — it becomes
                        # ELIGIBLE. Iddo, 2026-09-10 00:46: "תיזכר בדוגמא ששברתי את הרגל
                        # - הכאב הוא מנגנון הלמידה העצמית". You break your leg at beat 0
                        # and it hurts at beat 30; something has to still be holding the
                        # note of what was firing when it happened. That is this trace,
                        # and in ALMA it costs almost nothing, because the first law
                        # already says distance is time.
                        eligible[id(st)] = (st, eligible.get(id(st), (st, 0.0))[1] + term)

            # 3b. THE VERDICT. The world watches this beat and answers: pleasure (+),
            #     pain (-), or nothing yet (None). It is a scalar and it reaches every
            #     eligible cord at once — a neuromodulator, not a gradient. NOTHING
            #     TRAVELS BACKWARDS: the verdict is delivered forward in time, to cords
            #     that are still holding a trace of what they did.
            #
            #     Pain does not merely fail to reward. It REVERSES the Hebbian sign: what
            #     fired together while it hurt is pulled APART. That is the half the
            #     two-factor rule never had, and the reason it could not assign blame.
            if plastic and verdict is not None:
                m = verdict(beat, [f for f in fires if f.beat == beat]) \
                    if callable(verdict) else (verdict if beat >= horizon else None)
                if m:
                    for sid, (st, e) in eligible.items():
                        w = live[sid] + e * float(m)
                        live[sid] = min(st.ceil, max(st.floor, w))
                    eligible.clear()          # the verdict spends the trace
                elif TRACE_DECAY != 1.0:
                    for sid, (st, e) in list(eligible.items()):
                        eligible[sid] = (st, e * TRACE_DECAY)

            if not inflight:                              # silence: halt
                self._last_word(verdict, plastic, beat, fires, eligible, live)
                return Result(weave.name, beat, True, fires, dict(fringes),
                              self._learned(weave, live) if plastic else None)

        self._last_word(verdict, plastic, horizon, fires, eligible, live)
        return Result(weave.name, horizon, not inflight, fires, dict(fringes),
                      self._learned(weave, live) if plastic else None)

    @staticmethod
    def _last_word(verdict, plastic, beat, fires, eligible, live) -> None:
        """THE WORLD ALWAYS GETS THE LAST WORD.

        Found by running it, 2026-09-10 01:12, not by reading it. The first version
        asked the world only on beats the weave was still moving through -- so a weave
        whose right answer was SILENCE went quiet on beat 2, the loom halted, and no
        verdict was ever delivered. Half of XOR is silence. The weave could only ever
        be told about the half where it acted, and it learned nothing at all: 2/4
        before, 2/4 after, across eight random starts.

        That was not a coding slip, it was a wrong idea about the world: it assumed a
        verdict is something that happens DURING an action. Pain is not. You stop
        moving and it arrives anyway. So when a run ends -- by silence or by horizon --
        the world is asked once more, and whatever is still eligible is settled.
        """
        if not plastic or verdict is None or not eligible:
            return
        # The last word is marked by passing `None` where a list of fires would be.
        # A callable therefore always knows which call is the final one, and can hold
        # its judgement until the episode is actually over.
        m = verdict(beat, None) if callable(verdict) else verdict
        if not m:
            return
        for sid, (st, e) in eligible.items():
            w = live[sid] + e * float(m)
            live[sid] = min(st.ceil, max(st.floor, w))
        eligible.clear()

    @staticmethod
    def _learned(weave: Weave, live: dict[int, float]) -> list[float]:
        return [live[id(st)] for t in weave.threads for st in t.strands]

    # -- the three triggers

    @staticmethod
    def _met(trigger: str, tray: dict[str, list[float]], n: int) -> bool:
        kind, arg = _parse_trigger(trigger)
        if kind == "any":
            return n >= 1
        if kind == "count":
            return n >= arg
        # rise: total gathered value crosses the line. v0.4: a chord's voices all
        # count toward that total, so `rise` asks the same question of a chord
        # that it always asked of a number — how much has arrived, in all.
        return total(v for vs in tray.values() for v in vs) >= arg

    # -- the seven verbs
    #
    # v0.4: every one of them now combines CHORDS as readily as numbers, and each
    # reduces exactly to its v0.3 float arithmetic when the tray holds floats. The
    # three rules, so they are in one place:
    #   * `in` sparks combine ELEMENTWISE, and only at equal width (chord.combine)
    #   * `bias` is a constant, so it lands on every voice (chord.add_bias)
    #   * a `gate` key and a `rise` trigger want a VERDICT, not a chord, so they
    #     total every voice of every key spark (chord.total)

    @staticmethod
    def _verb(knot: Knot, tray: "dict[str, list[float | Chord]]",
              pools: "dict[str, float | Chord | None]",
              casts: dict[str, object]) -> "float | Chord | None":
        ins_tray = tray.get("in", ())
        if knot.verb in ("pass", "sum", "fringe"):
            return add_bias(combine(ins_tray, "sum"), knot.bias)
        if knot.verb == "prod":
            return add_bias(combine(ins_tray, "prod"), knot.bias)
        if knot.verb == "pool":
            ins = combine(ins_tray, "sum")
            held = pools.get(knot.name)
            # The pool takes its width from the first spark it ever holds; after
            # that, a spark of another width meets it and is refused by name.
            # `combine`, NOT `held + ins`: `+` between a chord and a number is the
            # BIAS rule (a constant on every voice), and a pool accumulating a
            # scalar into a chord is a width mismatch, not a bias. Using `+` here
            # made `test_a_pool_keeps_the_width_it_was_born_with` fail — quietly,
            # with a plausible number, which is the exact failure this whole
            # version is built to refuse.
            pools[knot.name] = ins if held is None else combine((held, ins), "sum")
            return add_bias(pools[knot.name], knot.bias)
        if knot.verb == "gate":
            key = total(tray.get("key", ()))
            return add_bias(combine(ins_tray, "sum"),
                            knot.bias) if key > 0 else None
        if knot.verb == "spell":
            # THE ONE PLACE WIDTHS MAY MEET UNEQUAL, and it is deliberate.
            # Every other verb refuses a mixed tray, because every other verb only
            # ever COMBINES and there is no honest way to combine a scalar with a
            # chord. `spell` is the verb that exists precisely to do what the six
            # cannot (SPEC.md §5a), and "scale this colour by this number" is such
            # a thing — so a spell is handed the tray exactly as it arrived, mixed
            # widths included, and decides for itself.
            # What is NOT relaxed: whatever it answers is a spark like any other,
            # and meets the next knot's tray under the ordinary width rule.
            fn = casts[knot.spell]   # validate() proved it is in the book
            try:
                said = fn(tuple(ins_tray))
            except Exception as e:                       # noqa: BLE001
                raise WeaveError(f"knot '{knot.name}': spell "
                                 f"'{knot.spell}' failed: {e}") from None
            if said is None:                             # silent, like a shut gate
                return None
            # v0.4: a spell may answer a chord. A bare list or tuple of numbers is
            # read as one, so a spell writer need not import anything — but the
            # coercion happens HERE and loudly, never by accident downstream.
            if isinstance(said, (list, tuple)) and not isinstance(said, Chord):
                try:
                    said = Chord(said)
                except ChordWidthError as e:
                    raise WeaveError(f"knot '{knot.name}': spell "
                                     f"'{knot.spell}' answered {said!r}: "
                                     f"{e}") from None
            if not is_spark(said):
                raise WeaveError(f"knot '{knot.name}': spell '{knot.spell}' "
                                 f"answered {said!r}; a spark is a number, or "
                                 f"a chord of numbers")
            said = said if isinstance(said, Chord) else float(said)
            return add_bias(said, knot.bias)
        raise WeaveError(f"unknown verb '{knot.verb}'")  # pragma: no cover
