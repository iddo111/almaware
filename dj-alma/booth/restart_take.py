# -*- coding: utf-8 -*-
"""restart_take.py -- the from-zero restart: one fresh model take through the
FIXED render path (true pitch lead, full-span pad, model bass roots).

Mirrors booth/almido.make_take's render block exactly -- same calls, same
flags -- but runs standalone so it can be launched from one cmd line.
Writes almido-RESTART-<stamp>-drop.{mid,wav,mp3,json} into booth/takes/
and prints the renderer's own measurements (the only evidence of what
reached the speaker). Refuses non-model sources like make_take does.

Needs: PC python with torch+numpy+scipy+pedalboard+mido, the v2 checkpoint,
D:\\ paths (runs on the PC, not WSL).
"""
import io
import json
import os
import sys
import time
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))          # booth/
BRIDGE = os.path.join(os.path.dirname(HERE), "bridge")
GALERIA = r"D:\CLAUDE\eran-brain\judging\galeria\darwish"
DARWISH_AI = r"D:\CLAUDE\darwish-ai"
for _p in (HERE, BRIDGE, GALERIA, DARWISH_AI,
           os.path.join(DARWISH_AI, "code-midi")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import compose as C
import psy_render as V1
import psy_render_v4 as V4

TAKES = os.path.join(HERE, "takes")
BPM = 143.55  # measured psy tempo, not a guess


def main():
    t0 = time.time()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    base = f"almido-RESTART-{stamp}-drop"
    mid = os.path.join(TAKES, base + ".mid")
    wav = os.path.join(TAKES, base + ".wav")
    mp3 = os.path.join(TAKES, base + ".mp3")

    sc, chords, meta = C.compose(bars=16, section="SECTION_DROP", bpm=BPM)
    if meta.get("source") != "model-v2":
        raise RuntimeError("REFUSED: source=%r, not model-v2" % meta.get("source"))
    C.write_midi(sc, mid)
    render = V4.render_one_v4(mid, wav, chord_notes=chords or None,
                              true_pitch_lead=True, chord_span_bars=16,
                              bass_roots=C.bass_roots(sc))
    for k in ("_placed_classes", "_orig_classes", "match_eq_db",
              "match_eq_pass2_db", "bar_roots_from_his_phrase"):
        render.pop(k, None)
    try:
        V1.to_mp3(wav, mp3)
        audio = os.path.basename(mp3)
    except Exception as e:
        print("mp3 failed, keeping wav: %r" % e)
        audio = os.path.basename(wav)
    meta.update({"name": base, "audio": audio,
                 "seconds_to_make": round(time.time() - t0, 1),
                 "render": render})
    with open(os.path.join(TAKES, base + ".json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False)
    print(json.dumps({"audio": audio, "seconds": meta["seconds_to_make"],
                      "render": render}, ensure_ascii=False)[:2000])


if __name__ == "__main__":
    main()
