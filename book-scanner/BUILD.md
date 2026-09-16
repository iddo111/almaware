> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY.

# ALMA BOOK SCANNER v1 — Build Guide

**לזכרה של עלמה ז״ל.**

Model: `D:\CLAUDE\book-scanner\alma_book_scanner.scad` (863 lines, fully parametric)
STLs: `D:\CLAUDE\book-scanner\stl\` (12 files, all verified watertight)

---

## 1. WHAT IT IS

This is a **manual V-cradle book scanner**. The book lies open in a 100° V made of two plywood
wings. A hinged V of two 4 mm glass panes drops onto the open spread and flattens it. Two cameras,
one per side, shoot both pages simultaneously through the glass. You press a USB foot pedal to fire
both shutters, lift the glass with one hand, turn the page with the other, drop the glass, press
again. That is the whole machine.

**What it will do:** capture books up to 240 × 320 mm pages and 80 mm total thickness, with the
spine supported and the gutter flattened, at consistent focus and exposure, without cracking spines
the way a flatbed does. The V-cradle is the reason: the book never has to open past 100°.

**What it will not do:** turn pages. You turn every page by hand, forever. There is no motor, no
vacuum, no electronics beyond the foot pedal. It will not scan a book you are unwilling to sit with
for an hour. It will not fix bad lighting — that is on you (§6).

**Realistic throughput:** the mechanical rhythm is **3–5 seconds per spread** once you have it in
your hands. Sustained over a real session, with fatigue, misfeeds and the occasional re-shoot,
expect **700–1000 pages/hour** (350–500 spreads). A 300-page book is roughly 20–25 minutes of
capture. Post-processing is separate and runs unattended.

**Honest limits:** the platen is not counterweighted to balance — it is trimmed (§ part 3). Two
4 mm panes are 884 g each; that weight is *what flattens the page*, and you do not want to cancel
it. The counterweight pocket and a light spring only kill the slam. And the camera mount is a
single-shear ear rated for a phone or a compact under 500 g. **Do not hang a DSLR on it.**

---

## 2. BILL OF MATERIALS

Prices are **ILS, mid-2026, including typical shipping**. Two columns because Iddo buys both ways:
local shops for anything he needs today, AliExpress for anything he can wait 2–4 weeks for.
Where a local price is much worse, the AliExpress route is marked **[ALI]** as the sane choice.

### Structure

| # | Part | Qty | Spec | Where | ILS |
|---|------|-----|------|-------|-----|
| 1 | 2020 aluminium extrusion | 4 × 1000 mm | standard 20×20, 6 mm slot | **[ALI]** or Israeli 3D-print supply (search *פרופיל אלומיניום 2020*) | 160 |
| 2 | M5 T-nuts, drop-in or hammer type | pack of 50 (need 6) | for 2020 6 mm slot | **[ALI]** | 30 |
| 3 | Baseboard | 1 | 560 × 420 × 18 mm MDF or ply | lumber yard / Home Center, cut to size in store | 45 |
| 4 | 6 mm plywood, wing panels | 2 × 260 × 300 mm | 6 mm birch ply (foam board works, but sags over 260 mm — ply is better) | lumber yard; buy one 600 × 600 sheet | 50 |

**Extrusion cut list — 3100 mm total, from 4 × 1000 mm bars:**

| Piece | Length | Qty |
|---|---|---|
| Base rail (carriages slide on this) | 500 mm | 1 |
| Rear posts (carry the hinge rod) | 300 mm | 2 |
| Camera posts (vertical) | 600 mm | 2 |
| Light side rails (horizontal) | 400 mm | 2 |

Cut as: `1000 → 500 + 400` · `1000 → 600 + 400` · `1000 → 600 + 300` · `1000 → 300 (+700 spare)`.
Most Israeli suppliers will cut to length for a few shekels — ask. A mitre saw with a carbide blade
cuts 2020 cleanly; deburr the ends with a file or the carriage will not start onto the rail.

### Fasteners — every screw in this machine is M3 or M5, nothing else

| # | Part | Qty | Spec | Where | ILS |
|---|------|-----|------|-------|-----|
| 5 | M3 heat-set inserts | 28 (buy 100) | M3 × 5 mm long × **4.6 mm OD** — the OD matters, it must match `m3_insert` | **[ALI]** | 35 |
| 6 | M3 socket screws | 28 | 8 × M3×20, 8 × M3×16, 12 × M3×12 | local ברגים shop or **[ALI]** assortment box | 45 |
| 7 | M5 bolts | 8 | 4 × M5×16, 4 × M5×30 | local ברגים shop | 20 |
| 8 | M5 nuts | 4 | standard, 8.0 mm across flats (captive in the printed knobs) | local | 5 |
| 9 | 1/4"-20 nuts | 2 | standard camera thread; **[ALI]** or any photo shop | local/ALI | 15 |
| 10 | Soldering iron + heat-set insert tip | 1 | *skip if you already own one* | **[ALI]** | 60 |

**Where the 28 inserts go:** 16 in the wing brackets (2 panel + 2 foot × 4), 8 in the hinge arms
(4 each), 4 in the light brackets (2 each). **None in the carriage** — its four deck holes are
clearance; those screws go *up from underneath* into the bracket feet.

**Where the 6 T-nuts go:** 2 carriage locks, 2 camera collars, 2 light brackets.

### Optics and glass

| # | Part | Qty | Spec | Where | ILS |
|---|------|-----|------|-------|-----|
| 11 | **Float glass panes** | 2 | **260 × 340 × 4 mm, edges SEAMED** | local glazier (זגגייה) | 180 |
| 12 | Silicone strip, 1 mm | ~1.5 m | 1 mm silicone strip, **or** split 4 mm silicone fuel hose lengthwise | hardware / aquarium / hobby shop | 20 |
| 13 | 8 mm smooth rod | **500 mm** | 8 mm ground steel shaft (linear-rail shaft is ideal) | **[ALI]** or hardware store | 30 |
| 14 | 8 mm shaft collars | 4 | set-screw type | **[ALI]** | 25 |

> ⚠️ **TELL THE GLAZIER: "seamed edges" — קנטים מלוטשים.** Raw cut float glass will open your hands
> and it will chip in the clamps. Ask explicitly for the edges to be ground/seamed on all four sides
> of both panes. It costs a few shekels more and every glazier does it. **Do not skip this.**
> There is usually a minimum charge, so 2 small panes may cost the same as 4 — consider ordering a
> spare pair.

> 📏 **Correction to the CAD header:** the model's parts list says a 480 mm rod. The real
> boss-to-boss span is **476.6 mm**, which leaves nothing for the shaft collars. **Buy 500 mm.**

**Lighter alternative:** two 3 mm acrylic panes are 313 g each instead of 884 g. Much gentler lid,
much less flattening force, and acrylic scratches — use it only if the glass feels too heavy or you
are scanning fragile paper.

### Lighting

| # | Part | Qty | Spec | Where | ILS |
|---|------|-----|------|-------|-----|
| 15 | LED strip, **high CRI** | 2 × 400 mm | 12 V, **CRI ≥ 95**, 4000 K neutral. COB strip is best — no LED dots | **[ALI]** — see warning | 90 |
| 16 | 12 V PSU | 1 | 12 V, 2–3 A, barrel jack | local electronics or **[ALI]** | 45 |
| 17 | Aluminium LED channel, 12 mm | 2 × 500 mm | with diffuser cover; bolts to the 45° pad | **[ALI]** | 50 |
| 18 | **Linear polarising film** | 1 sheet | ~200 × 200 mm, cut two 25 mm strips from it | **[ALI]** — see warning | 60 |
| 19 | CPL filter or 2nd polariser | 1–2 | circular polariser for the lens, or clip-on CPL for a phone | photo shop or **[ALI]** | 70 |

> 🔴 **Two things that are genuinely hard to source in Israel:**
>
> **High-CRI LED strip.** Almost every strip on a local shelf is CRI 70–80. That is fine for a
> corridor and bad for a scan — colours go muddy and greys go green. CRI ≥ 95 is basically an
> AliExpress order. Search *"CRI 95 COB LED strip 12V 4000K"*. Budget 2–4 weeks.
>
> **Linear polarising film.** Not stocked locally in any useful size. AliExpress or eBay, search
> *"linear polarizer film sheet"*. Make sure it says **linear**, not "3D glasses film" (circular).
> The lights need *linear*; the lens can be either linear or a normal CPL, because a CPL's front
> element is a linear polariser. Cross-polarisation is **optional but it is the single biggest
> quality lever in this build** (§6) — order the film with the extrusion so it arrives in time.

### Control and consumables

| # | Part | Qty | Spec | Where | ILS |
|---|------|-----|------|-------|-----|
| 20 | USB foot pedal | 1 | single or triple pedal, programmable HID | **[ALI]** (~85) or local (~150) | 85 |
| 21 | PLA filament | 2 kg | any decent PLA; PETG also fine (see §3) | local 3D shop or **[ALI]** | 200 |
| 22 | Felt strip, self-adhesive | 1 | for the spine support top face | hardware / haberdashery | 10 |
| 23 | Misc | — | threadlock, 400-grit paper, zip ties, cable clips | hardware | 30 |

### Total

| | ILS |
|---|---|
| Structure (1–4) | 285 |
| Fasteners (5–10) | 180 |
| Optics and glass (11–14) | 255 |
| Lighting (15–19) | 315 |
| Control and consumables (20–23) | 325 |
| **TOTAL** | **~1,360 ILS** |

**Realistic range: 1,150 – 1,600 ILS.** Lower if you already own a soldering iron and filament
(−260), if a glazier gives you offcuts, or if you skip cross-polarisation for now (−130). Higher if
you buy everything locally instead of waiting for AliExpress (extrusion and LED strip roughly
double).

**Not included: the cameras.** Use two phones (the phone-jaw part 5b exists for exactly this) or two
old compacts. If you buy, two used Canon compacts with CHDK support are the classic cheap answer —
but the machine is designed so that two phones you already own will work on day one.

---

## 3. PRINT SETTINGS

**Material: PLA.** 1.24 g/cm³. PETG is also fine and slightly tougher, but PLA is stiffer, which is
what a cradle wants. **Do not use PLA if the machine will sit in a hot car or in direct sun** — it
creeps at 55 °C. For a room, PLA is correct.

| Setting | Value |
|---|---|
| Layer height | 0.2 mm |
| Perimeters | **4** (this is what `wall = 3.2` at a 0.4 nozzle means) |
| Infill | **30 % gyroid** |
| Top/bottom layers | 5 / 4 |
| Nozzle / bed | 210 °C / 60 °C (adjust to your filament) |
| Support | **NONE. Not one part needs it.** |
| Brim | only on `glass_edge_clamp` and `camera_mount` — tall parts with small footprints |
| Seam | rear/aligned |

### Totals — measured off the exported STLs, not estimated

| | |
|---|---|
| Solid geometry, all 23 STL instances (25 physical pieces) | **1954.7 cm³** |
| Printed at 4 perimeters / 30 % infill (≈ 0.60 of solid) | **1172.8 cm³ = 1454 g PLA** |
| **Buy 2 spools.** 1.5 spools is the real number; you will waste some. |
| Print time at 0.2 mm on a K2 Plus | **~27 h** (22–33 h depending on flow: 32.6 h @ 10 mm³/s, 21.7 h @ 15 mm³/s) |
| Build plates | roughly 8–10 |

Bounds, honestly: 100 % solid would be 2424 g (never reached); 15 % infill drops it to ~1212 g.
Do not drop below 30 % on the carriage or the hinge arms — those carry the book and the glass.

### Per-part orientation and support

Every part is **modelled in its print orientation with Z = 0 on the bed.** Import and slice — do
not rotate anything.

| Part | Qty | Footprint (mm) | Print g ea | Orientation | Support |
|---|---|---|---|---|---|
| `cradle_wing_bracket` | **4** | 110 × 99.9 × 18 | 59 | On its side — flat 2D profile extruded 18 mm | **No** — every wall vertical; the 4 small bores are horizontal and self-bridge |
| `rail_carriage` | **2** | 110 × 190 × 26.4 | 127 | **UPSIDE DOWN** — deck flat on the bed, legs pointing up | **No** — this orientation leaves not one overhang and not one bridge |
| `platen_hinge_arm` | **1** | 310 × 86 × 26 | 206 | Flat on its side; pivot boss stands proud | **No** — pocket opens up, insert holes are vertical blind holes in the bed face |
| `platen_hinge_arm_mirror` | **1** | 310 × 86 × 26 | 206 | Same — **handed pair, print one of each** | **No** |
| `glass_edge_clamp` | **4** | 26.6 × 44 × 50 | 24 | Standing on its foot face | **No** — channel opens sideways. Use a brim |
| `camera_mount` | **1** | 126.3 × 46 × 110 | 75 | Both pieces flat as modelled: collar bore vertical, platform as an L corner-down | **No** — **2 bodies on one plate by design**, not a bug |
| `camera_mount_mirror` | **1** | 126.3 × 46 × 110 | 75 | Same — **handed pair** | **No** |
| `camera_mount_phone_jaw` | **2** | 78 × 22 × 18 | 17 | Base down, slot opening up | **No** — *optional, phones only* |
| `light_bar_bracket` | **1** | 85.5 × 111.2 × 50 | 100 | As modelled — 2D profile extruded 50 mm up | **No** |
| `light_bar_bracket_mirror` | **1** | 85.5 × 111.2 × 50 | 100 | Same — **handed pair** | **No** |
| `thumbscrew_knob` | **4** | 35.1 × 36 × 13 | 9 | Flat, nut pocket UP | **No** — print 6, you will lose one |
| `spine_support` | **1** | 44 × 90 × 20.8 | 34 | Flat face down, ridge up | **No** — flanks are a 50° overhang, prints clean |

> ⚠️ **THREE PARTS ARE HANDED PAIRS.** `platen_hinge_arm`, `camera_mount`, `light_bar_bracket`.
> Print the module **and** its `_mirror` — not two of the same. If you print two identical hinge
> arms, the insert holes end up on the outboard face of one of them and the glass clamps have
> nothing to bolt to. The mirrored STLs are already in `stl\`.

**Longest part is 310 mm** on a 350 mm bed — 40 mm of margin. Nothing is close to the limit.

### Re-rendering a part

Verified working, exit code 0:

```
cd D:\CLAUDE\book-scanner
"C:\Program Files\OpenSCAD\openscad.exe" -o stl\spine_support.stl -D "part=\"spine_support\"" alma_book_scanner.scad
```

`-D 'part="assembly"'` renders the whole machine as a preview; `-D 'part="all"'` renders every part
laid out on one virtual plate — use that as the eyeball check.

---

## 4. ASSEMBLY

Order matters. This is the order a person actually builds it, not the order the parts are numbered.

### Step 0 — Install the heat-set inserts (do this first, all 28, in one sitting)

Set the iron to ~230 °C with the insert tip. Push the insert in **slowly and straight** — 3–4
seconds — until it sits flush or 0.2 mm below the surface. Let it cool before you touch it.

- 16 into `cradle_wing_bracket`: 2 in each foot, 2 in each inclined panel face.
- 8 into `platen_hinge_arm` (4 per arm) — **in the bed face**, which becomes the *inboard* face.
- 4 into `light_bar_bracket` (2 per bracket) — on the 45° pad.

✅ **Check:** every insert flush and square. A tilted insert cracks the boss when you torque the
screw. If one goes in crooked, heat it, pull it out with the screw, and redo it.

### Step 1 — Baseboard and base rail

Mount the 500 mm 2020 base rail along the centreline of the baseboard, running left–right (X).
Rail top ends up at **Z = 20 mm**. Two M5 through the baseboard from underneath into T-nuts in the
rail's bottom slot, or two corner brackets.

✅ **Check:** rail is straight, level, and both ends are deburred.

### Step 2 — 🔴 CRITICAL: the carriages

**This is failure point #1.** Take your time here.

1. Drop one **M5 T-nut into the rail's side slot** *before* the carriage goes on. You cannot add it
   later — the carriage's printed keys run in both side slots and it will not come off sideways.
2. Slide the carriage on **from the END of the rail**, deck up, legs down. It cannot drop on from
   above; that is deliberate.
3. Repeat for the second carriage, second T-nut.

**How it should feel:** it should slide with light finger pressure and have no detectable rock. The
bearing is 110 mm on a 20 mm rail — a 5.5 : 1 ratio — so it physically cannot cock and jam. Nothing
touches the bottom face of the rail, so a bowed extrusion cannot preload it.

**If it binds:**
- Elephant foot on the first layer is the usual culprit. Take a 400-grit sheet flat on a table and
  sand the *inside* of the leg faces and the underside of the deck a few strokes. Sand, test, sand.
- Check the two lead-in chamfers at the carriage ends are clean.
- Do **not** file the slot keys down until you have ruled out the above — the keys are what stop the
  carriage rolling outward under the overhung weight of a wing.

**If it rocks:** the keys are not engaging. Check that the rail is genuine 20×20 with a 6 mm slot
mouth, not a 6.2 mm variant.

4. Assemble the **thumbscrew knobs**: press an M5 nut into the pocket (8.1 mm across flats against
   an 8.0 mm nut — a light interference fit), a drop of superglue **at the rim, never in the
   threads**, then run an M5×16 up through the 5.3 mm bore.
5. Fit one knob assembly to each carriage, threading into its T-nut.

✅ **Check:** tighten the knob — the carriage should lock solid against the rail. It should *clamp*,
never jack the carriage up. Loosen and it slides freely again. Both carriages, independently.

### Step 3 — Wing brackets onto the carriages

Each carriage takes **two** brackets, front and back, 130 mm apart in Y.

The four deck holes are **clearance, not inserts**. The screws go **UP from underneath the deck**
(open air at y = ±65) through the deck and into the inserts in the bracket feet. **M3 × 20.** The
head seats on the 11 mm boss face on the underside.

✅ **Check:** all four brackets on, feet flat, no rocking. The two brackets on one carriage must be
parallel — sight along them.

### Step 4 — Cut and fit the wing panels

Cut two panels of 6 mm plywood, **260 mm wide × 300 mm long**.

Drill 2 × 3.5 mm clearance holes in each panel at the insert positions: **40 mm and 80 mm up the
slope** from the edge that goes into the slot.

Slide each panel's lower edge into the bracket's **6.5 mm slot, 15 mm deep**, under the lip. Then
screw down through the panel into the two inserts in each bracket — **M3 × 16**, four screws per
panel.

The bracket supports the first 130 mm of the 260 mm slope. The rest cantilevers. **That is
deliberate** — it is what keeps the front of the machine open for your hands.

✅ **Check:** the two panels form a 100° V. Measure it. Each panel should rise at 40° from
horizontal. The virtual apex — where the two panel planes meet — sits at **Z ≈ 37 mm**.
✅ **Check:** put a book in. With the carriages run in to their closest (10 mm apart, centres at
X = ±60), the inboard panel edges are 30 mm apart. Slide the carriages outward for a thicker book.

### Step 5 — Rear posts and the hinge rod

The two 300 mm posts stand at the **back** and carry the 8 mm rod at **Z = 237 mm**.

> 🔴 **Dry-fit before you drill.** The hinge arms occupy X ≈ 212 → 238 mm on each side (the pivot
> boss stands 10 mm proud outboard of the 16 mm arm). So the **posts must go INBOARD of the arms** —
> put them at about **X = ±190 mm**, Y = +145 mm. The 500 mm rod then spans both posts with the arms
> and their collars living on the rod ends outboard. If you put the posts at ±220 they will collide
> with the arms.

Drill 8.5 mm through each post at 237 mm from the base. **Clamp both posts together and drill them
as a pair** so the holes are collinear — if they are not, the platen will bind on the rod.

Mount the posts to the baseboard with corner brackets.

### Step 6 — Hinge arms and the platen

1. Slide onto the rod, in order: shaft collar → **left arm** → post → post → **right arm** → shaft
   collar. Two collars sit outboard of the arms to retain them; use the other two to set the gap
   between post and arm.
2. Bore is 8.70 mm on an 8 mm rod — a running fit. It should swing freely.

✅ **Check:** the platen lifts like a lid, smoothly, with no bind at any angle.

The geometry that makes this work: the rod sits **behind and above** the rear edge of the glass, and
every point of the platen is *forward* of the rod. Lifting swings the panes up and **rearward** —
away from the wings, never into them. Only the last 25 mm of pane behind the rod dips, into open air
above the posts.

### Step 7 — Glass clamps and glass

**Fit the silicone first.** Line each clamp's 6.4 mm channel with 1 mm silicone strip (or split fuel
hose), leaving the 4.4 mm mouth. The glass must ride on rubber — **never on plastic, never on a hard
corner.**

1. Bolt two clamps to each arm's inboard face: **M3 × 12**, two per clamp, one high one low,
   **34 mm apart**. The pair is what takes the glass moment — one bolt would slowly work loose. The
   Ø8 counterbores give the heads a flat seat and let a 2.5 mm hex key in.
2. Slide each pane in **from the apex side**. 16 mm of glass sits in the clamp; the jaw covers the
   outermost ~20 mm of the pane.
3. Set each pane so its **outer 14 mm** sits in the clamps: 260 − 14 = **246 mm of clear glass over
   a 240 mm page.** Put all the pane margin at the outer edge and the page stays completely clear.

### Step 8 — 🔴 CRITICAL: glass must not foul the wings

**This is failure point #2.** Do this test before you go any further.

1. Put a **20 mm** book in the cradle. Lower the platen. The glass should meet the pages, not the
   plywood, and both panes should contact evenly.
2. Repeat with a **60 mm** book, sliding the carriages outward.
3. Now lift the platen through its **full arc**. Watch the leading edges of both panes. They must
   swing **up and back**, clear of the wing panel edges, at every angle.

**If a pane clips a wing:** the arms are sitting too far forward. Move the rear posts back in Y a
few mm, or shift the pane outward in its clamps. Do not force it — chipped 4 mm glass is sharp and
the chip will propagate.

**If the panes do not meet the page evenly:** the two carriages are not symmetric about the
centreline. Loosen both knobs, centre the book, let the cradle self-set, re-lock.

### Step 9 — Counterweight and anti-slam

The pocket in each arm tail is **24 × 54 × 11 mm = 14.3 cm³** (~14.0 cm³ with the corner radii).
Packed solid with steel washers that is **~112 g**; with loose coins, 70–80 g.

**Be honest with yourself about what this does.** Its lever is only 29 mm behind the pivot, so it
returns about **3 kg·mm** against the **~128 kg·mm** the pane applies. It cannot balance the platen
and nothing that fits in that pocket could. **That is fine — you do not want a balanced platen.**
884 g of glass per pane resting on a page is exactly what flattens it.

What you are killing is the **slam**. Use the **5 mm spring anchor** in the arm tail: one light
extension spring, or a doubled rubber band, up to the rear post (this is what the extra 63 mm of
post above the rod is for). That takes 30–40 % out of the fall and makes the lid *settle* instead of
*drop*.

✅ **Check:** release the platen from 45°. It should come down in about a second, not bang.

### Step 10 — Spine support

The wedge sits in the bottom of the V and stops a thick spine sagging into the gap. Stick a felt
strip on the flat top face.

> ⚠️ **USE IT ONLY ON BOOKS THICKER THAN ~35 mm.** Here is the actual rule: closing the platen on a
> book of thickness *t* lifts the glass apex above the cradle apex by `1.305 × t/2`. The wedge stands
> **20.8 mm** proud, so you need `1.305 × t/2 > 22.8 mm`, i.e. **t > ~35 mm**.
>
> | Book thickness | Glass apex rises | Wedge OK? |
> |---|---|---|
> | 20 mm | 13.0 mm | ❌ **no** — wedge holds the glass off the page |
> | 35 mm | 22.8 mm | ⚠️ borderline |
> | 40 mm | 26.1 mm | ✅ yes |
> | 60 mm | 39.1 mm | ✅ yes |
> | 80 mm | 52.2 mm | ✅ yes |
>
> Under 35 mm a spine does not sag anyway, and leaving the wedge in causes exactly the fault it is
> meant to prevent.

At 44 mm across it bridges the 30 mm gap with 7 mm landing on each panel. For a thicker book with
the carriages run further out, raise `spine_hw` in the SCAD and re-render — the height follows the
width through the wing angle automatically.

### Step 11 — Camera posts and mounts

Stand the two 600 mm posts vertically, **300 mm out from the machine centreline** on each side.

Drop each collar down its post (20.70 mm bore on a 20 mm post — a sliding fit) and lock with
**M5 × 16 into a T-nut** in the post slot. Set the platform **~295 mm above the cradle apex**.

Bolt each platform to its ear with **2 × M5 × 30** — one through the pivot, one through the arc
slot. Put a thumbscrew knob on the **arc** bolt (that is the one you adjust); a plain nut on the
pivot.

Drop a **1/4"-20 nut** into the pocket in the platform and bolt your camera down through the 6.5 mm
hole. **No threads are modelled anywhere in this machine** — the nut is the thread.

**For phones:** bolt the `camera_mount_phone_jaw` on with the same 1/4-20 bolt (nut goes in the
pocket in the jaw's slot floor, bolt comes up from under the platform). 11 mm slot takes a 7–11 mm
phone with or without a case, 78 mm of edge support. A rubber band in the grooves round both lips
holds it. **Stand the phone with its lens above the jaw, not inside it.**

**The tilt arc runs 15°–65°** — that is the page normal (40°) ± 25°. **At mid-arc the platform is
parallel to the page and the lens looks straight down the page normal.** That is the only aiming
that keeps a rectangular page rectangular. Lock both M5 and it will not creep.

✅ **Check:** ~300 mm from lens to page centre along the page normal. Nothing closer than 260 mm —
below that you cannot fit the page in frame.

### Step 12 — Lights

Mount the two 400 mm rails **horizontally, front-to-back, outboard of and above the cradle**. The
light bracket's U drops over the rail from above and one **M5 pulls down into a T-nut in the rail's
top slot**.

Bolt the aluminium LED channel to the 45° pad with **2 × M3 × 12** into the inserts. Feed the
**25 mm polarising strip** into the fork from either end — the prongs grip 3 mm of it on each side,
leaving a 19 mm clear aperture.

Wire both strips to the 12 V PSU. ✅ **Check:** both strips at the same brightness and colour.

### Step 13 — Foot pedal

Plug in the USB pedal and map it to your capture software's shutter (§7). Position it where your
foot rests naturally — you will press it several hundred times per book.

---

## 5. CAMERA SETUP

Get this right once and never touch it again. **Every setting is manual. That is the whole point.**

### Geometry

| | |
|---|---|
| Lens to page centre | **~300 mm** along the page normal |
| Post position | 300 mm out from centreline, platform ~295 mm above the cradle apex |
| Tilt | mid-arc — platform parallel to the page, lens down the page normal |
| Minimum working distance | **260 mm** — closer and the page will not fit |

**Framing check:** a 26 mm-equivalent phone camera (69.4° × 49.6°) at 300 mm covers **415 × 277 mm**.
Put the **long sensor axis along the page height**: 415 mm covers the 320 mm page height, 277 mm
covers the 240 mm page width. That is 15–30 % margin all round — enough to crop, not so much that
you throw away resolution.

The glass frame lives outboard of the pane edge, 20 mm outside the page area, so at this standoff
**no part of the machine enters the frame.**

### Settings — all manual, all locked

| Setting | Value | Why |
|---|---|---|
| **Focus** | **MANUAL**, locked | see below |
| **Exposure** | **MANUAL**, locked | see below |
| ISO | lowest clean value (100–200) | noise destroys OCR |
| Aperture | f/5.6–f/8 if you have the choice | depth of field across a slightly domed page; past f/8 diffraction softens text |
| Shutter | whatever gives correct exposure — the camera is on a post, nothing moves | |
| White balance | **manual / custom**, set once off a white page | auto WB drifts between shots |
| Format | **RAW if available, otherwise maximum-quality JPEG** | you will threshold this image later; JPEG artefacts around Hebrew letterforms become OCR errors |
| Image stabilisation | **OFF** | it is on a rigid post; IS introduces random micro-shifts |
| Flash | **OFF** | |

### 🔴 Why autofocus and auto-exposure MUST be off

This is not a preference. It is the difference between a usable scan and 300 unusable images.

**Autofocus will hunt.** Every shot, the camera re-decides where to focus. A page with a photo on it
focuses differently from a page of text. A page with a wide margin gives AF nothing to lock onto and
it racks the lens back and forth. You get a run of sharp pages, then three soft ones, then sharp
again — and you will not notice until you are 200 pages in. Worse, focus breathing subtly changes
the **magnification** shot to shot, so your pages are no longer the same size and batch cropping
stops working.

**Auto-exposure will drift.** A spread with a full-page illustration is darker than a spread of
text, so AE brightens it. Now that page's white point is different from every other page's. When you
threshold to bitonal, that page turns grey and mushy or blows out entirely. Consistency across the
whole book is worth far more than each page being individually "correct".

**Set it once:** put a mid-thickness book in, close the platen, focus manually on the text, set
exposure off a typical text page, lock everything, tape the focus ring if it is a lens that can
drift. Then do not touch it for the rest of the book.

**Both cameras must match.** Same ISO, same WB, same exposure, same distance. Shoot a test spread
and compare the two halves side by side before you commit to a book.

---

## 6. LIGHTING AND GLARE

**This is the single biggest quality lever in the whole build.** A perfectly built machine with bad
lighting produces worse scans than a rough machine with good lighting. Read this section twice.

### The problem

You are photographing a page **through a sheet of glass**. Glass reflects. Point a light at the page
from near the camera and you photograph the lamp, not the page. That white blob sits on top of the
text and no amount of post-processing brings the text back — the information is simply gone.

### The side-45 rule

**Light the page from the SIDE, at 45°, never from the front and never square-on.**

The physics is one line: **angle of incidence equals angle of reflection.** A light at 45° from the
side throws its specular reflection off to the **far side of the cradle**, away from the lens. A
light near the camera throws it straight back into the lens.

That is exactly what `light_bar_bracket` builds in — the 45° pad is not decorative. Mount the light
rails **outboard of and slightly above** the cradle, one per side, so each lamp rakes across its own
page from the outside edge toward the spine.

**Rake also reveals texture you do not want.** Very grazing light (below ~30°) throws shadows off
every fibre and fold and makes paper look like a relief map. 45° is the balance point: reflection
goes away, texture stays flat.

**Check it by eye before you shoot:** put your eye where the lens is and look at the glass. If you
can see a lamp in it, the camera can too. Move the lamp until the reflection leaves the page area
entirely. Do this for **both** sides — they are independent.

### Cross-polarisation — how to kill the last of the sheen

Side-45 removes the lamp's *image*. It does not remove the low, even **sheen** that coated or glossy
paper throws back across the whole page. Cross-polarisation removes that too, and it is close to
magic the first time you see it.

**How it works.** Light from an LED is unpolarised — waves vibrating in every orientation. Pass it
through a linear polariser and only one orientation survives. When that polarised light bounces
**specularly** off a shiny surface it stays polarised. When it scatters **diffusely** off the paper
fibres — which is the light that actually carries the image of the ink — it gets scrambled and comes
back unpolarised.

So: put a second polariser on the lens, rotated **90° to the first**. It blocks the surviving
specular light almost completely, while roughly half the scrambled diffuse light gets through.
**The reflection dies. The text stays.**

**How to set it up:**

1. Slide a **25 × 3 mm linear polariser** strip into the fork on each light bracket, in front of the
   LEDs. Both lights must have their film at the **same orientation** — mark the orientation on the
   sheet with a pen before you cut the strips.
2. Put a polariser on each lens: a **CPL filter** if your camera takes filters (a CPL's front element
   is a linear polariser, so it works as the analyser), or a clip-on CPL for a phone, or a square of
   the same linear film taped over the lens.
3. Look through the camera at the glass over a **glossy** page. **Rotate the lens polariser slowly.**
   You will see the sheen swell and then fade. **Keep turning until the reflection dies.** That is
   90° to the lights.
4. Lock it there. Tape it if it can rotate.
5. Repeat for the second camera — its film orientation is independent.

**The costs, honestly:**
- You lose about **1.5–2 stops** of light. Compensate with more LED, not higher ISO.
- On matte, uncoated paper the gain is small — the paper was not glossy to begin with. On coated
  stock, glossy art books, plastic-laminated pages and old photo plates, the gain is enormous.
- The film must be **linear** on the lights. Circular polariser film (the "3D glasses" kind) on the
  lights will not cross properly.

**If you build only one optional thing in this machine, build this.**

---

## 7. FIRST SCAN WORKFLOW

### Setup, once per book

1. Slide both carriages out to roughly the book's thickness. Lock both knobs.
2. Drop the book in, open to the middle. Let the cradle take it.
3. Thicker than 35 mm? Put the spine support in. Thinner? **Leave it out.**
4. Lower the platen. Both panes should touch both pages evenly. Adjust the carriages if not.
5. Check framing on both cameras — the page fills the frame with a comfortable margin, no machine
   parts in shot.
6. Set focus and exposure manually. **Lock everything.** (§5)
7. Shoot one test spread. Look at it at 100 %. Sharp corner to corner? Even lighting? No reflection?
   **Fix it now, not after 300 pages.**

### The loop

```
  press pedal        →  both cameras fire, both pages captured
  lift platen        →  one hand, up and back
  turn page          →  other hand, from the FRONT (the front is sacred — nothing blocks it)
  drop platen        →  let it settle, do not slam
  repeat
```

3–5 seconds per spread once you have the rhythm. **Do not chase speed on your first book.** Get
every page in focus and correctly exposed; speed arrives on its own.

**Every 20 spreads or so, glance at the last capture.** Cheap insurance against discovering a
knocked camera 200 pages later.

**Watch for:** a finger in frame, a page that did not lie flat (re-shoot immediately — do not fix it
in software), the platen not fully down, a double page turn.

### Post-processing chain

Runs unattended after capture. Order matters.

| # | Stage | Tool | Notes |
|---|---|---|---|
| 1 | **Split and sort** | script | left camera → even pages, right → odd. Interleave into reading order. Rename to a zero-padded sequence |
| 2 | **Rotate** | script | each camera is 90° off if you framed with the long axis along the page height |
| 3 | **Crop / deskew** | ScanTailor Advanced | the machine is rigid, so one crop box applies to the whole book. This is the big win of a fixed rig |
| 4 | **Dewarp** | ScanTailor | **mostly unnecessary — the glass already did it.** That is what the platen is *for*. Run it only on pages where the glass did not fully seat |
| 5 | **Greyscale / normalise** | ScanTailor | equalise illumination across the page |
| 6 | **Threshold to bitonal** | ScanTailor (Otsu / Sauvola) | text only. **Keep illustrations in greyscale or colour** — thresholding a photograph destroys it |
| 7 | **OCR** | see below | |
| 8 | **Bind** | `img2pdf` + `ocrmypdf`, or DjVu | PDF with an invisible text layer over the page images |

> 🚫 **Hebrew OCR runs on the DGX fleet, NOT on the PC.** Per workspace law, anything that does
> `import torch` + `torch.load()` runs on eran1–4, never here. Tesseract with `heb.traineddata` will
> run on the PC without torch, but it is genuinely weak on Hebrew — poor with nikud, poor with
> ligatures, and it fights right-to-left layout. Push the images to the fleet and run a modern
> vision-language OCR there. If the fleet is down, **wait** — do not fall back to the PC.
>
> Reach paths are in `D:\CLAUDE\CLAUDE.md`. Batch the whole book as one job; do not round-trip per
> page.

**Sanity check before you archive:** open the finished PDF, search for a word you know is on page
50, and confirm it lands on page 50. If the text layer is offset, your page ordering broke in
stage 1.

---

## 8. WHAT TO ADD LATER

### Automatic page turning — the honest version

Every DIY scanner project eventually tries this, and most of them fail. Here is why, so you go in
with your eyes open.

**The hard part is not lifting a page. It is separating exactly one sheet from the next.**

Paper sticks to paper. Electrostatic attraction, humidity, ink tack, and simple surface contact mean
that when a suction cup grabs the top sheet, it very often brings the second one with it — or tears
the first. A vacuum cup pulling straight up on a flat stack is close to the worst case: maximum
contact area, no separation force, nothing telling you it went wrong.

**The fix that actually works is air.** Before the cup touches anything, a **puff of air must fluff
the edge of the stack** — a short blast aimed along the fore-edge that lifts and separates the top
few sheets so there is a visible air gap under sheet one. *Then* the cup comes down on the now-lifted
top sheet, grabs it, and lifts. This is exactly how production document feeders work, and they use
an air knife plus a vacuum belt because nothing simpler is reliable enough.

If you build it, build it in this order:

1. **Air first.** A small aquarium pump or a solenoid on a compressed-air line, with a nozzle aimed
   along the fore-edge. Get *just one* sheet to lift, repeatably, 50 times in a row, **before you
   add any other mechanism.** If you cannot do this, nothing downstream will work.
2. **Then the cup.** A small silicone suction cup on a servo arm, coming down only after the puff.
   Compliant mount so it cannot press hard enough to tear.
3. **Then the sweep.** Once the sheet is held, an arc that carries it over the apex to the other side.
4. **Then detection.** You need to *know* it took two sheets. Page-number OCR on the captured image
   is the cheapest reliable detector — if page numbers skip, stop the machine.
5. **Only then, sequencing.** Foot pedal → puff → grab → sweep → release → settle → capture.

**Budget honestly:** this is a bigger project than the whole scanner. Expect it to be less reliable
than your hands for a long time, and expect to babysit it anyway. **A jam that tears a page is
unrecoverable** — you cannot un-tear a book. Never leave it running unattended on a book you care
about, and never on a book you cannot replace.

### Smaller upgrades, in order of value

| Upgrade | Why |
|---|---|
| **Tethered capture** | shoot straight to disk, see every frame on a monitor as it lands. Catches errors instantly instead of 200 pages later. This is the highest-value addition, by a wide margin |
| **Second foot pedal** | one to capture, one to mark "re-shoot this one" |
| **Glass-position dowels** | two small stops so the platen lands in exactly the same place every time — helps batch cropping |
| **A darker room / a shroud** | ambient light is an uncontrolled second light source; killing it makes exposure fully repeatable |
| **3 mm acrylic panes** | 313 g instead of 884 g. Gentler on fragile paper, easier on your arm. It scratches — swap back to glass for anything valuable |
| **A bigger cradle** | every dimension in the SCAD is parametric. Change `book_w` / `book_h` / `glass_w` / `glass_h` at the top of the file and re-render. Nothing is hard-coded |

---

## Appendix — file inventory (verified)

All 12 STLs re-checked with trimesh: **every one watertight, winding consistent.**

| STL | Qty | Size (mm) | Solid cm³ | Bodies | Notes |
|---|---|---|---|---|---|
| `cradle_wing_bracket.stl` | 4 | 110.0 × 99.9 × 18.0 | 79.48 | 1 | genus 1 = lightening window |
| `rail_carriage.stl` | 2 | 110.0 × 190.0 × 26.4 | 170.90 | 1 | genus 5 = M5 lock + 4 M3 clearance |
| `platen_hinge_arm.stl` | 1 | 310.0 × 86.0 × 26.0 | 277.18 | 1 | handed pair |
| `platen_hinge_arm_mirror.stl` | 1 | 310.0 × 86.0 × 26.0 | 277.18 | 1 | handed pair |
| `glass_edge_clamp.stl` | 4 | 26.6 × 44.0 × 50.0 | 32.69 | 1 | genus 2 = 2 M3 holes |
| `camera_mount.stl` | 1 | 126.3 × 46.0 × 110.0 | 100.96 | **2** | collar + platform, **by design** |
| `camera_mount_mirror.stl` | 1 | 126.3 × 46.0 × 110.0 | 100.96 | **2** | handed pair |
| `camera_mount_phone_jaw.stl` | 2 | 78.0 × 22.0 × 18.0 | 22.50 | 1 | optional, phones only |
| `light_bar_bracket.stl` | 1 | 85.5 × 111.2 × 50.0 | 134.95 | 1 | fork not severed |
| `light_bar_bracket_mirror.stl` | 1 | 85.5 × 111.2 × 50.0 | 134.95 | 1 | handed pair |
| `thumbscrew_knob.stl` | 4 | 35.1 × 36.0 × 13.0 | 11.85 | 1 | print 6 |
| `spine_support.stl` | 1 | 44.0 × 90.0 × 20.8 | 45.66 | 1 | plain prism, 16 facets |

**23 STL instances = 25 physical pieces** (each camera_mount plate holds 2 pieces).
**Total solid geometry: 1954.7 cm³.**
