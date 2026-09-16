# KAV-first-shape.stl — what it is, and what it is not

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

**KAV-15, measured 2026-09-06. `KAV-first-shape.stl` is STALE, and it is NOT A SOLID.**

It is 684 bytes, 12 faces, mtime **2026-09-02 05:35** — it PREDATES the 2026-09-03
rebuild of KAV onto vertex indices, which changed the grammar entirely. Until today no
code in this repository could write it: `mesh.write_stl` had **zero callers** anywhere
in `holobrain`. So the run leg produced stdout and nothing else, and three live
consumers were pinned to output from a model version that no longer exists:

- `tzelem/night.py:135` (its docstring calls it "the cube ERAN's own modeller emitted")
- `tzelem/hero8k.py:48`
- `einayim/truthviews.py:280`

Measured this morning with the live ruler:

| | faces | watertight | volume | bounding box |
|---|---|---|---|---|
| `KAV-first-shape.stl` (2026-09-02) | 12 | **False** | 364.635 | 0..40 on every axis |
| `KAV-first-shape-20260906.stl` (today) | 12 | **True** | 1.000 | 0..1 on every axis |

**The old one does not close.** 36 of its edges are owned by one face. It is
0.57% of its own bounding box by volume. It has been rendered as "the cube ERAN's
modeller emitted" for four days and it is a soup, not a cube.

## What was done, and what was deliberately NOT done

`KAV-first-shape.stl` was **left byte-for-byte untouched**. The three consumers above
fit and rotate it by hand-tuned constants and the new artifact is at a different scale
(0..1 rather than 0..40); swapping it is the render track's decision, not this
revision's. What this revision did instead:

1. **made the artifact regenerable** — `ruler.say_to_file`, reachable as

       cd D:\CLAUDE\eran-brain\holobrain\kav
       python ruler.py --say cube --out KAV-first-shape-20260906.stl

   which runs the real chain (fit the grove on the corpus minus HELD, seed a quarter
   of the shape, let the learner join the rest) and writes the STL **plus a sidecar
   JSON** naming the chain, the gates, the corpus fingerprint and the hour.
   `--whole` runs gate 3's chain instead: KAV says the vertices too.
2. **wrote the honest one** beside it as `KAV-first-shape-20260906.stl` +
   `KAV-first-shape-20260906.json`: 12 faces, watertight, volume x1.000 of the truth,
   `right_solid: true`.
3. **wrote this note**, so nobody reads the 2026-09-02 file as current again.

## For whoever owns TZELEM

Point `night.py`, `hero8k.py` and `truthviews.py` at `KAV-first-shape-20260906.stl` and
re-tune their scale constants (40 -> 1), or keep the old one knowingly. Either is fine.
Rendering a non-watertight soup while calling it the modeller's cube is not.
