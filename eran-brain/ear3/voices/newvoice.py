"""A NEW MOUTH — three minutes, twenty-two syllables, and the number moves.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

Iddo, 2026-08-31 00:30, after the measurement landed: *"אוי! יאללה!"*

## Why this exists, in numbers

ERAN's whole reference corpus is 396 clips: 22 syllables from **six mouths**. Measured
tonight on his own frozen cochlea:

    same syllable, same take        0.339
    same syllable, DIFFERENT take   0.575     <- the takes really are different people
    distance between syllables      0.631
    ------------------------------------------
    signal / spread                 1.10      <- barely above one

At 1.10 the thing that tells syllables apart is only just larger than the thing that
tells PEOPLE apart. A learner cannot find what is invariant across mouths from six of
them — there are not enough mouths to see what varies. That is exactly what Iddo said
before any of this was measured:

    *"האוזן שלי התאמנה על אלפי אנשים, אלפי שעות, אלפי וריאציות וסיטואציות תלויות הקשר."*

And what it is NOT: the recordings are clean — median SNR 33.6 dB, zero clipping, zero DC
offset. **Re-recording for quality would waste his time. Recording more PEOPLE is the
whole fix**, and it needs no studio, no gear and not one line of model code. Every person
who says twenty-two syllables raises that ratio.

## The laws this obeys

* **USB microphones only.** A Bluetooth headset is never a microphone here — opening one
  flips it to telephone quality and wrecks his sound. The refuse-list is enforced, and if
  no allowed mic exists this window will not open at all.
* **Nothing is ever played.** It records. It does not make a sound.
* **Consent is asked on screen, in Hebrew**, before the first syllable, because these are
  other people's voices and they are going into a child's ear.

    python newvoice.py
"""
from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import os
import sys
import tkinter as tk
import wave

import numpy as np
import sounddevice as sd

HERE = os.path.dirname(os.path.abspath(__file__))
SR = 16000
SECS = 1.2
REFUSE = ("vive", "wh-1000", "hands-free", "handsfree", "headset", "bluetooth",
          "virtual", "stereo mix", "mapper", "wave")
PREFER = ("brio", "scarlett", "usb")

# The same 22, in the same order and the same names as the throat search and the eye's
# corpus. One index, three organs -- getting this list wrong would quietly split them.
SYL = [("aa", "אָ"), ("ba", "בַּ"), ("ga", "גַ"), ("da", "דַ"), ("ha", "הַ"), ("va", "וַ"),
       ("za", "זַ"), ("kha", "חַ"), ("tha", "טַ"), ("ya", "יַ"), ("ka", "כַּ"), ("la", "לַ"),
       ("ma", "מַ"), ("na", "נַ"), ("sa", "סַ"), ("ah", "עַ"), ("pa", "פַּ"), ("tsa", "צַ"),
       ("qa", "קַ"), ("ra", "רַ"), ("sha", "שַׁ"), ("ta", "תַּ")]
PER = 3            # three sayings of each, as the existing corpus has


def pick_mic():
    """A USB mic or nothing. Never a headset, whatever Windows thinks is default."""
    for want in PREFER:
        for i, d in enumerate(sd.query_devices()):
            n = d["name"].lower()
            if d["max_input_channels"] > 0 and want in n and not any(r in n for r in REFUSE):
                return i, d["name"]
    return None, None


class Booth:
    def __init__(self, root: tk.Tk, out: str, take: str):
        self.root, self.out, self.take = root, out, take
        self.dev, self.name = pick_mic()
        self.i = 0
        self.clips: list[tuple[str, int, np.ndarray]] = []
        self.consented = False

        root.title("קול חדש לערן")
        root.configure(bg="#fffdf7")
        root.geometry("760x560")

        self.top = tk.Label(root, text="", font=("Segoe UI", 15), bg="#fffdf7", fg="#4a5570")
        self.top.pack(pady=(18, 4))
        self.big = tk.Label(root, text="", font=("David", 190), bg="#fffdf7", fg="#141828")
        self.big.pack(expand=True)
        self.sub = tk.Label(root, text="", font=("Segoe UI", 22), bg="#fffdf7", fg="#6b7590")
        self.sub.pack()
        self.meter = tk.Label(root, text="", font=("Consolas", 12), bg="#fffdf7", fg="#8b93a8")
        self.meter.pack(pady=6)
        self.btn = tk.Button(root, text="", font=("Segoe UI", 17, "bold"), bg="#1f8a4c",
                             fg="#fff", relief="flat", padx=26, pady=12, command=self.go)
        self.btn.pack(pady=(4, 22))
        root.bind("<space>", lambda _=None: self.go())

        if self.dev is None:
            self.big.config(text="✖", fg="#b03030")
            self.sub.config(text="אין מיקרופון USB מחובר")
            self.top.config(text="אוזנייה אף פעם לא מיקרופון. חבר BRIO או מיק USB אחר.")
            self.btn.config(state="disabled", text="—")
            return
        self.ask_consent()

    def ask_consent(self):
        self.top.config(text="מיקרופון: %s" % self.name[:52])
        self.big.config(text="🎙", font=("Segoe UI", 90))
        self.sub.config(
            text="ההקלטה הזאת נכנסת לאוזן של ערן — מודל שלומד לדבר.\n"
                 "היא נשמרת אצלנו בלבד ולא מועלית לשום מקום.")
        self.btn.config(text="הבנתי, אפשר להתחיל")

    def go(self):
        if not self.consented:
            self.consented = True
            self.next()
            return
        if self.i >= len(SYL) * PER:
            return
        self.record()

    def next(self):
        if self.i >= len(SYL) * PER:
            return self.finish()
        name, glyph = SYL[self.i // PER]
        rep = self.i % PER + 1
        self.top.config(text="%d מתוך %d   ·   טייק %s"
                             % (self.i + 1, len(SYL) * PER, self.take))
        self.big.config(text=glyph, font=("David", 190))
        self.sub.config(text="אמור/י   %s   ·   פעם %d מתוך %d" % (glyph, rep, PER))
        self.btn.config(text="רווח = הקלט (1.2 שניות)", bg="#1f8a4c")

    def record(self):
        self.btn.config(text="… מקליט", bg="#b03030")
        self.root.update()
        x = sd.rec(int(SECS * SR), samplerate=SR, channels=1, device=self.dev,
                   dtype="float32")
        sd.wait()
        x = x[:, 0]
        rms = float(np.sqrt((x ** 2).mean()))
        pk = float(np.abs(x).max())
        # A clip nobody can hear is not a recording. Say so and let them do it again --
        # silently keeping it would poison the corpus this whole exercise exists to widen.
        if pk < 0.02:
            self.meter.config(text="שקט מדי (peak %.3f) — קרוב יותר למיק, שוב" % pk,
                              fg="#b03030")
            self.btn.config(text="רווח = נסה שוב", bg="#1f8a4c")
            return
        if pk > 0.99:
            self.meter.config(text="רם מדי, נחתך — קצת רחוק יותר, שוב", fg="#b03030")
            self.btn.config(text="רווח = נסה שוב", bg="#1f8a4c")
            return
        self.meter.config(text="peak %.2f   rms %.3f   ✓" % (pk, rms), fg="#2a8a4c")
        name, _ = SYL[self.i // PER]
        self.clips.append((name, self.i % PER, x))
        self.i += 1
        self.next()

    def finish(self):
        os.makedirs(self.out, exist_ok=True)
        for name, k, x in self.clips:
            p = os.path.join(self.out, "%s_t%s_%d.wav" % (name, self.take, k))
            with wave.open(p, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(SR)
                w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())
        io.open(os.path.join(self.out, "take-%s.json" % self.take), "w",
                encoding="utf-8").write(json.dumps(
                    {"take": self.take, "clips": len(self.clips), "sr": SR,
                     "mic": self.name, "when": dt.datetime.now().isoformat(timespec="seconds"),
                     "note": "one new mouth for ERAN's ear; consent given on screen"},
                    ensure_ascii=False, indent=1))
        self.big.config(text="✓", font=("Segoe UI", 130), fg="#2a8a4c")
        self.sub.config(text="%d הקלטות נשמרו.\nכל פה חדש מרים את היחס." % len(self.clips))
        self.top.config(text=self.out)
        self.btn.config(text="סגור", bg="#2a3550", command=self.root.destroy)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Record one new voice for ERAN's ear.")
    ap.add_argument("--out", default=os.path.join(HERE, "voices"))
    ap.add_argument("--take", default=dt.datetime.now().strftime("%m%d%H%M"),
                    help="a label for this MOUTH; anything unique to the person")
    a = ap.parse_args(argv)
    root = tk.Tk()
    Booth(root, a.out, a.take)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
