"""alma-mic / _uipi_target.py — a receiving window for the UIPI self-test.

Spawned BY selftest_uipi.py, so it inherits that process's integrity level. It is
a separate process with a plain Win32 (tk) window, which makes it a faithful
stand-in for Iddo's elevated Claude CLI: typing into it crosses a real process
boundary and is subject to the same UIPI check.

Whatever lands in the box is written to the file given as argv[1], then it exits.
"""
from __future__ import annotations

import sys
import tkinter as tk

TITLE = "ALMA-UIPI-TARGET"
OUT = sys.argv[1] if len(sys.argv) > 1 else "uipi_target_got.txt"
SECONDS = 12


def main() -> None:
    root = tk.Tk()
    root.title(TITLE)
    root.geometry("640x140+120+120")
    root.attributes("-topmost", True)
    box = tk.Text(root, font=("Segoe UI", 14))
    box.pack(fill="both", expand=True)
    box.focus_force()

    def finish():
        try:
            with open(OUT, "w", encoding="utf-8") as f:
                f.write(box.get("1.0", "end-1c"))
        finally:
            root.destroy()

    root.after(SECONDS * 1000, finish)
    root.mainloop()


if __name__ == "__main__":
    main()
