"""What ERAN's hand actually drew. Rendered so Iddo can look at it.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

A number saying the eye reads back 68% is a proxy. **The letters are the real output.**
This puts them on a page next to the printed forms so the comparison is visible, and
prints under each one what the eye actually called it — including where it was wrong.
A sheet that hides the misses would be a demo, not a result.

Iddo, 2026-08-30: *"תראה לי את הדף עם הכישלונות באדום."*

Three verdicts per letter, never merged into one flattering number:

    the EYE      ERAN's own encoder — the thing that was trained. Closed room.
    the OCR      tesseract heb, which has never seen ERAN. Examined on print first.
    a HUMAN      the only one that counts, and no program can supply it. The sheet
                 exists so a person can supply it.

    python show.py --hand state/winston.pt --out ERAN-letters.png
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile

import numpy as np
import torch
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "eye"))
sys.path.insert(0, os.path.join(HERE, "..", "..", "miko", "model"))

from hand_eye import Winston, ink, centroids, penmarks, load_eye   # noqa: E402

CELL, REF, PAD, TOP = 132, 46, 18, 150
GREEN, RED, GREY = (30, 140, 75), (200, 55, 55), (120, 120, 135)


def fonts():
    for d in (r"C:\Windows\Fonts", "/usr/share/fonts/truetype/dejavu"):
        try:
            return (ImageFont.truetype(os.path.join(d, "segoeui.ttf"), 30),
                    ImageFont.truetype(os.path.join(d, "segoeui.ttf"), 15),
                    ImageFont.truetype(os.path.join(d, "david.ttf"), 38))
        except Exception:                                        # noqa: BLE001
            continue
    try:
        p = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        return (ImageFont.truetype(p, 30), ImageFont.truetype(p, 15),
                ImageFont.truetype(p, 38))
    except Exception:                                            # noqa: BLE001
        d = ImageFont.load_default()
        return d, d, d


def ocr_read(drawn, cal, letters):
    """Ask the outside judge, using the settings it earned on PRINT. Never other settings."""
    if not shutil.which("tesseract") or not cal:
        return None
    from judge_ocr import render, read_one                        # noqa: E402
    tmp = tempfile.mkdtemp(prefix="ocrsheet")
    got = [read_one(render(drawn[i]), tmp, cal["psm"], "heb", cal["whitelist"])
           for i in range(len(letters))]
    shutil.rmtree(tmp, ignore_errors=True)
    return got


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Draw what the hand learned.")
    ap.add_argument("--hand", default=os.path.join(HERE, "state", "hand.pt"))
    ap.add_argument("--eye", default=os.path.join(HERE, "..", "eye", "state", "eye.pt"))
    ap.add_argument("--data", default=os.path.join(HERE, "..", "eye", "corpus",
                                                   "letters.npz"))
    ap.add_argument("--meta", default=os.path.join(HERE, "..", "eye", "corpus",
                                                   "letters.json"))
    ap.add_argument("--judge", default=os.path.join(HERE, "state", "ocr-judge.json"))
    ap.add_argument("--out", default=os.path.join(HERE, "ERAN-letters.png"))
    ap.add_argument("--title", default="")
    ap.add_argument("--device", default="cpu")
    a = ap.parse_args(argv)

    dev = torch.device(a.device)
    enc = load_eye(a.eye, dev)
    d = np.load(a.data)
    X, y = d["X"].astype(np.float32), d["y"]
    cent, cls = centroids(enc, X, y, dev)
    n = len(cls)
    letters = json.load(open(a.meta, encoding="utf-8"))["letters"]

    ck = torch.load(a.hand, map_location=dev)
    hand = Winston(n, ck.get("strokes", 3), ck.get("points", 6),
                   ck.get("pressure", False)).to(dev)
    hand.load_state_dict(ck["hand"])
    with torch.no_grad():
        xy, w = hand(torch.eye(n, device=dev))
        drawn = ink(xy, w)
        g = enc.gist(drawn)
        read = (g @ cent.T).argmax(1).tolist()
        cos = (g * cent).sum(-1).tolist()
        marks = penmarks(drawn, xy, w)
    drawn = drawn.cpu().numpy()

    cal = None
    if os.path.exists(a.judge):
        cal = json.load(open(a.judge, encoding="utf-8")).get("calibration")
    got = ocr_read(drawn, cal, letters)

    # one real printed glyph per letter, for the eye of the person looking
    ref = {c: X[np.where(y == c)[0][3]] for c in range(n)}

    cols = 6
    rows = (n + cols - 1) // cols
    W = max(cols * (CELL + REF + PAD) + PAD, 1240)
    H = TOP + rows * (CELL + PAD + 54) + PAD
    im = Image.new("RGB", (W, H), (255, 255, 255))
    dr = ImageDraw.Draw(im)
    big, sm, heb = fonts()

    hits = sum(1 for i, r in enumerate(read) if r == i)
    ohits = sum(1 for i, gg in enumerate(got or []) if gg == letters[i]["char"])
    pieces = float(np.mean([m["pieces"] for m in marks]))
    cover = float(np.mean([m["cover"] for m in marks]))

    dr.text((PAD, 14), a.title or "ERAN's hand — and two judges, one of them a stranger",
            font=big, fill=(20, 20, 30))
    dr.text((PAD, 52), "LEFT of each pair is what ERAN drew. RIGHT, small, is the printed "
                       "letter. RED BORDER = ERAN's own eye read it as a different letter.",
            font=sm, fill=(90, 90, 110))
    line = ("his EYE reads back %d of %d." % (hits, n))
    if got is not None and cal:
        line += ("   tesseract heb — which has never seen ERAN and scored %.0f%% on "
                 "PRINTED letters — reads %d of %d." % (100 * cal["printed_accuracy"],
                                                        ohits, n))
    dr.text((PAD, 74), line, font=sm, fill=(90, 90, 110))
    dr.text((PAD, 96), "pen: %d strokes x %d points%s.  %.2f connected pieces per letter "
                       "(a letter is 1-2, a dot-cloud is many).  ink %.3f vs 0.040 for "
                       "print." % (
                           ck.get("strokes", 3), ck.get("points", 6),
                           ", pressure varies the width" if ck.get("pressure") else
                           ", fixed nib", pieces, cover),
            font=sm, fill=(90, 90, 110))
    dr.text((PAD, 118), "The third judge is a HUMAN and is not on this sheet. Look at it "
                        "and count how many are letters. That number is the one that "
                        "matters.", font=sm, fill=(150, 90, 40))

    for i in range(n):
        r, c = divmod(i, cols)
        x = PAD + c * (CELL + REF + PAD)
        yy = TOP + r * (CELL + PAD + 54)
        tile = Image.fromarray((255 - (drawn[i] * 255).astype(np.uint8))).resize(
            (CELL, CELL), Image.LANCZOS)
        ok = read[i] == i
        dr.rectangle([x - 3, yy - 3, x + CELL + 2, yy + CELL + 2],
                     outline=GREEN if ok else RED, width=4)
        im.paste(tile, (x, yy))
        rt = Image.fromarray((255 - (ref[i] * 255).astype(np.uint8))).resize(
            (REF, REF), Image.LANCZOS)
        im.paste(rt, (x + CELL + 6, yy + CELL - REF))
        dr.rectangle([x + CELL + 5, yy + CELL - REF - 1, x + CELL + REF + 6, yy + CELL],
                     outline=(205, 205, 215), width=1)

        dr.text((x + 2, yy + CELL + 8), letters[i]["char"], font=heb, fill=(20, 20, 30))
        dr.text((x + 34, yy + CELL + 10),
                "eye: %s" % ("read it" if ok else "\u2192 " + letters[read[i]]["char"]),
                font=sm, fill=GREEN if ok else RED)
        if got is not None:
            gg = got[i]
            ook = gg == letters[i]["char"]
            dr.text((x + 34, yy + CELL + 28),
                    "ocr: %s" % (gg if gg else "could not read"),
                    font=sm, fill=GREEN if ook else RED)
        dr.text((x + CELL - 30, yy + CELL + 28), "%.2f" % cos[i], font=sm,
                fill=GREY)
        if marks[i]["pieces"] > 2:
            dr.text((x + CELL - 30, yy + CELL + 10), "%dpc" % marks[i]["pieces"],
                    font=sm, fill=RED)

    im.save(a.out)
    print("eye %d/%d   ocr %s   -> %s"
          % (hits, n, ("%d/%d" % (ohits, n)) if got is not None else "n/a", a.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
