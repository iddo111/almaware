> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

# SCAR 2026-08-29 — the sweep that could not be re-run
# צלקת — הסקירה שלא ניתן היה להריץ מחדש

**What happened / מה קרה.** On 2026-08-29 Iddo asked whether the work being handed
to him was worth anything, and told me to run an agent to check. Two independent
agents were run. Both landed on the same place, and a hand check confirmed the
worst finding. Three files are quarantined here as a result.

## The finding, verified by hand

`DESIGN-SWEEP-winners.json` **cannot be produced by `design_sweep.py`.** Verified
directly, not taken on the agent's word:

| field | values in the JSON | grid in `design_sweep.py:84-89` |
|---|---|---|
| `t_mm`  | 0.8, 1.0, 1.2, 1.5 | 1.0, 1.5, 2.0, 3.0, 4.0 |
| `l_mm`  | 2.0, 2.5, 3.0 | 3.0, 4.0, 5.0, 6.0, 8.0 |
| `G0_mm` | 0.15, 0.2, 0.3 | 0.2, 0.4, 0.8 |

The JSON also carries keys the script never emits (`tau_at_band`, `F0_at_band`,
`F0_span`, `n_taus_alive`; the script emits `tau`, `F0`). Running the script that
is actually on disk yields **zero winners**. The 79-entry file is a record from
code that no longer exists — and `make_real_mold_b.py` was citing it as the
evidence for its "champion" leaf.

**This is the fourth stale record caught by hand in a week.** It is exactly the
failure SHAMASH was built for.

## Why the numbers were never trustworthy anyway

- **Fold length `L` cancels algebraically.** `sqrt(k/m) = (t/2l²)·sqrt(E(1+τ)/ρ)`.
  L = 8, 12 and 17 mm all return F0 = 220.0 Hz — visible in the JSON itself. So
  "79 winners" is really **27 unique geometries and 12 distinct F0 values**; L
  inflated the count by a free 3×.
- **The pressure law is not Steinecke–Herzel.** S-H gives `P1 = 0` in the
  divergent phase; `design_sweep.py:70` substitutes `0.5*Ps`, and
  `simulate_voicebox.py:75` carries the same invented term. **The rev-A M5 block
  was rejected by the same broken term that accepted rev-B.** With the correct
  law, rev-A at 5 kPa flips from "silent" to oscillating at depth 0.93.
- **Modal mass wrong by 4×** — full distributed mass instead of the cantilever's
  0.2427·ρAl, i.e. 2.03× in frequency. The servo tensioner existed only to close
  a gap this error created.
- **Beam theory does not apply.** Champion slenderness l/t = 2.08; every winner
  is 1.33–2.50. Euler–Bernoulli needs ≳10. These are squat blocks, not beams.
- **The one variable the literature calls the master lever was never swept:**
  silicone dilution. `design_sweep.py:88` only tried undiluted 36 and 69 kPa,
  then multiplied by (1+τ) to 144–276 kPa — **10–100× stiffer than anything that
  phonates in the published record.**

## What was quarantined

| file | why |
|---|---|
| `SCAR-DESIGN-SWEEP-winners-UNREPRODUCIBLE-20260829.json` | not reproducible from any code in this repo |
| `RETIRED-THROAT-MOLD-B-20260829.stl` | its only specification came from that file |
| `RETIRED-STENCIL-THROAT-MOLD-B-20260829.png` | the sheet that presented it |

The CAD itself was clean — watertight, 38×18×4 mm, pocket volume exact, no
overhangs. **Everything wrong was upstream of the geometry.** That is worth
remembering: a part passing every mechanical acceptance check can still be the
wrong part.

## What survived, and is now the plan

Both agents independently endorsed the same two things:

1. **`FULL-THROAT/` stands.** The tract mould, pinch rail, bars and levers are
   dimensioned from Sawada's measured numbers, are independent of the fold
   question, and should be printed.
2. **`make_silicone_fold_mold.py`'s M5 polygon is CORRECT** — the geometry was
   verified against the published Scherer parameters (θ1 = 50° from the flow
   axis, exit radius 0.987 mm, depth 8.4 mm, AP 17 mm). Only its docstring
   mislabels the angle as 40°, measuring from horizontal instead. **Rev-A's shape
   was never the problem; its material stiffness and a broken simulator were.**

The corrected fold route, from the literature:

- **Single-layer M5 self-oscillates** — ~1.15–1.2 kPa onset, ~120 Hz. Two layers
  are for the mucosal wave and realism, **not required for oscillation**.
- The one published design measured inside ERAN's band is a **fibre-tensioned M5:
  226.6 Hz at 1594 Pa**, pitch set by fibre elongation.
- **Do not scale the fold down to child size** — quarter-scale needs 13–18 kPa.
- **The mould must be flexible silicone (Smooth-Sil 950); the FDM print is the
  POSITIVE.** A rigid mould tears a 0.2 kPa cover. This is the real answer to
  demoulding, and it is why a printed tray was the wrong object all along.
- **PLA tooling cannot take the 121 °C cure** (Tg ≈ 60 °C). Either cure at 40 °C
  for 8 h, or use PA12-CF tooling.
- **PA12-CF against platinum-cure silicone is unproven in both directions** — it
  appears on no inhibitor list, but polyamides carry amine end groups and amines
  are listed platinum poisons. **Witness-test an offcut of the actual spool
  before committing a pour.**
- **Subglottal tube 12–20 cm, not the published 50 cm.** A 50 cm tube quarter-wave
  resonates at 172 Hz — inside the 150–300 Hz target — and will pull F0.

*Filed 2026-08-29 22:1x by claude-cli. Sources: two independent review agents run
at Iddo's instruction; the hand check of the JSON-vs-grid mismatch is my own.*
