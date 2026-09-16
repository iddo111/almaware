#!/usr/bin/env python3
# Clean (denoise+normalize+trim) the Cafe Claude recordings and stitch a tidy broadcast.
import os, sys, subprocess
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

SRC  = r"E:\_clod_writeok2"
DESK = os.path.join(os.environ.get("USERPROFILE", r"C:\Users\<user>"), "Desktop")
OUT  = os.path.join(DESK, "קפה קלוד - נקי")
os.makedirs(OUT, exist_ok=True)

# voice cleanup: low-cut -> FFT denoise -> trim gaps >2.5s -> normalize loudness
AF = ("highpass=f=70,afftdn=nf=-25,"
      "silenceremove=stop_periods=-1:stop_duration=2.5:stop_threshold=-40dB,"
      "loudnorm=I=-16:TP=-1.5:LRA=11")

# only the recordings that actually had speech (4 empty ones skipped)
SPEECH = ["20260624061811", "20260624070723", "20260625165315", "20260625165526",
          "20260625170458", "20260625171050", "20260625172706", "20260625173851"]

cleaned = []
for stem in SPEECH:
    inp = os.path.join(SRC, stem + ".WAV")
    out = os.path.join(OUT, stem + ".mp3")
    if not os.path.exists(inp):
        print("[skip] missing", stem, flush=True); continue
    r = subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                        "-i", inp, "-af", AF, "-b:a", "192k", out],
                       capture_output=True, text=True)
    if r.returncode == 0 and os.path.exists(out):
        cleaned.append(out); print("[clean]", stem, "OK", flush=True)
    else:
        print("[FAIL]", stem, (r.stderr or "")[-300:], flush=True)

# stitch the cleaned tracks into one tidy broadcast
if cleaned:
    listf = os.path.join(OUT, "_list.txt")
    with open(listf, "w", encoding="utf-8") as f:
        for c in cleaned:
            f.write("file '%s'\n" % c.replace("\\", "/").replace("'", "'\\''"))
    full = os.path.join(OUT, "קפה קלוד - שידור נקי.mp3")
    r = subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                        "-f", "concat", "-safe", "0", "-i", listf, "-c", "copy", full],
                       capture_output=True, text=True)
    print("[broadcast]", "OK -> " + full if r.returncode == 0 else "FAIL " + (r.stderr or "")[-300:], flush=True)
    try: os.remove(listf)
    except Exception: pass

print("[done] ->", OUT, flush=True)
