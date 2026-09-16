# -*- coding: utf-8 -*-
"""Supplementary shots. Ten narration blocks turned out to need one more clip
each so that no clip has to be held on screen longer than the 5.04 s LTX gives.
Same style rules as build_shots.py."""
import json

SUF = (", full frame edge to edge, no borders, no letterbox, no text, no captions, "
       "photorealistic, slow deliberate camera movement, rich detail")

EXTRA = {
    3: "Extreme macro of a paper card with a black circle printed on it sliding into a metal holder under a lamp, clean laboratory table, shallow focus",
    4: "A pair of hands sorting small wooden blocks into two separate piles on a plain table, warm daylight, top down view, unhurried",
    10: "A slow push in on a single small brass dial at the centre of a panel of hundreds of identical dials, warm raking light, shallow focus",
    13: "Extreme macro of a fine wiper arm sweeping a few millimetres across a carbon track inside a potentiometer, warm light, dark background",
    16: "A straight taut wire above a white surface scattered with black and white spheres, the wire rotating and never separating them, top down, clean light",
    22: "A slow orbit around a single glowing junction where two branching filaments meet, warm gold on deep blue, extreme macro, volumetric",
    25: "Thin copper foil being cut carefully with scissors on a kitchen table, the cut edge catching warm daylight, macro",
    26: "Extreme macro of the boundary between amber gel and a copper surface, the metal darkening slightly where the gel touches it, backlit",
    28: "A modest device of copper and amber gel sitting on a windowsill in plain afternoon light, ordinary and unglamorous, static shot",
    30: "A wide dark sky before dawn with one bright star low on the horizon, absolutely still, extremely slow drift",
}


def main():
    shots = []
    seed = 5510613
    for n in sorted(EXTRA):
        shots.append({"id": "b%02d_99" % n, "block": n, "k": 99,
                      "prompt": EXTRA[n] + SUF, "seed": seed})
        seed += 7717
    with open("shots_extra.json", "w") as f:
        json.dump(shots, f, indent=1)
    print("extra shots:", len(shots))


if __name__ == "__main__":
    main()
