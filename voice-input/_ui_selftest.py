"""Isolated self-test for the NEW ui_toggle behavior (signal-file surface).
Runs ui_toggle.run() with dummy state in a throwaway window, and a background
thread that: (a) confirms the window mapped, (b) touches .show_request and
confirms the poll CONSUMES it (proves icon->surface works), then quits.
Prints PASS/FAIL lines and exits. Does NOT touch the audio device.
"""
import os, threading, time, sys
import ui_toggle

RESULT = {"window_seen": False, "signal_consumed": False}

state = {"armed": True, "status": "selftest", "target": "claude", "mic_name": "TEST-DEV",
         "mode": "normal", "rms_level": 0.1, "rms_raw": 42, "last_lang": "he",
         "transcript": ["בדיקה עצמית", "self test"]}
lock = threading.Lock()
targets = {"claude": None, "chrome": None, "notepad": None}
def cb(k, v):
    pass

def driver():
    # give the window time to map
    time.sleep(2.0)
    # crude "window exists" check via win32 by title
    try:
        import ctypes
        h = ctypes.windll.user32.FindWindowW(None, "\U0001f3a4 Hebrew Mic")
        RESULT["window_seen"] = bool(h)
    except Exception:
        pass
    # touch the signal file; the running poll should delete it within ~120ms
    try:
        open(ui_toggle.SHOW_REQUEST, "w").close()
    except Exception:
        pass
    time.sleep(0.8)
    RESULT["signal_consumed"] = not os.path.exists(ui_toggle.SHOW_REQUEST)
    print("SELFTEST window_seen   =", RESULT["window_seen"], flush=True)
    print("SELFTEST signal_consumed =", RESULT["signal_consumed"], flush=True)
    # close everything
    os._exit(0 if (RESULT["window_seen"] and RESULT["signal_consumed"]) else 3)

threading.Thread(target=driver, daemon=True).start()
ui_toggle.run(state, lock, targets, cb)
