"""ALMA <-> Godot bridge — the Python side.

The two ends already exist and work: the loom (alma/loom.py) runs weaves,
and the VR world (D:\\CLAUDE\\alma-vr\\godot) is a real walkable Godot 4.3
scene. Nothing sat between them. This module is that bridge.

``weave_scene`` takes a Weave (and optionally a completed Result) and
returns the *canonical* ALMA JSON (alma.text.to_dict — SPEC.md §8) with two
more top-level blocks bolted on, additively:

    "scene": a deterministic 3D layout — one position per knot.
    "trace": present only if a Result was given — every fire, every
             fringe record, and every scheduled spark departure/arrival,
             so the VR side can play a run beat-for-beat without having
             to re-derive the loom's own scheduling.

Additive means exactly that: ``alma.text.from_dict`` never looks at keys
it doesn't know, so ``from_dict(weave_scene(w))`` reconstructs a Weave
behaviourally identical to ``w``. The wire format (§8) is not reinvented
here — it is extended.

Layout law (SPEC.md §10, "the layout is the program"): BFS-layer the graph
from the seeded knots (layer = shortest hop distance), lay layers out along
+Z, spread each layer's knots on a circle (or a line for <=3), and give
knots unreachable from any seed their own ring, behind the seeds. Seeded
jitter, fixed seed: same weave in, same positions out, every time. No
physics, no force-directed relaxation — a person must be able to predict
where a knot lands from the weave alone.

    python -m alma.godot --weave fib --out ../alma-vr/godot/weaves/fib.json --run 10
    python -m alma.godot --json some_weave.json --out scene.json
"""
from __future__ import annotations

import argparse
import json
import math
import random
from collections import defaultdict
from pathlib import Path

from .loom import Loom, Result, Weave
from .text import from_json, parse_voice, to_dict

# ---------------------------------------------------------------- layout

DEFAULT_SEED = 1337
LAYER_SPACING = 6.0     # +Z distance between BFS hop layers
BASE_Y = 3.0            # comfortable walking-height center for a layer
JITTER = 0.35           # +/- meters of seeded random nudge, for legibility
RING_MIN_RADIUS = 2.2
RING_SCALE = 1.15       # radius grows with knot count so rings don't crowd


def _bfs_layers(weave: Weave) -> tuple[dict[str, int], set[str]]:
    """Shortest-hop distance from the set of seeded knots, multi-source BFS.

    Returns (layer_of_name, names_unreachable_from_any_seed). Cycles are
    fine — BFS visits each name once, so a weave with a self-thread or a
    longer cycle still gets a finite layer for every knot a seed can reach.
    """
    sources: list[str] = []
    seen: set[str] = set()
    for s in weave.seeds:
        if s.dst not in seen:
            seen.add(s.dst)
            sources.append(s.dst)

    adj: dict[str, list[str]] = defaultdict(list)
    for t in weave.threads:
        adj[t.src].append(t.dst)

    layer: dict[str, int] = {name: 0 for name in sources}
    frontier = list(sources)
    while frontier:
        nxt: list[str] = []
        for name in frontier:
            for dst in adj.get(name, ()):
                if dst not in layer:
                    layer[dst] = layer[name] + 1
                    nxt.append(dst)
        frontier = nxt

    unreachable = {name for name in weave.knots if name not in layer}
    return layer, unreachable


def _place_group(names: list[str], z: float, rng: random.Random,
                  positions: dict[str, tuple[float, float, float]]) -> None:
    """Place one layer's (or the orphan ring's) knots and write into
    ``positions``. <=3 knots: a short line. More: a circle, so a big layer
    doesn't collapse into an unreadable clump."""
    n = len(names)
    if n == 0:
        return
    if n <= 3:
        span = 3.2
        for i, name in enumerate(names):
            x = 0.0 if n == 1 else (i - (n - 1) / 2.0) * span
            positions[name] = (
                round(x + rng.uniform(-JITTER, JITTER), 4),
                round(BASE_Y + rng.uniform(-JITTER, JITTER), 4),
                round(z, 4),
            )
        return
    radius = max(RING_MIN_RADIUS, RING_SCALE * n)
    y_amp = min(radius, 3.0)          # keep the ring from diving underground
    for i, name in enumerate(names):
        ang = 2 * math.pi * i / n
        x = radius * math.cos(ang)
        y = BASE_Y + y_amp * math.sin(ang) * 0.8
        positions[name] = (
            round(x + rng.uniform(-JITTER, JITTER), 4),
            round(y + rng.uniform(-JITTER, JITTER), 4),
            round(z, 4),
        )


def layout(weave: Weave, seed: int = DEFAULT_SEED
           ) -> dict[str, tuple[float, float, float]]:
    """A deterministic (x, y, z) per knot name. Same weave + seed -> same
    positions, every call, on every machine."""
    layer_of, unreachable = _bfs_layers(weave)
    by_layer: dict[int, list[str]] = defaultdict(list)
    for name in weave.knots:                 # insertion order: deterministic
        if name in layer_of:
            by_layer[layer_of[name]].append(name)
    orphans = [name for name in weave.knots if name in unreachable]

    rng = random.Random(seed)
    positions: dict[str, tuple[float, float, float]] = {}
    for lyr in sorted(by_layer):
        _place_group(by_layer[lyr], lyr * LAYER_SPACING, rng, positions)
    if orphans:
        # "cyclic/unreachable knots get their own ring" — one hop behind
        # the seeds, so it reads as disconnected from the story, not lost.
        _place_group(orphans, -LAYER_SPACING, rng, positions)
    return positions


# ----------------------------------------------------------------- trace

def spark_trace(weave: Weave, result: Result) -> list[dict]:
    """Every spark departure/arrival that actually took effect within a
    completed Result, recomputed by replaying Loom.run's own scheduling
    rule (SPEC.md §7 step 2: value x weight, arriving beat + delay) over
    its finished fires. This is what lets the VR side play a run
    beat-for-beat instead of re-deriving the loom in GDScript.

    A spark scheduled to arrive after ``result.beats`` never actually
    landed — the horizon cut the run before delivery — so it is left out;
    otherwise the trace would show a spark travelling toward a beat that
    never happened.
    """
    outgoing: dict[str, list] = defaultdict(list)
    for t in weave.threads:
        outgoing[t.src].append(t)

    events: list[dict] = []
    for f in result.fires:
        if f.spoke is None:                   # closed gate / silent fire
            continue
        knot = weave.knots.get(f.knot)
        if knot is None or knot.verb == "fringe":   # the fringe has no voice
            continue
        for t in outgoing.get(f.knot, ()):
            for s in t.strands:
                arrival = f.beat + int(s.delay)
                if arrival > result.beats:
                    continue
                events.append({
                    "from": f.knot,
                    "to": t.dst,
                    "port": t.port,
                    "weight": s.weight,
                    "delay": s.delay,
                    "depart_beat": f.beat,
                    "arrival_beat": arrival,
                    "value": f.spoke * s.weight,
                })
    return events


# ------------------------------------------------------------------ API

def weave_scene(weave: Weave, result: Result | None = None,
                 seed: int = DEFAULT_SEED) -> dict:
    """The canonical weave dict (alma.text.to_dict, SPEC.md §8) plus an
    additive "scene" block (layout) and, if ``result`` is given, a "trace"
    block (the run). Additive only — see module docstring."""
    d = to_dict(weave)
    positions = layout(weave, seed)
    d["scene"] = {
        "seed": seed,
        "layout": "bfs-layer",
        "positions": {name: list(p) for name, p in positions.items()},
    }
    if result is not None:
        d["trace"] = {
            "beats": result.beats,
            "finished": result.finished,
            "fires": [{"beat": f.beat, "knot": f.knot, "spoke": f.spoke}
                      for f in result.fires],
            "fringes": {name: [[b, v] for b, v in vals]
                        for name, vals in result.fringes.items()},
            "sparks": spark_trace(weave, result),
        }
    return d


def export(weave: Weave, path: str | Path, result: Result | None = None,
           seed: int = DEFAULT_SEED) -> None:
    """Write weave_scene(weave, result, seed) to ``path`` as JSON."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(weave_scene(weave, result, seed), indent=2) + "\n",
                 encoding="utf-8")


# ------------------------------------------------------------------ CLI

_EXAMPLES = Path(__file__).resolve().parent.parent / "examples"

_NAMED_LOADERS = {
    "heat": lambda: parse_voice(
        (_EXAMPLES / "heat.voice").read_text(encoding="utf-8")),
    "fib": lambda: from_json(
        (_EXAMPLES / "fib.json").read_text(encoding="utf-8")),
    "council": lambda: parse_voice(
        (_EXAMPLES / "council.voice").read_text(encoding="utf-8")),
}


def _load_named(name: str) -> Weave:
    try:
        loader = _NAMED_LOADERS[name]
    except KeyError:
        raise SystemExit(
            f"unknown --weave '{name}' (known: "
            f"{', '.join(sorted(_NAMED_LOADERS))})") from None
    return loader()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="python -m alma.godot",
        description="Export an ALMA weave as a 3D scene JSON for the "
                     "Godot bridge (D:\\CLAUDE\\alma-vr\\godot).")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--weave", choices=sorted(_NAMED_LOADERS),
                      help="one of the built-in example weaves")
    src.add_argument("--json", metavar="PATH",
                      help="convert an existing ALMA JSON file instead")
    p.add_argument("--out", required=True, metavar="PATH",
                    help="where to write the scene JSON")
    p.add_argument("--run", type=int, metavar="BEATS",
                    help="also run the weave for BEATS beats and embed "
                         "the trace (spark-by-spark playback data)")
    p.add_argument("--seed", type=int, default=DEFAULT_SEED,
                    help="layout jitter seed (default: %(default)s)")
    args = p.parse_args(argv)

    w = (_load_named(args.weave) if args.weave
         else from_json(Path(args.json).read_text(encoding="utf-8")))

    result = Loom().run(w, args.run) if args.run else None
    export(w, args.out, result, args.seed)
    suffix = f" (trace: {args.run} beats)" if args.run else ""
    print(f"wrote {args.out}{suffix}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
