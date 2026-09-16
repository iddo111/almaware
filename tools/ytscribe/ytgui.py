"""YTGET — a window for yt-dlp, with our own transcriber wired in.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

Iddo, 2026-08-30: *"תעשה לי גואי בשבילו."*

Paste a link, pick what you want, press. The window does not decide anything for you —
it runs `yt-dlp`, shows you exactly what yt-dlp says, and stops. **You choose what to
download.**

The one thing it adds beyond yt-dlp: a **תמלל** button that sends what you downloaded
through our own ear (`large-v3-turbo` + the Hebrew LoRA on 127.0.0.1:8737), the same
pipeline as `ytscribe.py`. Nothing is uploaded anywhere.

Sacred Audio Law: this window never plays audio. It downloads, reads numbers, writes text.

    python ytgui.py
"""
from __future__ import annotations

import io
import os
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, ttk

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

YTDLP = os.path.expanduser(
    r"~/AppData/Local/Programs/Python/Python313/Scripts/yt-dlp.exe")
DEFAULT_DIR = r"D:\CLAUDE\downloads"

DENO = os.path.expanduser(
    r"~/AppData/Local/Microsoft/WinGet/Packages"
    r"/DenoLand.Deno_Microsoft.Winget.Source_8wekyb3d8bbwe/deno.exe")

ANTI_STALL = ([
    "--js-runtimes", "deno:" + DENO] if os.path.exists(DENO) else []) + [
    "--throttled-rate", "100K",
    "--socket-timeout", "20",
    "--retries", "10",
    "--fragment-retries", "20",
    "--retry-sleep", "linear=1::5",
    "--concurrent-fragments", "4",
    "--continue",
]

MODES = {
    "וידאו + אודיו (הכי טוב)": ["-f", "bestvideo+bestaudio/best"],
    "וידאו 1080p לכל היותר":   ["-f", "bestvideo[height<=1080]+bestaudio/best"],
    "אודיו בלבד — wav":        ["-x", "--audio-format", "wav"],
    "אודיו בלבד — mp3":        ["-x", "--audio-format", "mp3"],
    "כתוביות בלבד":            ["--skip-download", "--write-subs", "--write-auto-subs",
                                "--sub-langs", "he,en", "--sub-format", "vtt/best"],
}


class YtGet:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("YTGET — הורדה ותמלול")
        root.configure(bg="#14141c")
        root.geometry("860x600")
        self.proc = None
        self.last_files: list[str] = []

        pad = dict(padx=12, pady=5)
        top = tk.Frame(root, bg="#14141c")
        top.pack(fill="x", **pad)

        tk.Label(top, text="קישור", bg="#14141c", fg="#cfe",
                 font=("Segoe UI", 11, "bold")).pack(anchor="e")
        self.url = tk.StringVar()
        e = tk.Entry(top, textvariable=self.url, font=("Consolas", 11),
                     bg="#1e1e2a", fg="#fff", insertbackground="#fff", relief="flat")
        e.pack(fill="x", ipady=6)
        e.focus_set()
        e.bind("<Return>", lambda _=None: self.start())
        self._wire_paste(e)

        # 2026-08-30: Iddo could not put a link in the box at all. Cause: he has a HEBREW
        # keyboard layout loaded, and tkinter's built-in paste is bound by KEYSYM -- under
        # a non-Latin layout Ctrl+V produces a different keysym and the paste silently does
        # nothing. No error, no beep, just a box that refuses text. Fixed three ways so it
        # cannot depend on the layout at all: bind by KEYCODE, add Shift+Insert, add a
        # right-click menu, and put a button on screen that reads the clipboard directly.
        tk.Button(top, text="📋  הדבק קישור מהלוח", command=self.paste_clip,
                  bg="#2a3550", fg="#fff", relief="flat", font=("Segoe UI", 10)
                  ).pack(fill="x", pady=(6, 0))

        row = tk.Frame(root, bg="#14141c")
        row.pack(fill="x", **pad)
        tk.Label(row, text="מה להוריד", bg="#14141c", fg="#cfe",
                 font=("Segoe UI", 10)).pack(side="right", padx=(0, 8))
        self.mode = tk.StringVar(value=list(MODES)[0])
        ttk.Combobox(row, textvariable=self.mode, values=list(MODES),
                     state="readonly", width=26).pack(side="right")

        row2 = tk.Frame(root, bg="#14141c")
        row2.pack(fill="x", **pad)
        self.outdir = tk.StringVar(value=DEFAULT_DIR)
        tk.Button(row2, text="תיקיית יעד…", command=self.pick_dir, bg="#2a3550",
                  fg="#fff", relief="flat").pack(side="right")
        tk.Label(row2, textvariable=self.outdir, bg="#14141c", fg="#889",
                 font=("Consolas", 9)).pack(side="right", padx=10)

        btns = tk.Frame(root, bg="#14141c")
        btns.pack(fill="x", **pad)
        self.go = tk.Button(btns, text="▼  הורד", command=self.start, bg="#1f8a4c",
                            fg="#fff", relief="flat", font=("Segoe UI", 12, "bold"),
                            pady=6, width=14)
        self.go.pack(side="right")
        self.stop_btn = tk.Button(btns, text="עצור", command=self.stop, bg="#7a2d2d",
                                  fg="#fff", relief="flat", state="disabled", width=8)
        self.stop_btn.pack(side="right", padx=8)
        self.tr = tk.Button(btns, text="תמלל את מה שירד", command=self.transcribe,
                            bg="#2a3550", fg="#fff", relief="flat", state="disabled")
        self.tr.pack(side="right", padx=8)
        tk.Button(btns, text="פתח תיקייה", command=self.open_dir, bg="#2a3550",
                  fg="#fff", relief="flat").pack(side="right")

        self.log = tk.Text(root, bg="#0e0e14", fg="#b9c6d4", insertbackground="#fff",
                           font=("Consolas", 9), relief="flat", wrap="word")
        self.log.pack(fill="both", expand=True, padx=12, pady=(4, 12))
        self.say("yt-dlp: %s" % ("נמצא" if os.path.exists(YTDLP) else "לא נמצא! " + YTDLP))
        self.say("הדבק קישור ולחץ הורד. שום דבר לא מתנגן — רק יורד.\n")

    def paste_clip(self):
        """Read the clipboard ourselves. Layout-proof, and it also strips the stray
        spaces and newlines that come with a copied YouTube link."""
        try:
            t = self.root.clipboard_get()
        except tk.TclError:
            self.say("!! הלוח ריק")
            return
        t = (t or "").strip().split()[0] if (t or "").strip() else ""
        if not t:
            self.say("!! אין טקסט בלוח")
            return
        self.url.set(t)
        self.say("הודבק: " + t[:90])

    def _wire_paste(self, w: tk.Entry):
        def do_paste(_=None):
            self.paste_clip()
            return "break"

        def on_key(ev):
            # keycode 86 is the physical V key on every Windows layout; keysym is not
            if (ev.state & 0x4) and ev.keycode in (86, 45):      # Ctrl+V, Ctrl+Insert
                return do_paste()
            if (ev.state & 0x1) and ev.keycode == 45:            # Shift+Insert
                return do_paste()
            return None

        w.bind("<Key>", on_key)
        w.bind("<<Paste>>", do_paste)
        w.bind("<Button-3>", lambda e: menu.tk_popup(e.x_root, e.y_root))
        menu = tk.Menu(w, tearoff=0)
        menu.add_command(label="הדבק", command=self.paste_clip)
        menu.add_command(label="נקה", command=lambda: self.url.set(""))

    # ------------------------------------------------------------------ ui

    def say(self, s: str):
        self.log.insert("end", s.rstrip() + "\n")
        self.log.see("end")

    def pick_dir(self):
        d = filedialog.askdirectory(initialdir=self.outdir.get() or DEFAULT_DIR)
        if d:
            self.outdir.set(d)

    def open_dir(self):
        d = self.outdir.get()
        if os.path.isdir(d):
            subprocess.Popen(["explorer", os.path.normpath(d)])

    # ------------------------------------------------------------ download

    def start(self):
        url = self.url.get().strip()
        if not url:
            self.say("!! אין קישור")
            return
        if not os.path.exists(YTDLP):
            self.say("!! yt-dlp לא נמצא")
            return
        d = self.outdir.get() or DEFAULT_DIR
        os.makedirs(d, exist_ok=True)
        args = ([YTDLP] + MODES[self.mode.get()] + ANTI_STALL +
                ["--newline",                      # one progress line at a time, parseable
                 "--print", "after_move:FILE %(filepath)s",
                 "-o", os.path.join(d, "%(title)s.%(ext)s"), url])
        self.last_files = []
        self.go.config(state="disabled", text="מוריד…")
        self.stop_btn.config(state="normal")
        self.tr.config(state="disabled")
        self.say("\n--- %s ---" % self.mode.get())

        def work():
            try:
                self.proc = subprocess.Popen(
                    args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding="utf-8", errors="replace", bufsize=1,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                for line in self.proc.stdout:
                    line = line.rstrip()
                    if line.startswith("FILE "):
                        self.last_files.append(line[5:].strip())
                    self.root.after(0, self.say, line)
                rc = self.proc.wait()
            except Exception as ex:                                    # noqa: BLE001
                rc = -1
                self.root.after(0, self.say, "!! %s" % ex)
            self.root.after(0, self.done, rc)

        threading.Thread(target=work, daemon=True).start()

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            self.say("-- נעצר --")

    def done(self, rc):
        self.go.config(state="normal", text="▼  הורד")
        self.stop_btn.config(state="disabled")
        if self.last_files:
            self.say("\n== ירדו %d קבצים ==" % len(self.last_files))
            for f in self.last_files:
                self.say("   " + f)
            self.tr.config(state="normal")
        self.say("== yt-dlp סיים, קוד %d ==" % rc)

    # ---------------------------------------------------------- transcribe

    def transcribe(self):
        audio = [f for f in self.last_files
                 if f.lower().endswith((".wav", ".mp3", ".m4a", ".webm", ".mp4", ".mkv"))]
        if not audio:
            self.say("!! אין קובץ מדיה לתמלל")
            return
        self.tr.config(state="disabled", text="מתמלל…")
        self.say("\n--- תמלול דרך האוזן שלנו (127.0.0.1:8737) ---")

        def work():
            import ytscribe as Y
            for src in audio:
                try:
                    wav = src
                    if not src.lower().endswith(".wav"):
                        wav = os.path.splitext(src)[0] + ".16k.wav"
                        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src,
                                        "-ar", "16000", "-ac", "1", wav], check=True)
                    self.root.after(0, self.say, "  " + os.path.basename(wav))
                    text = Y.transcribe(wav, "auto")
                    out = os.path.splitext(src)[0] + ".txt"
                    io.open(out, "w", encoding="utf-8").write(text + "\n")
                    self.root.after(0, self.say, "  נשמר: %s (%d תווים)" % (out, len(text)))
                except Exception as ex:                                # noqa: BLE001
                    self.root.after(0, self.say, "  !! %s" % ex)
            self.root.after(0, lambda: self.tr.config(state="normal",
                                                      text="תמלל את מה שירד"))

        threading.Thread(target=work, daemon=True).start()


if __name__ == "__main__":
    root = tk.Tk()
    YtGet(root)
    root.mainloop()
