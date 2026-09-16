> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

# SHARPEN-OURS — 2026-09-06

Iddo, 01:07: *"תתקן את המודלים שלנו שלא יהיו BLURRED."*

**The ruler** — `sharpness.py`. Laplacian variance, greyscale, long edge **capped**
at 2400 px (downscale only; an image already smaller is measured native). Calibrated
against the two readings the rejection was set on: `tzelem_boulevard.jpg` 719.5
(claude-cli-SHARP: 719), `oneroom-workshop-lit.jpg` 125.7 (SHARP: 126).

## The one-line answer

The blur was **the compositor, not the brush**. `canvas.render(soft=False)` — the
hard ownership path that has been in the file since it was written and that nobody
had ever measured — takes the workshop from **10.1 → 42.0 (dark)** and
**124 → 465 (lit)**, at **100.0% coverage** both ways, and it is **3x faster**.

## Why

`render` pass 2 makes every pixel the alpha-weighted **mean** of every stroke
covering it. Averaging *k* samples of a surface divides its variance by about *k*.
The measurement that proves it: at a **fixed** brush, **adding** strokes makes the
picture **blurrier** — 40k 79.2, 85k 51.1, 170k 17.6, 340k 9.1. It was drowning in
coats of paint. On the hard path the order reverses: 340k 34.3, 1.2M 42.0.

## What was NOT true

* **Shrinking the brush** looked like a 25x win (radius 0.021→0.007 = 9.1→231.7).
  Coverage went 100%→73%. Opened the images: **holes showing the background**.
  Close them by adding strokes and the softness comes back (r=0.007, 1.88M
  strokes = 10.6 at 99.9%).
* **Contact shadow + ambient occlusion bought nothing on the ruler** — 10.1→9.1
  soft, 43.4→41.8 hard. Built anyway (`tzelem/occlusion.py`) because the picture
  is visibly much better; lapvar does not reward large smooth regions.
* **Rendering bigger makes it worse**: 1280 11.5, 1600 9.1, 1920 7.4, 2560 4.3,
  4096 3.2. Strokes are constant WORLD size, so 8K is the same painting seen
  closer.

## The ruler's two blind spots, both measured

* **Exposure is worth 5.7x and is not sharpness.** gain 1.0→2.5 takes the dark
  room 9.1→52.2 while the contrast-normalised number stays flat (117.8→110.0).
* **2x supersampling halves the number** (468→206) and the 1:1 crops are
  near-indistinguishable. The ruler is scoring the aliasing staircase.

## The gate — all runs PASS all three conditions

`godot_gate.one_pair` and `verdict` imported verbatim, 1920x1080, 5 rail poses,
30,000 strokes, size 0.006. `SOFT/dark` and `SOFT/lit` reproduce the committed
`oneroom/out/gate.json` to the digit, which is what proves the new `edge`
parameter changed nothing.

| run | pass | steadier than floor | vs a flat colour | lapvar |
|---|---|---|---|---|
| SOFT/dark (the committed baseline) | ✓ | x2.07 | x4.69 | 130.8 |
| HARD/dark (the fix) | ✓ | **x2.24** | x3.58 | 171.1 |
| SOFT/lit | ✓ | x2.31 | x3.13 | 124.5 |
| HARD/lit (the fix) | ✓ | **x2.49** | x2.24 | 183.6 |
| SHARP/dark (shadow + AO + texture in the albedo) | ✓ | **x2.60** | x3.93 | 108.1 |
| SHARP/lit (same) | ✓ | **x2.84** | x2.92 | 114.8 |

**The trade, with both numbers.** The hard compositor **buys coherence**
(x2.07→x2.24 dark, x2.31→x2.49 lit) and **costs fidelity-MSE** (x4.69→x3.58 dark,
x3.13→x2.24 lit; absolute 0.00223→0.00293 and 0.00250→0.00350). That is expected,
not a defect: averaging is literally the MSE-optimal thing to do against a smooth
Lambert truth, so a sharper painting *must* score worse against it. Every
condition still passes, and the coherence claim — the one TZELEM exists to make —
gets stronger, not weaker.

`Stage.shade` never moved: `freeze.py` hashes its source (`2ee51c66396f8300`),
proves `ShadedStage` with every strength at zero equals `Stage` bit for bit
(`max|diff| 0.000e+00`), and git reports `stage.py` identical to HEAD.

## The delivered files, measured (JPEG quality 94, the file as it ships)

| | lapvar |
|---|---|
| published LIT — **the one he rejected** | 125.7 |
| published DARK — the room the player walks into | **10.2** |
| BEFORE lit (my reproduction of the same pipeline) | 133.0 |
| BEFORE dark (same) | 10.7 |
| **AFTER lit** | **377.1** |
| AFTER lit, 2x antialiased | 171.4 |
| AFTER lit, texture 0.6 | **513.2** |
| AFTER dark, ungraded | 45.1 |
| **AFTER dark, graded x2.2** | **217.4** |
| AFTER lit at 4K (measured after the 2400 cap) | 130.4 |

## The curves (workshop, `rail_camera(0.30)`, 1600x900, DARK unless said)

**radius**, 340k strokes, soft — the trap:

| radius m | 0.021 | 0.016 | 0.012 | 0.009 | 0.007 | 0.005 | 0.0035 |
|---|---|---|---|---|---|---|---|
| lapvar | 9.1 | 13.7 | 47.1 | 134.8 | 231.7 | 325.7 | 363.1 |
| **coverage** | 100% | 99.6% | 96.5% | **86.7%** | **72.9%** | **51.2%** | **33.6%** |

**count**, radius 0.021, soft — more paint is more blur:

| strokes | 40k | 85k | 170k | 340k | 647k |
|---|---|---|---|---|---|
| lapvar | 79.2 | 51.1 | 17.6 | 9.1 | 8.4 |
| coverage | 71.4% | 91.0% | 98.9% | 100% | 100% |

**count on the HARD path** — the order reverses, coverage stays 100%:

| strokes | 340k | 680k | 1.2M | 1.88M |
|---|---|---|---|---|
| dark | 34.3 | 37.5 | **42.0** | 41.5 |
| lit | 417.9 | 445.0 | 465.0 | **483.0** |

**resolution**, 340k, radius 0.021 — bigger is softer:

| px | 1280 | 1600 | 1920 | 2560 | 3200 | 4096 |
|---|---|---|---|---|---|---|
| lapvar | 11.5 | 9.1 | 7.4 | 4.3 | 3.6 | 3.2 |

**texture strength**, hard path, 1.2M: dark 40.9 / 41.6 / 44.3 / 49.0 / **55.6**,
lit 326.1 / 337.9 / 371.7 / 427.4 / **504.2** at 0.0 / 0.15 / 0.30 / 0.45 / 0.60.
All at 100% coverage.

**exposure**, dark, hard, 1.2M: gain 1.0 → 44.3, 1.6 → 112.4, 2.2 → **211.0**,
3.0 → 377.7, while contrast-normalised stays 557 / 555 / 555 / 549. It is a grade,
not sharpness — and it crosses his 126 between gain 1.6 and 2.2.

**4K and the real ceiling.** At 3840x2160, hard path, 1.88M strokes, the number
sits at 117-131 *whatever the brush* — 0.021 130.8, 0.012 124.1, 0.009 119.0,
0.0075 117.7, all at ~100% coverage — while the identical strokes at 1600x900 read
378.1. So a finer brush does not rescue 4K. The ceiling is the number of DISTINCT
STROKE COLOURS against the measured pixel count: 1.88M anchors over 1.44M native
pixels at 1600x900 is more than one colour per pixel, and over 3.24M measured
pixels at 4K it is 0.6. **To be sharp at 4K the room needs more anchors, not a
smaller brush** — a finer planting voxel, which costs plant time and a bigger
`strokes.bin` for the browser.

**cost**, on eran1, numpy only, no GPU: plant 647k anchors 34 s / 1.88M 36 s;
occlusion (shadow + 12-ray AO) 340k 43 s, 1.2M 159 s, 1.88M ~250 s; render
1600x900 soft 340k 3.0 s, hard 340k 1.2 s, hard 1.2M 3.7 s, hard 1.2M + 2x AA
4.7 s; peak RSS 1.13 GB with two plants resident.

## Files

| what | where |
|---|---|
| the ruler | `sharpness.py` |
| shadow / AO / texture, `Stage.shade` untouched | `../eran-brain/holobrain/tzelem/occlusion.py` |
| proof the ruler did not move | `freeze.py` |
| the sweeps | `sweep.py` `sweep2.py` `sweep3.py` `sweep4.py` + `*.json` |
| before / after renders | `final/` `final2/` |
| the gates | `gate_sharp.py` `gate_hard.py` → `gate-out/` |
| WINSTON, measured | `winston_repaint.py` `winston_fair.py` `wout/` |
| the sheet for Iddo | `TZELEM-sharpen-BEFORE-AFTER.jpg` / `.pdf` |
