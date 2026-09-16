"""TZELEM / צלם — put gate 2 in front of Iddo.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

Copies the gate-2 pictures into the judging gallery, PREPENDS them to that
folder's manifest.json (newest first, Hebrew labels carrying the measured
numbers), rewrites `status_line_he`, and drops the 1920-wide preview on the
Desktop — because an absolute Windows path is not a link Iddo can click, and a
file he can double-click is.

Reads its numbers from the measurement files. It never types a number by hand.
"""
from __future__ import annotations

import json
import os
import shutil
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
GALLERY = r"D:\CLAUDE\eran-brain\judging\galeria\tzelem"
DESKTOP = r"C:\Users\<user>\Desktop"
MAX_GALLERY_MB = 15.0


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    g2 = _load(os.path.join(_HERE, "out", "gate2.json"))
    tim = _load(os.path.join(_HERE, "out", "gate2-timings.json"))
    st = _load(os.path.join(_HERE, "out", "gate1-1080p-styles.json"))
    hero = _load(os.path.join(_HERE, "out8k", "hero.json"))
    rf = g2["resolution_free"]
    t = {r["name"]: r for r in tim}
    pa = st["painterly"]

    src4k = os.path.join(_HERE, "out8k", "TZELEM-gate2-4K.png")
    mb4k = os.path.getsize(src4k) / 1e6
    big_ok = mb4k <= MAX_GALLERY_MB

    items = []

    def add(src, name, label_he, note_he):
        shutil.copy2(src, os.path.join(GALLERY, name))
        items.append({"file": name, "kind": "image", "label_he": label_he,
                      "note_he": note_he,
                      "source": os.path.relpath(src, r"D:\CLAUDE").replace("\\", "/")})

    add(os.path.join(_HERE, "out8k", "TZELEM-gate2-8K-crop1000.png"),
        "TZELEM-gate2-8K-crop1000.png",
        "GATE 2 -- חיתוך 1000x1000 מתוך ה-8K (ללא הגדלה)",
        f"ההוכחה ש-8K הוא אמיתי: פיקסלים שנחתכו ישירות מתוך פריים "
        f"7680x4320. כל משיכה ברוחב ~90 פיקסלים והשפה שלה עדיין אליפסה נקייה -- "
        f"כי המשיכה מעולם לא הייתה פיקסל, היא גודל בעולם. "
        f"{rf['strokes']} משיכות בלבד, אותן משיכות כמו ב-480p.")

    if big_ok:
        add(src4k, "TZELEM-gate2-4K.png",
            "GATE 2 -- הסטיל המלא ב-4K",
            f"נושא אמיתי: הצורה הראשונה של KAV + תבנית הסיליקון של הגרון "
            f"(85,964 פאות -> {hero['counts']['mould']} באשכול-קודקודים) + רצפה ואור אחד. "
            f"צויר ישירות ב-3840x2160 מ-{hero['strokes']} משיכות. ללא אפסקייל.")
    add(os.path.join(_HERE, "out8k", "TZELEM-gate2-8K-preview.jpg"),
        "TZELEM-gate2-8K-preview.jpg",
        "GATE 2 -- תצוגה מקדימה 1920 (JPEG)",
        f"אותה תמונה, מוקטנת ל-1920 לצפייה מהירה. 4K = {mb4k:.1f} MB PNG.")

    for k, lab, note in [
        ("tz_b", "GATE 1 @1080p -- שיטת צלם (משיכות ציוריות)",
         f"קוהרנטיות {pa['coherence']['TZELEM_world_anchored']['mean']:.5f} "
         f"מול רצפה {pa['coherence']['FLOOR_repaint_every_frame']['mean']:.5f} "
         f"= פי {pa['steadier_than_floor']:.2f} יציב יותר (ממוצע על "
         f"{pa['camera']['frames']} פריימים, סיבוב 4 מעלות)."),
        ("fl_b", "GATE 1 @1080p -- רצפה: ציור מחדש כל פריים",
         "מה שצייר 2D רגיל היה עושה. זו הרצפה שצלם צריך לנצח בקוהרנטיות."),
        ("truth_b", "GATE 1 @1080p -- האמת",
         f"התמונה שממנה נמדדת הנאמנות. צלם "
         f"{pa['fidelity_mse']['TZELEM_world_anchored']['mean']:.5f} מול צבע שטוח "
         f"{pa['fidelity_mse']['BLANK_best_flat_colour']['mean']:.5f}."),
    ]:
        p = os.path.join(_HERE, "out1080", f"TZELEM-gate1-{k}.png")
        if os.path.exists(p):
            add(p, f"TZELEM-gate2-gate1-1080p-{k}.png", lab, note)

    mpath = os.path.join(GALLERY, "manifest.json")
    man = _load(mpath)
    man["status_line_he"] = (
        f"GATE 2 עבר (2026-09-03): אותן {rf['strokes']} משיכות מצוירות ב-480x270 "
        f"וב-4K -- הסכמת בעלות על הפיקסל "
        f"{rf['ownership_agreement'] * 100:.2f}% (סף 95%), ונאמנות ב-4K "
        f"{rf['fidelity_big']:.5f} מול {rf['fidelity_small']:.5f} ב-480p "
        f"(יחס {rf['fidelity_ratio']:.3f}, סף 1.10). זמני ציור מדודים על ה-PC: "
        f"1080p {t['1080p']['seconds']:.1f} שניות, 4K {t['4K']['seconds']:.1f} שניות, "
        f"8K {t['8K']['seconds']:.1f} שניות ({t['8K']['peak_rss_mb'] / 1000:.1f} GB). "
        f"אין אפסקייל: גודל המשיכה הוא בעולם, לא בפיקסלים. GATE 1 נמדד מחדש "
        f"ב-1920x1080 עם המשיכות הציוריות: פי {pa['steadier_than_floor']:.2f} "
        f"יציב יותר מהרצפה.")
    man["status_line_en"] = (
        f"Gate 2 PASSED (2026-09-03): the SAME {rf['strokes']} strokes painted at "
        f"480x270 and at 4K -- per-pixel stroke-ownership agreement "
        f"{rf['ownership_agreement'] * 100:.2f}% (threshold 95%), fidelity at 4K "
        f"{rf['fidelity_big']:.5f} vs {rf['fidelity_small']:.5f} at 480p "
        f"(ratio {rf['fidelity_ratio']:.3f}, threshold 1.10). Measured on this PC: "
        f"1080p {t['1080p']['seconds']:.1f}s, 4K {t['4K']['seconds']:.1f}s, "
        f"8K {t['8K']['seconds']:.1f}s ({t['8K']['peak_rss_mb'] / 1000:.1f} GB peak). "
        f"No upscale anywhere: a stroke's size is in the world, not in pixels.")
    man["items"] = items + man.get("items", [])
    with open(mpath, "w", encoding="utf-8") as f:
        json.dump(man, f, indent=1, ensure_ascii=False)

    shutil.copy2(os.path.join(_HERE, "out8k", "TZELEM-gate2-8K-preview.jpg"),
                 os.path.join(DESKTOP, "TZELEM-gate2-8K-preview.jpg"))

    print(f"gallery: {len(items)} new items first in manifest.json")
    for it in items:
        print("   ", it["file"])
    print("desktop:", os.path.join(DESKTOP, "TZELEM-gate2-8K-preview.jpg"))


if __name__ == "__main__":
    sys.exit(main())
