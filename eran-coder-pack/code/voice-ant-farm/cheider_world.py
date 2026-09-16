# -*- coding: utf-8 -*-
"""The cheider — a world where letters hang on the wall while syllables sound.

Iddo's directive (2026-08-11): teach reading the way a cheider does — the
child sees א while hearing "ah". This module builds the ENVIRONMENT only:

  * corpus-letters/           rendered Hebrew letters, natural variety
                              (many fonts, sizes, jitter, rotation, noise)
  * a co-presence stream      moments where a syllable's audio token and an
                              image of its letter are present TOGETHER, plus
                              letter-alone and sound-alone moments so mere
                              pairing cannot be gamed

Autonomy law: no label symbol ever crosses into the organism. The ants get
two sensory streams that happen to co-occur; the glyph map below is world
architecture (which picture hangs on the wall while which sound plays),
exactly as the TTS corpus was world architecture for the ears.

Font split: the exam shows fonts the ants have NEVER seen. Train fonts and
held-out fonts are disjoint by family, the same discipline as the audio
train/heldout splits.

    py -3.13 cheider_world.py --build     render corpus-letters/
"""
from __future__ import annotations

import argparse
import io
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
LETTERS = ROOT / "corpus-letters"
MANIFEST = LETTERS / "manifest.json"
SYLLABLE_MANIFEST = ROOT / "corpus-syllables" / "manifest.json"
SIDE = 48
CANVAS = 64

FONT_DIR = Path(r"C:\Windows\Fonts")
TRAIN_FONTS = ("arial.ttf", "times.ttf", "tahoma.ttf", "segoeui.ttf",
               "david.ttf", "lvnm.ttf", "ahronbd.ttf", "calibri.ttf")
HELDOUT_FONTS = ("frank.ttf", "gisha.ttf", "nrkis.ttf")
TRAIN_VARIANTS = 8      # per (letter, font)  -> 22*8*8 = 1408 train images
HELDOUT_VARIANTS = 2    # per (letter, font)  -> 22*3*2 = 132 exam images
SEED = 40_040


def glyph_map() -> dict[str, str]:
    """syllable id -> Hebrew letter, from the corpus provenance."""
    manifest = json.loads(io.open(SYLLABLE_MANIFEST, encoding="utf-8").read())
    return {e["item_id"]: e["glyph"] for e in manifest["entries"]
            if e["item_kind"] == "syllable"}


def render_letter(glyph: str, font_file: str, rng: np.random.Generator):
    """One letter image with natural variation. Returns PIL image (SIDE^2)."""
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
    size = int(rng.integers(26, 40))
    font = ImageFont.truetype(str(FONT_DIR / font_file), size)
    canvas = Image.new("L", (CANVAS, CANVAS), 255)
    draw = ImageDraw.Draw(canvas)
    left, top, right, bottom = draw.textbbox((0, 0), glyph, font=font)
    x = (CANVAS - (right - left)) // 2 - left + int(rng.integers(-3, 4))
    y = (CANVAS - (bottom - top)) // 2 - top + int(rng.integers(-3, 4))
    draw.text((x, y), glyph, font=font, fill=0)
    angle = float(rng.uniform(-6.0, 6.0))
    canvas = canvas.rotate(angle, resample=Image.BILINEAR, fillcolor=255)
    blur = float(rng.uniform(0.0, 0.7))
    if blur > 0.05:
        canvas = canvas.filter(ImageFilter.GaussianBlur(blur))
    crop = (CANVAS - SIDE) // 2
    canvas = canvas.crop((crop, crop, crop + SIDE, crop + SIDE))
    a = np.asarray(canvas, dtype=np.float32) / 255.0
    a = np.clip(a + rng.normal(0.0, rng.uniform(0.01, 0.05), a.shape), 0, 1)
    if a.min() > 0.85:                      # glyph missing from this font
        raise ValueError(f"{font_file} rendered no ink for {glyph!r}")
    return Image.fromarray((a * 255).astype("uint8"))


def build() -> dict:
    glyphs = glyph_map()
    rng = np.random.default_rng(SEED)
    entries = []
    for split, fonts, variants in (("train", TRAIN_FONTS, TRAIN_VARIANTS),
                                   ("heldout", HELDOUT_FONTS, HELDOUT_VARIANTS)):
        for syllable, glyph in sorted(glyphs.items()):
            folder = LETTERS / split / syllable
            folder.mkdir(parents=True, exist_ok=True)
            for font_file in fonts:
                for v in range(variants):
                    name = f"{syllable}_{font_file.split('.')[0]}_{v}.png"
                    image = render_letter(glyph, font_file, rng)
                    image.save(folder / name)
                    entries.append({"split": split, "syllable": syllable,
                                    "glyph": glyph, "font": font_file,
                                    "variant": v,
                                    "path": f"{split}/{syllable}/{name}"})
    manifest = {
        "note": "rendered letter board for the cheider; the glyph map is "
                "world architecture, never an organism input",
        "side": SIDE,
        "train_fonts": list(TRAIN_FONTS),
        "heldout_fonts": list(HELDOUT_FONTS),
        "seed": SEED,
        "entries": entries,
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=1),
                        encoding="utf-8")
    counts = {s: sum(1 for e in entries if e["split"] == s)
              for s in ("train", "heldout")}
    print(f"rendered {counts} letter images -> {LETTERS}")
    return manifest


def load_manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def co_presence_stream(train_audio_names_by_class: dict[str, list[str]],
                       train_images_by_class: dict[str, list[int]],
                       passes: int = 3, null_fraction: float = 0.3,
                       seed: int = 50_050):
    """Yield world moments: ('both', audio_name, image_idx),
    ('sound', audio_name, None) or ('sight', None, image_idx).

    Each pass shows every training audio token once, paired with a random
    training image of its letter. Null moments (letter alone on the wall,
    sound alone from the corridor) are mixed in so co-occurrence statistics,
    not mere presence, carry the signal.
    """
    rng = np.random.default_rng(seed)
    moments = []
    for _ in range(passes):
        for syllable, names in train_audio_names_by_class.items():
            pool = train_images_by_class[syllable]
            for name in names:
                moments.append(("both", name, int(rng.choice(pool))))
    n_null = int(null_fraction * len(moments))
    all_classes = sorted(train_audio_names_by_class)
    for _ in range(n_null // 2):
        c = str(rng.choice(all_classes))
        moments.append(("sound", str(rng.choice(train_audio_names_by_class[c])), None))
        c2 = str(rng.choice(all_classes))
        moments.append(("sight", None, int(rng.choice(train_images_by_class[c2]))))
    order = rng.permutation(len(moments))
    for i in order:
        yield moments[i]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    args = ap.parse_args()
    if args.build:
        build()
    else:
        ap.print_help()
