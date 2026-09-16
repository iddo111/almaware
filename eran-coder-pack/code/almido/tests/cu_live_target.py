# -*- coding: utf-8 -*-
r"""A target window for the LIVE computer-use proof -- ours, so the test never has to
click inside one of Iddo's applications.

An always-on-top Tk window with a scrollable Text widget. It records every click, key and
wheel event it really receives, plus the Text widget's scroll position, and writes them to
the JSON file given as argv[1] after each one. `escape` closes it and marks the log
"closed". The scroll position is the honest proof for the wheel: a <MouseWheel> binding
can be missed, a view that actually moved cannot.

Run by tests/test_almido_computer.py::test_live_... only, and only when ALMIDO_CU_LIVE=1.
"""
import json
import sys
import tkinter as tk

LOG = sys.argv[1] if len(sys.argv) > 1 else "cu-live-target.json"
state = {"clicks": [], "typed": [], "keys": [], "wheel": [], "yview": [], "closed": False}


def flush():
    try:
        with open(LOG, "w", encoding="utf-8") as fh:
            json.dump(state, fh, ensure_ascii=False)
    except Exception:
        pass


root = tk.Tk()
root.title("ALMIDO-LIVE-TARGET")
root.geometry("760x420+300+300")
root.attributes("-topmost", True)
tk.Label(root, text="ALMIDO live computer-use proof -- click / type / scroll here, escape closes",
         font=("Segoe UI", 12)).pack(fill="x")
text = tk.Text(root, font=("Consolas", 12))
text.pack(expand=True, fill="both")
text.insert("1.0", "\n".join("line %03d ---------------------------------" % i for i in range(400)))
text.focus_set()


def note_view():
    try:
        state["yview"].append(round(text.yview()[0], 4))
    except Exception:
        pass


def on_click(e):
    state["clicks"].append([e.x_root, e.y_root])
    note_view()
    flush()


def on_key(e):
    if e.char and e.char.isprintable():
        state["typed"].append(e.char)
    state["keys"].append(e.keysym)
    flush()
    if e.keysym == "Escape":
        note_view()
        state["closed"] = True
        flush()
        root.after(120, root.destroy)


def on_wheel(e):
    state["wheel"].append(int(e.delta))
    root.after(60, lambda: (note_view(), flush()))
    flush()


root.bind_all("<Button-1>", on_click)
root.bind_all("<Key>", on_key)
root.bind_all("<MouseWheel>", on_wheel)
root.after(100, lambda: (root.lift(), root.focus_force(), note_view(), flush()))
flush()
root.mainloop()
state["closed"] = True
flush()
