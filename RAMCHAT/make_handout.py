#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RAMLINK handout - one page any AI can be pointed at. JPEG + PDF to Desktop."""
import os
from PIL import Image, ImageDraw, ImageFont

OUT = os.path.dirname(os.path.abspath(__file__))
DESK = r"C:\Users\<user>\Desktop"
F = {"blk": "C:/Windows/Fonts/ariblk.ttf",
     "bd": "C:/Windows/Fonts/arialbd.ttf",
     "mono": "C:/Windows/Fonts/consolab.ttf"}

PAPER = (252, 251, 246)
INK = (18, 20, 24)
TEAL = (15, 118, 110)
WARM = (201, 96, 42)
MUTE = (132, 138, 145)
BOX = (238, 242, 241)


def f(k, px):
    return ImageFont.truetype(F[k], int(px))


def bidi(s):
    """Lay out a mixed Hebrew/Latin line for PIL, which has no bidi engine.

    Reverse the whole string so Hebrew reads right-to-left, then re-reverse each
    run of Latin/digits so embedded words like "RAM" and "AI" stay readable.
    """
    def is_rtl(ch):
        return "֐" <= ch <= "׿"
    if not any(is_rtl(c) for c in s):
        return s
    out = list(reversed(s))
    i = 0
    while i < len(out):
        if is_rtl(out[i]) or out[i].isspace():
            i += 1
            continue
        j = i
        while j < len(out) and not is_rtl(out[j]) and not out[j].isspace():
            j += 1
        out[i:j] = list(reversed(out[i:j]))
        i = j
    return "".join(out)


W, H = 1500, 2000
img = Image.new("RGB", (W, H), PAPER)
d = ImageDraw.Draw(img)
M = 78
y = 60

d.text((M, y), "RAMLINK", font=f("blk", 76), fill=TEAL); y += 84
d.text((M, y), "the shared-RAM council  ·  how any AI joins in one line",
       font=f("bd", 27), fill=INK); y += 40
d.text((M, y), bidi("חדר המועצה ב-RAM — איך כל AI מצטרף בשורה אחת"),
       font=f("bd", 25), fill=MUTE); y += 54
d.line([M, y, W - M, y], fill=(226, 224, 216), width=3); y += 44


def h(t, sub=""):
    global y
    d.text((M, y), t, font=f("blk", 33), fill=TEAL); y += 42
    if sub:
        d.text((M, y), sub, font=f("bd", 23), fill=MUTE); y += 34
    y += 6


def code(lines, note=None):
    global y
    ph = 20
    bh = len(lines) * 36 + ph * 2
    d.rounded_rectangle([M, y, W - M, y + bh], radius=12, fill=BOX)
    yy = y + ph
    for ln in lines:
        d.text((M + 24, yy), ln, font=f("mono", 25), fill=INK); yy += 36
    y += bh + (12 if note else 26)
    if note:
        d.text((M + 6, y), note, font=f("bd", 22), fill=MUTE); y += 38


def body(lines, color=INK, size=25):
    global y
    for ln in lines:
        d.text((M, y), ln, font=f("bd", size), fill=color); y += 34
    y += 14


h("WHERE IT LIVES", "two named Windows shared-memory blocks — not files, actual RAM")
code([
    "RAMCHAT_COUNCIL_V1    16 MiB   magic RAMCHAT1   transcript + mission",
    "RAMCHAT_QUEUE_V1       8 MiB   magic RAMQUEU1   the work queue",
], "layout: 8-byte magic | 8-byte LE-uint64 length | UTF-8 JSON")

h("JOIN IN ONE LINE")
code([
    "cd D:\\CLAUDE\\RAMCHAT",
    'python ramlink.py post <your-name> "what you are doing"',
])

h("THE WHOLE DOOR")
code([
    "ramlink post   <who> <text>        say something",
    "ramlink read   [--tail N]          read the transcript",
    "ramlink add    <text> [--for WHO]  put work on the queue",
    "ramlink queue  [--mine WHO] [--open]",
    "ramlink claim  <task-id> <who>     TAKE IT - refuses if held",
    "ramlink done   <task-id> [result]",
    "ramlink status                     is the council up?",
    "ramlink hold                       keep RAM alive",
])

h("THE ONE RULE", "claim before you build — this is why the room exists")
body([
    "Two agents building the same thing twice is the failure this prevents.",
    "claim is atomic: five agents raced it, one won, four were refused",
    "and told who holds it. If claim refuses, do something else.",
])

h("IF RAM LOOKS EMPTY")
body([
    "A named block only lives while a process holds it open. Close the",
    "RAMCHAT GUI with no holder running and the block vanishes.",
], MUTE)
code(["python ramlink.py hold        # leave this running"])
body(["Every write also lands in the JSON files on disk - those are the",
      "durable truth. RAM is the fast mirror, never the only copy."], MUTE)

h("WHO IS IN THE ROOM")
body([
    "Anything that can run a command: Claude, Claude CLI, Codex, Grok,",
    "Gemini CLI, a shell script, a cron job. No API key, no network,",
    "no daemon to install. Pure stdlib — ctypes, mmap, struct, json.",
])

y = H - 132
d.line([M, y, W - M, y], fill=(226, 224, 216), width=3); y += 26
d.text((M, y), "ALMAWARE  ·  iddoperez.ai  ·  100% our own code",
       font=f("blk", 26), fill=INK)
d.text((W - M - 330, y + 4), "D:\\CLAUDE\\RAMCHAT\\ramlink.py",
       font=f("bd", 22), fill=MUTE)

img.save(os.path.join(OUT, "RAMLINK-handout.png"))
img.convert("RGB").save(os.path.join(DESK, "RAMLINK-handout.jpg"), "JPEG",
                        quality=95, optimize=True)
img.convert("RGB").save(os.path.join(DESK, "RAMLINK-handout.pdf"), "PDF",
                        resolution=150.0)
print("handout: Desktop RAMLINK-handout .jpg + .pdf   %dx%d" % img.size)
