#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ALMA MIC DOCTOR - tells you exactly which microphone works, and why the others do not.
רופא המיקרופון - בודק כל מיקרופון ואומר מה עובד ומה לא.

The whole point: "the device is present" is NOT the same as "the device passes
audio". Windows will happily list a microphone that is muted, has zero gain, or
has nothing plugged into it. This opens every input on every host API, records
real samples, and measures them.

    python mic_doctor.py              test everything, print a verdict
    python mic_doctor.py --seconds 3  listen longer per device
    python mic_doctor.py --apply      write the winner into config.json

Speak while it runs. It reports both the quiet floor and your loudest moment.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

try:
    import numpy as np
    import sounddevice as sd
except ImportError:
    sys.exit("Needs sounddevice + numpy.\n"
             "  py -3.13 -m pip install sounddevice numpy\n"
             "Note: the launchers use Python 3.13, not the default python.")

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(HERE, "config.json")

# What counts as real. A silent room still reads ~0.0005; true digital silence
# is ~1e-5. Below SILENT_MAX nothing is arriving at all.
SILENT_MAX = 5e-5
FAINT_MAX = 2e-3

# MME duplicates are frequently silent for USB mics even when the same physical
# device works fine on WASAPI or DirectSound - rank accordingly.
API_RANK = {"Windows WASAPI": 0, "Windows DirectSound": 1, "Windows WDM-KS": 2, "MME": 3}

NOT_REAL = ("sound mapper", "primary sound capture", "@system32",
            "virtual", "audiorelay", "stereo mix", "what u hear", "loopback")


def is_real_input(name: str) -> bool:
    n = name.lower()
    return not any(bad in n for bad in NOT_REAL)


def measure(idx: int, dev: dict, seconds: float):
    """Record and return (rms, peak, error). Never raises."""
    try:
        sr = int(dev["default_samplerate"]) or 44100
        ch = min(2, max(1, dev["max_input_channels"]))
        rec = sd.rec(int(seconds * sr), samplerate=sr, channels=ch,
                     device=idx, dtype="float32")
        sd.wait()
        a = rec.astype(np.float64).ravel()
        if a.size == 0:
            return 0.0, 0.0, "no samples"
        return float(np.sqrt((a * a).mean())), float(np.abs(a).max()), None
    except Exception as e:
        msg = str(e).split("\n")[0][:60]
        return None, None, msg


def verdict(rms):
    if rms is None:
        return "cannot open"
    if rms < SILENT_MAX:
        return "SILENT - nothing arriving"
    if rms < FAINT_MAX:
        return "faint - gain too low?"
    return "WORKING"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=2.0)
    ap.add_argument("--apply", action="store_true",
                    help="write the best device into config.json")
    args = ap.parse_args()

    apis = sd.query_hostapis()
    devs = sd.query_devices()

    print()
    print("ALMA MIC DOCTOR   -   speak now, %.1fs per device" % args.seconds)
    print("=" * 78)
    print("%-38s %-19s %8s %8s" % ("device", "host API", "rms", "peak"))
    print("-" * 78)

    results = []
    for i, d in enumerate(devs):
        if d["max_input_channels"] < 1:
            continue
        api = apis[d["hostapi"]]["name"]
        rms, peak, err = measure(i, d, args.seconds)
        v = verdict(rms)
        results.append({"index": i, "name": d["name"], "api": api,
                        "rms": rms, "peak": peak, "verdict": v,
                        "real": is_real_input(d["name"])})
        print("%-38s %-19s %8s %8s  %s"
              % (d["name"][:38], api[:19],
                 "-" if rms is None else "%.5f" % rms,
                 "-" if peak is None else "%.5f" % peak,
                 v if not err else v + " (" + err + ")"))

    working = [r for r in results if r["verdict"] == "WORKING" and r["real"]]
    faint = [r for r in results
             if r["verdict"].startswith("faint") and r["real"]]
    physical = sorted({r["name"] for r in results if r["real"]})

    print("=" * 78)
    if working:
        working.sort(key=lambda r: (API_RANK.get(r["api"], 9), -r["rms"]))
        best = working[0]
        print("BEST: %s  [%s]  #%d   rms %.5f"
              % (best["name"], best["api"], best["index"], best["rms"]))
        if args.apply:
            apply_to_config(best)
        else:
            print("      run with --apply to write it into config.json")
    elif faint:
        faint.sort(key=lambda r: -r["rms"])
        b = faint[0]
        print("NOTHING IS CLEARLY WORKING.")
        print("Loudest was %s [%s] at rms %.5f - that is signal, but very weak."
              % (b["name"], b["api"], b["rms"]))
        print("Raise the input level: Settings > System > Sound > that device >")
        print("Input volume to about 80, and turn off any -20dB PAD on the hardware.")
    else:
        print("NO MICROPHONE IS PASSING AUDIO.")
        print()
        print("Every input read as digital silence, so this is not a software")
        print("problem - nothing is reaching the sound card. Check, in order:")
        print("  1. Is a mic actually plugged into the input? A USB audio dongle")
        print("     or an interface with an empty socket reads as pure silence.")
        print("  2. Hardware mute switch on the mic or interface.")
        print("  3. Input level set to 0 in Settings > System > Sound.")
        print("  4. On an interface (Scarlett): is the GAIN knob up, and does it")
        print("     need 48V phantom power for a condenser mic?")
        print()
        print("Physical inputs Windows can see: " + (", ".join(physical) or "none"))
    print()
    return 0 if working else 1


def apply_to_config(best):
    try:
        with open(CONFIG, encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception as e:
        print("  could not read config.json: %s" % e)
        return
    import shutil
    import datetime
    shutil.copy2(CONFIG, CONFIG + ".bak-doctor-"
                 + datetime.datetime.now().strftime("%Y%m%d-%H%M%S"))
    cfg["mic"] = best["name"]
    # Never leave the chosen device sitting in the avoid list - that is exactly
    # how this config ended up rejecting the only microphone on the machine.
    avoid = [a for a in cfg.get("avoid", [])
             if a.lower() not in best["name"].lower()]
    cfg["avoid"] = avoid
    prefer = cfg.get("prefer", [])
    key = best["name"].split("(")[-1].strip(") ").lower()[:12]
    if key and key not in [p.lower() for p in prefer]:
        prefer.insert(0, key)
    cfg["prefer"] = prefer
    with open(CONFIG, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    print("  config.json updated: mic=%r  avoid=%s  prefer=%s"
          % (cfg["mic"], avoid, prefer))


if __name__ == "__main__":
    sys.exit(main())
