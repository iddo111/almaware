# -*- coding: utf-8 -*-
"""ALMA CATCH -- the safe landing place for what Iddo dictates from his phone.

2026-09-06 17:56, he wrote "אני בחוץ סדר לי את העלמה מיק עם טיילסקייל".

The chain (phone -> keshev6 on eran1 -> intake :8892 -> a window) was measured
working end to end, 5/5, but the intake had NOTHING LOCKED. With no lock it types
into whatever happens to be in the foreground -- which today means his open,
unsaved Notepad file, or, if the DESKTOP has focus, an Enter that launches
whatever icon is selected (measured this afternoon: it relaunched a shortcut four
times in three minutes).

So: one window that exists only to be dictated into. It holds focus for the lock,
appends every line with a timestamp, and autosaves to state/alma_catch.txt so
nothing is lost if it is closed. It opens no microphone, no socket, and no file
of his. Close it and the lock simply goes stale -- nothing else breaks.
"""
import os, sys, time
import tkinter as tk
from datetime import datetime

STATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "state")
OUT = os.path.abspath(os.path.join(STATE, "alma_catch.txt"))

root = tk.Tk()
root.title("ALMA — מה שאמרת מהטלפון")
root.geometry("980x620+120+90")
root.configure(bg="#101418")

hdr = tk.Label(root, text="  ALMA — מה שאמרת מהטלפון · what you said from the phone  ",
               bg="#1b5e20", fg="#FFFFFF", font=("Segoe UI", 15, "bold"), anchor="w")
hdr.pack(fill="x")
sub = tk.Label(root, text=f"נשמר אוטומטית ל־{OUT}", bg="#101418", fg="#8aa0b0",
               font=("Segoe UI", 9), anchor="w")
sub.pack(fill="x", padx=8, pady=(4, 0))

txt = tk.Text(root, bg="#0b0f13", fg="#E8F0F5", insertbackground="#7CFC9A",
              font=("Segoe UI", 20), wrap="word", padx=14, pady=12,
              selectbackground="#1b5e20", undo=True)
txt.pack(fill="both", expand=True, padx=8, pady=8)
txt.focus_force()

status = tk.Label(root, text="", bg="#101418", fg="#7CFC9A",
                  font=("Segoe UI", 10), anchor="w")
status.pack(fill="x", padx=8, pady=(0, 6))

_last = [""]
def autosave():
    try:
        cur = txt.get("1.0", "end-1c")
        if cur != _last[0]:
            with open(OUT, "w", encoding="utf-8") as fh:
                fh.write(cur)
            _last[0] = cur
            n = len([l for l in cur.splitlines() if l.strip()])
            status.config(text=f"נשמר {datetime.now().strftime('%H:%M:%S')} · {n} שורות · {len(cur)} תווים")
    except Exception as exc:
        status.config(text=f"autosave failed: {exc!r}", fg="#FF8A80")
    root.after(2000, autosave)

if os.path.exists(OUT):
    try:
        txt.insert("1.0", open(OUT, encoding="utf-8").read())
        txt.see("end")
    except Exception:
        pass
txt.insert("end", f"\n— {datetime.now().strftime('%Y-%m-%d %H:%M')} —\n")
txt.see("end")
root.after(2000, autosave)
root.mainloop()
