#!/usr/bin/env python3
# Batch-transcribe Iddo's clod_writeok2 WAVs with the local Hebrew whisper.
import json, os, sys, traceback
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = r"D:\CLAUDE\voice-input"
sys.path.insert(0, HERE)
import transcribe as stt

cfg = json.load(open(os.path.join(HERE, "config.json"), encoding="utf-8"))
# GPU for speed; fall back to CPU if it fails.
cfg["device"] = "cuda"

FILES = [
    "20260624061811.WAV", "20260624070723.WAV", "20260625165315.WAV",
    "20260625165526.WAV", "20260625170458.WAV", "20260625171050.WAV",
    "20260625171740.WAV", "20260625172207.WAV", "20260625172706.WAV",
    "20260625173229.WAV", "20260625173851.WAV", "20260625182956.WAV",
]
SRC = r"E:\_clod_writeok2"
OUT = os.path.join(SRC, "transcripts")
os.makedirs(OUT, exist_ok=True)

def run(device):
    cfg["device"] = device
    print(f"[load] model={cfg.get('model')} device={device}", flush=True)
    stt.load(cfg)
    combined = []
    for name in FILES:
        path = os.path.join(SRC, name)
        if not os.path.exists(path):
            print(f"[skip] missing {name}", flush=True); continue
        try:
            res = stt.transcribe(path, cfg)
            text = (res.get("text") if isinstance(res, dict) else str(res)) or ""
            text = text.strip()
        except Exception as e:
            text = f"[transcription error: {e}]"
        with open(os.path.join(OUT, name + ".txt"), "w", encoding="utf-8") as f:
            f.write(text)
        combined.append(f"===== {name} =====\n{text}\n")
        print(f"[done] {name}  ({len(text)} chars)", flush=True)
    with open(os.path.join(OUT, "ALL_TRANSCRIPTS.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(combined))
    print(f"[ALL DONE] -> {OUT}\\ALL_TRANSCRIPTS.txt", flush=True)

try:
    run("cuda")
except Exception:
    print("[cuda failed, retrying on CPU]", flush=True)
    traceback.print_exc()
    try:
        # reset cached engine so it rebuilds on cpu
        stt._engine = None; stt._engine_key = None
    except Exception:
        pass
    run("cpu")
