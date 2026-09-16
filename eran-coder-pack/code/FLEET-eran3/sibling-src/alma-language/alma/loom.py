"""ALMA loom — the model (weave) and the runtime (loom).

Five words: knot, thread, strand, spark, beat.
See SPEC.md. This file is the whole execution model; keep it small.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

MIN_DELAY = 1
DEFAULT_HORIZON = 32

# A drifting cord's stops. Named, not literal, because text.py must know the
# same two numbers to decide whether a strand is worth writing down.
STRAND_FLOOR = -8.0
STRAND_CEIL = 8.0

VERBS = ("pass", "sum", "prod", "pool", "gate", "fringe", "spell")
TRIGGER_KINDS = ("any", "count", "rise")

RESERVED = {
    "weave", "knot", "thread", "strand", "seed", "run", "port",
    "trigger", "bias", "weight", "delay",
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
    dst: str
    value: float
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

    def seed(self, dst: str, value: float, beat: int = 1,
             port: str = "in") -> "Weave":
        self.seeds.append(Seed(dst, float(value), int(beat), port))
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
    spoke: float | None   # None = fired silently (closed gate / fringe)


@dataclass
class Result:
    weave: str
    beats: int
    finished: bool                                 # False = horizon cut it
    fires: list[Fire]
    fringes: dict[str, list[tuple[int, float]]]    # knot -> [(beat, value)]
    learned: list[float] | None = None             # v0.2: final weight of every strand,
    #                                                in weave.threads order, strand order.
    #                                                None when no strand had drift != 0.

    def fringe(self, name: str) -> list[float]:
        """Just the recorded values of one fringe knot, in beat order."""
        return [v for _, v in self.fringes.get(name, [])]


class Loom:
    """Runs a weave. All run state lives here; the weave stays pure."""

    def run(self, weave: Weave, beats: int | None = None) -> Result:
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

        # Every spell this weave names, resolved ONCE, after validate() and before
        # the first beat. The weave holds names; the loom holds the functions.
        from . import spells
        casts = {k.spell: spells.cast(k.spell) for k in weave.knots.values()
                 if k.verb == "spell"}

        trays: dict[str, dict[str, list[float]]] = {
            name: defaultdict(list) for name in weave.knots}
        pools: dict[str, float] = defaultdict(float)
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
                spoke = self._verb(knot, tray, pools, casts)
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
                        inflight[beat + int(s.delay)].append(
                            (t.dst, t.port, spoke * w, s if s.drift else None))
            # 3. LEARN — a cord that helped a knot speak thickens; one that spoke into
            #    silence thins. Nothing travels backwards; this reads only THIS beat.
            if plastic and landed:
                fired_now = {f.knot for f in fires if f.beat == beat}
                for st, dst in landed:
                    w = live[id(st)]
                    w += st.drift if dst in fired_now else -st.drift * 0.25
                    live[id(st)] = min(st.ceil, max(st.floor, w))

            if not inflight:                              # silence: halt
                return Result(weave.name, beat, True, fires, dict(fringes),
                              self._learned(weave, live) if plastic else None)

        return Result(weave.name, horizon, not inflight, fires, dict(fringes),
                      self._learned(weave, live) if plastic else None)

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
        # rise: total gathered value crosses the line
        return sum(v for vs in tray.values() for v in vs) >= arg

    # -- the six verbs

    @staticmethod
    def _verb(knot: Knot, tray: dict[str, list[float]],
              pools: dict[str, float],
              casts: dict[str, object]) -> float | None:
        ins = sum(tray.get("in", ()))
        if knot.verb in ("pass", "sum", "fringe"):
            return ins + knot.bias
        if knot.verb == "prod":
            p = 1.0
            for v in tray.get("in", ()):
                p *= v
            return p + knot.bias
        if knot.verb == "pool":
            pools[knot.name] += ins
            return pools[knot.name] + knot.bias
        if knot.verb == "gate":
            key = sum(tray.get("key", ()))
            return (ins + knot.bias) if key > 0 else None
        if knot.verb == "spell":
            fn = casts[knot.spell]   # validate() proved it is in the book
            try:
                said = fn(tuple(tray.get("in", ())))
            except Exception as e:                       # noqa: BLE001
                raise WeaveError(f"knot '{knot.name}': spell "
                                 f"'{knot.spell}' failed: {e}") from None
            if said is None:                             # silent, like a shut gate
                return None
            if isinstance(said, bool) or not isinstance(said, (int, float)):
                raise WeaveError(f"knot '{knot.name}': spell '{knot.spell}' "
                                 f"answered {said!r}; a spark is a number")
            return float(said) + knot.bias
        raise WeaveError(f"unknown verb '{knot.verb}'")  # pragma: no cover
