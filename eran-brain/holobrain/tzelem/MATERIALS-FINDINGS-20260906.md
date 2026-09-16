> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

# TZELEM STAGE 3 — MATERIALS / שלב 3: חומרים

Iddo, 2026-09-06 03:12: *"תבנה את שלב 3 - חומרים"*.

## The answer, first — two answers, and they point different ways

**On SHARPNESS: at TRUE real-world scale, materials made from Iddo's own footage
are a TIE with
the value-noise texture that was already in the engine.** Lit Laplacian variance:
flat colour **326.1**, the engine's procedural noise **371.7**, his photographs at
measured millimetre scale **370.1**. That is a dead heat, not a win.

They only pull ahead when the pattern is placed at **seven times life size**:
**403.6**, which is +8.6% over the noise and +23.8% over flat colour. Seven times
life size is a decision about art, not a fact about the world, and it is written
down as such in `ab.SCALE_ROOM`.

**On COHERENCE — the claim TZELEM exists to make — they win properly.** Steadier
than a repainted frame goes from **x2.49 to x3.51** (lit) and **x2.24 to x3.04**
(dark), with all three gate conditions still passing. World-anchored strokes hold
detail still; a repainted frame flickers on it. That is the bigger result, and it
is the one that matters for a game.

**Why the sharpness answer is only a tie.** A brushstroke in this room is
**42 mm** across. His desk photographs have
a **0.168 mm** texel. Filtered honestly, a 85.8 mm material behind a 42 mm brush
is a **4x4 map** (`material.lod_for`). There is nothing wrong with the photograph;
it is simply finer than the painter can hold.

## The thing that nearly got reported as a triumph

The first A/B said lit **326 → 1524, a 4.6x win**. I opened the picture. It was a
mosaic of randomly coloured dabs — not wood, not a wall, **noise**. Every stroke
was point-sampling ONE texel out of a patch 250 texels wide, so neighbouring
strokes landed on unrelated grain, and **Laplacian variance applauds aliasing
because aliasing is all high frequency.**

`tzelem-sharpen/README-FINDINGS.md` had already written the rule for the
procedural texture — *"a texture finer than the brush is a texture the painter
cannot carry"* — and it binds a photograph exactly as hard. The fix is ordinary
mip filtering (`material.lod_for` + `material.mips`), and it is what turned a
4.6x fantasy into a 1.09x fact.

**Anyone adding texture to TZELEM from any source must mip it, or their sharpness
number is a lie.** That includes the 8K proof room being built from this same
footage.

## The measurement

1.2M anchors, voxel 0.0090, radius 0.021, seed 17, world tangents,
`canvas.render(soft=False)` — the hard, sharp path — 1600x900,
`room.rail_camera(0.30)`. The anchors and the shadow/AO pass are computed ONCE and
shared by every arm, so **not one stroke moves between them**. Ruler:
`sharpness.lapvar_array`, greyscale, long edge capped at 2400 px, never upscaled.

| arm | LIT | vs flat | DARK | vs flat | lapvar_norm LIT |
|---|---|---|---|---|---|
| A  flat authored colour | 326.1 | — | 40.9 | — | 510.7 |
| B  procedural noise (what the engine had) | 371.7 | +14.0% | 44.3 | +8.3% | 577.3 |
| C  his photographs, TRUE scale | 370.1 | +13.5% | 43.1 | +5.4% | 566.2 |
| D  C with the normal map and specular OFF | 368.5 | +13.0% | 42.1 | +2.9% | 569.5 |
| F  7x life size, half strength | 360.1 | +10.4% | 44.0 | +7.6% | 551.3 |
| **E  7x life size, full strength** | **403.6** | **+23.8%** | **47.3** | **+15.6%** | **610.3** |

**Arms A and B reproduce `tzelem-sharpen`'s own numbers to the digit** (its texture
sweep reads 326.1 at strength 0 and 371.7 at 0.30). That is what proves the arms
are the same pipeline and that only the material changed.

**Mean brightness moves by less than 2% across every arm** (0.2270 → 0.2234 lit),
because every albedo map is normalised PER CHANNEL to a mean of exactly 1.0 and
multiplied into the room's own authored colour. The ruler is therefore not being
paid in exposure — the trap `tzelem-sharpen` measured at 5.7x. `lapvar_norm`,
which standardises contrast away entirely, tells the same story: 510.7 → 577.3 →
566.2 → 610.3.

**The normal map and the specular lobe are worth almost nothing here** (C 370.1 vs
D 368.5). At a 4x4 effective map there is no slope left to shade. Expect that to
change at a finer brush, and do not claim it before measuring it.

### What it looks like, not what it scores

I opened every render at 1:1. At arm E the walls stop being smooth cardboard and
pick up grime and staining; the pegboard gets grain; the floor gets dirt. It reads
as a **used** room. It is also, unambiguously, **dirtier** — the plaster is wearing
the stains off Iddo's vinyl floor tile — and half strength (arm F) scores WORSE
than the plain noise while looking calmer. Which of E and F is right is a call for
his eye, not for the ruler.

### Cost

| | |
|---|---|
| plant 1.2M anchors | 35.4 s |
| shadow + AO (shared by all arms) | 145.0 s |
| **material sample, 1.2M anchors, all six maps** | **1.4-1.6 s** |
| procedural texture, same anchors | 0.7 s |
| flat colour, same anchors | 0.3 s |
| render, hard path, 1600x900 | 3.6 s |
| peak RSS, whole run | **1.10 GB** |
| the six materials on disk | **11 MB** |

Materials cost about **0.8 s per 1.2M anchors** more than the noise it replaces,
paid ONCE at planting, and nothing at all per frame. On an axis-aligned box the
triplanar blend puts weight 1.0 on one plane, so it is one sample, not three
(`test_material.py` check 3 proves it).

## The gate — and this is the bigger result

`gate_mat.py` runs **`gate_hard.py` itself**, unmodified, with exactly one
substitution: `room.plain_stage` returns the same boxes wearing materials. Same
`one_pair`, same `verdict`, same `ruler._mse` / `ruler._resid`, same 1920x1080,
same 5 rail poses, same 30,000 strokes, same seeds.

| arm | state | steadier than floor | vs flat colour | verdict |
|---|---|---|---|---|
| OFF (the committed baseline) | lit | x2.49 | x2.24 | PASS |
| OFF (the committed baseline) | dark | x2.24 | x3.58 | PASS |
| ON true scale | lit | **x3.37** | x1.58 | PASS |
| ON true scale | dark | **x3.01** | x2.80 | PASS |
| ON 7x room scale | lit | **x3.51** | x1.44 | PASS |
| ON 7x room scale | dark | **x3.04** | x2.42 | PASS |

**All six PASS all three conditions**, and the OFF arm reproduces
`tzelem-sharpen`'s HARD numbers exactly (x2.49 lit, x2.24 dark) — which is what
proves only the material changed.

**Materials make TZELEM's own claim 41% stronger: x2.49 → x3.51.** That is a
bigger win than anything on the sharpness ruler, and it is the claim the organ
exists to make. The mechanism is worth stating: a repainted-every-frame render
(the FLOOR) gets much *worse* with texture — 0.00976 → 0.03079 — because
re-scattering strokes over a detailed surface flickers, while **world-anchored
strokes hold the detail still**. TZELEM's own residual rises too (0.00392 →
0.00878), but far less, and the ratio is the point.

The cost is on the other side of the same coin: fidelity-MSE against the truth
falls, x2.24 → x1.44 lit. That is the same trade `tzelem-sharpen` documented for
the hard compositor and for the same reason — 30,000 strokes cannot match a
textured truth as closely as a smooth one. Every condition still passes.

Full log and JSON: `gate-out/gate-materials.json`, `gate-out/gate-mat.log`.

Structurally, a material **cannot move an edge**, and that is tested rather than
asserted: `canvas.ownership` reads no colour at all, so changing every colour in
the scene leaves ownership bit-identical — `test_material.py` check 7, 0 pixels
different out of 76,800. This is `palette.py`'s law extended to stage 3, and it is
why `soft=False` is not regressed.

## What is measured, what is derived, what is authored

| | |
|---|---|
| **MEASURED** | the albedo (his photograph, flat-fielded) and the desk-plane scale: **5.964 px/mm**, read off the steel rule's own graduations by autocorrelation, six windows agreeing to 0.3%, cross-checked against the printed digits at 5.83 (**±2.2%**) |
| **DERIVED** | height (high-passed luminance), normal (from height, at real mm/texel), roughness variation (local micro-contrast), AO (cavity from height) — a phone has no depth channel and these are estimates |
| **AUTHORED** | the roughness LEVEL per material, metallic, `relief_mm`, the surface assignment, and the 7x placement size in arm E |
| **DOWNLOADED** | **nothing.** There is no Poly Haven, no ambientCG, no third-party asset anywhere in this set. `mats/MANIFEST.json` lists `third_party_assets: []` |

### Where the scale is NOT measured, said plainly

Only the desk plane of `f0008` has a rule lying in it at the surface's own depth.
`floor_vinyl`'s size is an **assumption** (a nominal 300 mm floor tile): the wooden
rule in `f0071` is motion-blurred and runs out of frame, and the autocorrelation
locked onto a periodicity 40% away from its visible length, so that measurement
was **refused** rather than fudged. `paper_stack`, `wood_carved_dark` and
`plastic_black` sit at other depths in the same frames and their scale is
**estimated**. Every file says which it is, in its own `.json`.

### And the awkward part

**Iddo filmed his desk, not a workshop.** There is no plaster wall, no concrete
floor and no painted steel cabinet in the footage. So the workshop's walls and
ceiling are wearing his **vinyl floor tile**, and its cabinets are wearing the
**brushed steel of his rule**. The room's authored colour is kept as the tint, so
a red toolbox is still red — it just stops being a flat red. Every assignment is a
judgement and they are all listed in `ab.ASSIGN`.

## The organ

`material.py` — installed at `D:\CLAUDE\eran-brain\holobrain\tzelem\material.py`,
with `mats/` beside it. **No existing TZELEM file was edited.**

* **`.tzm`** — the on-disk format, written in `gbuffer.py`'s idiom: magic
  `TZMAT01\0`, uint32 size, uint32 flags, float32 mm_per_texel, then albedo /
  normal / roughness / metallic / AO / height as raw uint8. No PNG, no EXR, no
  OpenCV. Round-trip proved byte-identical for all six materials.
* **triplanar** — chosen because neither the 105 boxes nor the photogrammetric
  meshes in `room3d/objects/` have UVs, and because the lookup coordinate IS the
  world position, so a 0.1677 mm texel lands at 0.1677 mm on every surface with no
  per-object tuning. `world_scale_mm` is 1000 for the workshop (authored in
  metres) and 403.0376 for the photogrammetric room (`room3d/scale.json`).
* **`MaterialStage`** — the engine's door: materials are baked into the
  **G-buffer**, never into `Stage.shade`, exactly as `occlusion.ShadedStage` does,
  because `shade` is the fidelity ruler and every gate number ever reported is an
  MSE against it.
* **`test_material.py` — 20 checks, all passing**: six round-trips byte-identical,
  five maps wrap, three axes each use one plane, repeat-at-physical-size (and a
  non-period offset really does change it), no camera anywhere in the sampler,
  the normal map really bends the normal (mean 3.8 deg, max 30), a material
  cannot move an edge, and BOTH worlds — the workshop at 1000 mm/unit and the
  photogrammetric room at 403.0376 mm/unit — land the same material at the same
  physical size.

## Files

| what | where |
|---|---|
| the organ | `material.py` (also installed into `tzelem/`) |
| the format + 6 materials | `mats/*.tzm` + `mats/MANIFEST.json` |
| the rule calibration | `calibrate.py` → `calibration.json` |
| the harvester | `harvest.py` |
| the tests | `test_material.py` |
| the A/B | `ab.py` → `ab-out/ab.json` + 12 renders |
| the coherence gate | `gate_mat.py` → `gate-out/gate-materials.json` |
| the sheet for Iddo | `sheet.py` → JPEG + PDF on the Desktop |

Run directory on eran1: `~/materials-run/lab/` — a copy, `nice -n 10`. Nothing in
`~/sharpen-run`, `~/eran-brain`, or any service was touched.
