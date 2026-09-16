# Fabrication Helper — K2 Plus + FoxAlien XE-PRO

## Product statement

One smart project-planning app for a mixed fabrication workshop. The user gives it a project description and optional drawings, photos, videos, CAD files, PDFs, or notes. It returns one coordinated fabrication plan:

```text
Project brief + references
            |
            v
     evidence and constraints
            |
   +--------+---------+----------------+
   |                  |                |
K2 Plus print plan  XE-PRO CNC plan  joining/test plan
   |                  |                |
   +--------+---------+----------------+
            |
            v
  reviewed build packet and risk register
```

## What it answers

For each assembly or part, the app must label one of these decisions:

| Decision | Meaning |
|---|---|
| `PRINT` | K2 Plus part, with orientation, material role, supports, and split strategy. |
| `CNC` | XE-PRO machining operation, with stock, workholding concept, tool category, and a human-reviewed job card. |
| `BUY` | Standard hardware/component; list specification but do not purchase. |
| `OUTSOURCE` | Requires a material/process outside the shop capability. |
| `UNKNOWN` | Missing measurements, engineering analysis, or validation. |

The result explains *why* a component belongs to printing, CNC, both, or neither—for example: CNC-cut bulkheads + printed fairings + bolted/gasketed seam.

## Workspaces

### K2 Plus workspace

- Checks the 350 mm cubed print envelope and proposes safe part splits.
- Produces material roles, orientation, supports, wall/infill intent, colour assignment, seam/fastener locations, and coupon tests.
- Imports supported local reference media and retains source/hash metadata.
- Never sends a print or generates machine-ready G-code without an explicit later approval step.

### FoxAlien XE-PRO workspace

- Uses the declared 400 × 400 × 95 mm work envelope as a planning constraint.
- Produces stock, fixture/workholding concept, tool category, operation order, dust-control reminder, zeroing plan, and inspection points.
- Can parse an imported G-code file offline for bounds and obvious state hazards, but cannot start, jog, or command the CNC.

### Assembly workspace

- Maps interfaces between printed and CNC parts.
- Labels fasteners, clearance, inserts, sealing, tolerances, and test coupons as assumptions until confirmed.
- Creates a build order, inspection gates, and the adversarial risk register.

## Output: Fabrication Packet

Every project produces these editable records:

1. `PROJECT_BRIEF.md` — goal, environment, scale, evidence, constraints.
2. `PARTS.csv` — part/operation classification (`PRINT`, `CNC`, `BUY`, `OUTSOURCE`, `UNKNOWN`).
3. `PRINT_PLAN.md` — K2 Plus parts and test coupons.
4. `CNC_PLAN.md` — XE-PRO setup and human preflight.
5. `ASSEMBLY_PLAN.md` — joins, sequence, tools, and inspection points.
6. `DEVILS_ADVOCATE.md` — failure modes, assumptions, stop conditions.

## Model and research policy

- The app may use verified local model endpoints through pluggable adapters for drafting and classification.
- Web research is opt-in per project and always cites source URLs and access dates.
- It does not claim professional engineering approval or material compatibility from model output alone.
- No account authentication, cloud spend, model downloads, printer commands, CNC commands, or external publishing in MVP.

## First implementation increment

A local-only desktop/web interface with: project intake, file drop zone, parts table, a `PRINT/CNC/BOTH/UNKNOWN` planner, editable fabrication packet preview, and export. It begins with manual facts about the K2 Plus and XE-PRO; machine connection remains disabled.
