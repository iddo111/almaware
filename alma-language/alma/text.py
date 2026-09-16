"""ALMA text formats — transcripts of a shape.

A: JSON        — what the future VR editor will emit/consume.
B: voice lines — canonical speech; each line is one spoken utterance.

Both describe the same Weave and round-trip through each other.
"""
from __future__ import annotations

import json
import re

from .chords import Chord, ChordWidthError
from .loom import (Strand, Weave, WeaveError, STRAND_CEIL, STRAND_FLOOR,
                   TRIGGER_KINDS, VERBS)

# Words the voice parser silently drops, so natural speech parses:
# "thread f to f", "seed f value 1 at beat 1", "run 10 beats" all work.
# A spell name is a plain lowercase word — the same shape `alma.spells.teach`
# enforces on the way in, so anything in the book can always be written and spoken.
SPELL_NAME = re.compile(r"^[a-z][a-z0-9_]*$")

FILLER = {
    "a", "an", "the", "at", "to", "into", "in", "with", "of", "and",
    "then", "named", "called", "value", "beat", "beats", "on", "from",
}

# Position 1 (0 = the command word) holds a NAME, not grammar, for these
# commands -- never filler-stripped even when the name happens to spell a
# filler word, because nothing can legally come between the command and
# this first name (no test or spec line ever puts filler there). "thread"
# only gets position 1 (its src), not position 2 (its dst): a thread line
# has an OPTIONAL connector filler ("to"/"into") between the two names
# ("thread a to b"), so the word right after src is genuinely ambiguous
# between "the connector" and "the dst, which happens to spell the same
# word" -- e.g. is "thread a to the" src=a,dst="the" (connector "to" then a
# filler-word name), or does "to" itself want to be read as dst with no
# connector at all? That ambiguity has no context-free answer, so a thread
# DESTINATION that collides with FILLER must still be quoted; its SOURCE
# is as unambiguous as any other command's first name.
_NAME_POSITIONS = {"weave": (1,), "knot": (1,), "thread": (1,), "seed": (1,)}


# ---------------------------------------------------------------- strands
#
# A strand has seven properties, and a transcript must carry every one of them.
# For the whole of v0.2 it carried two, and the other five — `drift`, `floor`,
# `ceil`, `bearing`, `tint` — were dropped in silence, which turned a PLASTIC
# weave into a static one the moment it was written down. See
# tests/test_strand_fields.py.
#
# The rule here is the same one `to_dict` already used for knots: **write a
# property only when it differs from its default.** So a plain cord still
# renders as exactly `{"weight": ..., "delay": ...}` and every `.json` and
# `.voice` file already on disk keeps its bytes — while a cord that carries
# something now says so.

PLAIN_STRAND = {"weight": 1.0, "delay": 1}


def _bearing_text(bearing, where: str) -> str:
    """A bearing on its way into a transcript. Text, or a loud refusal.

    In memory `Strand.bearing` is `object | None` — a host program may hang any
    object there. A transcript is text, so exactly one shape survives being
    written: a `str`, holding a path ("photo/x.jpg") or a phrase. Anything else
    is refused here, by name, rather than quietly disappearing — quiet
    disappearance is the bug this module is being fixed for.
    """
    if isinstance(bearing, str):
        return bearing
    raise WeaveError(
        f"{where}: bearing is a {type(bearing).__name__}, and a weave's "
        f"transcript can only carry text. Give it a path or a phrase "
        f"(e.g. 'photo/alma.jpg'), or leave it off — it will not be "
        f"silently dropped.")


def _strand_dict(s: Strand, where: str) -> dict:
    """One strand as JSON: the two always, the other five only when they say
    something."""
    sd: dict = {"weight": s.weight, "delay": s.delay}
    if s.drift:
        sd["drift"] = s.drift
    if s.floor != STRAND_FLOOR:
        sd["floor"] = s.floor
    if s.ceil != STRAND_CEIL:
        sd["ceil"] = s.ceil
    if s.tint:
        sd["tint"] = s.tint
    if s.bearing is not None:
        sd["bearing"] = _bearing_text(s.bearing, where)
    return sd


# ---------------------------------------------------------------- JSON

def to_dict(w: Weave) -> dict:
    d: dict = {"alma": "0.1", "weave": w.name, "knots": [], "threads": [],
               "seeds": []}
    for k in w.knots.values():
        kd: dict = {"name": k.name}
        if k.verb != "pass":
            kd["verb"] = k.verb
        if k.trigger != "any":
            kd["trigger"] = k.trigger
        if k.bias:
            kd["bias"] = k.bias
        if k.spell:
            kd["spell"] = k.spell
        d["knots"].append(kd)
    for t in w.threads:
        td: dict = {"from": t.src, "to": t.dst}
        if t.port != "in":
            td["port"] = t.port
        strands = [_strand_dict(s, f"thread '{t.src}'->'{t.dst}' strand #{j}")
                   for j, s in enumerate(t.strands)]
        if strands != [PLAIN_STRAND]:
            td["strands"] = strands
        d["threads"].append(td)
    for s in w.seeds:
        # v0.4: a chord seed writes down as a LIST of numbers, a scalar seed as a
        # number. The two shapes are distinguishable in JSON, so the round trip
        # never has to guess — `[2.0]` comes back a one-voice chord and `2.0`
        # comes back a scalar, which are different sparks and stay different.
        sd: dict = {"to": s.dst,
                    "value": s.value.as_list() if isinstance(s.value, Chord)
                    else s.value}
        if s.beat != 1:
            sd["beat"] = s.beat
        if s.port != "in":
            sd["port"] = s.port
        d["seeds"].append(sd)
    if w.run_hint:
        d["run"] = w.run_hint
    return d


def _require(d: dict, key: str, where: str):
    """Fetch a required key, raising WeaveError (not KeyError) if absent."""
    if not isinstance(d, dict):
        raise WeaveError(f"{where}: expected an object, got "
                         f"{type(d).__name__}")
    try:
        return d[key]
    except KeyError:
        raise WeaveError(f"{where}: missing '{key}'") from None


def _coerce(value, cast, where: str, field: str):
    """Coerce a field to a number, raising WeaveError on bad input."""
    try:
        return cast(value)
    except (ValueError, TypeError) as e:
        raise WeaveError(f"{where}: bad {field} {value!r} ({e})") from None


def from_dict(d: dict) -> Weave:
    if not isinstance(d, dict):
        raise WeaveError(f"weave: expected an object, got {type(d).__name__}")
    w = Weave(str(d.get("weave", "weave")))

    def _as_list(key):
        v = d.get(key, ())
        if isinstance(v, (str, bytes)) or not isinstance(v, (list, tuple)):
            raise WeaveError(f"'{key}' must be a list, got "
                             f"{type(v).__name__}")
        return v

    knots = _as_list("knots") if "knots" in d else ()
    for i, kd in enumerate(knots):
        where = f"knot #{i}"
        if not isinstance(kd, dict):
            raise WeaveError(f"{where}: expected an object, got "
                             f"{type(kd).__name__}")
        name = _require(kd, "name", where)
        w.knot(str(name), kd.get("verb", "pass"),
               kd.get("trigger", "any"),
               _coerce(kd.get("bias", 0.0), float, f"knot '{name}'", "bias"),
               str(kd.get("spell", "")))

    threads = _as_list("threads") if "threads" in d else ()
    for i, td in enumerate(threads):
        if not isinstance(td, dict):
            raise WeaveError(f"thread #{i}: expected an object, got "
                             f"{type(td).__name__}")
        src = _require(td, "from", f"thread #{i}")
        dst = _require(td, "to", f"thread from '{src}'")
        where = f"thread '{src}'->'{dst}'"
        raw_strands = td.get("strands", [{}])
        if not isinstance(raw_strands, list):
            raise WeaveError(f"{where}: 'strands' must be a list, got "
                             f"{type(raw_strands).__name__}")
        strands = []
        for j, sd in enumerate(raw_strands):
            if not isinstance(sd, dict):
                raise WeaveError(f"{where} strand #{j}: expected an object, "
                                 f"got {type(sd).__name__}")
            at = f"{where} strand #{j}"
            bearing = sd.get("bearing")
            if bearing is not None:
                _bearing_text(bearing, at)     # same rule reading as writing
            strands.append(Strand(          # by name: a reordered dataclass
                                            # must break loudly, not quietly
                weight=_coerce(sd.get("weight", 1.0), float, at, "weight"),
                delay=_coerce(sd.get("delay", 1), int, at, "delay"),
                drift=_coerce(sd.get("drift", 0.0), float, at, "drift"),
                floor=_coerce(sd.get("floor", STRAND_FLOOR), float, at, "floor"),
                ceil=_coerce(sd.get("ceil", STRAND_CEIL), float, at, "ceil"),
                bearing=bearing,
                tint=str(sd.get("tint", ""))))
        w.thread(str(src), str(dst), td.get("port", "in"), strands)

    seeds = _as_list("seeds") if "seeds" in d else ()
    for i, sd in enumerate(seeds):
        if not isinstance(sd, dict):
            raise WeaveError(f"seed #{i}: expected an object, got "
                             f"{type(sd).__name__}")
        dst = _require(sd, "to", f"seed #{i}")
        where = f"seed to '{dst}'"
        raw = _require(sd, "value", where)
        if isinstance(raw, (list, tuple)):
            try:
                value = Chord(raw)
            except ChordWidthError as e:
                raise WeaveError(f"{where}: bad chord {raw!r} ({e})") from None
        else:
            value = _coerce(raw, float, where, "value")
        beat = _coerce(sd.get("beat", 1), int, where, "beat")
        w.seed(str(dst), value, beat, sd.get("port", "in"))

    if "run" in d:
        w.run_hint = _coerce(d["run"], int, "weave", "run")
    return w


def to_json(w: Weave, indent: int = 2) -> str:
    return json.dumps(to_dict(w), indent=indent)


def from_json(text: str) -> Weave:
    try:
        d = json.loads(text)
    except json.JSONDecodeError as e:
        raise WeaveError(f"bad JSON: {e}") from None
    return from_dict(d)


# ---------------------------------------------------------------- voice

_UNSPOKEN = str.maketrans(",:", "  ")
_NEEDS_QUOTES = re.compile(r'[\s",:#]')


def _split_line(raw: str) -> list[tuple[str, bool]]:
    """One line into (word, quoted) pairs.

    Outside quotes this is the old behaviour exactly: a `#` begins a comment,
    commas and colons are whitespace, the rest splits on spaces.

    Inside `"..."` none of that happens. A quoted span is ONE word, kept
    verbatim — not comment-cut, not split, not filler-stripped. That is the only
    way a `bearing` can be the *phrase* v0.2 says it may be: "the sentence
    neither of them can take back" survives the filler stripper only if the
    stripper never sees inside it. A literal `"` is written doubled, as in CSV,
    so there is no phrase the grammar cannot say.
    """
    out: list[tuple[str, bool]] = []
    plain: list[str] = []

    def flush() -> None:
        if plain:
            text = "".join(plain).translate(_UNSPOKEN)
            plain.clear()
            out.extend((word, False) for word in text.split())

    i, n = 0, len(raw)
    while i < n:
        c = raw[i]
        if c == '"':
            flush()
            said, i = [], i + 1
            while True:
                j = raw.find('"', i)
                if j < 0:
                    raise WeaveError(
                        f"unclosed quote in {raw.strip()!r}. A spoken phrase "
                        f'opens and closes with ", and a literal " is doubled.')
                if raw[j + 1:j + 2] == '"':          # "" -> one literal quote
                    said.append(raw[i:j + 1])
                    i = j + 2
                    continue
                said.append(raw[i:j])
                i = j + 1
                break
            out.append(("".join(said), True))
        elif c == "#":
            break
        else:
            plain.append(c)
            i += 1
    flush()
    return out


def parse_voice(text: str) -> Weave:
    """Parse a transcript of utterances (one command per line)."""
    w = Weave()
    for lineno, raw in enumerate(text.splitlines(), 1):
        try:
            spoken = _split_line(raw)
        except WeaveError as e:
            raise WeaveError(f"line {lineno}: {e}") from None
        if not spoken:                      # blank line, or all comment
            continue
        # Filler is speech, not content, so it is dropped — but never from
        # inside a quoted phrase, which is one indivisible word however it
        # reads, and never from a NAME position (the word right after the
        # command: weave/knot/seed's name, thread's src and dst). A knot
        # really can be named "a" or "in" (to_voice's own NAMES ARE QUOTED
        # note above shows those are ordinary names, not grammar), and a
        # name always sits immediately after its command with no filler
        # able to come between them — the same assumption _utter already
        # makes by reading orig[1]/orig[2] unconditionally. Before this fix,
        # writing that name unquoted crashed parse_voice with 'cannot parse
        # (list index out of range)' instead of just hearing the name.
        cmd0 = spoken[0][0].lower() if spoken else ""
        protected = _NAME_POSITIONS.get(cmd0, ())
        kept = [t for idx, (t, quoted) in enumerate(spoken)
                if quoted or idx in protected or t.lower() not in FILLER]
        try:
            _utter(w, [t.lower() for t in kept], kept)
        except WeaveError:
            raise
        except (IndexError, ValueError) as e:
            raise WeaveError(f"line {lineno}: cannot parse '{raw.strip()}' "
                             f"({e})") from None
    return w


def _spoken(text: str) -> str:
    """A phrase as it must be said for the parser to hear it back unchanged.

    Bare when it is one plain word that means only itself; quoted when it holds
    whitespace or punctuation the tokeniser eats, when it is a filler word the
    stripper would drop, or when it collides with a word this line's grammar
    uses. Empty text quotes too — `bearing ""` is a bearing, `bearing` is a
    syntax error.
    """
    bare = (text
            and not _NEEDS_QUOTES.search(text)
            and text.lower() not in FILLER
            and text.lower() not in _THREAD_WORDS)
    return text if bare else '"' + text.replace('"', '""') + '"'


def _num(tok: str) -> float:
    return float(tok)


# The seven properties of a strand, as spoken: word -> (field, how to read it).
# `weight` and `delay` were the only two the grammar knew until 2026-08-30; the
# other five existed on `Strand` but could not be said, so a spoken weave came
# back stripped of them.
_STRAND_WORDS: dict[str, tuple[str, object]] = {
    "weight":  ("weight",  _num),
    "delay":   ("delay",   lambda t: int(_num(t))),
    "drift":   ("drift",   _num),
    "floor":   ("floor",   _num),
    "ceil":    ("ceil",    _num),
    "tint":    ("tint",    str),
    "bearing": ("bearing", str),
}

# Words a `thread` line uses for itself — a tint or bearing equal to one of
# these must be quoted, or it would be heard as grammar.
_THREAD_WORDS = {"strand", "port"} | set(_STRAND_WORDS)


def _utter(w: Weave, low: list[str], orig: list[str]) -> None:
    cmd = low[0]
    if cmd == "weave":
        w.name = orig[1]
    elif cmd == "knot":
        name = orig[1]
        verb, trigger, bias, spell = "pass", "any", 0.0, ""
        i = 2
        while i < len(low):
            if low[i] in VERBS:
                verb = low[i]; i += 1
                if verb == "spell":
                    # The name of the spell, and nothing else, follows the verb.
                    # A weave is a transcript of SPEECH (SPEC.md §9): a token no
                    # one could say aloud is not an utterance, it is a payload.
                    if i >= len(low) or not SPELL_NAME.match(low[i]):
                        raise WeaveError(
                            f"knot '{name}': verb spell needs a spoken spell "
                            f"name, got "
                            f"{orig[i] if i < len(low) else '(nothing)'!r}")
                    spell = low[i]; i += 1
            elif low[i] == "trigger":
                kind = low[i + 1]
                if kind not in TRIGGER_KINDS:
                    raise WeaveError(f"unknown trigger '{kind}'")
                if kind == "any":
                    trigger = "any"; i += 2
                else:
                    trigger = f"{kind} {_num(low[i + 2]):g}"; i += 3
            elif low[i] == "bias":
                bias = _num(low[i + 1]); i += 2
            else:
                raise WeaveError(f"knot '{name}': stray word '{orig[i]}'")
        w.knot(name, verb, trigger, bias, spell)
    elif cmd == "thread":
        src, dst = orig[1], orig[2]
        port, strands = "in", []
        i = 3
        while i < len(low):
            if low[i] == "port":
                port = orig[i + 1]; i += 2
            elif low[i] == "strand":
                strands.append(Strand()); i += 1
            elif low[i] in _STRAND_WORDS:
                # All seven strand properties are said the same way: the word,
                # then the value. Values are read from `orig`, never `low`, so
                # a tint or a bearing keeps its capitals.
                prop, read = _STRAND_WORDS[low[i]]
                if not strands:
                    strands.append(Strand())
                setattr(strands[-1], prop, read(orig[i + 1])); i += 2
            else:
                raise WeaveError(f"thread {src}->{dst}: "
                                 f"stray word '{orig[i]}'")
        w.thread(src, dst, port, strands or None)
    elif cmd == "seed":
        dst = orig[1]
        port, nums, voices = "in", [], None
        i = 2
        while i < len(low):
            if low[i] == "port":
                port = orig[i + 1]; i += 2
            elif low[i] == "chord":
                # v0.4. The COUNT comes first and the voices follow it, because
                # bare numbers on a seed line are already positional (value, then
                # beat) and a run of numbers with no announced length could not be
                # told from a value with a beat after it. Saying "chord 3" first
                # makes the line unambiguous both to the parser and to a listener:
                #   seed canvas chord 3 0.84 0.36 0.26 at beat 2
                if voices is not None:
                    raise WeaveError(f"seed {dst}: two chords on one seed line")
                if i + 1 >= len(low):
                    raise WeaveError(
                        f"seed {dst}: 'chord' must say how many voices follow")
                n = int(_num(low[i + 1]))
                if n < 1:
                    raise WeaveError(
                        f"seed {dst}: a chord of {n} voices is not a spark — "
                        f"say a number instead")
                if i + 2 + n > len(low):
                    raise WeaveError(
                        f"seed {dst}: chord says {n} voices but only "
                        f"{len(low) - i - 2} follow")
                voices = [_num(low[i + 2 + k]) for k in range(n)]
                i += 2 + n
            else:
                nums.append(_num(low[i])); i += 1
        if voices is None:
            if not nums:
                raise WeaveError(f"seed {dst}: needs a value")
            value = nums[0]
            beat = int(nums[1]) if len(nums) > 1 else 1
        else:
            value = Chord(voices)
            # after a chord, the only bare number left on the line is the beat
            if len(nums) > 1:
                raise WeaveError(
                    f"seed {dst}: a chord seed takes one beat, got {nums}")
            beat = int(nums[0]) if nums else 1
        w.seed(dst, value, beat, port)
    elif cmd == "run":
        w.run_hint = int(_num(low[1]))
    else:
        raise WeaveError(f"unknown utterance '{orig[0]}'")


def to_voice(w: Weave) -> str:
    """Render a weave back into canonical speech.

    NAMES ARE QUOTED WHEN THEY HAVE TO BE (fixed 2026-09-05). `_spoken` was applied
    to tints and bearings but not to KNOT NAMES, and `a` is a filler word — so a
    weave holding a knot called `a` wrote itself as `knot a`, the filler stripper
    ate the name on the way back in, and `parse_voice` died with an IndexError on
    its own output. The same held for `the`, `to`, `in`, `of`, `and`, `on`, `from`,
    `value`, `beat`, `named`, and every other word in FILLER.

    That is the round-trip guarantee §9 makes, broken, and it is the same shape as
    the v0.2 scar this module already carries a paragraph about: a transcript that
    silently loses part of the weave. `tests/test_loom.py` never caught it because
    every weave in it is named for what it does.
    """
    lines = [f"weave {_spoken(w.name)}"]
    for k in w.knots.values():
        line = f"knot {_spoken(k.name)}"
        if k.verb != "pass":
            line += f" {k.verb}"
        if k.spell:
            line += f" {k.spell}"
        if k.trigger != "any":
            line += f" trigger {k.trigger}"
        if k.bias:
            line += f" bias {k.bias:g}"
        lines.append(line)
    for t in w.threads:
        line = f"thread {_spoken(t.src)} to {_spoken(t.dst)}"
        if t.port != "in":
            line += f" port {_spoken(t.port)}"
        where = f"thread '{t.src}'->'{t.dst}'"
        # Same test as to_dict, so the two transcripts agree on when a cord is
        # plain enough to leave unsaid.
        if [_strand_dict(s, where) for s in t.strands] != [PLAIN_STRAND]:
            for s in t.strands:
                line += f" strand weight {s.weight:g} delay {s.delay}"
                if s.drift:
                    line += f" drift {s.drift:g}"
                if s.floor != STRAND_FLOOR:
                    line += f" floor {s.floor:g}"
                if s.ceil != STRAND_CEIL:
                    line += f" ceil {s.ceil:g}"
                if s.tint:
                    line += f" tint {_spoken(s.tint)}"
                if s.bearing is not None:
                    line += f" bearing {_spoken(_bearing_text(s.bearing, where))}"
        lines.append(line)
    for s in w.seeds:
        if isinstance(s.value, Chord):
            said = " ".join(f"{v:g}" for v in s.value)
            line = (f"seed {_spoken(s.dst)} chord {len(s.value)} {said} "
                    f"at beat {s.beat}")
        else:
            line = f"seed {_spoken(s.dst)} value {s.value:g} at beat {s.beat}"
        if s.port != "in":
            line += f" port {_spoken(s.port)}"
        lines.append(line)
    if w.run_hint:
        lines.append(f"run {w.run_hint} beats")
    return "\n".join(lines)
