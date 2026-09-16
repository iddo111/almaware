"""ALMAWARE Hebrew Mic — desktop launcher (compiled to ALMAWARE-HebMic.exe).

Click the icon → the "🎤 Hebrew Mic" window appears.

How (deliberately dead-simple so the frozen exe can NEVER throw the PyInstaller
"Unhandled exception in script" dialog — every step is wrapped):
  1. Touch a `.show_request` file. If the mic is already running, its UI sees the
     file on its next poll and surfaces its own window (native — no ctypes here).
  2. Start the mic via supervisor.py. If it's already running, supervisor's
     named-mutex singleton makes this a harmless no-op; if not, it starts it and
     the window appears (before the model load, so within ~1s).

No ctypes, no EnumWindows, no ShowWindow/SetForegroundWindow. The previous
version did window-surfacing with ctypes inside the frozen exe and crashed.
"""
import os
import subprocess

VOICE = r"D:\CLAUDE\voice-input"
PYW = r"C:\Users\<user>\AppData\Local\Programs\Python\Python312\pythonw.exe"
CREATE_NO_WINDOW = 0x08000000


def main():
    # 1) ask any already-running UI to surface its window
    try:
        open(os.path.join(VOICE, ".show_request"), "w").close()
    except Exception:
        pass
    # 2) start the mic (no-op if already running — supervisor singleton-guards)
    try:
        if os.path.exists(PYW) and os.path.isdir(VOICE):
            subprocess.Popen([PYW, "supervisor.py"], cwd=VOICE,
                             creationflags=CREATE_NO_WINDOW)
    except Exception:
        pass


try:
    main()
except Exception:
    pass
