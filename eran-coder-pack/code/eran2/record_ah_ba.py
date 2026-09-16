#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ההקלטה של ערן V2 — אַה ובַּ בלבד.
ERAN V2 corpus recorder — AH and BA, nothing else.

Iddo, 2026-09-10: "אני דוגל בנוקשות AH BAH ... איכות על כמות."

Two syllables. Two sessions. Session A is what he practises on, session B is what
he is EXAMINED on -- and they must be different recordings of the same sound, or
the exam is just a memory test. V1 died because every one of its 657 files came
from one sitting (t06) while the exam looked for a session that did not exist:
    [wake] split: 657 wav -> world/edible 657, dev/exam 0 (DEV_SESSION_PICK=1 of 6)
That is the whole reason this file exists. Never ship one session again.

THREE GUARDS, all learned the hard way today:

  1. CLIPPING. The mic level sat at 100% all morning and every peak above 32,767
     was flattened. Clipped audio sounds fine to a human ear and turns into
     confident nonsense in a decoder. Any take peaking over 0.90 is REFUSED here,
     not warned about.
  2. ONE MIC. KESHEV owns the BRIO. This paused it before opening the device and
     restores it on exit -- and it SIGNS the pause, because an unsigned one gets
     auto-cleared by the delivery watchdog after 15 minutes (that cost Iddo his
     microphone overnight on 2026-09-03).
  3. THE LABEL LAW. Every delivered sound carries its speaker in the filename.
     These are IDDO-*.wav. Nothing here is ever labelled ERAN.
"""

import json
import os
import queue
import sys
import threading
import tkinter as tk
from datetime import datetime
from tkinter import font as tkfont

import numpy as np
import sounddevice as sd
import soundfile as sf

ROOT = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.join(ROOT, "corpus")
KESHEV_STATE = r"D:\CLAUDE\keshev-next\state"
PAUSE_FILE = os.path.join(KESHEV_STATE, "PAUSED")

SR = 16000          # the pipeline's rate; recording at anything else just resamples later
TAKE_S = 1.6        # a syllable is well under a second; the rest is room for his timing
TARGET_PER = 12     # per syllable per session. He can stop early -- quality over quantity.

# peak limits, as fractions of full scale
CLIP_AT = 0.90      # above this the waveform is flattened -- refuse, do not warn
QUIET_AT = 0.04     # below this there is nothing to learn from

UNITS = [("ah", "אַה"), ("ba", "בַּ")]
SESSIONS = [("A", "תרגול"), ("B", "מבחן")]

BG = "#fffdf6"
INK = "#241a12"
MUTED = "#7a6a55"
GOOD = "#2f7d32"
BAD = "#b3261e"
CARD = "#ffffff"
LINE = "#ecdfc4"


# ── KESHEV custody ───────────────────────────────────────────────────────────

def keshev_pause():
    """Take the mic from KESHEV, signed. Returns True if WE created the pause."""
    if os.path.exists(PAUSE_FILE):
        return False                      # already paused by someone else; leave it alone
    try:
        os.makedirs(KESHEV_STATE, exist_ok=True)
        tmp = PAUSE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({
                "who": "eran2/record_ah_ba.py (ERAN V2 corpus recorder)",
                "why": "Iddo is recording the AH/BA corpus and the recorder needs the BRIO. "
                       "ONE MIC. This lifts itself when the recorder window closes.",
                "at": datetime.now().isoformat(),
                "expires": None,
                "restore": "close the recorder window, or delete state\\PAUSED",
                "disables": True,
            }, f, ensure_ascii=False, indent=2)
        os.replace(tmp, PAUSE_FILE)
        return True
    except Exception:
        return False


def keshev_resume(ours):
    if ours:
        try:
            os.remove(PAUSE_FILE)
        except Exception:
            pass


# ── audio ────────────────────────────────────────────────────────────────────

def brio_index():
    """The BRIO on WASAPI, matching KESHEV's own pick. USB mics only -- never a
    Bluetooth headset, which Windows would flip to HFP telephone quality."""
    apis = sd.query_hostapis()
    best = None
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] < 1:
            continue
        name = d["name"]
        api = apis[d["hostapi"]]["name"]
        if "brio" in name.lower():
            if api == "Windows WASAPI":
                return i
            best = i if best is None else best
    return best


def trim(x, sr=SR, thresh=0.02, pad_ms=60):
    """Cut leading/trailing silence so the file is the syllable, not his timing."""
    mag = np.abs(x)
    loud = np.where(mag > thresh)[0]
    if len(loud) == 0:
        return x
    pad = int(sr * pad_ms / 1000)
    a = max(0, loud[0] - pad)
    b = min(len(x), loud[-1] + pad)
    return x[a:b]


# ── app ──────────────────────────────────────────────────────────────────────

class Recorder(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("ההקלטה של ערן — אַה ובַּ")
        self.configure(bg=BG)
        self.geometry("620x560")

        self.paused_by_us = keshev_pause()
        self.dev = brio_index()
        self.session = "A"
        self.unit = 0
        self.last = None          # the take waiting for a verdict
        self.busy = False

        big = tkfont.Font(family="Segoe UI", size=13)
        huge = tkfont.Font(family="Segoe UI", size=64, weight="bold")
        mid = tkfont.Font(family="Segoe UI", size=15, weight="bold")

        tk.Label(self, text="ההקלטה של ערן", bg=BG, fg=INK,
                 font=tkfont.Font(family="Segoe UI", size=19, weight="bold")).pack(pady=(16, 0))
        tk.Label(self, text="שתי הברות בלבד. איכות על כמות.",
                 bg=BG, fg=MUTED, font=big).pack()

        # session picker
        row = tk.Frame(self, bg=BG); row.pack(pady=12)
        self.sess_btns = {}
        for key, label in SESSIONS:
            b = tk.Button(row, text=f"מושב {key} · {label}", font=big, width=13, bd=0,
                          command=lambda k=key: self.set_session(k))
            b.pack(side="right", padx=5)
            self.sess_btns[key] = b

        # the syllable
        self.glyph = tk.Label(self, text="אַה", bg=BG, fg=INK, font=huge)
        self.glyph.pack(pady=(6, 0))
        self.counter = tk.Label(self, text="", bg=BG, fg=MUTED, font=big)
        self.counter.pack()

        self.status = tk.Label(self, text="", bg=BG, fg=MUTED, font=mid, height=2,
                               wraplength=560, justify="center")
        self.status.pack(pady=6)

        self.rec_btn = tk.Button(self, text="הקלט  (רווח)", font=mid, width=22, height=2,
                                 bd=0, bg="#f0e2c8", fg="#5c4a30", command=self.record)
        self.rec_btn.pack(pady=4)

        vr = tk.Frame(self, bg=BG); vr.pack(pady=6)
        self.keep_btn = tk.Button(vr, text="שמור  (Enter)", font=mid, width=14, bd=0,
                                  bg="#dff0df", fg="#245224", command=self.keep, state="disabled")
        self.keep_btn.pack(side="right", padx=6)
        self.redo_btn = tk.Button(vr, text="שוב  (R)", font=mid, width=14, bd=0,
                                  bg="#f7dcdc", fg="#7a2020", command=self.redo, state="disabled")
        self.redo_btn.pack(side="right", padx=6)

        tk.Button(self, text="החלף הברה  (Tab)", font=big, bd=0, bg=BG, fg=MUTED,
                  command=self.flip).pack(pady=(8, 0))

        self.bind("<space>", lambda e: self.record())
        self.bind("<Return>", lambda e: self.keep())
        self.bind("<r>", lambda e: self.redo())
        self.bind("<Tab>", lambda e: self.flip() or "break")
        self.protocol("WM_DELETE_WINDOW", self.close)

        if self.dev is None:
            self.say("לא מצאתי את ה-BRIO. חבר אותו ופתח שוב.", BAD)
            self.rec_btn.config(state="disabled")
        else:
            self.say("לחץ רווח, ואמור את ההברה.", MUTED)
        self.set_session("A")

    # ── state ────────────────────────────────────────────────────────────────

    def dirpath(self):
        d = os.path.join(CORPUS, self.session)
        os.makedirs(d, exist_ok=True)
        return d

    def code(self):
        return UNITS[self.unit][0]

    def count(self, unit=None, session=None):
        unit = unit or self.code()
        session = session or self.session
        d = os.path.join(CORPUS, session)
        if not os.path.isdir(d):
            return 0
        return len([f for f in os.listdir(d) if f.startswith(f"IDDO-{unit}-") and f.endswith(".wav")])

    def refresh(self):
        code, glyph = UNITS[self.unit]
        self.glyph.config(text=glyph)
        n = self.count()
        mark = "✓" if n >= TARGET_PER else ""
        other = UNITS[1 - self.unit]
        self.counter.config(
            text=f"{n} / {TARGET_PER} {mark}          "
                 f"({other[1]}: {self.count(unit=other[0])})")
        for k, b in self.sess_btns.items():
            b.config(bg="#f0e2c8" if k == self.session else BG,
                     fg="#5c4a30" if k == self.session else MUTED)

    def set_session(self, k):
        self.session = k
        self.discard()
        self.refresh()
        if k == "B":
            self.say("מושב ב' — זה המבחן. אותן הברות, הקלטה נפרדת.", MUTED)
        else:
            self.say("מושב א' — זה מה שהוא מתאמן עליו.", MUTED)

    def flip(self):
        self.unit = 1 - self.unit
        self.discard()
        self.refresh()

    def say(self, text, colour=MUTED):
        self.status.config(text=text, fg=colour)

    # ── record / verdict ─────────────────────────────────────────────────────

    def record(self):
        if self.busy or self.dev is None:
            return
        self.busy = True
        self.discard()
        self.say("מקליט…  אמור עכשיו", INK)
        self.rec_btn.config(state="disabled")
        threading.Thread(target=self._record_worker, daemon=True).start()

    def _record_worker(self):
        try:
            n = int(SR * TAKE_S)
            buf = sd.rec(n, samplerate=SR, channels=1, dtype="float32", device=self.dev)
            sd.wait()
            x = buf[:, 0]
        except Exception as e:
            self.after(0, lambda: self._done_bad(f"ההקלטה נכשלה: {e}"))
            return
        self.after(0, lambda: self._judge(x))

    def _judge(self, x):
        peak = float(np.max(np.abs(x))) if len(x) else 0.0
        if peak >= CLIP_AT:
            self._done_bad(f"חתוך — שיא {peak:.2f}. תתרחק מהמיק או תדבר חלש יותר.")
            return
        if peak < QUIET_AT:
            self._done_bad(f"חלש מדי — שיא {peak:.2f}. תתקרב.")
            return
        x = trim(x)
        if len(x) < int(SR * 0.12):
            self._done_bad("קצר מדי. תגיד את ההברה שלמה.")
            return
        self.last = x
        try:
            sd.play(x, SR); sd.wait()
        except Exception:
            pass
        self.say(f"שיא {peak:.2f} · {len(x)/SR:.2f} שנ׳ — לשמור?", GOOD)
        self.keep_btn.config(state="normal")
        self.redo_btn.config(state="normal")
        self.rec_btn.config(state="normal")
        self.busy = False

    def _done_bad(self, msg):
        self.last = None
        self.say(msg, BAD)
        self.keep_btn.config(state="disabled")
        self.redo_btn.config(state="disabled")
        self.rec_btn.config(state="normal")
        self.busy = False

    def keep(self):
        if self.last is None:
            return
        code = self.code()
        n = self.count() + 1
        path = os.path.join(self.dirpath(), f"IDDO-{code}-{self.session}-{n:02d}.wav")
        sf.write(path, self.last, SR, subtype="PCM_16")
        self.last = None
        self.keep_btn.config(state="disabled")
        self.redo_btn.config(state="disabled")
        self.refresh()
        left = TARGET_PER - self.count()
        if left > 0:
            self.say(f"נשמר. עוד {left}.", GOOD)
        else:
            self.say(f"{UNITS[self.unit][1]} הושלמה במושב {self.session}. Tab להברה הבאה.", GOOD)

    def redo(self):
        self.discard()
        self.say("בסדר — שוב.", MUTED)

    def discard(self):
        self.last = None
        self.keep_btn.config(state="disabled")
        self.redo_btn.config(state="disabled")

    def close(self):
        keshev_resume(self.paused_by_us)
        self.destroy()


if __name__ == "__main__":
    os.makedirs(CORPUS, exist_ok=True)
    Recorder().mainloop()
