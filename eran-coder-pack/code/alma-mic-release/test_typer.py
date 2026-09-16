"""alma-mic / test_typer.py — STAGE 4 proof: SendInput actually types Hebrew Unicode.
Self-contained: types into our own focused Tk Entry and reads it back (no external app)."""
import sys
import time
import threading
import tkinter as tk
import typer

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

EXPECT = "שלום עולם"
result = {}

root = tk.Tk()
root.title("typer test")
root.geometry("300x80+200+200")
e = tk.Entry(root, font=("Segoe UI", 16))
e.pack(expand=True, fill="x", padx=10, pady=10)
root.after(200, lambda: (root.lift(), root.focus_force(), e.focus_set()))


def do():
    time.sleep(1.2)               # let the window take foreground focus
    typer.type_text(EXPECT, enter=False)
    time.sleep(0.6)
    result["text"] = e.get()
    root.after(0, root.destroy)


threading.Thread(target=do, daemon=True).start()
root.mainloop()

got = result.get("text", "")
print(f"[typer] expected {EXPECT!r}  got {got!r}")
if EXPECT in got:
    print("STAGE 4 (TYPER) PASS — Hebrew types into the focused window.")
else:
    print("STAGE 4 (TYPER) FAIL — check focus/SendInput.")
    sys.exit(1)
