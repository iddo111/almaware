# -*- coding: utf-8 -*-
"""listener_console.py -- a small always-on-top window for KESHEV to type
into.

WHY THIS EXISTS (measured, not guessed -- read D:\\CLAUDE\\keshev-next\\app\\
main.py and typer.py before writing this):
  KESHEV's only output path is `typer.type_string(text, auto_enter=True)`
  (main.py line ~1018, AUTO_ENTER=True at line 15) -- it uses Windows
  SendInput to type the recognized Hebrew sentence, plus a real Enter key
  press, into WHATEVER WINDOW CURRENTLY HAS OS FOCUS. There is no separate
  event bus, log, or IPC channel carrying clean recognized text (the closest
  thing, --debug-dump, writes .wav files and stderr prose, not a stable
  machine-readable stream).

  So the non-invasive way to receive KESHEV's output -- without touching
  KESHEV's code, the mic, or any audio device, which is forbidden for this
  task -- is to BE the focused window. This module is exactly that: a
  Tkinter Entry that, when focused, silently receives whatever KESHEV types
  and fires a callback on every Enter (i.e. every recognized utterance).

  This is a REAL constraint, not a workaround for its own sake: it means
  Iddo must click/alt-tab to this window (or leave it as the only visible
  window) while DJing for voice commands to reach it. That tradeoff is
  documented in README.md and the status report, not hidden.

Runs stdlib Tkinter only -- no extra dependency for this piece.
"""
import sys
import tkinter as tk
from datetime import datetime


class ListenerConsole:
    def __init__(self, on_utterance, title="DJ-ALMA console"):
        """on_utterance: callable(str) -> None, called with each line typed
        into the entry followed by Enter (this is what KESHEV sends)."""
        self.on_utterance = on_utterance
        self.root = tk.Tk()
        self.root.title(title)
        self.root.attributes("-topmost", True)
        self.root.geometry("640x360")

        tk.Label(
            self.root,
            text="DJ-ALMA — keep this window focused so KESHEV's speech reaches it.\n"
                 "Type here yourself too, for testing without the mic.",
            justify="left", anchor="w", wraplength=620,
        ).pack(fill="x", padx=8, pady=(8, 2))

        self.entry = tk.Entry(self.root, font=("Segoe UI", 14))
        self.entry.pack(fill="x", padx=8, pady=4)
        self.entry.bind("<Return>", self._on_return)
        self.entry.focus_set()

        self.log = tk.Text(self.root, state="disabled", font=("Consolas", 10))
        self.log.pack(fill="both", expand=True, padx=8, pady=(4, 8))

    def _on_return(self, _event=None):
        text = self.entry.get()
        self.entry.delete(0, tk.END)
        if text.strip():
            self._append_log(f"heard: {text}")
            try:
                self.on_utterance(text)
            except Exception as e:  # a bad command must never kill the window
                self._append_log(f"ERROR handling utterance: {e!r}")

    def append_result(self, text: str):
        self._append_log(text)

    def _append_log(self, text: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log.configure(state="normal")
        self.log.insert(tk.END, f"[{ts}] {text}\n")
        self.log.see(tk.END)
        self.log.configure(state="disabled")

    def run(self):
        self.root.mainloop()


def _selftest():
    """Headless check: build the widget tree without entering mainloop, and
    verify the Enter callback actually fires. No display server needed
    beyond whatever Tk can attach to (Windows always has one)."""
    seen = []
    c = ListenerConsole(on_utterance=lambda t: seen.append(t), title="selftest")
    c.entry.insert(0, "בדיקה")
    c._on_return()
    c.root.destroy()
    assert seen == ["בדיקה"], seen
    print("listener_console selftest OK")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    else:
        console = ListenerConsole(on_utterance=lambda t: print("heard:", t))
        console.run()
