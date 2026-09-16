# -*- coding: utf-8 -*-
"""Re-render the eighteen shots of the original 72-second cut at full LTX
resolution and fold them into the feature timeline.

The 2026-08-14 cut was built from eighteen 768x512 clips. Upscaling those into
a 1216x704 film would be visibly soft, so instead their own prompts are pulled
from eran1 (~/eran-movie/shotlist.json + shotlist_new.json) and re-rendered at
the full size, then mapped onto the narration block they belong to. Nothing
from the earlier cut is discarded; it is re-shot.
"""
import json
import re

SUF = (", full frame edge to edge, no borders, no letterbox, no text, no captions, "
       "photorealistic, slow deliberate camera movement, rich detail")

# legacy shot id -> narration block it illustrates
BLOCK = {
    "01_dust_light": 1,
    "03_rosenblatt_desk": 2,
    "05_neuron_fire": 7,
    "15_robot_wake": 9,
    "04_perceptron_machine": 11,
    "02_mark_i_wires": 12,
    "14_soldering": 25,
    "06_xor_wall": 17,
    "07_winter": 17,
    "09_deep_layers": 18,
    "18_forward_backprop": 18,
    "08_rebirth_gpu": 19,
    "17_bulb_memristor": 21,
    "10_memristor_crossbar": 23,
    "11_optical_brain": 27,
    "12_child_hand": 29,
    "16_campfire": 29,
    "13_negev_dawn": 30,
}

# words that make LTX bake letterbox bars into the frame
STRIP = re.compile(r"\b(cinematic|cinematography|35mm|16mm|anamorphic|widescreen)\b[,.]?\s*",
                   re.I)


def main():
    legacy = json.load(open("legacy/legacy16.json")) + json.load(open("legacy/legacy2.json"))
    shots = []
    seed = 9910613
    for i, s in enumerate(legacy):
        b = BLOCK.get(s["id"])
        if b is None:
            continue
        p = STRIP.sub("", s["prompt"]).strip()
        shots.append({"id": "b%02d_L%02d" % (b, i + 1), "block": b, "k": 50 + i,
                      "prompt": p + SUF, "seed": seed})
        seed += 7717
    with open("shots_legacy.json", "w") as f:
        json.dump(shots, f, indent=1)
    print("legacy re-shoots:", len(shots))
    for s in shots:
        print(" ", s["id"])


if __name__ == "__main__":
    main()
