# ALMA Language

**A programming language whose programs are shapes.**
ALMAWARE original — 100% ours: the model, the code, the words.

An ALMA program is a **weave**: named **knots** joined by **threads**,
each thread carrying one or more **strands** (a weight and a delay).
Values travel as **sparks**, time passes in **beats**. You address knots,
never registers. A spark is a number — or, since v0.4, a **chord** of numbers
sounded on one beat. The full model — five words, seven verbs, three triggers,
five design laws — is in [SPEC.md](SPEC.md).

Why it is its own thing:

- **Nothing is instant.** Every strand costs at least one beat, so cycles
  are legal and *are* the loop construct. One `sum` knot with one
  self-thread of two strands (delay 1 and delay 2) emits Fibonacci forever.
- **Arithmetic lives in the connections.** Multiply-by-1.8 is a strand's
  weight; add-32 is a knot's bias. The knots only combine.
- **The layout is the program.** In VR, a strand's length *is* its delay
  and its thickness *is* its weight. Rearranging the sculpture rewrites
  the code — the shape IS the algorithm.
- **One text format is speech.** Every weave is a transcript of spoken
  utterances (`knot f sum` / `thread f to f strand weight 1 delay 2`).
  Building by hand in VR and building by voice are the same act.

## Run it (Python ≥ 3.10, no dependencies)

```
cd D:\CLAUDE\alma-language
python demo.py                                  # three self-checking weaves
python -m unittest discover -s tests -v        # 147 unit tests
python -m pytest tests -q                      # same suite, if you have pytest
```

The demo runs, and asserts the answers of, three real weaves:

1. **heat** — Celsius→Fahrenheit where a *strand* multiplies and a *bias*
   adds (parsed from the voice transcript `examples/heat.voice`).
2. **fib** — Fibonacci from one knot, one thread, two strands
   (loaded from `examples/fib.json`, the format the VR editor will emit).
3. **council** — a `rise`-triggered knot that gathers faint evidence
   across beats and speaks once it crosses the line.

## What is real vs. what is vision

*(This section was stale for weeks — it still claimed v0.1, six verbs, 16 tests
and unbuilt learning strands. Corrected 2026-09-05. SPEC.md §11 is the
authoritative ledger; this is its summary.)*

**Real, in this folder** (v0.4, 147 tests, Python ≥ 3.10, no dependencies):
the complete SPEC §1–§7 execution model with a deterministic loom; **seven**
verbs including `spell`, a knot that carries a named function from a book that
cannot be fed source text; **learning strands** — `drift` thickens a cord that
helped its knot speak and thins one that spoke into silence, with nothing
travelling backwards; **chord sparks** (v0.4) — a spark may be several numbers
at once, combined elementwise, with unequal widths refused by name and beat
rather than broadcast away; both serializations (JSON + voice grammar) carrying
every property, round-tripped; and the read-only **Godot bridge**, which renders
any weave as a sculpture you can walk inside while it runs.

**Vision, not yet built:** authoring *inside* VR (the bridge is read-only, and
nothing leads from an edit in Godot back to a file the language accepts); an
actual headset — the bridge scene is flat-screen desktop and no OpenXR runtime
is wired in; live voice input and a Hebrew command set; **matrix strands** (a
cord that could rotate a chord instead of merely scaling it — ALMA v0.5); and
the silicon compiler. The roadmap below is the plan, not a claim.

## Roadmap to the VR editor

> ⚠️ **These version numbers are the ORIGINAL PLAN and reality has already diverged
> from them.** What actually shipped as v0.2 was *strand plasticity*, v0.3 was *the
> `spell` verb*, and v0.4 (2026-09-05) was *chord sparks* — none of which appear
> below. The browser viewer named "v0.3" here was never built; a **Godot** bridge was
> built instead. Read the list below as a list of *intentions in rough order*, not as
> a version table — SPEC.md §11 is the only ledger of what exists. Left unrewritten
> on purpose: rewriting a plan to match what happened is how a roadmap stops being
> evidence of anything.

- **v0.2 — richer weaves.** Strand tints (typed channels), weave-in-weave
  (a whole weave folded into one knot — the composition story), a `.weave`
  file convention, and a tiny CLI (`alma run fib.weave`).
- **v0.3 — see it flat.** Browser viewer (three.js): load a weave JSON,
  fly around the sculpture, watch sparks travel in real time. Read-only —
  its purpose is to prove the length=delay / thickness=weight mapping
  feels right before hands get involved.
- **v0.4 — touch it.** WebXR (Quest) editing: pinch-place knots, pull
  cords, stretch delays, roll weights. Emits exactly the JSON of SPEC §8.
- **v0.5 — speak it.** Microphone → utterances of SPEC §9. English first;
  Hebrew command set (`קשר`, `חוט`, `זרע`) once alma-ozen can feed it.
- **v0.6 — beyond the PC.** Parallel loom (per-beat firing is naturally
  parallel), then the long line: weaves compiled to physical signal paths
  on ALMA silicon / ALMAPHONE. The laws were chosen so this mapping is
  natural (delays = wire lengths, weights = physical couplings) — but
  that is the horizon, not the prototype.

## Folder

```
SPEC.md            the model (five words, seven verbs, three triggers, five laws)
alma/loom.py       weave + loom: the whole execution model
alma/chords.py     v0.4: the chord — a spark with more than one number in it
alma/spells.py     v0.3: the book behind the seventh verb (names, never code)
alma/text.py       JSON format + voice grammar (parse and render)
alma/godot.py      the read-only VR/3D export (see alma-vr/docs/WEAVE-BRIDGE.md)
demo.py            three self-checking weaves
examples/          fib.json, heat.voice, council.voice
tests/             147 tests: loom, strand fields, spells, chords, godot, world
```
