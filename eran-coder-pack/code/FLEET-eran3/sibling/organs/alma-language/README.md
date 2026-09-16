# ALMA Language

**A programming language whose programs are shapes.**
ALMAWARE original — 100% ours: the model, the code, the words.

An ALMA program is a **weave**: named **knots** joined by **threads**,
each thread carrying one or more **strands** (a weight and a delay).
Values travel as **sparks**, time passes in **beats**. You address knots,
never registers. The full model — five words, six verbs, three triggers,
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
python -m unittest discover -s tests -v        # 16 unit tests
```

The demo runs, and asserts the answers of, three real weaves:

1. **heat** — Celsius→Fahrenheit where a *strand* multiplies and a *bias*
   adds (parsed from the voice transcript `examples/heat.voice`).
2. **fib** — Fibonacci from one knot, one thread, two strands
   (loaded from `examples/fib.json`, the format the VR editor will emit).
3. **council** — a `rise`-triggered knot that gathers faint evidence
   across beats and speaks once it crosses the line.

## What is real vs. what is vision

**Real, in this folder:** the complete v0.1 execution model (SPEC §1–§7),
a deterministic loom in ~200 lines of Python, both serializations
(JSON + voice grammar) with round-tripping, examples, tests.

**Vision, not yet built:** the VR editor, live voice input, Hebrew
commands, learning strands, the silicon compiler. Nothing below this line
exists yet — the roadmap is the plan, not a claim.

## Roadmap to the VR editor

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
SPEC.md            the model (five words, six verbs, three triggers, five laws)
alma/loom.py       weave + loom: the whole execution model
alma/text.py       JSON format + voice grammar (parse and render)
demo.py            three self-checking weaves
examples/          fib.json, heat.voice, council.voice
tests/test_loom.py unit tests
```
