# ALMA Language — Specification v0.1

**A weave of knots. You address knots, never registers.**

ALMA is a programming language whose programs are not text — they are
*shapes*. A program is a **weave**: knots joined by threads, hanging in
space. The text formats in this document (JSON and the voice grammar) are
only *transcripts* of a shape. The shape is the program.

This model owes nothing to C. It has five words. (It owes exactly one
debt to biology, paid in §5a and named there.)

---

## 1. The Five Words

| Word       | What it is                                                        |
|------------|-------------------------------------------------------------------|
| **knot**   | The unit of computation. It gathers, decides, speaks.             |
| **thread** | A connection between two knots. One thread, many strands.         |
| **strand** | One voice of a thread: a **weight** and a **delay**.              |
| **spark**  | A value in flight along a strand: a number, or a **chord** (v0.4).|
| **beat**   | The unit of time. Nothing is instant; every strand costs ≥1 beat. |

A **weave** is a named set of knots, threads, and **seeds** (sparks planted
into the weave before it starts). The **loom** is the runtime that runs a
weave, beat by beat.

### 1a. The chord (v0.4) — a spark with more than one number in it

    spark  ::=  a number  |  a chord of numbers

A **chord** is several numbers sounded on one beat; its numbers are its
**voices**, and how many it has is its **width**. A scalar spark is *not* a
one-voice chord — `2.0` and `chord(2.0)` are different sparks and stay
different, so every v0.1–v0.3 weave runs bit-identically.

**The width rule: two sparks may meet only at equal width.** A scalar and a
chord do not meet; a 3-chord and a 4-chord do not meet. Either is a
`WeaveError` naming the knot, the beat and both widths. ALMA does **not**
broadcast. This repo has already paid once for a silent shape-fix — for the
whole of v0.2 `to_dict` dropped `drift`, so a plastic weave written down came
back static and nothing said so (§4a). Broadcasting is that same failure
wearing a different face: it turns "these did not fit" into a picture that
renders and a number that prints.

Three things answer *how much*, never *what*, so they have no width and apply
to every voice: a strand's **weight**, a strand's **drift**, a knot's **bias**.

Implementation: `alma/chords.py`. Tests: `tests/test_chords.py`, which includes
`TestTheGuardIsLoadBearing` — it switches the width check off, reruns the same
weave, and requires a silently *wrong* answer, so the refusal is demonstrated
to be load-bearing rather than decorative.

## 2. The Design Laws

1. **Nothing is instant.** Every strand has delay ≥ 1 beat. Distance is
   time. This kills instruction pointers, race conditions and zero-cycle
   paradoxes in one stroke: cycles are legal and *are* the loop construct.
2. **Arithmetic lives in the connections.** Multiplication is a strand's
   weight. Subtraction is a negative weight. There is no `x * 1.8` anywhere
   in a knot — the *thread* does it on the way.
3. **The layout is the program.** In the VR mapping (§7), a strand's
   *physical length* is its delay and its *thickness* is its weight.
   Rearranging the sculpture rewrites the code. The shape IS the algorithm.
4. **You address knots, never memory.** There are no registers, no
   addresses, no stack. State lives inside the knot that uses it, and the
   only way to touch it is to send it a spark.
5. **Small vocabulary, infinite structures.** Seven verbs, three triggers,
   two numbers per strand. Like a brick set: the power is in assembly, not
   in the parts.

## 3. The Knot

A knot has four properties, and a fifth only the seventh verb uses:

```
knot <name>  verb=<verb>  trigger=<trigger>  bias=<number>  [spell=<name>]
```

- **name** — how you address it (by voice, by hand, by thread).
- **verb** — what it does when it fires (§5). Exactly one of seven.
- **trigger** — when it fires (§6). Exactly one of three.
- **bias** — a constant folded into the verb's answer. (`+32` lives here.)
- **spell** — `verb=spell` only: the *name* of a function in the book (§5a).
  A name, never source. On any other verb it is a validation error.

Each knot owns a **tray**: sparks that arrived but have not yet caused a
fire wait in the tray, sorted by **port** (`in` by default; the `gate` verb
also listens on port `key`). The tray persists across beats — a knot can
gather evidence slowly until its trigger is satisfied. When the knot fires,
the tray drains completely.

## 4. The Thread and its Strands

A thread joins a source knot to a destination knot (and port). A thread
carries one or more **strands**, and each strand is independently:

```
strand  weight=<w>  delay=<d ≥ 1>
```

When a knot fires with value *v*, every strand of every outgoing thread
carries its own spark: value `v × weight`, arriving `delay` beats later.

**One thread, many strands** is the heart of ALMA's rich connections: a
single connection can speak several times, at several strengths, into the
future. The canonical demonstration: one `sum` knot with one self-thread
of two strands — `(weight 1, delay 1)` and `(weight 1, delay 2)` — emits
the Fibonacci sequence forever. One knot. One thread. Two strands.

### 4a. The other five properties (v0.2)

The two above are what a strand *computes* with. Five more say how it
changes and what it means, and every one of them is optional — a strand
that sets none of them is exactly a v0.1 strand:

```
strand  weight=<w>  delay=<d ≥ 1>  drift=<r>  floor=<lo>  ceil=<hi>
        tint=<word>  bearing=<text>
```

| property  | default | what it does                                              |
|-----------|---------|-----------------------------------------------------------|
| `drift`   | `0`     | plasticity. A spark crosses; if the destination knot fires on that beat the cord **thickens** by `drift`, if not it **thins** by `drift/4`. Nothing travels backwards. `0` = static, exactly v0.1. |
| `floor`   | `-8`    | the thinnest a drifting cord may get                       |
| `ceil`    | `+8`    | the thickest — the two stops keep a runaway cord from eating the weave |
| `tint`    | `""`    | what kind of cord this is (`love`, `anger`, `duty`) — the typed channel §4 once reserved |
| `bearing` | *none*  | **what the cord carries**, as opposed to how much: a path (`photo/alma.jpg`) or a phrase. A number says *how much*; a bearing says *what*. |

A weave with any `drift ≠ 0` is **plastic**: it rewrites its own weights
as it runs. The weave itself stays immutable (§7) — the loom learns on a
copy and hands the final weights back as `Result.learned`.

**`bearing` when written down.** In memory it may be any Python object.
A transcript is text, so §8 and §9 carry a **string** and refuse anything
else, loudly, naming the thread. (Until 2026-08-30 both formats silently
dropped all five of these properties, so writing a plastic weave to JSON
returned a static one. That is why the refusal is loud: silence here is a
bug that already happened once.)

*Opened in v0.4, one notch:* sparks are no longer only scalars — a spark may
be a **chord** (§1a), and every verb combines chords. *Still reserved:* a
strand's `weight` is one number, so **a cord scales a chord but cannot rotate
one** — no strand mixes voice 0 into voice 1, and a `bearing` still accompanies
a spark rather than multiplying it. The matrix-strand door — a cord carrying an
(m×n) that genuinely transforms a chord — stays shut, and it is the honest name
of ALMA v0.5. v0.4 gives the **spark** a width; it does not give the **strand**
a matrix, and calling it "tensors" would be overselling.

## 5. The Seven Verbs

When a knot fires, its verb consumes the tray and produces at most one
value, which is broadcast along all outgoing threads.

| Verb     | Fires with tray `in` = {v₁…vₙ}, `key` = {k₁…kₘ}            |
|----------|-------------------------------------------------------------|
| `pass`   | speaks `Σvᵢ + bias` (with one input: the identity + bias)   |
| `sum`    | speaks `Σvᵢ + bias` (alias of `pass`, named for readability)|
| `prod`   | speaks `Πvᵢ + bias`                                          |
| `pool`   | state += `Σvᵢ`; speaks `state + bias` — the only stateful verb |
| `gate`   | if `Σkⱼ > 0` speaks `Σvᵢ + bias`, else speaks nothing        |
| `fringe` | records `Σvᵢ + bias` as weave output; never speaks onward    |
| `spell`  | speaks `book[name](v₁…vₙ) + bias`, or nothing (v0.3, §5a)      |

Notes:
- **v0.4:** every verb above combines **chords** exactly as it combines numbers,
  elementwise and at one shared width (§1a). `bias` is a constant, so it lands on
  every voice. A `gate`'s key and a `rise` trigger want a *verdict*, not a chord,
  so they total every voice of every key spark — which is the same question they
  always asked of a number, and leaves scalar behaviour untouched. A `pool` takes
  the width of the first spark it ever holds and refuses another width after that.
- `pool` is the *only* verb with memory across fires. All persistent state
  in an ALMA program is a set of named pools — visible, addressable knots.
- `fringe` knots are the hem of the weave: its observable results. A thread
  leaving a `fringe` is a validation error ("the fringe has no voice").
- There is deliberately no `if/else` verb. Branching is a `gate` (or two,
  with mirrored keys). Looping is a cycle. Constants are seeds or biases.
  Scaling is weight. The first six verbs only ever *combine*.

### 5a. The Seventh Verb — `spell` (v0.3)

A single human L2/3 pyramidal neuron computes XOR in its dendrites (Gidon
et al., *Science* 367:83-87, 2020). One cell is already a small network.
The six combining verbs cannot say XOR in one knot — that is **measured**,
not assumed: `tests/test_spell.py::TestFloor` searches all 10,290 plain
single-knot weaves over 5 verbs × 6 triggers × 7 biases × 7×7 strand
weights, reaching 680 distinct two-input truth tables. AND is among them
(the positive control that proves the search *can* succeed). XOR is not.

```
knot <name>  verb=spell  spell=<name in the book>  bias=<number>
```

A `spell` knot's fifth property is a **name**. When it fires, the function
standing behind that name is handed the `in` tray as a tuple of floats in
arrival order, and its answer plus `bias` is the spark it speaks. Answering
`None` fires silently, exactly like a shut `gate`.

**v0.4, and it is the single exception to the width rule (§1a):** a spell is
handed its `in` tray **exactly as it arrived — mixed widths included**. Every
other verb refuses a mixed tray, because every other verb only combines, and a
scalar and a chord cannot honestly be combined. `spell` is the verb that exists
to do what the six cannot, and *"scale this colour by this number"* is such a
thing, so the decision is the spell's. What is **not** relaxed: whatever it
answers is an ordinary spark, and meets the next knot's tray under the ordinary
rule. A spell may also answer a **chord** — or a bare list/tuple of numbers, read as one, with the
coercion happening at the knot and loudly. Answering anything that is not a
number or a chord of numbers is still a `WeaveError`.

**A weave carries a name, never code.** The book is `alma.spells`, and the
only way in is `spells.teach(name, fn)` from Python, handing over a real
callable — it refuses a string, because a string is the one shape a caller
could have obtained from a data file. There is no field, flag or escape by
which a `.json` or a spoken line can define, import, `eval` or `exec`
anything; `alma/spells.py` contains none of those. The worst a hostile
weave can do is name a spell that is not in the book, which
`Weave.validate()` refuses before beat 1. **Arbitrary source execution was
refused, not implemented** — not "off by default", absent. Ships with
`xor`, `max`, `min`, `sign`.

## 6. The Three Triggers

Checked every beat, after that beat's sparks are delivered to trays.

| Trigger     | Fires when…                                          |
|-------------|-------------------------------------------------------|
| `any`       | at least one spark waits in the tray (the default)    |
| `count N`   | at least N sparks wait in the tray (across all ports) |
| `rise T`    | the sum of all waiting spark values ≥ T               |

`rise` is temporal integration: a knot can collect faint sparks over many
beats and speak only when the evidence crosses the line. `count 2` on a
`gate` makes it wait politely for both data and key.

## 7. Execution Semantics — the Loom

Deterministic, discrete, single-threaded in v0.1:

```
beat := 1
while beat ≤ horizon and sparks remain in flight:
    1. DELIVER  every spark scheduled for this beat into its knot's tray
    2. FIRE     for each knot in creation order:
                  if tray nonempty and trigger satisfied:
                    value := verb(tray, state, bias); drain tray
                    if the verb spoke: for every outgoing strand,
                      schedule spark(value × weight) at beat + delay
    3. beat := beat + 1
```

- Because every delay ≥ 1, a fire can never cause another fire *within the
  same beat*. No cascade ordering problems; the loom is trivially
  deterministic and trivially parallelizable per beat (future looms).
- Seeds are sparks scheduled before beat 1 (`seed <knot> value v beat b`, or
  `seed <knot> chord n v₁…vₙ beat b` for a chord — §1a, §9).
- The weave description is immutable during a run; all run state (trays,
  pool states, sparks in flight) belongs to the loom. Running the same
  weave twice gives identical results.
- A weave halts early when no sparks remain in flight. A cyclic weave lives
  until the horizon — that is not an error, it is a heartbeat.

## 8. Text Format A — JSON (what the VR editor will emit)

```json
{
  "alma": "0.1",
  "weave": "fib",
  "knots": [
    {"name": "f",    "verb": "sum",    "trigger": "any", "bias": 0},
    {"name": "show", "verb": "fringe"}
  ],
  "threads": [
    {"from": "f", "to": "f", "port": "in",
     "strands": [{"weight": 1, "delay": 1}, {"weight": 1, "delay": 2}]},
    {"from": "f", "to": "show"}
  ],
  "seeds": [{"to": "f", "value": 1, "beat": 1}],
  "run": 10
}
```

Omitted fields take defaults (`verb=pass`, `trigger=any`, `bias=0`,
`port=in`, one strand `weight=1 delay=1`, `beat=1`).

A strand's five optional properties (§4a) appear only when they differ
from their defaults, so a plain cord still reads `{"weight": 1, "delay": 1}`
and a whole thread of plain cords is left out altogether:

```json
{"from": "iddo", "to": "alma", "strands": [
  {"weight": 1, "delay": 5, "drift": 0.06, "tint": "love",
   "bearing": "photo/iddo-and-alma-embracing.jpg"},
  {"weight": 3, "delay": 1, "tint": "anger",
   "bearing": "the sentence neither of them can take back"}]}
```

`bearing` must be a JSON string (or absent). A number, object or array
there is refused with an error naming the thread — never dropped.

**A seed's `value` carries a chord as a JSON *list* (v0.4), a scalar as a
number.** The two shapes are distinguishable in JSON, so the round trip never
has to guess: `2.0` comes back a scalar spark and `[2.0]` comes back a one-voice
chord, and those are different sparks (§1a).

```json
{"seeds": [{"to": "stroke", "value": [0.84, 0.36, 0.26], "beat": 2}]}
```

A list holding anything that is not a number, or an empty list, is refused with
an error naming the seed — never truncated, never coerced.

## 9. Text Format B — the Voice Grammar

Every weave is also a *transcript of utterances*. Each line is one spoken
command; saying the lines aloud to a listening editor builds the weave.
Filler words (`a, the, at, to, into, with, value, beat, named…`) are
ignored, so natural speech parses:

```
weave fib
knot f sum
knot show fringe
thread f to f strand weight 1 delay 1 strand weight 1 delay 2
thread f to show
seed f value 1 at beat 1
run 10 beats
```

Grammar (after filler-stripping):

```
command := "weave" NAME
         | "knot" NAME [VERB] ["trigger" TRIGGER] ["bias" NUM]
         | "thread" SRC DST ["port" NAME] ("strand" PROPERTY*)*
PROPERTY := "weight" NUM | "delay" INT | "drift" NUM | "floor" NUM
          | "ceil" NUM   | "tint" PHRASE | "bearing" PHRASE
PHRASE   := WORD | '"' any text '"'          # a literal " is doubled
         | "seed" DST NUM [INT] ["port" NAME]        # value, then beat
         | "seed" DST "chord" INT NUM+ [INT] ["port" NAME]   # v0.4
         | "run" INT
TRIGGER := "any" | "count" INT | "rise" NUM
```

**A chord announces its width before its voices** (v0.4):

```
seed canvas chord 3 0.84 0.36 0.26 at beat 2
```

The count comes first because bare numbers on a seed line are already
positional — value, then beat — and an unannounced run of numbers could not be
told from a value followed by a beat. Saying "chord 3" first makes the line
unambiguous to the parser and to a listener alike. A line whose count does not
match the numbers that follow is refused, never truncated. `chord` is therefore
a reserved word and cannot name a knot.

A `tint` or `bearing` is a **phrase**, so it may be quoted — and must be
whenever it holds spaces or punctuation, is a filler word, or collides
with a grammar word. Inside quotes nothing is stripped, split or treated
as a comment, which is how a bearing survives being spoken:

```
thread iddo to alma strand weight 1 delay 5 drift 0.06 tint love
       bearing photo/iddo-and-alma-embracing.jpg
   strand weight 3 delay 1 tint anger
       bearing "the sentence neither of them can take back"
```

(Unquoted, that last phrase would come back as *"sentence neither them
can take back"* — the stripper eats `the` and `of`. Quoting is what makes
the phrase one indivisible word.)

The voice grammar is *canonical speech*, not a convenience: the VR editor
and the voice channel emit the same commands, so building by hand and
building by mouth are the same act. (Hebrew command set — `קשר`, `חוט`,
`זרע` — is planned once alma-ozen can feed it; the grammar was designed
keyword-light so it survives translation.)

## 10. The 3D / VR Mapping

The weave is a sculpture you stand inside. Every semantic quantity has
exactly one physical carrier — nothing is decoration:

| Semantic          | Physical (VR)                                          |
|-------------------|--------------------------------------------------------|
| knot              | a graspable solid, floating where you leave it         |
| verb              | the solid's **shape** (sphere=pass/sum, cube=pool, ring=gate, cone=prod, shell=fringe, prism=spell) |
| trigger           | a **collar** around the knot (open=any, notched=count, banded=rise) |
| bias              | a small tile socketed into the knot, engraved with the number |
| thread            | a cord you pull from knot to knot with your hand       |
| strand weight     | the strand's **thickness** (negative = inverted twist) |
| strand delay      | the strand's **length** — pulling knots apart slows the signal |
| spark             | a light running down the strand in real time           |
| pool state        | the knot's glow intensity                              |
| fringe            | knots at the hem, facing outward, showing their record |

Editing gestures: pinch-drag to place a knot; pull a cord for a thread;
stretch to set delay; roll the cord between fingers to set weight; speak
any §9 utterance while pointing. Debugging is walking: you stand inside
the running weave and watch the sparks travel.

Because length *is* delay, spatial reasoning is temporal reasoning: two
strands to the same knot with visibly different lengths are visibly
different echoes. Fibonacci looks like a knot holding two loops of rope,
one loop longer than the other. You can *see* the algorithm from across
the room.

## 11. Prototype vs. Vision (honest ledger)

**Real today (this folder, runs on any Python ≥ 3.10):**
- The full §1–§7 model: knots, multi-strand threads, seven verbs, three
  triggers, deterministic loom.
- **Chord sparks (§1a, v0.4)** — a spark may be several numbers on one beat,
  every verb combines them elementwise, and unequal widths are refused by name
  and beat rather than broadcast away. Both text formats carry them (§8, §9).
  `tests/test_chords.py` — 36 tests, of which one deliberately disables the
  width guard to prove the refusal is what produces the error.
- Strand tints (typed channels) and strand plasticity — weaves that
  learn, §4a. A cord with `drift ≠ 0` thickens when it helped its knot
  speak and thins when it did not, bounded by `floor`/`ceil`, with no
  gradient and nothing travelling backwards; `Result.learned` hands back
  the final weights. Strand `bearing` carries *what* a cord is (a path, a
  phrase) beside *how much* it weighs.
- Both text formats (§8 JSON, §9 voice grammar) with round-tripping —
  **all seven strand properties included**, verified by
  `tests/test_strand_fields.py`, which runs a plastic weave on both sides
  of a round trip and compares what it learned.
- Working example weaves: unit conversion, Fibonacci-by-strands,
  evidence-integration (`rise`).
- **The §10 mapping, rendered and playable — not just designed.**
  `alma/godot.py` exports any weave (plus, optionally, a `Loom.run` result)
  as JSON: the canonical §8 format extended, additively, with a
  deterministic 3D layout and a beat-by-beat playback trace.
  `D:\CLAUDE\alma-vr\godot\scripts\alma_weave.gd` loads that JSON at
  runtime and builds the sculpture the table in §10 describes — knot
  shape = verb, collar = trigger, cord thickness = weight, cord bow =
  delay — and, if a trace is present, plays the run: sparks travel cords
  over exactly their strand's delay, arriving on the beat the loom
  recorded, while knots pulse when they fire. You can `--path . res://
  scenes/alma_weave.tscn` and **walk inside a running weave**, at a
  controllable `beats_per_second`, with `play()`/`pause()`/`restep()`.
  Three real weaves (heat, fib, council) ship pre-exported with traces in
  `alma-vr/godot/weaves/`. Tests: `tests/test_godot.py` (determinism, no
  lost/duplicate knots, cycles still lay out, exact match to `Loom.run`'s
  own scheduling, additive JSON that round-trips through `from_dict`
  unchanged). See `alma-vr/docs/WEAVE-BRIDGE.md` for the full mapping and
  usage.

**Vision (still not built, do not claim otherwise):**
- **Matrix strands (ALMA v0.5).** v0.4 gave the *spark* a width; the *strand*
  is still one number, so a cord scales a chord and cannot rotate one. Until a
  strand can carry an (m×n), no weave can mix voice 0 into voice 1, and a
  `bearing` accompanies a spark rather than multiplying it (§4).
- **Authoring inside VR.** The bridge above is read-only: you can load a
  weave and watch it, but you cannot yet pinch-place a knot, pull a cord,
  stretch a delay, or speak a §9 utterance while pointing, and there is no
  path yet from an edit made in Godot back to a `.json`/`.voice` file the
  language would accept. The editing *gestures* §10 describes remain a
  target, not a feature.
- OpenXR / an actual headset — the bridge scene is flat-screen desktop,
  same as `neuron_forest.tscn`; no VR runtime is wired in yet.
- Live voice input (alma-ozen → §9 grammar), Hebrew command set.
- Parallel/distributed looms; compiling weaves onto ALMA silicon and the
  ALMAPHONE — the beat/strand model maps naturally onto physical signal
  paths, which is *why* the laws are what they are, but no such compiler
  exists yet.

---
*ALMA Language v0.4 — ALMAWARE. 100% ours: model, code, and words.*
