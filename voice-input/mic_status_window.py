"""ALMAWARE Mic — always-on-top status WINDOW for the working voice-input LKG.

The voice-input engine is headless (reliable, auto-detects the live mic, types +
Enter) but had NO window, so it felt "not loaded". This is a tiny separate window
that READS the engine's live log and shows: status, the live device, and the last
thing it heard. Bright/white per Iddo's preference. Does not touch the engine.
"""
import tkinter as tk
import os, glob

VOICE = r"D:\CLAUDE\voice-input"
CHILD_LOG = os.path.join(VOICE, "history", "mic-child.log")

def _tail(path, n):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return [l.rstrip("\n") for l in f.readlines()[-n:]]
    except Exception:
        return []

def _today_history():
    fs = sorted(glob.glob(os.path.join(VOICE, "history", "20*.txt")))
    return fs[-1] if fs else None

root = tk.Tk()
root.title("ALMAWARE Mic")
root.configure(bg="white")
root.attributes("-topmost", True)
W, H = 470, 158
sw = root.winfo_screenwidth()
root.geometry(f"{W}x{H}+{sw-W-14}+14")  # top-right corner

tk.Label(root, text="\U0001F3A4  ALMAWARE Mic — LKG", font=("Segoe UI", 14, "bold"),
         bg="white", fg="#0a0a0a").pack(anchor="w", padx=14, pady=(12, 2))
lbl_status = tk.Label(root, text="starting…", font=("Segoe UI", 12, "bold"),
                      bg="white", fg="#1a7f37", anchor="w", wraplength=W-28, justify="left")
lbl_status.pack(anchor="w", padx=14)
lbl_dev = tk.Label(root, text="", font=("Segoe UI", 9), bg="white", fg="#666", anchor="w")
lbl_dev.pack(anchor="w", padx=14, pady=(2, 0))
lbl_last = tk.Label(root, text="", font=("Segoe UI", 12), bg="white", fg="#0a0a0a",
                    anchor="w", wraplength=W-28, justify="left")
lbl_last.pack(anchor="w", padx=14, pady=(6, 0))

def refresh():
    recent = _tail(CHILD_LOG, 30)
    # live device
    for line in reversed(recent):
        if "MIC: using" in line:
            lbl_dev.config(text="mic: " + line.split("MIC:")[-1].strip()[:58]); break
    # current state (newest meaningful marker)
    state, color = "\U0001F7E2 listening (idle) — talk", "#1a7f37"
    for line in reversed(recent):
        if "loading base" in line: state, color = "⏳ loading language model…", "#b06a00"; break
        if "loading faster-whisper" in line or "warming up" in line: state, color = "⏳ loading Whisper model…", "#b06a00"; break
        if "LISTENING" in line or "DUCKED" in line: state, color = "\U0001F3A4 HEARING YOU…", "#0a66c2"; break
        if "TYPING" in line: state, color = "⌨️ typing…", "#0a66c2"; break
        if "IDLE" in line: state, color = "\U0001F7E2 listening (idle) — talk", "#1a7f37"; break
    lbl_status.config(text=state, fg=color)
    # last transcription
    hf = _today_history()
    if hf:
        t = _tail(hf, 1)
        if t:
            lbl_last.config(text="\U0001F5E3  " + t[0][-90:])
    root.after(600, refresh)

refresh()
root.mainloop()
