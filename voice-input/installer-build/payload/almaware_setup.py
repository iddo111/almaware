"""almaware_setup.py — ALMAWARE Hebrew Mic FIRST-RUN setup.

Runs ONCE, the first time the app is launched (the launcher calls this when the
.venv / .setup_complete marker is missing). Shows a small progress window and:

  1. Locates a system Python 3.10-3.12 (the heavy deps don't have 3.13 wheels for
     all packages yet, so we prefer 3.10-3.12; falls back to whatever launched us).
  2. Creates a virtual environment in <app>\.venv.
  3. pip-installs the requirements. If an NVIDIA GPU is detected (nvidia-smi),
     uses requirements-gpu.txt for CUDA acceleration; otherwise requirements.txt.
  4. Triggers the Whisper model download from Hugging Face (faster-whisper fetches
     ivrit-ai/whisper-large-v3-turbo-ct2 + the base multilingual model on first
     load; ~2-3 GB). This needs INTERNET and may take several minutes.
  5. Writes a .setup_complete marker so this never re-runs.

Everything is logged to <app>\history\setup.log. Closing the window cancels.

לזכרה של עלמה ז"ל — iddoperez.ai
"""
import os
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
VENV = os.path.join(HERE, ".venv")
VENV_PY = os.path.join(VENV, "Scripts", "python.exe")
MARKER = os.path.join(HERE, ".setup_complete")
LOG = os.path.join(HERE, "history", "setup.log")
REQ_CPU = os.path.join(HERE, "requirements.txt")
REQ_GPU = os.path.join(HERE, "requirements-gpu.txt")
CREATE_NO_WINDOW = 0x08000000


def log(msg):
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {msg}"
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def find_system_python():
    """Find a Python 3.10-3.12 interpreter for the venv. Prefer the py launcher;
    fall back to the interpreter that launched us."""
    # Preference order: best-tested (3.12..3.10) first, then 3.13/3.11, then the
    # launcher's default, then whatever launched us. faster-whisper/ctranslate2
    # publish wheels for 3.9-3.13, so 3.13 also works; we just prefer the most-
    # tested 3.10-3.12 when present.
    probe = "import sys;print(sys.executable)"
    cmds = []
    for ver in ("3.12", "3.11", "3.10", "3.13"):
        cmds.append(["py", f"-{ver}", "-c", probe])
    cmds.append(["py", "-c", probe])  # launcher default
    for c in cmds:
        try:
            out = subprocess.check_output(c, creationflags=CREATE_NO_WINDOW,
                                          stderr=subprocess.DEVNULL, text=True)
            exe = out.strip()
            if exe and os.path.isfile(exe):
                return exe
        except Exception:
            pass
    # fall back to the interpreter running this script
    return sys.executable


def has_nvidia_gpu():
    try:
        subprocess.check_output(["nvidia-smi"], creationflags=CREATE_NO_WINDOW,
                                stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False


def run_setup(progress, status, done_cb):
    """Worker thread: build venv, install deps, download model."""
    try:
        py = find_system_python()
        log(f"system python: {py}")
        status(f"Using Python: {py}")
        progress(5)

        # 1) venv
        if not os.path.isfile(VENV_PY):
            status("Creating virtual environment (.venv)…")
            log("creating venv")
            rc = subprocess.call([py, "-m", "venv", VENV],
                                 creationflags=CREATE_NO_WINDOW)
            if rc != 0 or not os.path.isfile(VENV_PY):
                raise RuntimeError("venv creation failed")
        progress(15)

        # 2) pip upgrade
        status("Upgrading pip…")
        log("pip upgrade")
        subprocess.call([VENV_PY, "-m", "pip", "install", "--upgrade", "pip"],
                        creationflags=CREATE_NO_WINDOW)
        progress(25)

        # 3) install requirements (GPU if NVIDIA present)
        gpu = has_nvidia_gpu()
        req = REQ_GPU if (gpu and os.path.isfile(REQ_GPU)) else REQ_CPU
        status(f"Installing dependencies ({'GPU/CUDA' if gpu else 'CPU'})… this can take several minutes.")
        log(f"pip install -r {req}  (gpu={gpu})")
        rc = subprocess.call([VENV_PY, "-m", "pip", "install", "-r", req],
                             cwd=HERE, creationflags=CREATE_NO_WINDOW)
        if rc != 0:
            raise RuntimeError("pip install failed — see history\\setup.log")
        progress(60)

        # 4) download the Whisper model (faster-whisper fetches on first load)
        status("Downloading the Hebrew Whisper model from Hugging Face (~2-3 GB)…\nThis needs internet and may take several minutes.")
        log("downloading model via faster-whisper")
        dl = (
            "import sys;"
            "from faster_whisper import WhisperModel;"
            "import faster_whisper.utils as u;"
            # download the primary Hebrew model + the base multilingual model
            "print('downloading ivrit-ai turbo...');"
            "WhisperModel('ivrit-ai/whisper-large-v3-turbo-ct2', device='cpu', compute_type='int8');"
            "print('downloading base multilingual...');"
            "WhisperModel('mobiuslabsgmbh/faster-whisper-large-v3-turbo', device='cpu', compute_type='int8');"
            "print('model ready')"
        )
        rc = subprocess.call([VENV_PY, "-c", dl], cwd=HERE,
                             creationflags=CREATE_NO_WINDOW)
        if rc != 0:
            # Non-fatal: the app will retry the download on first real launch.
            # We still mark setup complete so deps don't reinstall; the model
            # downloads on first mic start instead.
            log("model pre-download returned nonzero — will download on first launch")
            status("Dependencies installed. The model will download on first mic start.")
        progress(95)

        # 5) marker
        with open(MARKER, "w", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S") + "\n")
        log("setup complete")
        progress(100)
        status("Setup complete. Starting the Hebrew Mic…")
        time.sleep(1.0)
        done_cb(True, None)
    except Exception as e:
        log(f"SETUP FAILED: {e!r}")
        done_cb(False, str(e))


def main():
    # already done?
    if os.path.isfile(VENV_PY) and os.path.isfile(MARKER):
        sys.exit(0)

    try:
        import tkinter as tk
        from tkinter import ttk
    except Exception:
        # No Tk — run headless (still works, just no window).
        result = {"ok": False, "err": None}
        run_setup(lambda p: None, lambda s: log(s),
                  lambda ok, err: result.update(ok=ok, err=err))
        sys.exit(0 if result["ok"] else 1)

    root = tk.Tk()
    root.title("ALMAWARE Hebrew Mic — First-Run Setup")
    root.configure(bg="#ffffff")
    try:
        ico = os.path.join(HERE, "mic.ico")
        if os.path.isfile(ico):
            root.iconbitmap(ico)
    except Exception:
        pass
    w, h = 540, 260
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    root.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 3}")

    tk.Label(root, text="ALMAWARE Hebrew Mic", font=("Segoe UI", 16, "bold"),
             fg="#1a1a1a", bg="#ffffff").pack(pady=(18, 2))
    tk.Label(root, text="Preparing your microphone (one-time setup)",
             font=("Segoe UI", 10), fg="#444444", bg="#ffffff").pack()

    status_var = tk.StringVar(value="Starting…")
    status_lbl = tk.Label(root, textvariable=status_var, font=("Segoe UI", 9),
                          fg="#222222", bg="#ffffff", wraplength=480, justify="center")
    status_lbl.pack(pady=(16, 8), padx=20)

    bar = ttk.Progressbar(root, orient="horizontal", length=460, mode="determinate",
                          maximum=100)
    bar.pack(pady=6)

    tk.Label(root, text='לזכרה של עלמה ז"ל — iddoperez.ai', font=("Segoe UI", 8),
             fg="#888888", bg="#ffffff").pack(side="bottom", pady=8)

    def set_progress(v):
        root.after(0, lambda: bar.configure(value=v))

    def set_status(s):
        root.after(0, lambda: status_var.set(s))

    def on_done(ok, err):
        def finish():
            if ok:
                root.destroy()
            else:
                status_var.set(f"Setup failed: {err}\nSee history\\setup.log. Close and retry.")
        root.after(0, finish)

    t = threading.Thread(target=run_setup,
                         args=(set_progress, set_status, on_done), daemon=True)
    t.start()
    root.mainloop()
    # exit code: success if marker written
    sys.exit(0 if os.path.isfile(MARKER) else 1)


if __name__ == "__main__":
    main()
