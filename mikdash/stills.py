# -*- coding: utf-8 -*-
"""
Render the Temple stills with TZELEM — our own renderer, not anybody else's.

Two passes per view:
  TRUTH      stage.gbuffer + stage.shade — clean box ray-cast, reads as architecture
  PAINTED    anatomy.scatter + canvas.render — TZELEM's world-anchored brushstrokes

The strokes are planted once on a SMALL camera and then re-seen by the big one,
which is what makes the painted pass cheap at high resolution (the ray-cast is the
expensive half, and it only ever runs at plant size).

Everything is numpy on the CPU at BELOW_NORMAL. No GPU, no fleet box, nothing that
could compete with Iddo's live microphone.
"""
from __future__ import annotations
import json, os, sys, time

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
NTHREAD = "4"
for v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[v] = NTHREAD

# TZELEM only. KAV must NOT go on this path: both packages have an anatomy.py and
# whichever lands first wins — kav's has no scatter(), so the import dies.
sys.path.insert(0, r"D:\CLAUDE\eran-brain\holobrain\tzelem")

import numpy as np
from stage import Stage, Box, Camera
import canvas
from hero8k import save

OUT = os.path.join(HERE, "stills")
TRUTH_W, TRUTH_H = 1280, 720
PAINT_W, PAINT_H = 1920, 1080
PLANT_W, PLANT_H = 800, 450
STROKES = 28000
LIGHT = (-0.68, -0.62, -0.39)          # morning sun out of the east, as in the viewer
AMBIENT = 0.34                         # bright and high-contrast: the deliverable law

# (key, title_en, title_he, caption, eye, target, fov)
VIEWS = [
    ("01-approach", "The approach, from outside the east gate",
     "הגישה, מחוץ לשער המזרחי",
     "Where the man with the measuring reed stood (40:6). The whole 500-cubit axis: "
     "outer gate, outer court, inner gate, the altar, the House.",
     (272, 4.0, 0), (-70, 20, 0), 55),

    ("02-gate", "Inside the outer gate",
     "בתוך שער החצר החיצונה",
     "Fifty cubits deep, twenty-five across (40:21,13). Three guardrooms a side, six "
     "cubits square, five cubits between them (40:7,10,12). The blue figure against the "
     "right-hand wall is 1.80 m tall.",
     (247, 5.4, 0), (120, 8, 0), 60),

    ("03-altar", "The altar, before the House",
     "המזבח, לפני הבית",
     "Twelve by twelve at the hearth, fourteen by fourteen at the settle, each stage "
     "stepping in one cubit (43:14-17). Its steps look toward the east (43:17).",
     (38, 17, 26), (-6, 11, 0), 50),

    ("04-house", "The porch and the House",
     "האולם והבית",
     "The porch twenty long and eleven broad (40:49); the Heichal forty by twenty (41:2); "
     "the Holy of Holies twenty by twenty (41:4). Side chambers in three tiers (41:5-6).",
     (-14, 15, 46), (-95, 22, 0), 52),

    ("05-precinct", "The whole precinct, five hundred cubits square",
     "כל המקדש, חמש מאות אמה על חמש מאות",
     "Four gates alike on four sides (40:20-37), a hundred cubits from gate to gate "
     "(40:23), the inner court a hundred square (40:47).",
     (390, 335, 285), (-25, 5, 0), 46),
]


def load_boxes():
    m = json.load(open(os.path.join(HERE, "web", "model.json"), encoding="utf-8"))
    pal = m["palette"]

    def colour(kind):
        if kind in pal:
            return pal[kind]
        i = kind.rfind("_")
        if i > 0 and "_gate" + kind[i:] in pal:
            return pal["_gate" + kind[i:]]
        return pal["_default"]

    return [Box(np.array(b["lo"], float), np.array(b["hi"], float),
                np.array(colour(b["kind"]), float)) for b in m["boxes"]], m


def main():
    try:
        import psutil
        psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
        print("priority BELOW_NORMAL, numpy threads capped at " + NTHREAD)
    except Exception as e:
        print(f"could not lower priority: {e}")

    os.makedirs(OUT, exist_ok=True)
    boxes, model = load_boxes()
    st = Stage(boxes, ground_albedo=(0.50, 0.485, 0.455), light_dir=LIGHT, ambient=AMBIENT)
    print(f"{len(boxes)} boxes, cubit {model['cubit_m']} m")

    only = sys.argv[1] if len(sys.argv) > 1 else ""
    made = []
    for key, en, he, cap, eye, tgt, fov in VIEWS:
        t0 = time.time()
        mk = lambda w, h: Camera(eye=np.array(eye, float), target=np.array(tgt, float),
                                 fov_deg=fov, width=w, height=h)

        p1 = os.path.join(OUT, f"{key}-truth.jpg")
        if only != "painted":
            cam = mk(TRUTH_W, TRUTH_H)
            p1 = save(st.shade(st.gbuffer(cam)), p1, quality=95)
        t1 = time.time()

        plant = mk(PLANT_W, PLANT_H)
        from anatomy import scatter                      # needs alma-language
        strokes = scatter(st, plant, n=STROKES, seed=7, size=0.010)
        big = mk(PAINT_W, PAINT_H)
        pimg = canvas.render(None, big, strokes, style="painterly", seed=17)
        p2 = save(pimg, os.path.join(OUT, f"{key}-painted.jpg"), quality=95)

        print(f"  {key:12s} truth {t1-t0:5.1f}s   painted {time.time()-t1:5.1f}s "
              f"({len(strokes)} strokes)")
        made.append({"key": key, "en": en, "he": he, "cap": cap,
                     "truth": p1, "painted": p2})

    json.dump(made, open(os.path.join(OUT, "views.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"\n{len(made)} views -> {OUT}")
    return made


if __name__ == "__main__":
    main()
