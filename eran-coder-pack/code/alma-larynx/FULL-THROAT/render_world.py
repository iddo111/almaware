# -*- coding: utf-8 -*-
"""WHO IN THE WORLD is building a talking mouth - and what nobody has built.

Synthesis of three independent country sweeps run 2026-08-30 (Germany, Japan,
USA/Canada). The three items marked TRIPLE-CONFIRMED came back independently
from all three sweeps.
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

INK, GREY, RED, GOLD, GREEN = ("#12233a", "#7d8fa3", "#b0322a", "#a97612", "#1a7f45")

ROW = 6.4          # vertical space per lab entry
LINE = 1.62        # body line height

fig, ax = plt.subplots(figsize=(17.4, 16.8), facecolor="white")
ax.set_xlim(0, 100)
ax.axis("off")

ax.text(50, 97.0, "WHO IN THE WORLD IS BUILDING A TALKING MOUTH",
        ha="center", fontsize=24, weight="bold", color=INK)
ax.text(50, 93.9, "three independent country sweeps, 2026-08-30   \u00b7   "
                  "and the three things nobody anywhere has built",
        ha="center", fontsize=12, color=GREY, style="italic")

LABS = [
    ("ALIVE, AND CLOSEST TO ERAN", GREEN, "#eef7ed", [
        ("JP", "Nobutsuna Endo \u2014 Tokyo Denki University", [
            "Lingua-R: a mechanical speech robot built on the anatomy of a SIX-MONTH-OLD INFANT, 7-DOF tongue.",
            "ZETS: a soft pneumatic tongue. The grant runs to MARCH 2029 and explicitly includes feedback of",
            "deformation + breath pressure + flow + phonation acoustics. That is ERAN's loop, funded, in Japan."]),
        ("JP", "Atsushi Nakamura's lab — Shizuoka University", [
            "An ACTIVE 2024-2026 mechanical talking robot that nobody in the field would find: exhalation-driven,",
            "mechanical vocal folds, a tongue mechanism, oral AND nasal cavity control, formant control. Won a",
            "best-paper award. It hides inside an ELECTRON-DEVICES conference, invisible to every speech and",
            "robotics search path - a student team, publishing in Japanese only."]),
        ("JP", "Isao Tokuda — Ritsumeikan University", [
            "The largest physical-larynx program in Japan: six or seven physical-model papers per meeting,",
            "sustained. Silicone folds, false folds, air sacs, a micro-CT macaque larynx, a zebra finch syrinx."]),
        ("JP", "Tsukasa Yoshinaga   ⚠ affiliation disputed", [
            "Mechanical CONSONANTS, 2025: a movable tongue + reed larynx, an electromagnet gating voicing. Got",
            "/su/ and /zu/ apart, and the contrast turned out to be 20-60% TEMPORAL OVERLAP of hiss and voice.",
            "MY TWO JAPAN SWEEPS DISAGREE - one places him at Osaka, the other at Toyohashi and calls his recent",
            "work mostly CFD. The consonant result carries a DOI; the affiliation does not. Left unresolved."]),
        ("JP", "Takayuki Arai \u2014 Sophia University", [
            "The most productive physical-tract lab on earth, and accelerating. May 2026: a tract actuated by a",
            "ROBOTIC ARM \u2014 6 blocks x 4 settings = 4096 configurations, covering most of the human vowel space."]),
        ("DE", "Peter Birkholz \u2014 TU Dresden", [
            "A 'mechatronic vocal tract', funded since 2025, built expressly for CONSONANTS: plosive release and",
            "voiced fricatives. NOT PUBLISHED YET. Their dataset is already on our disk, CC BY 4.0."]),
        ("UK", "Ian Howard \u2014 University of Plymouth", [
            "The one working actuated tract: a 2-D tongue, lips AND a nasal cavity \u2014 vowels, nasals and fricatives.",
            "2026: a servo-driven artificial lung, accordion duct, ~2000 cm3 tidal volume."]),
    ]),
    ("DEAD OR DORMANT \u2014 and our own notes were built on these", RED, "#fdeceb", [
        ("JP", "Waseda Talker (Takanishi) \u2014 WT-1 \u2192 WT-7RII", [
            "DEAD. Last hardware 2009, last paper about 2012. The lab page still ends at WT-7RII."]),
        ("JP", "Hideyuki Sawada \u2014 the talking robot", [
            "DORMANT. Last voice paper 2020, grant ended 2019. Fifty-four papers since 2022, ZERO on voice \u2014",
            "he moved to drones and spherical robots. BUILD-NOTES.md rests almost entirely on this lab."]),
    ]),
]

y = 90.5
for title, ec, fc, rows in LABS:
    h = 3.4 + sum(2.0 + LINE * len(b) for _, _, b in rows)
    ax.add_patch(FancyBboxPatch((2, y - h), 96, h,
                                boxstyle="round,pad=0.4,rounding_size=0.9",
                                fc=fc, ec=ec, lw=2.2))
    ax.text(4.6, y - 2.1, title, fontsize=14, weight="bold", color=ec, va="center")
    ry = y - 4.6
    for flag, name, body in rows:
        ax.text(4.6, ry, "[%s]" % flag, fontsize=10.5, weight="bold", color=ec, va="center")
        ax.text(9.8, ry, name, fontsize=12.5, weight="bold", color=INK, va="center")
        for k, line in enumerate(body):
            ax.text(9.8, ry - 1.5 - k * LINE, line, fontsize=10.2,
                    color="#3d5771", va="top")
        ry -= 2.0 + LINE * len(body)
    y -= h + 1.6

# ---------------- three things nobody has built ----------------
BH = 17.0
ax.add_patch(FancyBboxPatch((2, y - BH), 96, BH,
                            boxstyle="round,pad=0.4,rounding_size=0.9",
                            fc="#fffaef", ec=GOLD, lw=3.0))
ax.text(50, y - 2.4, "THREE THINGS NOBODY ON EARTH HAS BUILT",
        ha="center", fontsize=17, weight="bold", color="#8a5a10")
cols = [
    (18.5, "\u05d7   \u05e2", "PHARYNGEALS",
     ["no machine anywhere has an actuator", "that narrows the pharynx. Japanese,",
      "German and English have none at all.", "TRIPLE-CONFIRMED"]),
    (50.0, "\u05e5", "AFFRICATES",
     ["zero papers on a physical or mechanical", "affricate model since 2015. The",
      "closure-then-hiss transition has never", "been built into hardware."]),
    (81.5, "\u21ba", "THE CLOSED LOOP",
     ["nobody has run an acoustic learning loop", "on real vocal hardware since 2018.",
      "Sawada's is the last \u2014 four citations,", "all his own. The thread is dead."]),
]
for cx, glyph, head, body in cols:
    ax.text(cx, y - 6.4, glyph, ha="center", va="center",
            fontsize=27, weight="bold", color="#8a5a10")
    ax.text(cx, y - 9.6, head, ha="center", va="center",
            fontsize=13, weight="bold", color="#8a5a10")
    for k, line in enumerate(body):
        ax.text(cx, y - 11.2 - k * 1.35, line, ha="center", va="top",
                fontsize=9.8, color="#5c4410")

# ---------------- the warning ----------------
y3 = y - BH - 1.6
WH = 9.4
ax.add_patch(FancyBboxPatch((2, y3 - WH), 96, WH,
                            boxstyle="round,pad=0.4,rounding_size=0.9",
                            fc="#fdeceb", ec=RED, lw=2.6))
ax.text(4.8, y3 - 2.2, "\u26a0   THE WARNING THAT HITS YOUR LOOP DIRECTLY",
        fontsize=14, weight="bold", color=RED, va="center")
warn = [
    "Waseda needed TACTILE sensors and an intraoral PRESSURE sensor on the palate to learn obstruents, because auditory feedback",
    "alone was insufficient for /t/ and /d/. Sawada needed VISUAL feedback plus a cerebellar spiking network just to time plosive release.",
    "A microphone alone will teach ERAN vowels and pitch. It will NOT teach him the eight plosive letters.  He will need TOUCH.",
]
for k, line in enumerate(warn):
    ax.text(4.8, y3 - 4.2 - k * 1.75, line, fontsize=10.6,
            color="#7a2b24", va="top")

ax.set_ylim(y3 - WH - 2.0, 100)
plt.tight_layout()
out = r"D:\CLAUDE\alma-larynx\FULL-THROAT\WORLD-MAP.png"
plt.savefig(out, dpi=120, facecolor="white")
print("wrote", out)
