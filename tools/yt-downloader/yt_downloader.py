"""
YouTube / Video Downloader — native Tkinter GUI
Uses yt-dlp. Supports video (mp4/best), audio-only (mp3), and playlist.
"""
from __future__ import annotations
import os, sys, threading, subprocess, tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path

DEFAULT_OUT = str(Path.home() / "Downloads")
VENV_YTDLP = r"D:\ai-movie-maker\ComfyUI\venv\Scripts\yt-dlp.exe"
SYS_YTDLP = "yt-dlp"

def find_ytdlp():
    if Path(VENV_YTDLP).exists():
        return VENV_YTDLP
    try:
        subprocess.run([SYS_YTDLP, "--version"], capture_output=True, check=True)
        return SYS_YTDLP
    except Exception:
        return None

class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("YT Downloader")
        root.geometry("680x420")
        root.configure(bg="#141413")
        root.resizable(True, False)
        self._build()
        self.ytdlp = find_ytdlp()
        if not self.ytdlp:
            self._log("yt-dlp not found — install it: pip install yt-dlp")

    def _build(self):
        BG, FG, ACC = "#141413", "#faf9f5", "#d97757"
        S = {"bg": BG, "fg": FG, "font": ("Segoe UI", 10)}
        def lbl(parent, text, **kw):
            return tk.Label(parent, text=text, **S, **kw)
        def entry(parent, textvariable, width=60):
            e = tk.Entry(parent, textvariable=textvariable, bg="#2a2926", fg=FG,
                         insertbackground=FG, relief="flat", font=("Segoe UI", 10), width=width)
            return e
        def btn(parent, text, cmd, accent=False):
            b = tk.Button(parent, text=text, command=cmd,
                          bg=ACC if accent else "#2a2926", fg="white", relief="flat",
                          font=("Segoe UI", 10, "bold"), padx=10, pady=5, cursor="hand2",
                          activebackground="#e88566", activeforeground="white")
            return b

        top = tk.Frame(self.root, bg=BG, padx=16, pady=12)
        top.pack(fill="x")

        # URL
        lbl(top, "URL").grid(row=0, column=0, sticky="w", pady=4)
        self.url_var = tk.StringVar()
        entry(top, self.url_var, 55).grid(row=0, column=1, sticky="ew", padx=(8,0), pady=4)
        top.columnconfigure(1, weight=1)

        # Output folder
        lbl(top, "Save to").grid(row=1, column=0, sticky="w", pady=4)
        self.out_var = tk.StringVar(value=DEFAULT_OUT)
        entry(top, self.out_var, 48).grid(row=1, column=1, sticky="ew", padx=(8,4), pady=4)
        btn(top, "…", self._browse).grid(row=1, column=2, padx=4)

        # Format
        fmt_frame = tk.Frame(self.root, bg=BG, padx=16)
        fmt_frame.pack(fill="x")
        lbl(fmt_frame, "Format:").pack(side="left")
        self.fmt_var = tk.StringVar(value="video")
        for val, label in [("video","Best video (mp4)"),("audio","Audio only (mp3)"),("playlist","Playlist (all)")]:
            tk.Radiobutton(fmt_frame, text=label, variable=self.fmt_var, value=val,
                           bg=BG, fg=FG, selectcolor="#2a2926", activebackground=BG,
                           font=("Segoe UI", 10)).pack(side="left", padx=8)

        # Quality selector (video only)
        q_frame = tk.Frame(self.root, bg=BG, padx=16, pady=4)
        q_frame.pack(fill="x")
        lbl(q_frame, "Quality:").pack(side="left")
        self.qual_var = tk.StringVar(value="1080")
        for q in ["2160","1080","720","480","best"]:
            tk.Radiobutton(q_frame, text=q, variable=self.qual_var, value=q,
                           bg=BG, fg=FG, selectcolor="#2a2926", activebackground=BG,
                           font=("Segoe UI", 10)).pack(side="left", padx=6)

        # Buttons
        btn_frame = tk.Frame(self.root, bg=BG, padx=16, pady=8)
        btn_frame.pack(fill="x")
        btn(btn_frame, "Download", self._start, accent=True).pack(side="left")
        btn(btn_frame, "Open folder", self._open_folder).pack(side="left", padx=8)
        self.progress = ttk.Progressbar(btn_frame, mode="indeterminate", length=200)
        self.progress.pack(side="left", padx=8)

        # Log
        log_frame = tk.Frame(self.root, bg=BG, padx=16, pady=4)
        log_frame.pack(fill="both", expand=True)
        self.log = tk.Text(log_frame, bg="#0d0d0c", fg="#b0aea5", font=("Consolas", 9),
                           relief="flat", height=8, state="disabled")
        sb = ttk.Scrollbar(log_frame, command=self.log.yview)
        self.log.configure(yscrollcommand=sb.set)
        self.log.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

    def _browse(self):
        d = filedialog.askdirectory(initialdir=self.out_var.get())
        if d:
            self.out_var.set(d)

    def _open_folder(self):
        os.startfile(self.out_var.get())

    def _log(self, msg: str):
        self.log.configure(state="normal")
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _start(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("No URL", "Paste a YouTube or video URL first.")
            return
        if not self.ytdlp:
            messagebox.showerror("yt-dlp missing", "Install yt-dlp: pip install yt-dlp")
            return
        threading.Thread(target=self._run, args=(url,), daemon=True).start()

    def _run(self, url: str):
        self.root.after(0, self.progress.start)
        fmt = self.fmt_var.get()
        qual = self.qual_var.get()
        out = self.out_var.get()

        if fmt == "audio":
            cmd = [self.ytdlp, "-x", "--audio-format", "mp3",
                   "-o", f"{out}/%(title)s.%(ext)s", url]
        elif fmt == "playlist":
            cmd = [self.ytdlp, "-f", f"bestvideo[height<={qual}]+bestaudio/best" if qual != "best" else "best",
                   "--merge-output-format", "mp4",
                   "-o", f"{out}/%(playlist_title)s/%(playlist_index)s - %(title)s.%(ext)s", url]
        else:
            fmt_str = f"bestvideo[height<={qual}]+bestaudio/best[height<={qual}]/best" if qual != "best" else "best"
            cmd = [self.ytdlp, "-f", fmt_str, "--merge-output-format", "mp4",
                   "-o", f"{out}/%(title)s.%(ext)s", url]

        self.root.after(0, lambda: self._log(f"▶ {' '.join(cmd[:3])} … {url}"))
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, encoding="utf-8", errors="replace")
            for line in proc.stdout:
                line = line.rstrip()
                if line:
                    self.root.after(0, lambda l=line: self._log(l))
            proc.wait()
            msg = "Done!" if proc.returncode == 0 else f"Exit code {proc.returncode}"
            self.root.after(0, lambda: self._log(msg))
        except Exception as e:
            self.root.after(0, lambda: self._log(f"Error: {e}"))
        finally:
            self.root.after(0, self.progress.stop)

def main():
    root = tk.Tk()
    try: root.option_add("*Font", "{Segoe UI} 10")
    except: pass
    App(root)
    root.mainloop()

if __name__ == "__main__":
    main()
