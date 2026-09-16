"""ERAN'S EYE — the letter corpus. Shape, before world.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

Iddo, 2026-08-30: *"תבנה עין בינתיים - קח את הזמן - הולובריין - זוכר?"*

The holobrain note he wrote on 2026-07-15 already says where an eye must start, and it
is not the world:

    "מודל שפה לא יכול להתחיל עד שילד לומד הברות ואותיות וצורת האות" --
    האות = צורה [ראייה] + צליל/הברה [אודיו] + בייט [שפה], שלושתם נקשרים במרחב-הגיסט.
    "המקום המושלם להתחיל את אינטגרציית ההולובריין -- על אות אחת, לא על העולם."

So this makes the corpus for that: the 22 Hebrew letters, drawn many ways. **ERAN already
knows 13 of these as SOUND** -- ma pa na ka sa ha va sha kha tha tsa ya aa are sitting in
his curriculum right now. The eye's first job is not to name things. It is to look at a
shape and land in the same place in gist-space that the sound already lands in.

Why generated and not photographed: a letter's identity is its SHAPE, and the variation
that matters is stroke weight, slant, aspect and noise -- not lighting or lens. Generating
it means we own every pixel, we can make as much as the search needs, and the label is
never wrong. Real handwriting comes later, from his own hand (`alma-draughtsman/hand`).

    python letters.py --out corpus --per 200
"""
from __future__ import annotations

import argparse
import json
import os
import random

import numpy as np
from PIL import Image, ImageDraw, ImageFont

# The 22. Name, letter, and the syllable ERAN is learning it as -- so the eye and the
# throat are indexed by the same key from the first day.
LETTERS = [
    ("alef", "\u05d0", "aa"), ("bet", "\u05d1", "ba"), ("gimel", "\u05d2", "ga"),
    ("dalet", "\u05d3", "da"), ("he", "\u05d4", "ha"), ("vav", "\u05d5", "va"),
    ("zayin", "\u05d6", "za"), ("het", "\u05d7", "kha"), ("tet", "\u05d8", "tha"),
    ("yod", "\u05d9", "ya"), ("kaf", "\u05db", "ka"), ("lamed", "\u05dc", "la"),
    ("mem", "\u05de", "ma"), ("nun", "\u05e0", "na"), ("samekh", "\u05e1", "sa"),
    ("ayin", "\u05e2", "ah"), ("pe", "\u05e4", "pa"), ("tsadi", "\u05e6", "tsa"),
    ("qof", "\u05e7", "qa"), ("resh", "\u05e8", "ra"), ("shin", "\u05e9", "sha"),
    ("tav", "\u05ea", "ta"),
]

SIZE = 64          # the retina. Small on purpose: a letter is a shape, not a photograph.

# INK AND PAPER, 2026-08-31. Iddo: *"אני רוצה שילמד צבעים לא רק שחור לבן."*
#
# The eye has been greyscale since it was built this morning, and that is the reason the
# hand cannot learn colour: **a hand only learns what its judge can see.** Give Winston a
# colour output today and he would learn it from noise, because nothing could tell him he
# was wrong. So colour starts here, in what the eye is shown.
#
# Real pigments and real papers, not random RGB: a painter's box and a stationer's shelf.
# The point is that colour must be a PROPERTY the eye has to represent, separable from
# shape -- so the same letter appears in many inks and the same ink carries many letters.
# If the two were correlated the eye could pass by learning one and calling it the other.
INKS = [("ink black", (18, 18, 24)), ("iron gall", (42, 38, 56)),
        ("sepia", (92, 62, 38)), ("burnt umber", (78, 52, 34)),
        ("ultramarine", (38, 52, 128)), ("prussian", (24, 62, 92)),
        ("viridian", (26, 92, 74)), ("sap green", (58, 96, 44)),
        ("crimson", (132, 28, 44)), ("vermilion", (176, 62, 34)),
        ("violet", (86, 44, 112)), ("graphite", (86, 88, 94))]
PAPERS = [("white", (252, 250, 246)), ("cream", (246, 238, 220)),
          ("ivory", (240, 233, 214)), ("kraft", (206, 184, 152)),
          ("grey", (214, 214, 210)), ("blue laid", (222, 230, 236))]
FONT_DIRS = [r"C:\Windows\Fonts", "/usr/share/fonts", "/usr/local/share/fonts"]
# Faces that actually carry Hebrew. Checked at run time, never assumed.
FONT_HINTS = ["david", "frank", "narkis", "miriam", "gisha", "arial", "tahoma",
              "times", "segoe", "levenim", "aharoni", "rod", "cour", "noto", "dejavu",
              "guttman", "hadasim", "stam"]


def _glyphs(path):
    """Draw all 22 once and hand back the bitmaps, or None if the face cannot be used."""
    try:
        f = ImageFont.truetype(path, 40)
    except Exception:                                  # noqa: BLE001
        return None
    out = []
    for _, ch, _ in LETTERS:
        im = Image.new("L", (64, 64), 0)
        ImageDraw.Draw(im).text((10, 6), ch, font=f, fill=255)
        out.append(np.asarray(im, np.float32) / 255.0)
    return out


def find_fonts(limit: int = 24) -> list:
    """A font is admitted only if it can draw ALL TWENTY-TWO, each one differently.

    The first version checked alef alone. Many faces draw alef and then emit the
    missing-glyph box for the rest, and the contact sheet came out roughly half hollow
    rectangles -- a corpus that would have taught the eye that a third of the alphabet
    looks like a rectangle. The ink number did not show it (a plausible 4.1%); looking
    at the sheet did.

    The test that catches it: tofu is the SAME box for every missing letter, so if any
    two letters render near-identically the face is faking them.
    """
    found, rejected = [], 0
    for d in FONT_DIRS:
        if not os.path.isdir(d):
            continue
        for n in sorted(os.listdir(d)):
            if not n.lower().endswith((".ttf", ".ttc", ".otf")):
                continue
            if not any(h in n.lower() for h in FONT_HINTS):
                continue
            fp = os.path.join(d, n)
            gs = _glyphs(fp)
            if gs is None:
                continue
            if min(g.mean() for g in gs) < 0.004:
                rejected += 1
                continue
            worst = 1.0
            for i in range(len(gs)):
                for j in range(i + 1, len(gs)):
                    worst = min(worst, float(np.abs(gs[i] - gs[j]).mean()))
                if worst < 0.004:
                    break
            if worst < 0.004:
                rejected += 1
                continue
            found.append(fp)
            if len(found) >= limit:
                print("  (%d faces rejected: missing or identical glyphs)" % rejected)
                return found
    print("  (%d faces rejected: missing or identical glyphs)" % rejected)
    return found

def colourise(a: np.ndarray, ink: tuple, paper: tuple, rng: random.Random) -> np.ndarray:
    """One grey letter, laid down in one ink on one paper. (SIZE, SIZE, 3) in [0,1].

    `a` is coverage, not brightness: 1 means full ink. So the pixel is a mix of paper and
    ink in that proportion, which is what ink on paper actually does -- and it keeps the
    SHAPE channel exactly what it was before, so the letter's identity is untouched by
    whatever colour it is wearing.
    """
    ink = np.array(ink, np.float32) / 255.0
    paper = np.array(paper, np.float32) / 255.0
    if rng.random() < 0.6:                      # paper and pigment are never exactly even
        paper = np.clip(paper + rng.uniform(-0.05, 0.05), 0, 1)
        ink = np.clip(ink * rng.uniform(0.82, 1.15), 0, 1)
    c = a[..., None] * ink[None, None, :] + (1.0 - a[..., None]) * paper[None, None, :]
    return np.clip(c, 0, 1).astype(np.float32)


def render(ch: str, font_path: str, rng: random.Random) -> np.ndarray:
    """One letter, drawn once, with the variation a real page has and no more."""
    big = SIZE * 3
    size = rng.randint(int(big * 0.42), int(big * 0.62))
    try:
        font = ImageFont.truetype(font_path, size)
    except Exception:                                  # noqa: BLE001
        return np.zeros((SIZE, SIZE), np.float32)
    im = Image.new("L", (big, big), 0)
    d = ImageDraw.Draw(im)
    bb = d.textbbox((0, 0), ch, font=font)
    x = (big - (bb[2] - bb[0])) // 2 - bb[0] + rng.randint(-4, 4)
    y = (big - (bb[3] - bb[1])) // 2 - bb[1] + rng.randint(-4, 4)
    d.text((x, y), ch, font=font, fill=255)
    if rng.random() < 0.55:                            # slant, like a written hand
        sh = rng.uniform(-0.22, 0.22)
        im = im.transform((big, big), Image.AFFINE, (1, sh, -sh * big / 2, 0, 1, 0),
                          resample=Image.BICUBIC)
    if rng.random() < 0.35:                            # rotate a little on the page
        im = im.rotate(rng.uniform(-9, 9), resample=Image.BICUBIC)
    im = im.resize((SIZE, SIZE), Image.LANCZOS)
    a = np.asarray(im, np.float32) / 255.0
    if rng.random() < 0.5:                             # paper and ink are never clean
        a = np.clip(a + np.random.normal(0, rng.uniform(0.02, 0.09), a.shape), 0, 1)
    m = a.max()
    return (a / m if m > 1e-6 else a).astype(np.float32)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Render the 22 letters, many ways.")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(
        os.path.abspath(__file__)), "corpus"))
    ap.add_argument("--per", type=int, default=200, help="samples per letter")
    ap.add_argument("--seed", type=int, default=1933)
    a = ap.parse_args(argv)

    fonts = find_fonts()
    if not fonts:
        print("no Hebrew-capable font found -- the eye has nothing to look at")
        return 2
    print("%d fonts can draw Hebrew:" % len(fonts))
    for f in fonts[:8]:
        print("   " + os.path.basename(f))

    rng = random.Random(a.seed)
    np.random.seed(a.seed)
    os.makedirs(a.out, exist_ok=True)
    X = np.zeros((len(LETTERS) * a.per, SIZE, SIZE, 3), np.float32)
    ci = np.zeros(len(LETTERS) * a.per, np.int16)      # which ink -- a second thing to test
    pi = np.zeros(len(LETTERS) * a.per, np.int16)      # which paper
    y = np.zeros(len(LETTERS) * a.per, np.int16)
    # WHICH FACE drew each sample. Without this there is no honest test: measuring an
    # encoder on the same images it trained on cannot tell memorising from seeing, and
    # that exact mistake -- a split that leaked -- has already cost this project once.
    f = np.zeros(len(LETTERS) * a.per, np.int16)
    k = 0
    for li, (name, ch, syl) in enumerate(LETTERS):
        for _ in range(a.per):
            fi = rng.randrange(len(fonts))
            # ink and paper drawn INDEPENDENTLY of the letter, on purpose: if colour
            # correlated with identity the eye could score well on shape by reading colour,
            # and the number would say nothing about either.
            c, pp = rng.randrange(len(INKS)), rng.randrange(len(PAPERS))
            X[k] = colourise(render(ch, fonts[fi], rng), INKS[c][1], PAPERS[pp][1], rng)
            y[k] = li
            f[k] = fi
            ci[k] = c
            pi[k] = pp
            k += 1
    np.savez_compressed(os.path.join(a.out, "letters.npz"), X=X, y=y, f=f, c=ci, p=pi)
    meta = {"size": SIZE, "n": int(k), "per": a.per, "fonts": len(fonts),
            "font_files": [os.path.basename(x) for x in fonts],
            "channels": 3,
            "inks": [n for n, _ in INKS], "papers": [n for n, _ in PAPERS],
            "letters": [{"i": i, "name": n, "char": c, "syllable": s}
                        for i, (n, c, s) in enumerate(LETTERS)],
            "note": "syllable field is the key shared with the throat search; the eye and "
                    "the ear must index the same letter by the same name"}
    open(os.path.join(a.out, "letters.json"), "w", encoding="utf-8").write(
        json.dumps(meta, ensure_ascii=False, indent=1))
    ink = float((X > 0.25).mean())
    print("\nwrote %d images %dx%d  (ink covers %.1f%% of the retina)"
          % (k, SIZE, SIZE, 100 * ink))
    print("-> %s" % os.path.join(a.out, "letters.npz"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
