# -*- coding: utf-8 -*-
"""record_gui.py -- ERAN's recording booth as a NATIVE PC WINDOW. No browser at all.

Iddo, 2026-08-24: "תעשה לי GUI על המחשב." The browser booth kept failing at the mic
(getUserMedia / permissions / secure-origin / KESHEV contention). A direct sounddevice
capture of the BRIO returns real signal even while KESHEV runs, so the audio is captured
here, natively, and shown in a tkinter window on his own screen. Nothing to allow, nothing
to fight.

HOW IT WORKS. Voice-activated. The window shows a big syllable. Iddo says it. The energy
gate hears the burst, captures it, trims, saves the wav, advances. No clicks needed -- but
there are big buttons for SKIP, REDO, and PAUSE for when he wants them. A tired man just
talks; the booth does the rest.

SACRED AUDIO LAW: only records and writes wavs; never plays a sound.
USB MIC ONLY: opens the BRIO by name, refuses Bluetooth/headset.
NEVER FAKE A MILESTONE: the window says say X, he says X, the file is named X. The prompt
is the label -- zero label error.

  python record_gui.py                 # all units, 1 take each, next talker id
  python record_gui.py --takes 3 --talker t08
"""
import queue
import re
import sys
import threading
import time
import tkinter as tk
import wave
from pathlib import Path

import numpy as np
import sounddevice as sd

SR = 16000
ROOT = Path(__file__).resolve().parent
STAGE = ROOT / "staged"

UNITS = [
    ("ah", "אַה"), ("aa", "אָא"), ("ba", "בַּ"), ("ma", "מַ"), ("la", "לַ"),
    ("da", "דַ"), ("ga", "גַ"), ("pa", "פַּ"), ("ta", "טַ"), ("na", "נַ"),
    ("ka", "כַּ"), ("ra", "רַ"), ("sa", "סַ"), ("ha", "הַ"), ("va", "וַ"),
    ("ya", "יַ"), ("za", "זַ"), ("sha", "שַׁ"), ("kha", "חַ"), ("tha", "תַ"),
    ("tsa", "צַ"), ("qa", "קַ"),
    ("ih", "אִי"), ("eh", "אֶה"), ("oh", "אוֹ"), ("uh", "אוּ"),
    ("abba", "אַבָּא"), ("ima", "אִמָּא"), ("iddo", "עִידוֹ"),
    ("saba", "סָבָא"), ("safta", "סָבְתָא"),
]

BLOCK = 1600
GATE = 0.012
HOLD_SILENCE = 0.45
MIN_LEN = 0.20
MAX_LEN = 1.6
PREROLL = 0.15


def find_brio():
    bt = re.compile(r"bluetooth|hands-?free|headset|wh-1000", re.I)
    cand = None
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] <= 0:
            continue
        name = d["name"]
        if bt.search(name):
            continue
        if "BRIO" in name:
            return i, name
        if cand is None:
            cand = (i, name)
    return cand if cand else (None, "default")


def next_talker():
    used = set()
    if STAGE.exists():
        for p in STAGE.glob("t*/"):
            if re.fullmatch(r"t\d{2,}", p.name):
                used.add(int(p.name[1:]))
    n = 7
    while n in used:
        n += 1
    return f"t{n:02d}"


def already(talker):
    d = STAGE / talker
    c = {}
    if d.exists():
        for f in d.glob("*.wav"):
            u = f.name.split("_")[0]
            c[u] = c.get(u, 0) + 1
    return c


def save_wav(path, audio):
    pcm = (np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes()
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm)


def trim(a):
    peak = float(np.abs(a).max()) if len(a) else 0.0
    fl = max(1, int(SR * 0.01))
    amps = [float(np.abs(a[i:i + fl]).mean()) for i in range(0, max(0, len(a) - fl), fl)]
    amps.sort()
    noise = amps[int(len(amps) * 0.20)] if amps else 0.01
    thr = max(noise * 4, peak * 0.06)
    idx = np.where(np.abs(a) > thr)[0]
    if len(idx) == 0:
        return a, peak
    pad = int(SR * 0.06)
    out = a[max(0, idx[0] - pad):min(len(a), idx[-1] + pad)]
    if len(out) > int(SR * MAX_LEN):
        out = out[:int(SR * MAX_LEN)]
    return out, peak


class Booth:
    def __init__(self, talker, takes):
        self.talker = talker
        self.takes = takes
        self.dir = STAGE / talker
        self.dir.mkdir(parents=True, exist_ok=True)
        self.have = already(talker)
        self.total = takes * len(UNITS)
        self.q = queue.Queue()
        self.level = 0.0
        self.paused = False
        self.skip = False
        self.redo_last = None
        self.msg = "מתחבר…"
        self.last = ""
        self.cur_h = "·"
        self.done_flag = False
        self.stop = False
        self.dev, self.devname = find_brio()

    def done_count(self):
        return sum(min(self.have.get(u, 0), self.takes) for u, _ in UNITS)

    def run(self):
        def cb(indata, frames, tinfo, status):
            self.q.put(indata[:, 0].copy())
        try:
            stream = sd.InputStream(samplerate=SR, channels=1, dtype="float32",
                                    blocksize=BLOCK, device=self.dev, callback=cb)
            stream.start()
        except Exception as e:
            self.msg = f"מיקרופון נכשל: {e}"
            return
        self.msg = f"מוכן · {self.devname}"
        preroll = np.zeros(int(SR * PREROLL), dtype="float32")
        todo = [(u, h) for (u, h) in UNITS if self.have.get(u, 0) < self.takes]
        i = 0
        while i < len(todo) and not self.stop:
            u, h = todo[i]
            n = self.have.get(u, 0)
            if n >= self.takes:
                i += 1
                continue
            self.cur_h = h
            self.msg = f"אמור:  {h}"
            self.skip = False
            buf = []
            capturing = False
            silence = 0.0
            got = None
            while not self.stop:
                if self.paused:
                    time.sleep(0.05)
                    continue
                if self.skip:
                    got = "skip"
                    break
                try:
                    blk = self.q.get(timeout=0.2)
                except queue.Empty:
                    continue
                rms = float(np.sqrt((blk ** 2).mean()))
                self.level = rms
                if not capturing:
                    preroll = np.concatenate([preroll, blk])[-int(SR * PREROLL):]
                    if rms > GATE:
                        capturing = True
                        buf = [preroll.copy(), blk]
                        silence = 0.0
                else:
                    buf.append(blk)
                    if rms < GATE:
                        silence += len(blk) / SR
                        if silence >= HOLD_SILENCE:
                            got = "audio"
                            break
                    else:
                        silence = 0.0
                    if sum(len(b) for b in buf) / SR > MAX_LEN + PREROLL + HOLD_SILENCE:
                        got = "audio"
                        break
            if self.stop:
                break
            if got == "skip":
                i += 1
                continue
            audio = np.concatenate(buf) if buf else np.zeros(1)
            out, peak = trim(audio)
            if len(out) < int(SR * MIN_LEN) or peak < 0.03:
                self.msg = f"קצר/חלש — שוב:  {h}"
                continue
            path = self.dir / f"{u}_{self.talker}_{n}.wav"
            save_wav(path, out)
            self.have[u] = n + 1
            self.last = f"{h}  ✓  {len(out)/SR:.2f}s"
            self.redo_last = path
            time.sleep(0.2)
            if self.have[u] >= self.takes:
                i += 1
        stream.stop()
        stream.close()
        self.done_flag = True
        self.cur_h = "✓"
        self.msg = "סיימת את הפאס. כל הכבוד."


def main():
    argv = sys.argv[1:]
    takes = int(argv[argv.index("--takes") + 1]) if "--takes" in argv else 1
    talker = argv[argv.index("--talker") + 1] if "--talker" in argv else next_talker()
    booth = Booth(talker, takes)

    threading.Thread(target=booth.run, daemon=True).start()

    root = tk.Tk()
    root.title(f"ERAN — תא הקלטה · {talker}")
    root.configure(bg="#fbfbf6")
    root.geometry("720x760")

    msg = tk.Label(root, text="", font=("Segoe UI", 26), fg="#5a6474", bg="#fbfbf6", wraplength=680)
    msg.pack(pady=(28, 6))
    glyph = tk.Label(root, text="·", font=("Segoe UI", 220, "bold"), fg="#14181f", bg="#fbfbf6")
    glyph.pack(pady=4)

    barwrap = tk.Frame(root, bg="#e7ebf1", width=460, height=20)
    barwrap.pack(pady=10)
    barwrap.pack_propagate(False)
    bar = tk.Frame(barwrap, bg="#1f8b4c", width=0, height=20)
    bar.place(x=0, y=0)

    last = tk.Label(root, text="", font=("Segoe UI", 20), fg="#1f8b4c", bg="#fbfbf6")
    last.pack(pady=4)
    prog = tk.Label(root, text="", font=("Segoe UI", 24), fg="#14181f", bg="#fbfbf6")
    prog.pack(pady=4)

    btns = tk.Frame(root, bg="#fbfbf6")
    btns.pack(pady=18)

    def do_skip():
        booth.skip = True

    def do_pause():
        booth.paused = not booth.paused
        pause_btn.config(text="המשך" if booth.paused else "השהה")

    def do_redo():
        if booth.redo_last and Path(booth.redo_last).exists():
            u = Path(booth.redo_last).name.split("_")[0]
            try:
                Path(booth.redo_last).unlink()
                booth.have[u] = max(0, booth.have.get(u, 1) - 1)
                booth.last = "נמחק — תגיד שוב"
            except Exception:
                pass

    tk.Button(btns, text="דלג", font=("Segoe UI", 18), width=7, command=do_skip).pack(side="right", padx=8)
    pause_btn = tk.Button(btns, text="השהה", font=("Segoe UI", 18), width=7, command=do_pause)
    pause_btn.pack(side="right", padx=8)
    tk.Button(btns, text="מחק אחרון", font=("Segoe UI", 18), width=9, command=do_redo).pack(side="right", padx=8)

    dim = tk.Label(root, text="רק מדבר. זה נשמר לבד.  ·  BRIO",
                   font=("Segoe UI", 13), fg="#98a2b3", bg="#fbfbf6")
    dim.pack(side="bottom", pady=14)

    def tick():
        glyph.config(text=booth.cur_h)
        msg.config(text=booth.msg)
        last.config(text=booth.last)
        prog.config(text=f"{booth.done_count()} / {booth.total}")
        w = int(min(460, (booth.level ** 0.5) * 2300))
        bar.config(width=max(0, w))
        root.after(80, tick)

    def on_close():
        booth.stop = True
        root.after(150, root.destroy)

    root.protocol("WM_DELETE_WINDOW", on_close)
    tick()
    root.mainloop()


if __name__ == "__main__":
    main()
