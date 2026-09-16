r"""accept_decoy -- the throwaway window the standing acceptance test types into.

🪟 NEVER TEST A SAFETY GATE ON A LIVING SYSTEM. The acceptance test pushes a
real sentence through the real decoder and the REAL typer, which means real
keystrokes go into whatever window has the focus. That window must therefore be
one we own and can throw away -- never his chat, never a document, never Notepad
(Windows 11 reuses its tabs and can land text in a file he cares about, and its
text cannot be read back reliably anyway).

A fresh Tk window every launch. It writes whatever it contains to the path given
in argv[1], ten times a second, so the test can assert on the REAL CONTENT of
the window rather than on "SendInput returned success" -- which is exactly the
lie UIPI tells (2026-09-03).

    pythonw tools\accept_decoy.py <out_path>

It has no save dialog and no file of its own: killing it loses nothing.
"""
import sys
import tkinter as tk

OUT_PATH = sys.argv[1] if len(sys.argv) > 1 else "accept_decoy_content.txt"

root = tk.Tk()
root.title("KESHEV-ACCEPT-DECOY")
root.geometry("640x260+160+160")
root.attributes("-topmost", True)

txt = tk.Text(root, font=("Segoe UI", 14))
txt.pack(fill="both", expand=True)
txt.focus_force()


def dump():
    try:
        with open(OUT_PATH, "w", encoding="utf-8") as fh:
            fh.write(txt.get("1.0", "end-1c"))
    except Exception:
        pass
    root.after(100, dump)


root.after(50, dump)
root.after(120, lambda: (root.lift(), root.focus_force(), txt.focus_force()))
root.mainloop()
