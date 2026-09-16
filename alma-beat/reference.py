# -*- coding: utf-8 -*-
"""THE REFERENCE. What Chai's own bars actually look like, measured.

Read-only from 40 of Chai's compositions copied off eran4's outbox. dmidi-life
was never touched: scp read the files, nothing on eran4 was written or stopped.

HONEST LIMIT, stated here and repeated in the deliverable: this is the CURRENT
MODEL'S OUTPUT, not human Darwish. Iddo's ear ruled at 02:54 tonight that it is
"זוועה". So `similarity` to this profile is the LOWEST-weighted term in the
judge -- it is a sanity anchor on density and placement, not a definition of
good. Anyone who raises its weight is asking the organ to imitate a verdict
Iddo already rejected.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import midi_in

HERE = Path(__file__).resolve().parent
BAR = 16


def profile(paths: list[str]) -> dict:
    kick = [0.0] * BAR
    snare = [0.0] * BAR
    hat = [0.0] * BAR
    bass_on = [0.0] * BAR
    pcs = [0.0] * 12
    bars = 0
    files = 0
    for p in paths:
        try:
            L = midi_in.lanes(p)
        except Exception as e:                                   # noqa: BLE001
            print(f"  skip {Path(p).name}: {e}", file=sys.stderr)
            continue
        files += 1
        n = L["steps"] // BAR
        for b in range(n):
            o = b * BAR
            for i in range(BAR):
                kick[i] += L["kick"][o + i]
                snare[i] += L["snare"][o + i]
                hat[i] += L["hat"][o + i]
                d = L["bass"][o + i]
                if d:
                    bass_on[i] += 1
                    pcs[(d - 1) % 12] += 1
            bars += 1
    if not bars:
        raise SystemExit("no bars found")
    norm = lambda v: [round(x / bars, 5) for x in v]              # noqa: E731
    tot = sum(pcs) or 1.0
    return {
        "files": files, "bars": bars,
        "kick_pos": norm(kick), "snare_pos": norm(snare),
        "hat_pos": norm(hat), "bass_pos": norm(bass_on),
        "kick_density": round(sum(kick) / (bars * BAR), 5),
        "snare_density": round(sum(snare) / (bars * BAR), 5),
        "hat_density": round(sum(hat) / (bars * BAR), 5),
        "bass_density": round(sum(bass_on) / (bars * BAR), 5),
        "bass_pc": [round(x / tot, 5) for x in pcs],
    }


if __name__ == "__main__":
    src = sys.argv[1:] or sorted(str(p) for p in (HERE / "data" / "chai").glob("*.mid"))
    prof = profile(src)
    out = HERE / "reference.json"
    out.write_text(json.dumps(prof, indent=2), encoding="utf-8")
    print(f"{prof['files']} files, {prof['bars']} bars -> {out}")
    print("kick_pos ", [f"{x:.2f}" for x in prof["kick_pos"]])
    print("hat_pos  ", [f"{x:.2f}" for x in prof["hat_pos"]])
    print("bass_pos ", [f"{x:.2f}" for x in prof["bass_pos"]])
    print("bass_pc  ", [f"{x:.2f}" for x in prof["bass_pc"]])
    print("density  kick=%.3f snare=%.3f hat=%.3f bass=%.3f" % (
        prof["kick_density"], prof["snare_density"],
        prof["hat_density"], prof["bass_density"]))
