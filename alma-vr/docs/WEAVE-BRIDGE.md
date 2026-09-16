# 🪟 BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

# The Weave Bridge — ALMA language <-> Godot

**The thing that was asked for four times and never built.** Both ends
already existed and worked on their own: `D:\CLAUDE\alma-language` runs
weaves (27/27 tests passing before this bridge, real loom, real math), and
`D:\CLAUDE\alma-vr\godot` is a real walkable Godot 4.3 scene (neuron
forest, WASD player, an NPC that talks to the DGX fleet). Nobody had
written what sits *between* them. This is that bridge.

## What it is

An ALMA **weave** (a program — knots, threads, strands; SPEC.md §1–§9) can
now be exported as a 3D scene and loaded straight into Godot, where you
can **walk inside it** and, if it was run, **watch it think** — a small
spark travels each cord over exactly as many beats as its strand's delay,
arriving exactly when the loom says it arrives.

Two new files carry the bridge:

- `D:\CLAUDE\alma-language\alma\godot.py` — Python side. Turns a `Weave`
  (optionally with a `Result` from a run) into JSON: the canonical ALMA
  format (SPEC.md §8) plus two additive blocks, `"scene"` (a deterministic
  3D layout) and `"trace"` (the run, replayable beat by beat).
- `D:\CLAUDE\alma-vr\godot\scripts\alma_weave.gd` — Godot side. Loads that
  JSON at runtime and builds/animates the sculpture.

Additive means exactly that: `alma.text.from_dict` never looks at keys it
doesn't know, so loading a scene-exported JSON back through the language
reconstructs the identical weave. The wire format from SPEC.md §8 was not
reinvented — only extended.

## How to export a weave

```
cd D:\CLAUDE\alma-language
python -m alma.godot --weave fib     --out ..\alma-vr\godot\weaves\fib.json     --run 10
python -m alma.godot --weave heat    --out ..\alma-vr\godot\weaves\heat.json    --run 8
python -m alma.godot --weave council --out ..\alma-vr\godot\weaves\council.json --run 10
```

`--weave {heat,fib,council}` loads one of the language's own example
fixtures (`examples/heat.voice`, `examples/fib.json`,
`examples/council.voice`). `--json PATH` converts an existing ALMA JSON
file instead. `--run N` runs the weave for N beats and embeds the trace
(fires, fringe records, and every scheduled spark departure/arrival) so
the scene can be played, not just viewed static. `--seed N` changes the
layout's jitter seed (default 1337) — same weave and seed always produce
the same positions.

The three weaves above are already exported and committed at
`D:\CLAUDE\alma-vr\godot\weaves\{heat,fib,council}.json`, so the scene
works out of the box with no export step required first.

## How to run the scene

The main scene (`res://scenes/neuron_forest.tscn`, the spy-thriller world)
is untouched — `alma_weave.tscn` lives alongside it, not instead of it.
Open the project in the Godot 4.3 editor and switch scenes, or run it
directly:

```
D:\tools\godot43\Godot_v4.3-stable_win64.exe --path D:\CLAUDE\alma-vr\godot res://scenes/alma_weave.tscn
```

Once inside: WASD + mouse to walk (same as the neuron forest), Esc to
release the mouse. The exported `AlmaWeave` node has three properties in
the inspector: `weave_path` (which JSON to load — default `fib.json`),
`beats_per_second` (playback speed, default 0.6 — slow enough to actually
watch a weave think), and `autoplay`. The script also exposes
`play()`/`pause()`/`restep(beats)` for driving playback from another
script or the in-editor remote debugger.

## The mapping (SPEC.md §10, now built)

| Semantic | Physical (built) |
|---|---|
| knot | a solid, positioned by a deterministic BFS-layer layout |
| verb | the solid's **shape** — sphere (pass/sum), box (pool), torus (gate), cone (prod), hemisphere (fringe) |
| trigger | a **collar** around the knot's equator — open ring (any), notched ring with N notches (count N), wide band (rise T) |
| bias | a small floating tile engraved with the number, shown only when nonzero |
| thread | one **cord per strand** — a 3-strand thread is 3 visible cords |
| strand weight | the cord's **thickness**; negative weight = a cool colour instead of warm |
| strand delay | the cord's **path** — straight for delay 1, a visible bow/arc for delay > 1 |
| spark | a small emissive sphere travelling the cord in real time, from the trace |
| pool state | (not yet wired to a live glow — see below) |
| fringe | a hemisphere, the hem of the weave, facing outward |

## Layout law

Knots are BFS-layered from the seeded knots: layer = shortest hop
distance from any seed. Layers run along +Z (you walk *through* the
program as it unfolds). Within a layer, ≤3 knots sit on a short line;
more sit on a circle, so a busy layer never collapses into an unreadable
clump. Knots unreachable from any seed get their own ring, one layer
*behind* the seeds (negative Z) — visibly disconnected from the story
being told. A single fixed-seed RNG (default 1337) adds small
deterministic jitter for legibility; there is no physics and no
force-directed relaxation, so a person can predict where a knot will land
just from reading the weave. See `alma-language/tests/test_godot.py` for
the properties this guarantees (determinism, no duplicate/missing knots,
cycles still lay out, exact match to `Loom.run`'s own scheduling).

## What is not built yet (honest ledger)

- **Hand-editing in VR.** You can only load a weave and watch it; you
  cannot yet pinch-place a knot, pull a cord, or speak a SPEC.md §9
  utterance to build one. The mapping above is read-only.
- **Writing edits back to JSON.** There is no path yet from "moved a knot
  in Godot" back to a `.json` (or `.voice`) file the language would
  accept. Editing gestures from SPEC.md §10 are a target, not a feature.
- **OpenXR / actual headset.** `alma_weave.tscn` is a flat-screen desktop
  scene, same as `neuron_forest.tscn`. No VR headset support has been
  wired into this bridge; that is `D:\CLAUDE\alma-vr\docs\GAME-DESIGN.md`
  milestone M3's job, not this one's.
- **Pool-state glow.** SPEC.md §10 maps pool state to "the knot's glow
  intensity" as a *continuous* readout; today the box knot for `pool`
  gets the same fire-pulse as every other verb, not a persistent glow
  tied to its accumulated state between fires.
- **Live re-export.** The bridge is export-then-load, not a live link —
  changing a weave in Python does not update a running Godot scene; you
  re-run the exporter and reload.

*ALMA VR — ALMAWARE. 100% ours: model, bridge, code, and words.*
