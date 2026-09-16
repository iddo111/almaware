"""AN OUTSIDE JUDGE — Hebrew OCR that has never seen ERAN, and never will.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

Iddo, 2026-08-30: *"ותביא שופט חיצוני, OCR עברי, במקום העין של ערן."*

ERAN's eye scoring ERAN's hand is a closed room. The eye was trained to tell letters
APART, not to be a template of a letter, so a shape can satisfy it without being a
letter — that is exactly how a sheet of dot-clouds scored 86% on 2026-08-30. An outside
reader breaks the room open.

## THE JUDGE IS EXAMINED FIRST

**Calibration comes before verdict.** If tesseract cannot read a PRINTED Hebrew letter
out of the very corpus the eye was trained on, then a zero on ERAN's hand means nothing
at all — it means the judge is deaf. A disqualified judge is a real result and gets
reported as one. So this script always prints the printed-corpus number, and refuses to
report a verdict on ERAN as meaningful when that number is at the floor.

    python3 judge_ocr.py --calibrate                 # examine the judge
    python3 judge_ocr.py --hand state/winston.pt     # then let it judge
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

import numpy as np
import torch
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "eye"))
sys.path.insert(0, os.path.join(HERE, "..", "..", "miko", "model"))

ALEFBET = "אבגדהוזחטיכלמנסעפצקרשת"
FINALS = {"ך": "כ", "ם": "מ", "ן": "נ", "ף": "פ", "ץ": "צ"}   # same letter, end form


def render(a, box=320, margin=0.22):
    """A 64x64 float page -> a clean black-on-white PNG the size a scanner would give.

    Tesseract was built for scanned print: it wants dark glyphs on light paper, a real
    margin, and an x-height of tens of pixels. Handing it a 64px tile with no border is
    setting the judge up to fail and then blaming it.
    """
    a = np.clip(a, 0, 1)
    img = Image.fromarray((255 * (1.0 - a)).astype(np.uint8), "L")
    inner = int(box * (1 - 2 * margin))
    img = img.resize((inner, inner), Image.LANCZOS)
    page = Image.new("L", (box, box), 255)
    page.paste(img, ((box - inner) // 2, (box - inner) // 2))
    return page


def read_one(page, tmp, psm=10, lang="heb", whitelist=True):
    p = os.path.join(tmp, "q.png")
    page.save(p)
    cmd = ["tesseract", p, "stdout", "-l", lang, "--psm", str(psm)]
    if whitelist:
        cmd += ["-c", "tessedit_char_whitelist=" + ALEFBET + "ךםןףץ"]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=30)
    except Exception:                                            # noqa: BLE001
        return ""
    txt = r.stdout.decode("utf-8", "replace")
    keep = [FINALS.get(c, c) for c in txt if c in ALEFBET or c in FINALS]
    return keep[0] if keep else ""


def score(pages, truth, tmp, psm, lang, whitelist):
    got = [read_one(p, tmp, psm, lang, whitelist) for p in pages]
    hit = sum(1 for g, t in zip(got, truth) if g == t)
    blank = sum(1 for g in got if g == "")
    return hit / len(truth), blank / len(truth), got


def calibrate(a, letters, tmp):
    """Can it read PRINT? Every configuration tried, the best one reported and kept."""
    d = np.load(a.data)
    X, y, f = d["X"].astype(np.float32), d["y"], d["f"]
    rng = np.random.default_rng(7)
    idx = []
    for c in range(len(letters)):                    # even spread over letters and fonts
        pool = np.where(y == c)[0]
        idx += list(rng.choice(pool, size=min(a.per, len(pool)), replace=False))
    idx = np.array(idx)
    pages = [render(X[i]) for i in idx]
    truth = [letters[int(y[i])]["char"] for i in idx]
    print("examining the judge on %d PRINTED letters from %d typefaces it has never "
          "been tuned on" % (len(idx), len(set(f[idx].tolist()))))
    best = None
    for psm in (10, 8, 6, 13):
        for wl in (True, False):
            acc, blank, _ = score(pages, truth, tmp, psm, a.lang, wl)
            print("   psm %-2d whitelist %-5s ->  %5.1f%% correct   %4.1f%% unreadable"
                  % (psm, str(wl), 100 * acc, 100 * blank), flush=True)
            if best is None or acc > best[0]:
                best = (acc, psm, wl, blank)
    acc, psm, wl, blank = best
    print("\n   BEST: psm %d, whitelist %s -> %.1f%% on print (chance %.1f%%)"
          % (psm, wl, 100 * acc, 100.0 / len(letters)))
    verdict = ("ADMITTED" if acc >= 0.50 else
               "DISQUALIFIED -- it cannot read PRINTED Hebrew, so it cannot be asked "
               "about ERAN's hand")
    print("   %s" % verdict)
    return {"printed_accuracy": acc, "psm": psm, "whitelist": wl, "blank": blank,
            "n": len(idx), "admitted": bool(acc >= 0.50), "verdict": verdict}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="An OCR that has never seen ERAN judges him.")
    ap.add_argument("--data", default=os.path.join(HERE, "..", "eye", "corpus",
                                                   "letters.npz"))
    ap.add_argument("--meta", default=os.path.join(HERE, "..", "eye", "corpus",
                                                   "letters.json"))
    ap.add_argument("--hand", default="")
    ap.add_argument("--eye", default=os.path.join(HERE, "..", "eye", "state", "eye.pt"))
    ap.add_argument("--per", type=int, default=8, help="printed samples per letter")
    ap.add_argument("--lang", default="heb")
    ap.add_argument("--out", default=os.path.join(HERE, "state", "ocr-judge.json"))
    ap.add_argument("--device", default="cpu")
    a = ap.parse_args(argv)

    if not shutil.which("tesseract"):
        print("NO JUDGE: tesseract is not installed here. Nothing can be reported.")
        return 2
    ver = subprocess.run(["tesseract", "--version"], capture_output=True)
    langs = subprocess.run(["tesseract", "--list-langs"], capture_output=True)
    print(ver.stdout.decode().splitlines()[0])
    if "heb" not in langs.stdout.decode():
        print("NO JUDGE: no Hebrew traineddata. Nothing can be reported.")
        return 2

    letters = json.load(open(a.meta, encoding="utf-8"))["letters"]
    tmp = tempfile.mkdtemp(prefix="ocr")
    cal = calibrate(a, letters, tmp)
    out = {"calibration": cal}

    if a.hand:
        from hand_eye import Winston, ink, centroids, load_eye     # noqa: E402
        dev = torch.device(a.device)
        ck = torch.load(a.hand, map_location=dev)
        n = len(letters)
        hand = Winston(n, ck["strokes"], ck["points"], ck["pressure"]).to(dev)
        hand.load_state_dict(ck["hand"])
        with torch.no_grad():
            xy, w = hand(torch.eye(n, device=dev))
            drawn = ink(xy, w).cpu().numpy()
        pages = [render(drawn[i]) for i in range(n)]
        truth = [l["char"] for l in letters]
        acc, blank, got = score(pages, truth, tmp, cal["psm"], a.lang, cal["whitelist"])
        print("\nthe same judge, same settings, on ERAN's 22 drawn letters:")
        print("   %.1f%% correct  (%d of %d)   %.0f%% it could not read at all"
              % (100 * acc, round(acc * n), n, 100 * blank))
        for i, (t, g) in enumerate(zip(truth, got)):
            print("     %s -> %s %s" % (t, g if g else "(nothing)",
                                        "OK" if g == t else ""))
        if not cal["admitted"]:
            print("\n   ^ REPORT THIS AS NOTHING. The judge failed its own exam on print.")
        out["eran"] = {"accuracy": acc, "blank": blank, "read": got,
                       "truth": truth, "hand": os.path.basename(a.hand)}

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    json.dump(out, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
