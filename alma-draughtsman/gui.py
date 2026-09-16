"""ALMA DRAUGHTSMAN — the studio window.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

Iddo, 2026-08-28: *"תעשה לי גואי לצייר שלנו."*

An artist needs to see the dial move. So the window previews a single frame **instantly**
at small size while you drag, and only renders the film when you say render. Same code
path either way — `draw.draw_frame` — so what you dial is exactly what you get.

Sacred Audio Law: this window NEVER plays audio. It reads the wav to measure it, draws,
and writes a file. Pressing play is yours.

    python gui.py
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, ttk

from PIL import Image, ImageTk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import draw as D                                                    # noqa: E402

ROOT = os.path.dirname(os.path.abspath(__file__))
DEFAULT_AUDIO = os.path.normpath(os.path.join(
    ROOT, "..", "perceptron-movie", "music", "perceptron_score.wav"))
PREVIEW_W, PREVIEW_H = 640, 360
SIZES = {"1080p  1920x1080": (1920, 1080),
         "4K     3840x2160": (3840, 2160),
         "8K     7680x4320": (7680, 4320),
         "square 2160x2160": (2160, 2160)}


class Studio:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("ALMA DRAUGHTSMAN — הצייר")
        root.configure(bg="#12121a")
        self.audio = tk.StringVar(value=DEFAULT_AUDIO if os.path.exists(DEFAULT_AUDIO) else "")
        self.bands = None          # cached measurement of the current wav
        self.sr = None
        self._preview_job = None

        wrap = tk.Frame(root, bg="#12121a")
        wrap.pack(fill="both", expand=True, padx=12, pady=12)

        # ---- the canvas
        self.canvas = tk.Label(wrap, bg="#05040a", bd=0)
        self.canvas.grid(row=0, column=0, rowspan=14, padx=(0, 14), sticky="n")

        r = 0

        def head(text):
            nonlocal r
            tk.Label(wrap, text=text, bg="#12121a", fg="#8fb8ff",
                     font=("Segoe UI", 11, "bold")).grid(row=r, column=1, columnspan=2,
                                                         sticky="w", pady=(10, 2))
            r += 1

        def slider(label, lo, hi, init, step=1):
            nonlocal r
            tk.Label(wrap, text=label, bg="#12121a", fg="#ddd",
                     font=("Segoe UI", 10)).grid(row=r, column=1, sticky="w")
            v = tk.DoubleVar(value=init)
            s = tk.Scale(wrap, from_=lo, to=hi, resolution=step, orient="horizontal",
                         variable=v, length=250, bg="#12121a", fg="#fff",
                         troughcolor="#2a2a3a", highlightthickness=0,
                         command=lambda _=None: self.schedule_preview())
            s.grid(row=r, column=2, sticky="w")
            r += 1
            return v

        head("החומר · the material")
        tk.Button(wrap, text="בחר קובץ שמע…", command=self.pick_audio,
                  bg="#2a3550", fg="#fff", relief="flat", font=("Segoe UI", 10)
                  ).grid(row=r, column=1, columnspan=2, sticky="we", pady=2)
        r += 1
        self.audio_lbl = tk.Label(wrap, textvariable=self.audio, bg="#12121a", fg="#889",
                                  font=("Consolas", 8), wraplength=300, justify="left")
        self.audio_lbl.grid(row=r, column=1, columnspan=2, sticky="w")
        r += 1

        head("היד · the hand")
        self.v_knots = slider("קשרים   knots", 6, 60, 26)
        self.v_mirror = slider("סימטריה  mirror", 1, 16, 6)
        self.v_strokes = slider("חלקות   smoothness", 8, 90, 44)
        self.v_fade = slider("שובל    trail", 0.30, 0.97, 0.80, 0.01)
        self.v_seed = slider("זרע     seed", 1, 9999, 1337)

        head("הזמן · the time")
        self.v_start = slider("התחלה (שנ׳)", 0, 600, 120)
        self.v_dur = slider("אורך (שנ׳)", 2, 120, 12)
        self.v_fps = slider("fps", 12, 60, 30)

        head("הפלט · the output")
        tk.Label(wrap, text="גודל", bg="#12121a", fg="#ddd",
                 font=("Segoe UI", 10)).grid(row=r, column=1, sticky="w")
        self.v_size = tk.StringVar(value="4K     3840x2160")
        ttk.Combobox(wrap, textvariable=self.v_size, values=list(SIZES), state="readonly",
                     width=22).grid(row=r, column=2, sticky="w")
        r += 1

        self.btn = tk.Button(wrap, text="▶  רנדר סרט", command=self.render,
                             bg="#1f8a4c", fg="#fff", relief="flat",
                             font=("Segoe UI", 12, "bold"), pady=6)
        self.btn.grid(row=r, column=1, columnspan=2, sticky="we", pady=(12, 2))
        r += 1
        self.status = tk.Label(wrap, text="גרור חוגה — התצוגה מתעדכנת מיד",
                               bg="#12121a", fg="#9ab", font=("Segoe UI", 9),
                               wraplength=300, justify="left")
        self.status.grid(row=r, column=1, columnspan=2, sticky="w")

        self.schedule_preview()

    # ---------------------------------------------------------------- audio

    def pick_audio(self):
        p = filedialog.askopenfilename(title="קובץ שמע", filetypes=[("WAV", "*.wav")])
        if p:
            self.audio.set(p)
            self.bands = None
            self.schedule_preview()

    def measure(self, n_frames, fps):
        """Cache the FFT measurement; re-measure only when the window it covers changes."""
        key = (self.audio.get(), int(self.v_start.get()), n_frames, fps)
        if self.bands is not None and self._key == key:
            return self.bands
        a, sr = D.read_wav_mono(self.audio.get())
        s0 = int(self.v_start.get() * sr)
        a = a[s0:s0 + int(n_frames / fps * sr)]
        self.bands = D.bands(a, sr, fps, n_frames)
        self._key = key
        return self.bands

    # -------------------------------------------------------------- preview

    def schedule_preview(self):
        # coalesce drags: redraw 90 ms after the last movement, not on every pixel
        if self._preview_job:
            self.root.after_cancel(self._preview_job)
        self._preview_job = self.root.after(90, self.preview)

    def preview(self):
        self._preview_job = None
        if not self.audio.get() or not os.path.exists(self.audio.get()):
            self.status.config(text="אין קובץ שמע", fg="#e88")
            return
        try:
            fps = int(self.v_fps.get())
            B = self.measure(max(2, int(2 * fps)), fps)     # 2 s is enough to pick a frame
            idx = min(len(B) - 1, int(0.9 * fps))
            canvas = Image.new("RGB", (PREVIEW_W, PREVIEW_H), (5, 4, 9))
            K = D.knots(int(self.v_knots.get()), PREVIEW_W, PREVIEW_H, int(self.v_seed.get()))
            # a few frames so the trail is visible in the still, exactly as in the film
            fade = float(self.v_fade.get())
            for i in range(6):
                canvas = self._one(canvas, K, B[max(0, idx - 5 + i)], (idx - 5 + i) / fps, fade)
            self.canvas.img = ImageTk.PhotoImage(canvas)
            self.canvas.config(image=self.canvas.img)
            self.status.config(text="תצוגה חיה · %d קשרים × %d סימטריה" %
                                    (int(self.v_knots.get()), int(self.v_mirror.get())),
                               fg="#9ab")
        except Exception as e:                                # noqa: BLE001
            self.status.config(text="תצוגה נכשלה: %s" % e, fg="#e88")

    def _one(self, canvas, K, bnd, t, fade):
        """The film's own renderer, at preview size. No second code path."""
        return D.draw_frame(PREVIEW_W, PREVIEW_H, K, bnd, t, int(self.v_seed.get()),
                            int(self.v_strokes.get()), int(self.v_mirror.get()),
                            canvas, fade)

    # --------------------------------------------------------------- render

    def render(self):
        w, h = SIZES[self.v_size.get()]
        out = filedialog.asksaveasfilename(
            title="שמור סרט", defaultextension=".mp4",
            initialfile="alma-draughtsman-%dx%d.mp4" % (w, h),
            filetypes=[("MP4", "*.mp4")])
        if not out:
            return
        self.btn.config(state="disabled", text="מרנדר…")
        args = ["--audio", self.audio.get(), "--out", out,
                "--w", str(w), "--h", str(h),
                "--fps", str(int(self.v_fps.get())),
                "--start", str(float(self.v_start.get())),
                "--dur", str(float(self.v_dur.get())),
                "--knots", str(int(self.v_knots.get())),
                "--strokes", str(int(self.v_strokes.get())),
                "--mirror", str(int(self.v_mirror.get())),
                "--seed", str(int(self.v_seed.get())),
                "--fade", str(round(float(self.v_fade.get()), 3))]

        def work():
            env = dict(os.environ, PYTHONIOENCODING="utf-8")
            p = subprocess.run([sys.executable, os.path.join(ROOT, "draw.py")] + args,
                               capture_output=True, text=True, env=env, cwd=ROOT)
            ok = p.returncode == 0 and os.path.exists(out)
            self.root.after(0, lambda: self.done(ok, out, p.stderr[-300:]))

        threading.Thread(target=work, daemon=True).start()

    def done(self, ok, out, err):
        self.btn.config(state="normal", text="▶  רנדר סרט")
        if ok:
            mb = os.path.getsize(out) / 2 ** 20
            # NEVER auto-play: Sacred Audio Law. Show it in Explorer instead.
            subprocess.Popen(["explorer", "/select,", os.path.normpath(out)])
            self.status.config(text="נשמר · %.1f MB\n%s\n(לא הופעל — תלחץ אתה)"
                                    % (mb, os.path.basename(out)), fg="#8ec")
        else:
            self.status.config(text="הרנדר נכשל:\n%s" % err, fg="#e88")


if __name__ == "__main__":
    root = tk.Tk()
    Studio(root)
    root.mainloop()
