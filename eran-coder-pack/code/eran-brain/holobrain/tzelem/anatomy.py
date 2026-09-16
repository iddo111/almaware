"""TZELEM / צלם — THE ANATOMY: the beat IS the depth.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

לזכרה של עלמה ז"ל.

THE CLAIM THIS FILE EXISTS TO PROVE
-----------------------------------
ALMA's first law:      *nothing is instant; every strand costs >= 1 beat; distance is time.*
Rendering's first law: *what is farther away is hidden.*

They are the same law. So in TZELEM:

    a knot   is a brushstroke, anchored to a point on a surface in the world
    a thread is that stroke's path to one patch of canvas
    the DELAY of that thread IS THE DEPTH
    the canvas patch keeps THE FIRST SPARK THAT ARRIVES

and that is the whole hidden-surface algorithm. There is no depth buffer in this
file. There is no sort. Nothing anywhere compares two depths. Occlusion happens
because the near stroke's spark simply gets there first — the language does it.

WINSTON's facade was "the strand IS the stroke". TZELEM's is "THE BEAT IS THE DEPTH",
and `tests/test_organ.py` proves it the only way that counts: move a stroke farther
away, change no code, and watch the picture occlude differently.

HONEST LIMITS, stated before anyone can be misled:
  * COLOUR NOW TRAVELS THE WEAVE (2026-09-05). This paragraph used to read: *"A
    spark in ALMA v0.3 is a scalar. So a stroke's spark carries ONE number — a
    palette index, not an RGB triple. Colour is looked up outside the weave."*
    ALMA v0.4 gave a spark a WIDTH (`alma/chords.py`), so `weave_for_colour` seeds
    each stroke with a **chord of three voices — its actual RGB** — and the tile
    keeps the first chord that arrives. The organ of a holobrain whose law is
    *everything inside must be ALMA* no longer carries a receipt for a colour; it
    carries the colour. `test_the_colour_travels_the_cord` proves it the only way
    that counts: halve one cord's weight and the painted colour must halve, which
    a lookup table physically cannot do.
    What is STILL true, and is the reason `palette.py` has not been deleted: the
    weave runs at TILE resolution, so the full-resolution painting in `canvas.py`
    is still numpy reading a table. The definition carries colour; the fast body
    still looks it up, and `test_the_loom_and_the_palette_agree` is the chain
    between them.
  * A cord's weight is still ONE number, so a cord can SCALE a chord but cannot
    rotate one — no strand mixes red into green. That is ALMA v0.5's door and it
    is shut.
  * The weave runs the canvas at TILE resolution (hundreds of knots). 4K is 8.3M
    pixels; a Python loom will not run 8.3M knots per frame and pretending otherwise
    would be the overselling this lab has a law against. So `paint_tiles_numpy`
    reimplements the SAME semantics in numpy for real resolutions, and
    `test_organ.py::test_numpy_is_pinned_to_the_weave` refuses to pass unless the two
    agree exactly. The weave is the definition; numpy is the fast body; the test is
    the chain between them. This is the pattern WINSTON already uses on eran4.
  * Ties: two strokes landing on one tile at the same beat would SUM (`fringe` sums
    its tray), which would be a wrong colour. So `_delays` bumps a collision one beat
    farther — deterministic, monotone in depth, and it can only ever push the FARTHER
    stroke later. Depth order is never inverted by it.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
_ALMA = os.path.abspath(os.path.join(_HERE, "..", "..", "..", "alma-language"))
if _ALMA not in sys.path:
    sys.path.insert(0, _ALMA)

from alma import Chord, Loom, Strand, Weave      # noqa: E402

EMPTY = 0.0          # a tile nobody reached
BUCKET = 0.06        # world units per beat — the exchange rate between space and time


# --------------------------------------------------------------- strokes

@dataclass
class Strokes:
    """Brushstrokes anchored in the WORLD, not on the screen.

    That single choice is the whole difference between a painting of a frame and a
    renderer: when the camera moves, these do not get repainted — they get re-seen.

    point  (N,3) world anchor        normal (N,3) surface normal at the anchor
    rgb    (N,3) colour              radius (N,)  world-space size

    tangent (N,3) OPTIONAL world direction the stroke lies along, inside the
    surface. None (the default) keeps the original behaviour exactly: the
    direction is `cross(normal, view)`, which is a legal surface tangent but an
    ARBITRARY one -- so strokes point every which way and no edge ever reads as a
    line. Giving a tangent lets a planter say "this stroke lies along the trunk",
    and because it is a WORLD vector in the surface it still turns with the wall
    when the camera moves. Nothing else in TZELEM changes.

    elong (N,) OPTIONAL per-stroke ratio of half-length to half-width. None (the
    default) keeps the original behaviour exactly: the style decides the shape and
    every stroke of a style is drawn from the same distribution. Giving it lets a
    planter say "this stroke is a SHORT DAB because a boundary is 3 px away" —
    which is what a painter does at an edge, and it keeps the stroke's WIDTH, so
    the canvas does not open holes the way shrinking the whole stroke does.
    """
    point: np.ndarray
    normal: np.ndarray
    rgb: np.ndarray
    radius: np.ndarray
    tangent: np.ndarray | None = None
    elong: np.ndarray | None = None
    # TZ-9 (2026-09-06): how many strokes the planter was ASKED for. `len(strokes)`
    # alone cannot tell a full painting from one that got 3% of its brush.
    asked: int | None = None

    def __len__(self) -> int:
        return int(self.point.shape[0])


def scatter(stage, cam, n: int = 220, seed: int = 7,
            size: float = 0.020) -> Strokes:
    """Plant n strokes on the surfaces this camera can see.

    They are planted ONCE, in the world. Every later frame re-projects these same
    strokes — the organ's whole coherence claim rests on that and nothing else.
    """
    g = stage.gbuffer(cam)
    seen = stage.shade(g)          # what the eye receives, not what the wall is
    ys, xs = np.nonzero(g["mask"])
    if len(xs) == 0:
        raise ValueError("the camera sees nothing — no surface to plant strokes on")
    rng = np.random.default_rng(seed)
    # TZ-9 (2026-09-06): this line silently plants fewer strokes than asked whenever
    # the camera sees few surface pixels -- no warning, no exception, just an emptier
    # painting. The total miss above has a named refusal; the NEAR miss had nothing,
    # and the near miss is the one that produces a plausible-looking bad picture.
    # Measured: 100,000 asked on a 24x18 camera returned 360, silently.
    if len(xs) < n:
        print(f"anatomy.scatter: planted {len(xs)}/{n} strokes — the camera sees "
              f"only {len(xs)} surface pixels", flush=True)
    pick = rng.choice(len(xs), size=min(n, len(xs)), replace=False)
    y, x = ys[pick], xs[pick]
    depth = g["depth"][y, x]
    return Strokes(
        point=g["point"][y, x],
        normal=g["normal"][y, x],
        rgb=seen[y, x],
        # Constant ANGULAR size: a stroke covers the same patch of canvas wherever it
        # sits, so the picture does not thin out with distance. 0.055 was a 9-pixel
        # radius on a 200-wide canvas — one stroke was 5% of the image and the painting
        # could not be anything but blurry.
        radius=size * depth,
        asked=int(n),
    )


# ------------------------------------------------------- the weave itself

def _tile_of(px, py, cam, tiles):
    """Which canvas patch a projected stroke lands on. -1 = off canvas."""
    tx = np.floor(px / cam.width * tiles).astype(np.int64)
    ty = np.floor(py / cam.height * tiles).astype(np.int64)
    ok = (tx >= 0) & (tx < tiles) & (ty >= 0) & (ty < tiles)
    return np.where(ok, ty * tiles + tx, -1)


def _delays(depth: np.ndarray, tile: np.ndarray) -> np.ndarray:
    """DEPTH -> BEATS. The only place in TZELEM where distance becomes time.

    Monotone: farther is never earlier. Collisions inside one tile are pushed one
    beat farther, in depth order, so `fringe` never sums two strokes into a colour
    that belongs to neither.
    """
    # TZ-10 (2026-09-06): `depth` deliberately holds np.inf for every stroke BEHIND
    # the camera. Casting that to int64 gives INT64_MIN ("RuntimeWarning: invalid
    # value encountered in cast", fired on every gate frame after a camera move), and
    # the np.maximum(...,1) that followed turned INT64_MIN into beat 1 — the EARLIEST
    # slot. An off-screen stroke was being handed the winning beat, and the only thing
    # stopping it mattering was an unrelated guard (tile == -1) twenty lines away.
    # Now a stroke that is not in front of the camera carries -1, which no consumer
    # can mistake for a beat.
    finite = np.isfinite(depth)
    live = depth[finite]
    d0 = float(live.min()) if live.size else 0.0
    beats = np.full(depth.shape, -1, dtype=np.int64)
    beats[finite] = np.maximum(
        1 + np.rint((depth[finite] - d0) / BUCKET), 1.0).astype(np.int64)
    # BY DEPTH, never by beat. Sorting the collision pass by the QUANTISED beat let
    # two strokes in one bucket be seated in arrival order instead of distance order,
    # so a farther stroke could be handed the earlier slot — the one thing "distance
    # is time" forbids. test_delays_never_invert_depth caught it.
    order = np.lexsort((depth, tile))          # by tile, then by true depth
    taken: dict[tuple[int, int], bool] = {}
    for i in order:
        t = int(tile[i])
        if t < 0:
            continue
        b = int(beats[i])
        while (t, b) in taken:
            b += 1
        taken[(t, b)] = True
        beats[i] = b
    return beats


def weave_for(strokes: Strokes, cam, tiles: int = 12) -> tuple[Weave, np.ndarray]:
    """Build the ALMA weave for one view. Returns (weave, delays).

    knots:   one per stroke  (`pass`)   +  one per canvas tile (`fringe`)
    threads: stroke -> tile, delay = depth in beats, weight = 1
    seeds:   every stroke is knocked awake on beat 1 carrying its palette index
    """
    px, py, z = cam.project(strokes.point)
    depth = np.linalg.norm(strokes.point - cam.eye, axis=-1)
    depth = np.where(z > 0, depth, np.inf)
    tile = _tile_of(px, py, cam, tiles)
    tile = np.where(np.isfinite(depth), tile, -1)
    beats = _delays(depth, tile)

    w = Weave("tzelem")
    for t in range(tiles * tiles):
        w.knot(f"canvas_{t}", verb="fringe")
    for i in range(len(strokes)):
        w.knot(f"stroke_{i}", verb="pass")
        w.seed(f"stroke_{i}", 1.0, beat=1)
        if tile[i] < 0:
            continue
        # the spark IS the palette index; the strand's weight carries it, the
        # strand's DELAY carries the depth. Nothing else is needed.
        w.thread(f"stroke_{i}", f"canvas_{int(tile[i])}",
                 strands=[Strand(weight=float(i + 1), delay=int(beats[i]))])
    # TZ-10: a bare .max() over an empty selection died with numpy's own
    # "zero-size array to reduction operation maximum which has no identity" —
    # twenty lines after scatter's properly named refusal for the same condition.
    front = np.isfinite(depth)
    if len(strokes) and not front.any():
        raise ValueError("no stroke is in front of this camera — nothing to weave")
    w.run_hint = int(beats[front].max()) + 2 if len(strokes) else 4
    return w, beats


def paint_tiles_weave(strokes: Strokes, cam, tiles: int = 12) -> np.ndarray:
    """Run the real ALMA loom. The FIRST spark to reach a tile wins it.

    Returns (tiles, tiles) of stroke index + 1, or EMPTY where nothing arrived.
    """
    w, _ = weave_for(strokes, cam, tiles)
    res = Loom().run(w)
    out = np.full((tiles, tiles), EMPTY)
    for t in range(tiles * tiles):
        rec = res.fringes.get(f"canvas_{t}")
        if rec:
            out[t // tiles, t % tiles] = rec[0][1]      # rec[0] is the earliest beat
    return out


def paint_tiles_numpy(strokes: Strokes, cam, tiles: int = 12) -> np.ndarray:
    """The same semantics, without the loom. Pinned to it by the test.

    Reads only the delays — never the depths — so that if `_delays` ever stopped
    encoding depth, this would break in exactly the same way the weave does.
    """
    px, py, z = cam.project(strokes.point)
    depth = np.linalg.norm(strokes.point - cam.eye, axis=-1)
    depth = np.where(z > 0, depth, np.inf)
    tile = _tile_of(px, py, cam, tiles)
    tile = np.where(np.isfinite(depth), tile, -1)
    beats = _delays(depth, tile)

    out = np.full((tiles, tiles), EMPTY)
    first = np.full(tiles * tiles, np.inf)
    for i in np.argsort(beats, kind="stable"):
        t = int(tile[i])
        if t < 0 or beats[i] >= first[t]:
            continue
        first[t] = beats[i]
        out[t // tiles, t % tiles] = i + 1
    return out


# ------------------------------------------------- the weave that carries COLOUR
#
# ALMA v0.4 (2026-09-05) gave a spark a WIDTH. Everything below is what that buys
# TZELEM, and it is a deletion, not an addition: the palette INDEX that used to
# ride the strand was a workaround for a scalar spark, and it is gone from here.
#
#   before (v0.3):  seed 1.0        strand weight = i+1      -> a tile holds an INDEX
#   after  (v0.4):  seed chord(rgb) strand weight = 1.0      -> a tile holds a COLOUR
#
# Note what did NOT change: the delay. Occlusion is still the beat and nothing but
# the beat, so `test_the_beat_is_the_depth` covers this weave word for word.

def weave_for_colour(strokes: Strokes, cam, tiles: int = 12) -> tuple[Weave, np.ndarray]:
    """The same weave as `weave_for`, except the spark IS the colour.

    knots:   one per stroke (`pass`)  +  one per canvas tile (`fringe`)
    threads: stroke -> tile, delay = depth in beats, weight = 1
    seeds:   every stroke is knocked awake on beat 1 carrying a 3-voice chord —
             the shaded RGB sampled at its anchor, which is what a painter sees.

    The weight is 1.0 and means it: a cord that is fully open passes a colour
    through unchanged. Turn a weight down and the colour that lands is dimmer,
    because a strand's weight scales every voice of a chord (SPEC.md §1a).
    """
    px, py, z = cam.project(strokes.point)
    depth = np.linalg.norm(strokes.point - cam.eye, axis=-1)
    depth = np.where(z > 0, depth, np.inf)
    tile = _tile_of(px, py, cam, tiles)
    tile = np.where(np.isfinite(depth), tile, -1)
    beats = _delays(depth, tile)

    rgb = np.asarray(strokes.rgb, dtype=np.float64)
    if rgb.ndim != 2 or rgb.shape[1] != 3:
        raise ValueError(f"a stroke's colour is (N,3), got {rgb.shape}")

    w = Weave("tzelem-colour")
    for t in range(tiles * tiles):
        w.knot(f"canvas_{t}", verb="fringe")
    for i in range(len(strokes)):
        w.knot(f"stroke_{i}", verb="pass")
        # THE CHANGE: the spark is the colour, not a receipt for one.
        w.seed(f"stroke_{i}", Chord(rgb[i]), beat=1)
        if tile[i] < 0:
            continue
        w.thread(f"stroke_{i}", f"canvas_{int(tile[i])}",
                 strands=[Strand(weight=1.0, delay=int(beats[i]))])
    # TZ-10: a bare .max() over an empty selection died with numpy's own
    # "zero-size array to reduction operation maximum which has no identity" —
    # twenty lines after scatter's properly named refusal for the same condition.
    front = np.isfinite(depth)
    if len(strokes) and not front.any():
        raise ValueError("no stroke is in front of this camera — nothing to weave")
    w.run_hint = int(beats[front].max()) + 2 if len(strokes) else 4
    return w, beats


def paint_tiles_weave_colour(strokes: Strokes, cam, tiles: int = 12,
                             background=(0.82, 0.87, 0.94),
                             cut: float | None = None) -> np.ndarray:
    """Run the real ALMA loom and get back a PICTURE. (tiles, tiles, 3) in 0..1.

    No palette is consulted anywhere in this function. The first chord to reach a
    tile is that tile's colour, exactly as the first spark to reach a tile was
    that tile's owner — the same law, now carrying what it was always about.

    `cut` IS THE FACADE KNIFE, and it lives here on purpose — the same reason
    MOREH's `run_weave` carries one. Every strand's weight is multiplied by it
    before the loom runs, so `cut=0.5` must halve the painted colour and
    `cut=0.0` must put it out. **A painter that looked its colour up in a table
    would be blind to this**, because a lookup is indexed by who won and knows
    nothing about how open the cord was.

    It is here rather than in the test because of what happened when it was NOT:
    the first version of `test_the_colour_travels_the_cord` built its own weave
    and ran the loom itself, so it never entered this function — and a deliberate
    mutation that replaced this whole body with an index-and-lookup (i.e. exactly
    the v0.3 facade wearing the v0.4 name) passed all fourteen tests. The knife
    has to cut the thing people actually call.
    """
    w, _ = weave_for_colour(strokes, cam, tiles)
    if cut is not None:
        for t in w.threads:
            for st in t.strands:
                st.weight *= float(cut)
    res = Loom().run(w)
    out = np.tile(np.asarray(background, dtype=np.float64), (tiles, tiles, 1))
    for t in range(tiles * tiles):
        rec = res.fringes.get(f"canvas_{t}")
        if rec:
            out[t // tiles, t % tiles] = np.asarray(rec[0][1])   # earliest beat
    return out


def paint_tiles_numpy_colour(strokes: Strokes, cam, tiles: int = 12,
                             background=(0.82, 0.87, 0.94)) -> np.ndarray:
    """The same semantics without the loom. Pinned to it by the test.

    Reads only the delays — never the depths — so that if `_delays` ever stopped
    encoding depth this would break in exactly the way the weave does.
    """
    px, py, z = cam.project(strokes.point)
    depth = np.linalg.norm(strokes.point - cam.eye, axis=-1)
    depth = np.where(z > 0, depth, np.inf)
    tile = _tile_of(px, py, cam, tiles)
    tile = np.where(np.isfinite(depth), tile, -1)
    beats = _delays(depth, tile)
    rgb = np.asarray(strokes.rgb, dtype=np.float64)

    out = np.tile(np.asarray(background, dtype=np.float64), (tiles, tiles, 1))
    first = np.full(tiles * tiles, np.inf)
    for i in np.argsort(beats, kind="stable"):
        t = int(tile[i])
        if t < 0 or beats[i] >= first[t]:
            continue
        first[t] = beats[i]
        out[t // tiles, t % tiles] = rgb[i]
    return out
