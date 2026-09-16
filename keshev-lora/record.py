# -*- coding: utf-8 -*-
"""
KESHEV-LORA / record.py  --  clean labelled-speech collection harness for Iddo.

WHY THIS EXISTS
---------------
A voice LoRA that HELPS instead of HARMS needs (audio, CORRECT-transcript) pairs.
The previous personal LoRA LOST to the ivrit-ai baseline because it was trained on
CIRCULAR labels -- transcripts the old mic pipeline itself typed, hallucinations and
all. This harness fixes the data at the root: it shows Iddo EXACT text to read, so
the ground-truth transcript is known letter-for-letter before a single sample is cut.

It targets the real measured failures: project vocabulary (ERAN, ALMA, KESHEV, TZELEM,
KAV, DARWISH, MIKO, holobrain, WINSTON, MAKOM, Chinchilla, Sonnet, Opus, ...), general
Hebrew, and Iddo's own command phrases.

SACRED AUDIO LAW  (חוק השמע הקדוש)
----------------------------------
* Captures from a USB microphone ONLY -- BRIO preferred, then Scarlett, then any USB mic.
* HARD-REFUSES to open any Bluetooth / headset / hands-free device (WH-1000XM4 etc).
  A BT headset mic flips the headset to HFP telephone quality and wrecks his sound.
* Never opens, ducks, mutes or touches any audio OUTPUT device. Records only.
* If no acceptable USB mic is alive, it EXITS. It never falls back to a headset.

HOW IDDO RUNS IT
----------------
    setx PYTHONIOENCODING utf-8        (once, if not already set)
    cd D:\\CLAUDE\\keshev-lora
    python record.py

Controls per prompt:  ENTER = start/stop recording · r = re-record · s = skip · q = save & quit
Progress is saved after every clip, so he can stop any time and resume later; already
recorded prompts are skipped on the next run.

OUTPUT
------
    data/clips/NNNN_<block>.wav      16 kHz mono PCM16, one clip per prompt
    data/manifest.jsonl             {"wav","text","lang","block","prompt_id"} -- THE ground truth
"""
from __future__ import annotations
import json, os, sys, time, wave

# UTF-8 or the Hebrew script crashes silently on cp1252 (project law).
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdin.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
CLIPS = os.path.join(HERE, "data", "clips")
MANIFEST = os.path.join(HERE, "data", "manifest.jsonl")
SR = 16000
CH = 1

# --------------------------------------------------------------------------- #
#  SACRED AUDIO LAW -- device selection
# --------------------------------------------------------------------------- #
# Any input device whose name matches one of these is NEVER opened as a mic.
FORBIDDEN = (
    "wh-1000", "wh1000", "hands-free", "hands free", "handsfree", "bthhf",
    "bluetooth", "a2dp", "headset", "energy olla", "airpod", "buds",
)
# Preference order for an acceptable USB mic.
PREFERRED = ("logitech brio", "brio", "scarlett", "usbaudio", "usb")


def pick_mic():
    """Return (device_index, name) of the best allowed USB mic, or (None, reason)."""
    import sounddevice as sd
    ins = []
    for i, d in enumerate(sd.query_devices()):
        if d.get("max_input_channels", 0) > 0:
            ins.append((i, d["name"]))

    def forbidden(name: str) -> bool:
        n = name.lower()
        return any(f in n for f in FORBIDDEN)

    allowed = [(i, n) for i, n in ins if not forbidden(n)]
    if not allowed:
        return None, "no non-Bluetooth input device found at all"

    for key in PREFERRED:
        for i, n in allowed:
            if key in n.lower():
                return i, n
    # No known-USB name matched; do NOT guess a random device -- too risky.
    return None, ("no BRIO/Scarlett/USB mic found. Allowed inputs seen: "
                  + ", ".join(n for _, n in allowed))


# --------------------------------------------------------------------------- #
#  The reading script  --  ground truth lives here
# --------------------------------------------------------------------------- #
# block "vocab":     project words inside TRAIN carrier sentences
# block "vocab_eval":same words inside DIFFERENT sentences (generalisation, held out)
# block "sentence":  general Hebrew
# block "command":   Iddo's real mic command phrases
# Split rule (train_lora / eval_gate): prompt_id % 5 == 0  -> EVAL, else TRAIN.
# Every "vocab_eval" line is FORCED into EVAL regardless, so project names are tested
# in sentences the model never trained on.
from script_he import SCRIPT  # noqa: E402  (single source of truth for prompts)


# --------------------------------------------------------------------------- #
#  Recording
# --------------------------------------------------------------------------- #
def record_one(dev):
    """Blocking push-to-talk capture. ENTER starts, ENTER stops. Returns np.int16 mono."""
    import numpy as np
    import sounddevice as sd
    frames = []

    def cb(indata, n, t, status):
        frames.append(indata.copy())

    input("      [ENTER] to START speaking ...")
    with sd.InputStream(samplerate=SR, channels=CH, dtype="int16",
                        device=dev, callback=cb):
        input("      speaking -- [ENTER] to STOP ...")
    if not frames:
        return np.zeros(0, dtype=np.int16)
    return np.concatenate(frames).reshape(-1)


def save_wav(path, audio_int16):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with wave.open(path, "wb") as w:
        w.setnchannels(CH)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(audio_int16.tobytes())


def load_done():
    done = set()
    if os.path.exists(MANIFEST):
        with open(MANIFEST, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        done.add(int(json.loads(line)["prompt_id"]))
                    except Exception:
                        pass
    return done


def append_manifest(row):
    with open(MANIFEST, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def rms(audio_int16):
    import numpy as np
    if audio_int16.size == 0:
        return 0.0
    a = audio_int16.astype(np.float64)
    return float((a * a).mean() ** 0.5)


def main():
    print("=" * 68)
    print(" KESHEV-LORA recording harness  --  clean labelled speech for Iddo")
    print(" מקליט קול נקי עם תמלול מדויק כדי לאמן ולבדוק לורה למיקרופון")
    print("=" * 68)

    dev, name = pick_mic()
    if dev is None:
        print("\n  [STOP] SACRED AUDIO LAW: " + name)
        print("  Plug in the Logitech BRIO (or a wired USB mic) and run again.")
        print("  חבר את ה-BRIO (מיק USB) והרץ שוב. לא נפתח אוזניות בלוטות' לעולם.")
        return 2
    print(f"\n  Mic: [{dev}] {name}")
    print("  (USB mic, per the Sacred Audio Law. No Bluetooth headset is ever opened.)\n")

    done = load_done()
    todo = [p for p in SCRIPT if p["id"] not in done]
    if done:
        print(f"  Resuming: {len(done)} already recorded, {len(todo)} left.\n")
    if not todo:
        print("  All prompts already recorded. Nothing to do. Run train_lora.py next.")
        return 0

    print("  Controls:  ENTER start/stop · r re-record · s skip · q save & quit")
    print("  Speak in a normal voice, like you talk to the mic. Read the line as written.\n")
    input("  [ENTER] when you are ready to begin ...")

    n_saved = 0
    for k, p in enumerate(todo, 1):
        print("\n" + "-" * 68)
        print(f"  {k}/{len(todo)}   (block: {p['block']})")
        print(f"\n      >>>   {p['text']}   <<<\n")
        while True:
            cmd = input("      [ENTER]=record  r=redo  s=skip  q=quit : ").strip().lower()
            if cmd == "q":
                print(f"\n  Saved {n_saved} clips this run. Total on disk: {len(done)+n_saved}.")
                print("  Run again any time to continue where you left off.")
                return 0
            if cmd == "s":
                print("      skipped.")
                break
            # record (ENTER or 'r' both lead here)
            audio = record_one(dev)
            secs = audio.size / SR
            level = rms(audio)
            print(f"      captured {secs:.1f}s, level {level:.0f}")
            if secs < 0.3:
                print("      too short -- try again.")
                continue
            if level < 150:
                print("      very quiet -- is the BRIO the active mic? try again (r) or keep (ENTER).")
            keep = input("      keep this? [ENTER]=yes  r=redo  s=skip : ").strip().lower()
            if keep == "r":
                continue
            if keep == "s":
                print("      skipped.")
                break
            wav = os.path.join(CLIPS, f"{p['id']:04d}_{p['block']}.wav")
            save_wav(wav, audio)
            append_manifest({
                "wav": os.path.basename(wav),
                "text": p["text"],
                "lang": p.get("lang", "he"),
                "block": p["block"],
                "prompt_id": p["id"],
                "secs": round(secs, 2),
            })
            n_saved += 1
            print(f"      saved -> {os.path.basename(wav)}")
            break

    print("\n" + "=" * 68)
    print(f"  DONE. {n_saved} clips saved this run. Total: {len(done)+n_saved}.")
    print("  Next: python train_lora.py  (on a fleet GPU -- see README).")
    print("=" * 68)
    return 0


if __name__ == "__main__":
    sys.exit(main())
