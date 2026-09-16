# CNC Helper — absorbed into Fabrication Helper

This former standalone brief is now the **FoxAlien XE-PRO workspace** within `../fabrication-helper/PRODUCT.md`. It remains only as historical context.

## Verified machine boundary

The official XE-PRO specification lists GRBL control, a 400 × 400 × 95 mm work area, 400 W spindle, 1204 ball screws, and closed-loop NEMA 23 steppers. [FoxAlien XE-PRO product page](https://www.foxalien.com/products/cnc-router-machine-xe-pro?variant=43138100461705) Official manuals/drivers are linked by FoxAlien. [Manual resource page](https://www.foxalien.com/blogs/news/foxalien-cnc-and-laser-machine-user-manual)

## MVP

- Ingest photos/video of the setup plus CAD/CAM exports.
- Create a visual preflight checklist: machine, workholding, bit, material, dust control, zero, travel limits, and emergency stop.
- Parse and review G-code offline for bounds, unsafe Z movement, units, spindle state, and unrecognised commands.
- Present a human-readable job card and require operator confirmation; do not connect to or command the CNC.

## Safety exclusions

No automatic feeds/speeds guarantee, no automatic toolpath execution, no bypass of firmware limits, and no operation without an attending trained operator, guarding, dust control, and emergency stop.
