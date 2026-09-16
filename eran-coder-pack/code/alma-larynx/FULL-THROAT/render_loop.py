# -*- coding: utf-8 -*-
"""The closed training loop Iddo described, drawn once, with the measured numbers.

"servo, air pump, and an ordinary mic that closes a training loop - then you
play him the voice through a speaker next to the mic, and let him repeat and
train by himself."  (Iddo, 2026-08-29 21:56)

Every number on this drawing is cited to BUILD-NOTES.md, which cites Sawada.
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Circle

W, H = 16.6, 9.2
fig, ax = plt.subplots(figsize=(W, H*1.06), facecolor="white")
ax.set_xlim(0, 100)
ax.set_ylim(0, 60)
ax.axis("off")

INK = "#12233a"
BLUE = "#1769b0"
WARM = "#c8641e"
GREEN = "#1a7f45"
GREY = "#7d8fa3"


def blockc(x, y, w, h, title, sub, fc, ec, fs=11.5, subfs=9.2):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.6,rounding_size=1.4",
                                fc=fc, ec=ec, lw=2.2))
    ax.text(x + w / 2, y + h * 0.63, title, ha="center", va="center",
            fontsize=fs, weight="bold", color=INK)
    ax.text(x + w / 2, y + h * 0.26, sub, ha="center", va="center",
            fontsize=subfs, color="#3d5771", linespacing=1.45)


def arrow(x1, y1, x2, y2, color=BLUE, lw=2.4, style="-|>", rad=0.0, ls="-"):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle=style,
                                 mutation_scale=19, lw=lw, color=color,
                                 linestyle=ls,
                                 connectionstyle="arc3,rad=%s" % rad,
                                 shrinkA=2, shrinkB=2))


# ---------------- the physical chain, left to right ----------------
blockc(1.0, 33, 18, 12, "AIR PUMP", "the lungs\nvoicing 0.3-1.7 kPa at 4-20 L/min\nCONSONANTS to 4.8 kPa at 90 L/min",
       "#eaf3fb", BLUE)
blockc(20.5, 33, 13.5, 12, "PLENUM", "the anti-flutter buffer\nTUNED, not big: ~250 cm3\n1.5x volume KILLED the source",
       "#eaf3fb", BLUE)
blockc(36.5, 33, 16, 12, "LARYNX", "cast M5 folds + ONE servo\nthat tensions them = pitch\nmeasured 226.6 Hz at 1.59 kPa",
       "#fff2e2", WARM)
blockc(55.5, 33, 20, 12, "THE TRACT", "soft tube + FIVE pinch stations\nadult 180x36; child ~116 is OPEN\nVOWELS ONLY until a tongue exists",
       "#fff2e2", WARM)
blockc(78.5, 33, 14, 12, "LIPS", "the open end\nradiates the sound",
       "#fff2e2", WARM)

for x1, x2 in ((19.0, 20.5), (33.5, 36.5), (52.5, 55.5), (75.5, 78.5)):
    arrow(x1, 39, x2, 39)

ax.text(50, 53.2, "THE BODY  —  air becomes sound", ha="center", fontsize=13,
        weight="bold", color=INK)
ax.text(50, 50.4, "PA12-CF scaffold holds all of it rigid, so the servos move the tube and not the frame",
        ha="center", fontsize=9.6, color=GREY, style="italic")

# ---------------- the ear and the loop ----------------
blockc(78.5, 15, 14, 11, "MICROPHONE", "an ordinary mic\nERAN hears\nHIMSELF", "#eaf7ee", GREEN)
blockc(52, 15, 21, 11, "THE JUDGE", "ERAN's FROZEN COCHLEA\nthe same ear that already\nfound /ah/ in the digital tract",
       "#eaf7ee", GREEN)
blockc(24, 15, 22, 11, "THE LEARNER", "babble -> listen -> map\nmotor space to sound space\n-> climb toward the target",
       "#eaf7ee", GREEN)

arrow(85.5, 33, 85.5, 26, GREEN)
arrow(78.5, 20.5, 73, 20.5, GREEN)
arrow(52, 20.5, 46, 20.5, GREEN)
# the learner commands the servos back up
arrow(35, 26, 45, 33, GREEN, rad=-0.25)
ax.text(33.0, 28.6, "6 servo commands", fontsize=8.8, color=GREEN, weight="bold", rotation=30)

# ---------------- the teacher ----------------
blockc(2, 15, 18, 11, "SPEAKER", "plays a HUMAN voice\nbeside the mic\n= the target to copy",
       "#fdf0f0", "#b0322a")
arrow(20, 20.5, 24, 20.5, "#b0322a", ls="--")
ax.add_patch(FancyArrowPatch((11, 26.4), (11, 31.6), arrowstyle="-|>", mutation_scale=17,
                             lw=2.0, color="#b0322a", linestyle="--"))
ax.text(12.2, 28.6, "same room, same air", fontsize=8.0, color="#b0322a", rotation=90, va="center")

ax.text(62, 30.6, "THE LOOP  —  he hears himself, compares to the human, and moves",
        ha="center", fontsize=12.5, weight="bold", color=GREEN)

# ---------------- the number that makes it plausible ----------------
ax.add_patch(FancyBboxPatch((2, 2.5), 90, 9.2, boxstyle="round,pad=0.6,rounding_size=1.4",
                            fc="#fffaef", ec="#d9a021", lw=2.4))
ax.text(4.5, 9.1, "WHY THIS IS NOT A FANTASY:", fontsize=11.5, weight="bold", color="#8a5a10")
ax.text(4.5, 6.4, "Sawada organised his ENTIRE motor-to-vowel map from 150 random articulations - motor babbling. "
                  "That is an afternoon for a physical\nthroat, not a corpus. And ERAN's cochlea already found /ah/ "
                  "on the digital tract, so the judge is not new code - it exists and it works.",
        fontsize=10.2, color="#5c4410", va="center", linespacing=1.6)

ax.text(50, 0.6, "ERAN'S FULL SILICONE THROAT  ·  the closed training loop  ·  numbers from "
                 "alma-larynx/sawada-talking-robot/BUILD-NOTES.md  ·  2026-08-29",
        ha="center", fontsize=8.8, color=GREY)

plt.tight_layout()
out = r"D:\CLAUDE\alma-larynx\FULL-THROAT\THE-LOOP.png"
plt.savefig(out, dpi=130, facecolor="white")
print("wrote", out)
