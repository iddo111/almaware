# -*- coding: utf-8 -*-
"""Re-roll the shots that came back wrong.

Reviewing the contact sheets turned up a real prompting mistake: the suffix
asked for "no borders, no letterbox, no text, no captions". LTX-Video 13B
distilled runs at cfg 1.0, where the negative prompt is inert, so those words
only ever acted as POSITIVE prompt tokens — and the model duly drew framed
pictures, white borders and letterbox bars. The re-roll suffix names only what
should be in the picture.

    python build_rerolls.py b01_02 b02_04 ...
"""
import json
import re
import sys

CLEAN_SUF = (", photorealistic, natural light, shallow depth of field, "
             "slow deliberate camera movement, rich detail")
BAD = re.compile(r",\s*(full frame edge to edge|no borders|no letterbox|"
                 r"no text|no captions|photorealistic|slow deliberate camera movement|"
                 r"rich detail)", re.I)


def load_all():
    shots = {}
    for f in ("shotlist_perceptron.json", "shots_extra.json", "shots_legacy.json"):
        try:
            for s in json.load(open(f)):
                shots[s["id"]] = s
        except FileNotFoundError:
            pass
    return shots


def main():
    ids = [a for a in sys.argv[1:] if not a.startswith("-")]
    allshots = load_all()
    out = []
    for i, sid in enumerate(ids):
        s = allshots.get(sid)
        if not s:
            print("  ?? unknown id", sid)
            continue
        p = BAD.sub("", s["prompt"]).strip().rstrip(",")
        out.append({"id": sid + "x", "block": s["block"], "k": s["k"],
                    "prompt": p + CLEAN_SUF,
                    "seed": int(s["seed"]) + 313131 + i * 977})
    json.dump(out, open("shots_reroll.json", "w"), indent=1)
    for i, nd in enumerate(["eran1", "eran4", "eran2"]):
        part = out[i::3]
        json.dump(part, open("shots_%sR.json" % nd, "w"), indent=1)
        print(nd, len(part))
    print("rerolls:", len(out))


if __name__ == "__main__":
    main()
