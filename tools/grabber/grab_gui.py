"""
Generic Media Grabber — GUI front-end.

Tkinter window: paste URLs (one per line), pick options, hit Start.
Live log streams the per-URL progress.

Run:
    python D:\\CLAUDE\\tools\\grabber\\grab_gui.py
or via the .cmd shortcut:
    grab_gui.cmd
"""
from __future__ import annotations
import os
import queue
import subprocess
import sys
import threading
from pathlib import Path

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

ROOT = Path(__file__).parent
GRAB_PY = ROOT / "grab.py"
OUT = ROOT / "downloads"
OUT.mkdir(parents=True, exist_ok=True)

# Force UTF-8 stdout/stderr on Windows so Hebrew titles don't crash
if sys.platform == "win32":
    import io
    for s in ("stdout", "stderr"):
        try:
            getattr(sys, s).reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


class GrabberApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("Media Grabber  ·  iddoperez.ai")
        root.geometry("980x720")
        root.configure(bg="#141413")

        # palette
        self.NAVY = "#1a2238"
        self.BONE = "#f4ecd8"
        self.COPPER = "#b8651a"
        self.INK = "#0a0a0a"
        self.PANEL = "#1f1e1c"
        self.TEXT = "#faf9f5"
        self.MUTED = "#b0aea5"

        self.proc: subprocess.Popen | None = None
        self.log_queue: queue.Queue[str] = queue.Queue()

        self._build_ui()
        self.root.after(100, self._drain_log_queue)

    def _build_ui(self):
        # Header
        hdr = tk.Frame(self.root, bg=self.NAVY, height=56)
        hdr.pack(side="top", fill="x")
        tk.Label(hdr, text="Media Grabber", bg=self.NAVY, fg=self.BONE,
                 font=("Segoe UI", 14, "bold"), padx=18, pady=10).pack(side="left")
        tk.Label(hdr, text="iddoperez.ai", bg=self.NAVY, fg=self.MUTED,
                 font=("Segoe UI", 9)).pack(side="right", padx=14)

        # Body — two columns
        body = tk.Frame(self.root, bg=self.INK)
        body.pack(fill="both", expand=True, padx=14, pady=14)

        # Left: URL input
        left = tk.Frame(body, bg=self.INK)
        left.pack(side="left", fill="both", expand=True, padx=(0, 10))

        tk.Label(left, text="URLs  ·  one per line  ·  # for comments",
                 bg=self.INK, fg=self.MUTED, font=("Segoe UI", 9, "bold")).pack(anchor="w")

        url_frame = tk.Frame(left, bg=self.PANEL)
        url_frame.pack(fill="both", expand=True, pady=(4, 8))
        self.url_text = tk.Text(url_frame, bg=self.PANEL, fg=self.TEXT,
                                insertbackground=self.TEXT, font=("Consolas", 10),
                                bd=0, padx=10, pady=10, wrap="none", undo=True)
        sbv = ttk.Scrollbar(url_frame, orient="vertical", command=self.url_text.yview)
        sbh = ttk.Scrollbar(url_frame, orient="horizontal", command=self.url_text.xview)
        self.url_text.configure(yscrollcommand=sbv.set, xscrollcommand=sbh.set)
        self.url_text.grid(row=0, column=0, sticky="nsew")
        sbv.grid(row=0, column=1, sticky="ns")
        sbh.grid(row=1, column=0, sticky="ew")
        url_frame.grid_rowconfigure(0, weight=1)
        url_frame.grid_columnconfigure(0, weight=1)

        # Buttons row under the URL box
        btnrow = tk.Frame(left, bg=self.INK)
        btnrow.pack(fill="x")
        self._btn(btnrow, "Paste from clipboard", self._paste_clip).pack(side="left", padx=(0, 6))
        self._btn(btnrow, "Load .txt list…", self._load_list).pack(side="left", padx=6)
        self._btn(btnrow, "Clear", self._clear_urls).pack(side="left", padx=6)

        # Right: options panel
        right = tk.Frame(body, bg=self.PANEL, width=280)
        right.pack(side="right", fill="y")
        right.pack_propagate(False)

        tk.Label(right, text="OPTIONS", bg=self.PANEL, fg=self.MUTED,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=12, pady=(12, 6))

        # Audio-only
        self.audio_var = tk.BooleanVar(value=False)
        tk.Checkbutton(right, text="Audio only (MP3, best quality)",
                       variable=self.audio_var,
                       bg=self.PANEL, fg=self.TEXT, selectcolor=self.PANEL,
                       activebackground=self.PANEL, activeforeground=self.COPPER,
                       font=("Segoe UI", 10), bd=0, padx=12).pack(anchor="w")

        # Backend
        tk.Label(right, text="Backend", bg=self.PANEL, fg=self.MUTED,
                 font=("Segoe UI", 9)).pack(anchor="w", padx=12, pady=(14, 2))
        self.backend_var = tk.StringVar(value="auto")
        backend_box = ttk.Combobox(right, textvariable=self.backend_var,
                                   values=["auto", "ytdlp", "gallery"],
                                   state="readonly", width=22)
        backend_box.pack(anchor="w", padx=12)

        # Concurrency
        tk.Label(right, text="Parallel downloads", bg=self.PANEL, fg=self.MUTED,
                 font=("Segoe UI", 9)).pack(anchor="w", padx=12, pady=(14, 2))
        self.concurrent_var = tk.IntVar(value=1)
        conc_frame = tk.Frame(right, bg=self.PANEL)
        conc_frame.pack(anchor="w", padx=12)
        self.conc_scale = tk.Scale(conc_frame, from_=1, to=8, orient="horizontal",
                                   variable=self.concurrent_var, length=200,
                                   bg=self.PANEL, fg=self.TEXT, troughcolor="#2a2926",
                                   activebackground=self.COPPER, highlightthickness=0,
                                   bd=0, font=("Segoe UI", 9))
        self.conc_scale.pack()

        # Output dir
        tk.Label(right, text="Output", bg=self.PANEL, fg=self.MUTED,
                 font=("Segoe UI", 9)).pack(anchor="w", padx=12, pady=(14, 2))
        out_frame = tk.Frame(right, bg=self.PANEL)
        out_frame.pack(fill="x", padx=12)
        self.out_label = tk.Label(out_frame, text=str(OUT), bg="#2a2926", fg=self.TEXT,
                                   font=("Consolas", 8), anchor="w", padx=8, pady=4,
                                   wraplength=240, justify="left")
        self.out_label.pack(fill="x", pady=(0, 6))
        self._btn(right, "Open output folder", self._open_output).pack(anchor="w", padx=12)

        # Big action buttons
        action_frame = tk.Frame(right, bg=self.PANEL)
        action_frame.pack(side="bottom", fill="x", padx=12, pady=12)
        self.start_btn = self._btn(action_frame, "▶  START GRAB", self._start_grab, accent=True, big=True)
        self.start_btn.pack(fill="x", pady=(0, 6))
        self.stop_btn = self._btn(action_frame, "■  STOP", self._stop_grab, big=True)
        self.stop_btn.pack(fill="x")
        self.stop_btn.configure(state="disabled")

        # Bottom: log + status
        bottom = tk.Frame(self.root, bg=self.INK)
        bottom.pack(fill="both", expand=False, padx=14, pady=(0, 8))

        tk.Label(bottom, text="LOG", bg=self.INK, fg=self.MUTED,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w")

        log_frame = tk.Frame(bottom, bg=self.PANEL)
        log_frame.pack(fill="both", expand=True, pady=(4, 0))
        self.log = tk.Text(log_frame, bg="#0f1410", fg="#9fd9a8",
                           font=("Consolas", 9), bd=0, padx=10, pady=8,
                           wrap="word", height=14, state="disabled")
        sb = ttk.Scrollbar(log_frame, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=sb.set)
        self.log.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        # Status bar
        self.status = tk.Label(self.root, text="Ready",
                               bg="#0a0a09", fg=self.MUTED,
                               anchor="w", font=("Segoe UI", 9), padx=12, pady=4)
        self.status.pack(side="bottom", fill="x")

    # ── helpers ──
    def _btn(self, parent, text, cmd, accent=False, big=False):
        bg = self.COPPER if accent else "#2a2926"
        return tk.Button(parent, text=text, command=cmd,
                         bg=bg, fg=self.TEXT, relief="flat",
                         padx=14, pady=8 if big else 5,
                         font=("Segoe UI", 11 if big else 10, "bold"),
                         activebackground="#e88566" if accent else "#3a3937",
                         activeforeground=self.TEXT, cursor="hand2", bd=0)

    def _paste_clip(self):
        try:
            t = self.root.clipboard_get()
            self.url_text.insert("end", t.strip() + "\n")
        except Exception as e:
            self._set_status(f"Clipboard read failed: {e}")

    def _load_list(self):
        path = filedialog.askopenfilename(title="Open URL list",
                                          filetypes=[("Text", "*.txt"), ("All", "*.*")])
        if not path:
            return
        try:
            self.url_text.insert("end", Path(path).read_text(encoding="utf-8") + "\n")
            self._set_status(f"Loaded {path}")
        except Exception as e:
            messagebox.showerror("Load failed", str(e))

    def _clear_urls(self):
        self.url_text.delete("1.0", "end")

    def _open_output(self):
        try:
            os.startfile(str(OUT))  # type: ignore[attr-defined]
        except Exception as e:
            messagebox.showerror("Cannot open", str(e))

    # ── log handling ──
    def _set_status(self, text: str):
        self.status.configure(text=text)

    def _log(self, line: str):
        self.log.configure(state="normal")
        self.log.insert("end", line + ("\n" if not line.endswith("\n") else ""))
        self.log.see("end")
        self.log.configure(state="disabled")

    def _drain_log_queue(self):
        try:
            while True:
                line = self.log_queue.get_nowait()
                if line is None:
                    self._on_grab_done()
                else:
                    self._log(line)
        except queue.Empty:
            pass
        self.root.after(80, self._drain_log_queue)

    # ── start / stop ──
    def _start_grab(self):
        raw = self.url_text.get("1.0", "end").strip()
        urls = [l.strip() for l in raw.splitlines() if l.strip() and not l.strip().startswith("#")]
        if not urls:
            messagebox.showwarning("No URLs", "Paste one or more URLs first.")
            return

        cmd = [sys.executable, str(GRAB_PY)]
        if self.backend_var.get() != "auto":
            cmd += ["--backend", self.backend_var.get()]
        if self.audio_var.get():
            cmd += ["--audio-only"]
        cmd += ["--concurrent", str(self.concurrent_var.get())]
        cmd += urls

        self._log("=" * 60)
        self._log(f"$ python grab.py [...] {len(urls)} URL(s)")
        self._set_status(f"Running — {len(urls)} URL(s)…")
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")

        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"
        creationflags = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW

        self.proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
            env=env, creationflags=creationflags,
        )
        threading.Thread(target=self._reader_thread, daemon=True).start()

    def _reader_thread(self):
        assert self.proc is not None
        try:
            for line in iter(self.proc.stdout.readline, ""):
                if not line:
                    break
                self.log_queue.put(line.rstrip("\n"))
            self.proc.wait()
            self.log_queue.put(f"=== exit code: {self.proc.returncode} ===")
        except Exception as e:
            self.log_queue.put(f"reader error: {e!r}")
        finally:
            self.log_queue.put(None)  # sentinel: done

    def _on_grab_done(self):
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        rc = self.proc.returncode if self.proc else None
        self._set_status(f"Done. Exit code: {rc}")
        self.proc = None

    def _stop_grab(self):
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
                self._log("--- terminate signal sent ---")
            except Exception as e:
                self._log(f"terminate failed: {e!r}")


def main():
    root = tk.Tk()
    try:
        root.option_add("*Font", "{Segoe UI} 10")
    except Exception:
        pass
    GrabberApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
