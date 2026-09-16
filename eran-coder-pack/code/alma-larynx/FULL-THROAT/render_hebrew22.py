# -*- coding: utf-8 -*-
"""Draw the 22-letter gap analysis. Bright, honest, one page."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle
import hebrew22 as H

INK = "#12233a"
GREY = "#7d8fa3"
RED = "#b0322a"
GOLD = "#a97612"
GREEN = "#1a7f45"

GROUP_COLOR = {
    "GUTTURAL": ("#fdeceb", "#b0322a"),
    "PALATAL":  ("#fdf3e3", "#c8791e"),
    "LINGUAL":  ("#eef7ed", "#2d7d46"),
    "DENTAL":   ("#eaf1fb", "#1769b0"),
    "LABIAL":   ("#f4ecf9", "#7d3fa8"),
}

fig, ax = plt.subplots(figsize=(17.4, 14.6), facecolor="white")
ax.set_xlim(0, 100)
ax.set_ylim(-3.2, 100)
ax.axis("off")

ax.text(50, 97.2, "ERAN'S MOUTH  vs  THE 22 LETTERS", ha="center",
        fontsize=25, weight="bold", color=INK)
ax.text(50, 94.4, "\u05d0\u05d7\u05d4\u05e2   \u05d2\u05d9\u05db\u05e7   "
                  "\u05d3\u05d8\u05dc\u05e0\u05ea   \u05d1\u05d5\u05de\u05e3   "
                  "\u05d6\u05e1\u05e9\u05e8\u05e5",
        ha="center", fontsize=19, color=GREY)
ax.text(50, 91.8, "for each letter: the organ that physically makes it, and whether the "
                  "planned throat has that organ",
        ha="center", fontsize=11.5, color=GREY, style="italic")

# ---------------- the five groups ----------------
y = 88.0
for letters, name, place, rows in H.GROUPS:
    fc, ec = GROUP_COLOR[name]
    h = 2.05 + 2.35 * len(rows)
    ax.add_patch(FancyBboxPatch((2, y - h), 96, h,
                                boxstyle="round,pad=0.4,rounding_size=0.8",
                                fc=fc, ec=ec, lw=2.0))
    ax.text(5.0, y - 1.9, letters, fontsize=20, weight="bold", color=ec, va="center")
    ax.text(15.5, y - 1.9, "%s  \u2014  %s" % (name, place),
            fontsize=13, weight="bold", color=ec, va="center")
    ax.text(96, y - 1.9, "%d letters" % len(rows), fontsize=11,
            color=ec, va="center", ha="right")
    ry = y - 4.0
    for ch, translit, ipa, organs in rows:
        ax.text(8.2, ry, ch, fontsize=21, weight="bold", color=INK,
                va="center", ha="center")
        ax.text(11.6, ry, translit, fontsize=11.5, color=INK, va="center")
        ax.text(21.5, ry, ipa, fontsize=11.5, color="#44607d", va="center")
        ax.text(48.0, ry, "needs:  " + ",  ".join(organs), fontsize=11,
                color="#3d5771", va="center")
        ax.add_patch(Rectangle((92.0, ry - 0.75), 4.4, 1.5, fc="#ffffff",
                               ec=RED, lw=1.6))
        ax.text(94.2, ry, "NO", fontsize=10.5, weight="bold", color=RED,
                va="center", ha="center")
        ry -= 2.35
    y -= h + 1.15

# ---------------- the score ----------------
ax.add_patch(FancyBboxPatch((2, y - 7.3), 46, 7.1,
                            boxstyle="round,pad=0.4,rounding_size=0.8",
                            fc="#fdeceb", ec=RED, lw=2.6))
ax.text(25, y - 2.2, "SCORE TODAY:   0  of  22", ha="center",
        fontsize=19, weight="bold", color=RED)
ax.text(25, y - 4.7, "the planned throat is a VOWEL machine, not a mouth",
        ha="center", fontsize=11.5, color="#7a2b24")

ax.add_patch(FancyBboxPatch((51, y - 7.3), 47, 7.1,
                            boxstyle="round,pad=0.4,rounding_size=0.8",
                            fc="#fffaef", ec=GOLD, lw=2.6))
ax.text(74.5, y - 1.6, "TWO LETTERS NOBODY HAS EVER BUILT", ha="center",
        fontsize=13.5, weight="bold", color="#8a5a10")
ax.text(74.5, y - 3.05, "ח        ע", ha="center", va="center",
        fontsize=16, weight="bold", color="#8a5a10")
ax.text(74.5, y - 4.35, "pharyngeal. Japanese, German and English have none, so no talking" + chr(10) +
                       "robot ever built has a pharyngeal squeeze. Nothing to copy.",
        ha="center", va="top", fontsize=10.2, color="#5c4410", linespacing=1.5)

# ---------------- build order ----------------
y2 = y - 9.6
ax.text(50, y2, "BUILD ORDER  \u2014  add these ten organs in this sequence",
        ha="center", fontsize=15, weight="bold", color=GREEN)
steps = H.build_order()
y2 -= 3.0
bar_x0, bar_w = 56.0, 38.0
for i, (organ, new, total) in enumerate(steps, 1):
    ax.text(4.0, y2, "%d." % i, fontsize=11.5, weight="bold", color=GREY, va="center")
    ax.text(7.0, y2, organ, fontsize=12, weight="bold", color=INK, va="center")
    ax.text(33.0, y2, "unlocks  " + " ".join(new), fontsize=13, color=GREEN, va="center")
    ax.add_patch(Rectangle((bar_x0, y2 - 0.72), bar_w, 1.44,
                           fc="#eef2f6", ec="none"))
    ax.add_patch(Rectangle((bar_x0, y2 - 0.72), bar_w * total / 22.0, 1.44,
                           fc=GREEN, ec="none"))
    ax.text(bar_x0 + bar_w + 1.4, y2, "%d/22" % total, fontsize=11,
            weight="bold", color=GREEN, va="center")
    y2 -= 2.15

ax.text(50, y2 - 1.9, "the tongue alone \u2014 back, tip, teeth and timing \u2014 is worth "
                 "12 of the 22.  Sawada had no tongue until 2010, and named it as "
                 "why his fricatives failed.",
        ha="center", fontsize=11, color=GREY, style="italic")

ax.set_ylim(y2 - 3.4, 100)
plt.tight_layout()
out = r"D:\CLAUDE\alma-larynx\FULL-THROAT\HEBREW-22.png"
plt.savefig(out, dpi=118, facecolor="white")
print("wrote", out)
