"""KESHEV UIPI selftest — the RECEIVING window (spawned by client/selftest.py).

A separate process with a plain Win32 (tk) window: it inherits the spawner's
integrity level, so typing into it crosses a real process boundary and is
subject to the same UIPI check as Iddo's elevated terminals (criterion 8:
"a same-integrity child"). Whatever actually LANDS in the text box is written
to the got-file — reading THAT is the honest check, never the sender's return
value (scar 19: "TYPED ok" lied for weeks).

argv: got_file ready_file done_file [title] [spin]
  got_file    where the received text is written on exit
  ready_file  written once the window is up: JSON {"hwnd": .., "pid": ..}
  done_file   the parent creates this file when it wants the text flushed
  title       window title (must NOT contain 'keshev' — that is the guard's
              own-window marker; the default is a neutral nonce)
  spin        if "spin", rewrite the title every 100ms like a terminal
              spinner (scar 34: identity is HWND+PID+exe, never the caption)

Ported as knowledge from alma-mic _uipi_target.py; hardened with an explicit
ready/done handshake instead of a fixed timer.
"""
from __future__ import annotations

import ctypes
import json
import os
import sys
import tkinter as tk

HARD_TIMEOUT_S = 60
SPINNER = "⠂⠐⠠⠂⠈⠁"


def main() -> None:
    got_file = sys.argv[1]
    ready_file = sys.argv[2]
    done_file = sys.argv[3]
    title = sys.argv[4] if len(sys.argv) > 4 else f"UIPI-TARGET-{os.getpid()}"
    spin = len(sys.argv) > 5 and sys.argv[5] == "spin"

    root = tk.Tk()
    root.title(title)
    root.geometry("640x140+120+120")
    root.attributes("-topmost", True)
    box = tk.Text(root, font=("Segoe UI", 14))
    box.pack(fill="both", expand=True)
    box.focus_force()

    finished = {"done": False}

    def finish():
        if finished["done"]:
            return
        finished["done"] = True
        try:
            with open(got_file, "w", encoding="utf-8") as f:
                f.write(box.get("1.0", "end-1c"))
        finally:
            root.destroy()

    def poll_done():
        if os.path.exists(done_file):
            finish()
        else:
            root.after(150, poll_done)

    tick = {"i": 0}

    def spin_title():
        tick["i"] += 1
        root.title(f"{SPINNER[tick['i'] % len(SPINNER)]} {title}")
        root.after(100, spin_title)

    def announce_ready():
        root.update_idletasks()
        hwnd = int(ctypes.windll.user32.GetAncestor(root.winfo_id(), 2))  # GA_ROOT
        with open(ready_file, "w", encoding="utf-8") as f:
            f.write(json.dumps({"hwnd": hwnd, "pid": os.getpid()}))

    root.after(50, announce_ready)
    root.after(300, poll_done)
    if spin:
        root.after(100, spin_title)
    root.after(HARD_TIMEOUT_S * 1000, finish)
    root.mainloop()


if __name__ == "__main__":
    main()
