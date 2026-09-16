"""Render what the hand drew FROM A SOUND, beside the letter it was supposed to be.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

On 2026-08-30 a hand scored 86% while drawing dot-clouds no person would call a letter,
and the number said nothing about it. So the sheet gets looked at, every time.

The reference glyph is looked up from `want`, never from the row index: row i of the
drawings is SYLLABLE i, and the letters are in a different order. The first version of
this file put letter i beside syllable i and produced a sheet where alef happened to line
up and the other twenty-one did not.

## 2026-09-06, code revision — the sheet was drawn against the WRONG corpus

ZIV-06. This file re-read the LIVE corpus for the reference glyph even though the run had
already stored its own: `sound-drawings.npz` carries `ref` (22,64,64), and it was unused.
So the picture was drawn against whatever `letters.npz` happens to be on disk today, not
against the corpus the run used — and today that corpus is COLOUR, so it died with
`ValueError: Too many dimensions: 3 > 2`. Even before the colour change, a corpus
regeneration would have put a different glyph beside each drawing without a word: exactly
the failure the paragraph above says this file exists to prevent.

The run's own `ref` is used when the npz has it. The corpus is a fallback, it says so out
loud, and it refuses rather than rendering a lie when the font count no longer matches.

    python show_sound_drawings.py state/sound-drawings.npz sheet.png
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.join(HERE, "..", "eye", "corpus")
CELL, PAD, COLS = 64, 6, 6


def _gray(a):
    """One channel to paste. A colour glyph is averaged to luminance for the sheet.

    Image.fromarray(x, "L") on a (64,64,3) array raises "Too many dimensions: 3 > 2",
    which is how this file died on the colour corpus.
    """
    a = np.asarray(a, dtype=np.float32)
    if a.ndim == 3:
        a = a.mean(-1)
    return a


def main(src, dst, corpus=CORPUS, holdout_fonts=6):
    d = np.load(src, allow_pickle=True)
    drawn, read, want = d["drawn"], d["read"], d["want"]
    meta = json.load(open(os.path.join(corpus, "letters.json"),
                          encoding="utf-8"))["letters"]
    syl = [m["syllable"] for m in meta]

    # ZIV-06: the run's OWN reference glyphs first. Falling back to the live corpus means
    # drawing today's letters beside a run from another day, and saying so is the least
    # this file owes the sheet.
    ref_run = d["ref"] if "ref" in d.files else None
    if ref_run is not None and len(ref_run) == len(drawn):
        src_note = "the run's own stored reference glyphs (%s['ref'])" % os.path.basename(src)
        refs = [ref_run[i] for i in range(len(drawn))]
    else:
        L = np.load(os.path.join(corpus, "letters.npz"))
        X, ly, lf = L["X"], L["y"], L["f"]
        n_fonts = int(lf.max()) + 1
        if n_fonts <= holdout_fonts:
            raise SystemExit(
                "REFUSING to render: the corpus at %s has %d typefaces and this sheet "
                "claims %d were held out. The corpus is not the one the run used, and a "
                "sheet drawn from it would be a lie." % (corpus, n_fonts, holdout_fonts))
        te = lf >= (n_fonts - holdout_fonts)      # a typeface the eye never trained on
        src_note = ("THE LIVE CORPUS at %s (the npz carries no 'ref' -- this sheet may "
                    "not show the glyphs the run saw)" % corpus)
        refs = [X[(ly == int(want[i])) & te][0] for i in range(len(drawn))]
    print("reference glyphs from: %s" % src_note)

    n = len(drawn)
    rows = (n + COLS - 1) // COLS
    cw, ch = CELL * 2 + PAD * 3, CELL + PAD * 2 + 14
    img = Image.new("RGB", (cw * COLS, ch * rows), "white")
    dr = ImageDraw.Draw(img)
    for i in range(n):
        r, c = divmod(i, COLS)
        x0, y0 = c * cw, r * ch
        for k, arr in enumerate((refs[i], drawn[i])):
            a = (255 * (1.0 - np.clip(_gray(arr), 0, 1))).astype(np.uint8)
            img.paste(Image.fromarray(a, "L").convert("RGB"),
                      (x0 + PAD + k * (CELL + PAD), y0 + PAD))
        ok = bool(read[i] == want[i])
        dr.text((x0 + PAD, y0 + CELL + PAD + 1),
                "heard %s  %s" % (syl[int(want[i])],
                                  "OK" if ok else "eye read " + syl[int(read[i])]),
                fill=(0, 130, 0) if ok else (190, 0, 0))
        dr.rectangle([x0 + 1, y0 + 1, x0 + cw - 2, y0 + ch - 2], outline=(220, 220, 220))
    img = img.resize((img.width * 2, img.height * 2), Image.NEAREST)
    img.save(dst)
    print("%s  %d drawings, the eye read %d of them as the right letter"
          % (dst, n, int((read == want).sum())))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "sheet.png")
