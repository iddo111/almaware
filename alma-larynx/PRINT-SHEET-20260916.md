> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

# PRINT SHEET — throat cast day, 2026-09-16 (read-only prep, nothing printed/poured/heated by me)


> **⚠️ CORRECTION 2026-09-16 12:50 (claude-cli, Opus) — the first draft of this sheet had the SCALE BACKWARDS.**
> Iddo's spec, 2026-09-01 21:16 (memory `project_eran_mouth_must_be_adult`): *"הפה המדבר הפיזי — זה חייב להיות של אדם בוגר"* — the physical tract is an **ADULT's** (~17-18 cm). The child-scale ERAN-TUBES (119.8 mm) were generated at 13:27 that same day, **before** that spec, so they are the superseded ones and the adult `FULL-THROAT` mould is the correct one. Rows 1, 3, the net line and step 2 below are rewritten accordingly.
> **Fold mould FIXED 12:48:** the 08-24 file was 1,713 bodies (1,704 flat two-triangle marching-cubes slivers). Added `weld()` to `make_silicone_fold_mold.py`, regenerated; independently verified with trimesh: **1 body, watertight, euler 2, 4,364 mm³** (same geometry as before, slivers gone). Broken original kept as `JUNK-silicone-fold-mold-1713-pieces-DO-NOT-PRINT-20260824.stl`.

## 1. Printer — NOT REACHABLE right now
K2 Plus, `fleet_inventory.json` authoritative record: LAN **<lan-ip>**, fluidd `:4408`, moonraker likely `:7125`.
`curl -m5 http://<lan-ip>:4408/printer/info` → **connection timeout**. Same for `:7125`. `fleet_inventory.py --refresh` (12:37) also reports `printer.reachable: false`.
Matches RAMCHAT 12:37 claude-cli note: "K2 Plus at .220 did not answer 12:30." **State/temps/nozzle/chamber: unknown — cannot query, it is off the network or off.** Last *known* state was 09-01 13:2x: idle, last job `captain_Base01.stl_PLA_9h52m37s.gcode` complete — 15 days stale, not trustworthy. Fix the network/power first (step 1 below) before anything else.

## 2. Current print set, honestly ranked (STL watertightness checked live with `trimesh 4.12.2`)

| # | part · path | purpose | material | verdict |
|---|---|---|---|---|
| 1 | `ERAN-TUBES-20260901/TUBE-UNIFORM-calibration.stl` (+ `TUBE-NEUTRAL`, `TUBE-A`) | acoustic calibration only | PLA | **OPTIONAL.** Watertight, never printed. **CHILD scale (119.8 mm) — superseded by Iddo's adult spec**; `TUBE-UNIFORM` is still a cheap check of the resonance model against a real object, but it is not ERAN's throat. Don't print `TUBE-NEUTRAL`/`TUBE-A` as the voice. |
| 2 | `silicone-fold-mold.stl` (the vocal-fold cast mould, M5 profile) | cavity to pour the fold into | PLA | **READY (fixed 12:48).** 1 body, watertight, euler 2, 26×18×12.5 mm, 4,364 mm³, ~1,490 mm³ void. Print 2 (a pair). 0.12-0.16 mm layers for a smooth cavity, 100% infill. |
| 3 | `FULL-THROAT/TRACT-MOULD-core.stl` + `shellA.stl` + `shellB.stl` | the vocal-tract mould | PLA | **READY — matches Iddo's ADULT spec.** `make_scaffold.py`: `LEN=180`, `BORE=36`, `WALL=4` (WALL is still open question Q1). Verified 12:49: all 3 watertight, 1 body each; core 34×36×212 mm, shells 80×27×212 mm — fits the K2 Plus. Print upright or on the flat face; ~112 cm³ each shell. |
| — | `RETIRED-THROAT-MOLD-B-20260829.stl` | old fold mold B | — | **DO NOT PRINT.** Retired by filename and SCAR-20260829: spec (`DESIGN-SWEEP-winners.json`) is unreproducible from any code on disk. |
| — | `JUNK-solid-block-DO-NOT-PRINT-20260824.stl` | — | — | **DO NOT PRINT.** Explicitly junk (96.5% solid block, no cavity) — this is the exact 08-24 scar object. |
| — | `latex-fold-mold.stl` | superseded water/latex approach | — | **DO NOT PRINT.** Superseded on purpose by `silicone-fold-mold.stl` per that script's own docstring ("not the water-tube hack"). Also fails watertight check. |
| — | `buzz-collar.stl`, `plenum-cap.stl`, `bleed-tee.stl`, `mouth-ah.stl`, `mouth-ooh.stl` | downstream assembly (collar/plenum/bleed/mouth) | PLA | **UNVERIFIED today** — all fail the live watertight check (not re-checked since original build). Not needed until a fold actually casts and flutters; hold off, repair before printing. |

Net for today (corrected): **print-ready = fold mould ×2 + adult tract mould (core + 2 shells).** Downstream collar/plenum/mouth parts still fail watertight and wait until a fold flutters.

## 3. Slicer
- **OrcaSlicer** — installed, `C:\Program Files\OrcaSlicer\orca-slicer.exe` present. CLI test (`--help`) returned exit 0 with no captured output — inconclusive from here (may need a 3mf project + `--slice`/`--export-gcode` flags per its documented headless mode; not confirmed working in this session).
- **Creality Print 7.2** — installed, `C:\Program Files\Creality\Creality Print 7.2`. Consumer build; CLI slicing not confirmed/typically unsupported.
- **PrusaSlicer** — not found in Program Files or PATH.

## 4. Silicone recipe (sourced — Smooth-On TDS pages fetched live today)
**Identify what's in the tub first:** A:B mixed **1:1 by weight/volume = platinum-cure** (addition cure — what everything below assumes). A:B mixed **100:5 or 100:10 with a small separate catalyst = tin-cure** (condensation cure — Slacker and most inhibitor rules below do NOT apply the same way). Check the label before mixing anything.
- **Silicone Thinner** ([TDS](https://www.smooth-on.com/products/silicone-thinner/)): premix into **Part A** before adding Part B; **do not exceed 10% by weight of total A+B**. Lowers cured hardness, tear and tensile strength **proportionally** to amount added; **lengthens pot life and cure time proportionally**; improves flow/de-air.
- **Slacker** ([TDS](https://www.smooth-on.com/products/slacker/)): **platinum-cure only** — compatible with Dragon Skin 10/10NV/FX-Pro, Ecoflex 00-50/00-30/00-20; **NOT compatible** with Ecoflex 00-10/GEL. Mix **1A : 1B : 1–3 parts Slacker by weight** (progressive softening — e.g. FX-Pro 100g B + 50g Slacker → Shore 00-20; +200g → Shore 000-3); surface goes tacky above ~1:1:1. Needs >65°F/18°C to cure; heat accelerates cure.
- **Cure inhibition risk (mold material):** platinum silicone is poisoned by sulfur-based clays, polyesters, some woods, epoxies, urethane rubber, tin-cure silicone (Slacker TDS). PA12-CF is on **no published inhibitor list either way** but its amine end-groups are a known platinum-poison family (SCAR-20260829) — **unproven, test before trusting.**
- **Mandatory test-pour-on-scrap step** (per SCAR-20260829, never skipped): mix a small dab of the actual platinum silicone, place it on a printed **offcut** of the exact PLA/PA12-CF spool, next to a control dab on glass/metal. If the mold-material dab stays tacky/uncured after the labeled cure time while the control cures, that surface **is** inhibiting — do not pour the real mold until fixed (release coat, different material, or barrier film).
- **Mold release:** use a platinum-safe release (Smooth-On Universal or similar); avoid petroleum-jelly/sulfur-clay releases — they're on the inhibitor list above.
- **Degassing without a vacuum chamber:** mix slowly to minimize entrained air, let the mixed batch dwell 1-2 min to let large bubbles rise, then pour in a **thin, steady stream from height** into the lowest point of the cavity so air is pushed ahead of the silicone, not trapped.
- **⚠️ Shore 10A alone is likely too stiff for phonating folds.** `make_silicone_fold_mold.py`'s own docstring: neat Shore-10A is **~150 kPa**, "far too stiff — it squeals." Published self-oscillation onset for a single-layer M5 fold is **~1.15–1.2 kPa** (~120 Hz); the one published design inside ERAN's target band is a fibre-tensioned M5 at **226.6 Hz / 1594 Pa**; SCAR-20260829 estimated **13–18 kPa** for the old child/quarter scale (superseded — the M5 fold is adult-size). That's 8-100× softer than neat Shore-10A. **Softening path:** thin toward the low end with Silicone Thinner (≤10% by weight) and/or Slacker (1:1:1-3, platinum only); the script's own honest first-cast target is a **single layer thinned to ~10-15 kPa** — verify with a durometer or thumb-press comparison against a known-shore reference, not by feel, before casting the pair.

## 5. PA12-CF notes (sourced)
- **Dry before printing:** 80°C for 8–12h in a dry box with desiccant; confirm the dryer actually holds 80°C.
- **Nozzle:** 260–290°C, **hardened nozzle required** (CF is abrasive) — Iddo has one on hand per his message; not verified installed since printer is offline.
- **Bed:** 80–100°C. No specific PA12-CF part is currently designed in this project (all current molds are PLA); PA12-CF would only be justified if Iddo wants to heat-cure the silicone above PLA's ~55-60°C heat-deflection range, or wants a more durable rigid mold body.

## 6. First three things Iddo does with his hands today
1. **Get the K2 Plus back on the network.** It did not answer at 12:30 or just now on either :4408 or :7125 — check power and the ethernet/wifi link at the printer itself; nothing here can print until it responds to a read-only `printer/info` query.
2. **Print the fold mould ×2 first (small, fast, PLA)**, then the adult tract mould (core + shellA + shellB).
3. **Confirm the Shore-10 tub's A:B ratio on the label** (1:1 → platinum, matches Slacker's compatibility list) and run the test-pour-on-scrap step (§4) on both a PLA offcut and a PA12-CF offcut side by side — before any real fold-mold pour, so the mold material choice is measured, not assumed.
