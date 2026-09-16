# -*- coding: utf-8 -*-
"""One-page print card for Dave's U-clip. Numbers are READ FROM measured.json,
which was produced by ray-casting the exported STLs - nothing here is retyped.
English only on purpose: matplotlib has no bidi shaper and would ship Hebrew
reversed (the ASS-spacing scar). Bilingual summary goes in the chat, not here."""
import json, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.image as mpimg

M = json.load(open("D:/CLAUDE/pongo-dave/measured.json", encoding="utf-8"))
fig = plt.figure(figsize=(8.27, 11.69), facecolor="white")   # A4 portrait

fig.text(.5, .966, "DAVE'S U-CLIP", ha="center", fontsize=25, fontweight="bold", color="#111")
fig.text(.5, .944, "Pongo Shirts  ·  print-ready  ·  PETG on the K2 Plus", ha="center",
         fontsize=11.5, color="#555")
fig.text(.5, .921, "DO NOT PRINT YET  —  waiting on Iddo's word", ha="center", fontsize=13,
         fontweight="bold", color="white",
         bbox=dict(fc="#c62828", ec="none", boxstyle="round,pad=0.45"))

for i, key in enumerate(["v1", "v2-thick"]):
    ax = fig.add_axes([0.05 + i * 0.475, 0.700, 0.45, 0.205])
    ax.imshow(mpimg.imread(f"D:/CLAUDE/pongo-dave/dave-uclip-{key}-preview.png")); ax.axis("off")

rows = []
for key in ["v1", "v2-thick"]:
    d = M[key]
    bb = d["bbox_mm_XxYxZ"]
    rows.append([key.split("-")[0].upper(),
                 f"{bb[0]}", f"{d['measured_slot_width_mm']}", f"{d['measured_wall_left_mm']}",
                 f"{bb[2]}", f"{bb[1]}", f"{d['petg_mass_g_at_1.27']:.1f} g",
                 "yes" if d["watertight"] else "NO"])

ax = fig.add_axes([0.05, 0.560, 0.90, 0.115]); ax.axis("off")
ax.set_title("MEASURED BACK OFF THE STL  (ray-cast, not copied from the code)",
             fontsize=11.5, fontweight="bold", color="#111", loc="left", pad=12)
t = ax.table(cellText=rows, colWidths=[0.10]+[0.115]*7,
             colLabels=["variant", "outer", "slot", "wall", "height", "length", "PETG", "watertight"],
             cellLoc="center", loc="center")
t.auto_set_font_size(False); t.set_fontsize(10); t.scale(1, 1.75)
for (r, c), cell in t.get_celld().items():
    cell.set_edgecolor("#bbb")
    if r == 0:
        cell.set_facecolor("#123f6d"); cell.set_text_props(color="white", fontweight="bold")
    else:
        cell.set_facecolor("#eef4fb" if r % 2 else "#ffffff")

BODY = [
    ("#c62828", "ORIENTATION — the one thing that decides if it survives"),
    ("#222", "Lay it on its SIDE: the 70 mm length flat on the bed, the U-axis parallel to the bed,"),
    ("#222", "mouth pointing sideways. Printed standing up, the layer lines run across the spring and"),
    ("#222", "the clip snaps at the fillet on the first open. No supports needed in this orientation."),
    ("", ""),
    ("#123f6d", "K2 PLUS  ·  PETG"),
    ("#222", "nozzle 240 °C   ·   bed 80 °C   ·   4 perimeters   ·   40 % infill   ·   40 mm/s"),
    ("#222", "fan 30 %   ·   DRY THE FILAMENT — damp PETG strings and the thin wall goes rough."),
    ("", ""),
    ("#123f6d", "DESIGN DECISIONS  (say these to Dave)"),
    ("#222", "Slot is 12.4 mm, not 12.0 — 0.2 mm clearance each side so it slides onto a 12 mm panel."),
    ("#222", "A printed 12.0 slot binds and splits the legs."),
    ("#222", "R3 fillet at the inner corner of the U. That corner is where a clip cracks; the fillet"),
    ("#222", "spreads the stress. Cost: full-width grip runs 0-17 mm, the last 3 mm is the radius."),
    ("#222", "Two wall options because 1.5 mm PETG is a weak spring: stiffness goes with thickness"),
    ("#222", "CUBED, so 2.5 mm is ~4.6x stiffer than 1.5 mm. V1 is the sketch, V2 is the safe one."),
    ("", ""),
    ("#b3005c", "DEVIATION FROM THE SKETCH — one number, stated plainly"),
    ("#222", "The sketch says outer 15 with a 12 slot, i.e. 1.5 mm walls. Adding the 0.4 mm print"),
    ("#222", "clearance forces a choice: keep outer 15 (walls drop to 1.3 mm, 35 % less stiff) or keep"),
    ("#222", "the 1.5 mm wall (outer grows to 15.4). We kept the WALL. Outer is 15.4, not 15.0."),
    ("#222", "If Dave needs outer 15.0 exactly, say so — it is one number in uclip.py."),
    ("", ""),
    ("#123f6d", "STILL UNANSWERED BY DAVE"),
    ("#222", "1.  What is the 12 mm panel — glass, table edge, sign board?"),
    ("#222", "2.  What hangs off the clip, and which way does the load pull?  That decides whether"),
    ("#222", "     the spine needs a hole, a hook, or a flat face."),
]
y = 0.532
for colour, line in BODY:
    if not line:
        y -= 0.0105; continue
    bold = colour in ("#c62828", "#123f6d", "#b3005c")
    fig.text(0.055, y, line, fontsize=10.6 if bold else 9.9, color=colour,
             fontweight="bold" if bold else "normal", va="top")
    y -= 0.0158 if bold else 0.0145

fig.text(.5, .028, "dave-uclip-v1.stl  ·  dave-uclip-v2-thick.stl  ·  built parametrically by uclip.py",
         ha="center", fontsize=8.6, color="#777")
fig.text(.5, .014, "D:\CLAUDE\pongo-dave   ·   2026-09-01", ha="center", fontsize=8.6, color="#777")

for ext in ("png", "pdf"):
    fig.savefig(f"D:/CLAUDE/pongo-dave/dave-uclip-PRINT-CARD.{ext}", dpi=190, facecolor="white")
plt.close(fig)

img = mpimg.imread("D:/CLAUDE/pongo-dave/dave-uclip-PRINT-CARD.png")
plt.imsave("D:/CLAUDE/pongo-dave/dave-uclip-PRINT-CARD.jpg", img)
print("print card written (png/pdf/jpg)")
