"""ALMAWARE Hebrew Mic - one-click launcher (.exe entry point).

Double-clicking the built .exe boots the always-on diamond watchdog
(supervisor.py), which starts the Hebrew mic + floating GUI panel
(ui_toggle.py). Silent (no console), singleton-safe (supervisor's own
guard prevents duplicates), and uses the already-configured Python +
GPU DLLs - so the .exe stays small (~8 MB) instead of a 1-3 GB freeze.

"""
import ctypes
import os
import subprocess

DIR = r"D:\CLAUDE\voice-input"
PYW_CANDIDATES = [
    r"C:\Users\<user>\AppData\Local\Programs\Python\Python312\pythonw.exe",
    r"C:\Users\<user>\AppData\Local\Programs\Python\Python311\pythonw.exe",
    "pythonw.exe",
]

CREATE_NO_WINDOW = 0x08000000
DETACHED_PROCESS = 0x00000008

def main() -> None:
    pyw = next((p for p in PYW_CANDIDATES if p == "pythonw.exe" or os.path.exists(p)),
               "pythonw.exe")
    supervisor = os.path.join(DIR, "supervisor.py")
    try:
        subprocess.Popen(
            [pyw, supervisor],
            cwd=DIR,
            creationflags=CREATE_NO_WINDOW | DETACHED_PROCESS,
            close_fds=True,
        )
        ctypes.windll.user32.MessageBoxW(
            0,
            "\U0001F3A4 ALMAWARE Hebrew Mic is ON.\n\nSpeak and it types. "
            "The floating panel appears at the top-right.\n\n"ל",
            "ALMAWARE Mic",
            0x40,  # MB_ICONINFORMATION
        )
    except Exception as e:  # pragma: no cover - last-resort visibility
        ctypes.windll.user32.MessageBoxW(
            0, f"Failed to start mic:\n{e}", "ALMAWARE Mic", 0x10)

if __name__ == "__main__":
    main()
