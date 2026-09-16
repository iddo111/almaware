#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""QUORUM handout - one page any AI can be pointed at. JPEG + PDF to Desktop."""
import os
import sys
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, r"D:\CLAUDE\RAMCHAT")
from make_handout import bidi          # reuse the bidi pass, do not rewrite it

OUT = os.path.dirname(os.path.abspath(__file__))
DESK = r"C:\Users\<user>\Desktop"
F = {"blk": "C:/Windows/Fonts/ariblk.ttf",
     "bd": "C:/Windows/Fonts/arialbd.ttf",
     "mono": "C:/Windows/Fonts/consolab.ttf"}

PAPER = (252, 251, 246)
INK = (18, 20, 24)
TEAL = (15, 118, 110)
WARM = (156, 52, 18)
MUTE = (132, 138, 145)
BOX = (238, 242, 241)
GOLD = (146, 64, 14)


def f(k, px):
    return ImageFont.truetype(F[k], int(px))


def _is_rtl(ch):
    return "֐" <= ch <= "׿"


def heb(s):
    """For a mostly-ENGLISH line with Hebrew words inside.

    bidi() reverses the whole string, which is right for a Hebrew line but
    scrambles an English one. Here we keep LTR order and reverse only the
    Hebrew runs in place, so "not a דעה" renders correctly instead of "העד".
    """
    out = list(s)
    i = 0
    while i < len(out):
        if not _is_rtl(out[i]):
            i += 1
            continue
        j = i
        while j < len(out) and (_is_rtl(out[j]) or (out[j] in " ׳״\"'" and
                                                    j + 1 < len(out) and _is_rtl(out[j + 1]))):
            j += 1
        out[i:j] = list(reversed(out[i:j]))
        i = j
    return "".join(out)


W, H = 1500, 2100
img = Image.new("RGB", (W, H), PAPER)
d = ImageDraw.Draw(img)
M = 78
y = 54

d.text((M, y), "QUORUM", font=f("blk", 76), fill=TEAL); y += 82
d.text((M, y), "the Talmudic debate  ·  how any AI joins the argument",
       font=f("bd", 27), fill=INK); y += 38
d.text((M, y), bidi("שקלא וטריא — לזכרה של עלמה ז״ל"),
       font=f("bd", 25), fill=MUTE); y += 52
d.line([M, y, W - M, y], fill=(226, 224, 216), width=3); y += 42


def h(t, sub=""):
    global y
    d.text((M, y), t, font=f("blk", 33), fill=TEAL); y += 42
    if sub:
        d.text((M, y), sub, font=f("bd", 23), fill=MUTE); y += 34
    y += 6


def code(lines, mono=True, pad=20):
    global y
    bh = len(lines) * 36 + pad * 2
    d.rounded_rectangle([M, y, W - M, y + bh], radius=12, fill=BOX)
    yy = y + pad
    for ln in lines:
        # Consolas has no Hebrew glyphs - any line containing Hebrew must use
        # Arial Bold or it prints as empty boxes.
        use_mono = mono and not any(_is_rtl(c) for c in ln)
        d.text((M + 24, yy), heb(ln), font=f("mono" if use_mono else "bd", 24),
               fill=INK)
        yy += 36
    y += bh + 26


def body(lines, color=INK, size=25):
    global y
    for ln in lines:
        d.text((M, y), heb(ln), font=f("bd", size), fill=color); y += 34
    y += 14


h("THE FORM", "every speaker answers ONE named opponent - never a monologue")
code([
    "Round 0      \u05e2\u05de\u05d3\u05d5\u05ea       state one clear, CONTESTABLE claim",
    "Round 1..N   \u05e9\u05e7\u05dc\u05d0 \u05d5\u05d8\u05e8\u05d9\u05d0  facing a named opponent:",
    "               \u05e7\u05d5\u05e9\u05d9\u05d0    attack their weakest point",
    "               \u05ea\u05d9\u05e8\u05d5\u05e5    defend your own",
    "               \u05e8\u05d0\u05d9\u05d4     ONE strong proof",
    "               \u05d3\u05d7\u05d9\u05d9\u05d4     reject them - or CONCEDE",
    "Closing      \u05de\u05e1\u05e7\u05e0\u05d4      where all agree, where the",
    "                          \u05de\u05d7\u05dc\u05d5\u05e7\u05ea stands, who is strongest",
])
d.text((M, y - 12), "Conceding is a win condition, not a loss.",
       font=f("blk", 24), fill=GOLD); y += 34

h("HOW YOU JOIN", "QUORUM calls YOU - be on PATH and honour the argv contract")
code([
    "claude   claude -p --output-format text          prompt on STDIN",
    "grok     grok --output-format plain ... -p <p>   prompt in argv",
    "gemini   gemini --output-format text ... -p <p>  prompt in argv",
    "alma:*   Alma Harness route                      HTTP",
    "ollama   any installed local model               :11434",
])
body([
    "Presence on PATH is DISCOVERY ONLY. You are admitted to the debate",
    "only after a real, non-empty first turn. Installed is not participant.",
], MUTE)

h("RUN IT")
code([
    "cd D:\\CLAUDE\\quorum",
    ".\\run-quorum.ps1            # inert - detection only",
    ".\\run-quorum.ps1 -Enable    # live - reaches your CLIs",
    "                            # then http://127.0.0.1:8099",
])

h("BORN INERT - ON PURPOSE")
body([
    "config.ENABLED = False by default. The server boots and shows status,",
    "but /debate refuses to reach any model until you turn it on. That is a",
    "safety default, not a bug. Do not 'fix' it.",
], MUTE)

h("WHAT MAKES A GOOD TURN")
body([
    "Be contestable - a claim nobody can attack is a platitude, not a \u05d3\u05e2\u05d4.",
    "Name your opponent. \"Claude argues X\", never \"some might say\".",
    "One proof - your strongest. Not five weak ones.",
    "Say where you are wrong, explicitly. That is what \u05d3\u05d7\u05d9\u05d9\u05d4 is for.",
    "Do not hedge into agreement. The visible \u05de\u05d7\u05dc\u05d5\u05e7\u05ea is the whole value.",
])

y = H - 150
d.line([M, y, W - M, y], fill=(226, 224, 216), width=3); y += 22
d.text((M, y), "Coordinate first through RAMLINK - claim before you wire a provider.",
       font=f("bd", 23), fill=MUTE); y += 36
d.text((M, y), "ALMAWARE  ·  iddoperez.ai  ·  stdlib only - no Flask, no framework, no CDN",
       font=f("blk", 24), fill=INK)

img.save(os.path.join(OUT, "QUORUM-handout.png"))
img.convert("RGB").save(os.path.join(DESK, "QUORUM-handout.jpg"), "JPEG",
                        quality=95, optimize=True)
img.convert("RGB").save(os.path.join(DESK, "QUORUM-handout.pdf"), "PDF",
                        resolution=150.0)
print("handout: Desktop QUORUM-handout .jpg + .pdf   %dx%d" % img.size)
