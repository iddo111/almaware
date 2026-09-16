# -*- coding: utf-8 -*-
"""todo_widget.py -- Iddo's floating focus widget. The first rung of the smart-glasses
second brain, on the desktop.

Iddo, 2026-08-24: a special GUI with a to-do list, "כזה widget, כזה חלון" -- a small
always-on-top window that keeps the important things in front of his eyes and focuses him.
Focus is hard to hold; the list has to be SEEN without asking, not filed in
an app he forgets to open (project_bci_ai_second_brain, feedback_salon_nag_mandate).

Design: small, bright, always-on-top, draggable by its header, one FOCUS line big at the top,
a checkable list below, an add box at the bottom. Closeable by a clear X (his law: a GUI must
always be closeable -- feedback_never_take_over_pc_audio). Persists to todos.json so it
survives a restart. Pure stdlib tkinter.
"""
import json
import os
import tkinter as tk
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
STORE = os.path.join(HERE, "todos.json")

BG = "#fdfdf8"
INK = "#1a1f2b"
DIM = "#8a94a6"
GOLD = "#e6a400"
DONE = "#b7c0cc"
LINE = "#e6e9ef"
FOCUS_BG = "#fff6d8"


def load():
    try:
        with open(STORE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"items": []}


def save(state):
    try:
        with open(STORE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=1)
    except Exception:
        pass


class Widget:
    def __init__(self):
        self.state = load()
        self.root = tk.Tk()
        self.root.title("מוח שני — מטלות")
        try:
            self.root.iconbitmap(os.path.join(HERE, "todo.ico"))
        except Exception:
            try:
                self._icon = tk.PhotoImage(file=os.path.join(HERE, "todo.png"))
                self.root.iconphoto(True, self._icon)
            except Exception:
                pass
        self.root.configure(bg=BG)
        self.root.geometry("340x460+40+40")
        self.root.attributes("-topmost", True)
        self.root.minsize(280, 300)

        # header (drag handle + controls)
        hdr = tk.Frame(self.root, bg=INK)
        hdr.pack(fill="x")
        tk.Label(hdr, text="  🧠 מוח שני", bg=INK, fg="white",
                 font=("Segoe UI", 13, "bold")).pack(side="left", pady=6)
        tk.Button(hdr, text="✕", bg=INK, fg="white", bd=0, activebackground="#c0392b",
                  activeforeground="white", font=("Segoe UI", 12, "bold"),
                  command=self.close).pack(side="right", padx=(0, 6))
        self.pin = tk.BooleanVar(value=True)
        tk.Checkbutton(hdr, text="📌", bg=INK, fg="white", selectcolor=INK, bd=0,
                       activebackground=INK, variable=self.pin,
                       command=lambda: self.root.attributes("-topmost", self.pin.get())
                       ).pack(side="right")
        for w in (hdr,):
            w.bind("<Button-1>", self._drag_start)
            w.bind("<B1-Motion>", self._drag)

        # focus line (the one thing)
        self.focus_frame = tk.Frame(self.root, bg=FOCUS_BG)
        self.focus_frame.pack(fill="x")
        self.focus_lbl = tk.Label(self.focus_frame, text="", bg=FOCUS_BG, fg=INK,
                                  font=("Segoe UI", 15, "bold"), wraplength=310,
                                  justify="right", anchor="e")
        self.focus_lbl.pack(fill="x", padx=10, pady=8)

        # list
        self.listbox = tk.Frame(self.root, bg=BG)
        self.listbox.pack(fill="both", expand=True, padx=4, pady=4)

        # add box
        addf = tk.Frame(self.root, bg=BG)
        addf.pack(fill="x", padx=8, pady=(0, 8))
        self.entry = tk.Entry(addf, font=("Segoe UI", 12), justify="right",
                              bg="white", fg=INK, relief="solid", bd=1)
        self.entry.pack(side="left", fill="x", expand=True, ipady=4)
        self.entry.bind("<Return>", lambda e: self.add())
        tk.Button(addf, text="＋", font=("Segoe UI", 14, "bold"), bg=GOLD, fg="white",
                  bd=0, width=3, command=self.add).pack(side="right", padx=(6, 0))

        self.render()
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    # --- drag a frameless-ish window by the header ---
    def _drag_start(self, e):
        self._dx, self._dy = e.x, e.y

    def _drag(self, e):
        x = self.root.winfo_x() + e.x - self._dx
        y = self.root.winfo_y() + e.y - self._dy
        self.root.geometry(f"+{x}+{y}")

    def add(self):
        t = self.entry.get().strip()
        if t:
            self.state["items"].append({"text": t, "done": False,
                                        "ts": datetime.now().isoformat(timespec="minutes")})
            self.entry.delete(0, "end")
            save(self.state)
            self.render()

    def toggle(self, i):
        self.state["items"][i]["done"] = not self.state["items"][i]["done"]
        save(self.state)
        self.render()

    def remove(self, i):
        del self.state["items"][i]
        save(self.state)
        self.render()

    def make_focus(self, i):
        # move item to the top = the one thing
        it = self.state["items"].pop(i)
        self.state["items"].insert(0, it)
        save(self.state)
        self.render()

    def render(self):
        # focus line = first not-done item
        active = [it for it in self.state["items"] if not it["done"]]
        self.focus_lbl.config(text=("⭐ " + active[0]["text"]) if active else "הכול נקי ✓")

        for w in self.listbox.winfo_children():
            w.destroy()
        for i, it in enumerate(self.state["items"]):
            row = tk.Frame(self.listbox, bg=BG)
            row.pack(fill="x", pady=1)
            box = "☑" if it["done"] else "☐"
            tk.Button(row, text=box, bd=0, bg=BG, fg=(DONE if it["done"] else GOLD),
                      font=("Segoe UI", 13), command=lambda i=i: self.toggle(i)
                      ).pack(side="right")
            fg = DONE if it["done"] else INK
            font = ("Segoe UI", 12, "overstrike") if it["done"] else ("Segoe UI", 12)
            lbl = tk.Label(row, text=it["text"], bg=BG, fg=fg, font=font,
                           anchor="e", justify="right", wraplength=250)
            lbl.pack(side="right", fill="x", expand=True, padx=4)
            if not it["done"]:
                lbl.bind("<Double-Button-1>", lambda e, i=i: self.make_focus(i))
            tk.Button(row, text="🗑", bd=0, bg=BG, fg=DIM, font=("Segoe UI", 10),
                      command=lambda i=i: self.remove(i)).pack(side="left")
        tk.Label(self.listbox, text="לחיצה כפולה = הפוך למיקוד",
                 bg=BG, fg=DIM, font=("Segoe UI", 8)).pack(side="bottom", pady=(4, 0))

    def close(self):
        save(self.state)
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    Widget().run()
