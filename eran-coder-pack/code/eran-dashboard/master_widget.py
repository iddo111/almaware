#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""ALMAWARE MASTER WIDGET — compact, always-on-top desktop widget (pure stdlib).

A tiny glanceable companion to the web Master Dashboard. NOT a browser window —
a frameless, draggable, always-on-top Tkinter card that sits in a corner of the
screen and shows Iddo's whole AI world at a glance:

  ERAN    step/loss + slim progress bar + a play-babble button
  YIGAEL  step/loss + slim progress bar + a play-babble button
  FLEET   eran1..eran4 health dots + hottest GPU temp

It does NOT poll the training nodes directly. It polls the existing web backend's
cached JSON at http://127.0.0.1:8790/api/state every ~13s, so the gentle, guarded
node polling stays in ONE place (the web server) and we never double-poll the
training boxes. Babble playback fetches the latest WAV the backend already copied
locally and plays it with winsound (stdlib).

ALMAWARE-pure: Python standard library ONLY —
  tkinter, winsound, urllib, json, threading, tempfile, os.
NO external packages (no pywebview / Electron / pygame / requests / PIL).

Run:  pythonw master_widget.py      (no console window)
  or  python  master_widget.py      (with console, for debugging)
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
import time
import tkinter as tk
import urllib.request

try:
    import winsound  # stdlib on Windows
except Exception:                      # pragma: no cover - non-Windows fallback
    winsound = None

# --------------------------------------------------------------------------
# Config — talk to the web backend, never to the nodes directly.
# --------------------------------------------------------------------------
BACKEND = "http://127.0.0.1:8790"
STATE_URL = BACKEND + "/api/state"
POLL_EVERY = 13          # seconds between JSON polls (gentle; backend is cached)
TARGET_STEPS = 4000      # fallback progress horizon

# Bright / clean palette (Iddo's default look).
BG = "#ffffff"          # card background
HDR = "#0f4c81"         # ALMAWARE blue
ACC = "#2563eb"         # accent (progress / step)
TXT = "#1f2937"
SUB = "#6b7280"
LINE = "#e5e7eb"
TRACK = "#eef1f7"       # progress track
OK = "#16a34a"
WARN = "#f59e0b"
HOT = "#dc2626"
OFF = "#9ca3af"

FONT = "Segoe UI"

# --------------------------------------------------------------------------
# Shared state (filled by the poller thread, read by the Tk main loop).
# --------------------------------------------------------------------------
_lock = threading.Lock()
_state: dict = {"data": None, "ok": False, "err": "connecting…"}


def _set_state(data, ok, err):
    with _lock:
        _state["data"] = data
        _state["ok"] = ok
        _state["err"] = err


def _get_state():
    with _lock:
        return _state["data"], _state["ok"], _state["err"]


# --------------------------------------------------------------------------
# Background poller — fetch the backend's cached JSON.
# --------------------------------------------------------------------------
def _poller():
    while True:
        try:
            req = urllib.request.Request(
                STATE_URL + "?_=" + str(int(time.time())),
                headers={"Cache-Control": "no-store"},
            )
            with urllib.request.urlopen(req, timeout=6) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            _set_state(data, True, "")
        except Exception as e:
            _set_state(None, False, "backend offline")
        time.sleep(POLL_EVERY)


# --------------------------------------------------------------------------
# Babble playback — fetch the latest WAV the backend already cached, play async.
# --------------------------------------------------------------------------
_tmp_dir = os.path.join(tempfile.gettempdir(), "almaware_widget")
os.makedirs(_tmp_dir, exist_ok=True)


def _play_babble(name, audio_url):
    """Download the latest babble WAV for `name` and play it (stdlib winsound)."""
    if not audio_url:
        return
    url = BACKEND + audio_url if audio_url.startswith("/") else audio_url

    def _work():
        try:
            local = os.path.join(_tmp_dir, "%s_latest.wav" % name)
            with urllib.request.urlopen(url, timeout=10) as resp:
                blob = resp.read()
            with open(local, "wb") as fh:
                fh.write(blob)
            if winsound is not None:
                winsound.PlaySound(
                    local, winsound.SND_FILENAME | winsound.SND_ASYNC
                )
        except Exception:
            pass

    threading.Thread(target=_work, daemon=True).start()


# --------------------------------------------------------------------------
# Small UI helpers
# --------------------------------------------------------------------------
def _temp_color(t):
    try:
        t = float(t)
    except Exception:
        return SUB
    return OK if t < 50 else (WARN if t < 72 else HOT)


def _node_dot_color(n):
    if not n or not n.get("online"):
        return OFF
    return _temp_color(n.get("temp"))


# --------------------------------------------------------------------------
# The widget
# --------------------------------------------------------------------------
class Widget:
    def __init__(self, root):
        self.root = root
        self.pinned = True
        self._drag = (0, 0)
        self._sib_audio = {"eran": "", "yigael": ""}

        root.title("ALMAWARE Widget")
        root.overrideredirect(True)            # frameless
        root.attributes("-topmost", True)      # always on top
        root.configure(bg=HDR)
        try:
            root.attributes("-alpha", 0.98)
        except Exception:
            pass

        W = 360
        # Bottom-right corner by default, with a small margin.
        try:
            sw = root.winfo_screenwidth()
            sh = root.winfo_screenheight()
            x = sw - W - 24
            y = sh - 300 - 64
        except Exception:
            x, y = 900, 500
        root.geometry("%dx%d+%d+%d" % (W, 300, max(0, x), max(0, y)))

        outer = tk.Frame(root, bg=HDR, bd=0)
        outer.pack(fill="both", expand=True, padx=2, pady=2)

        # ----- title bar (drag handle) -----
        bar = tk.Frame(outer, bg=HDR, height=30)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        title = tk.Label(bar, text="ALMAWARE · ער\"ן + יגאל",
                         bg=HDR, fg="#ffffff", font=(FONT, 11, "bold"))
        title.pack(side="left", padx=10)

        self.close_btn = tk.Label(bar, text="✕", bg=HDR, fg="#cfe0f5",
                                  font=(FONT, 12, "bold"), cursor="hand2")
        self.close_btn.pack(side="right", padx=(4, 10))
        self.close_btn.bind("<Button-1>", lambda e: self.root.destroy())

        self.pin_btn = tk.Label(bar, text="\U0001f4cc", bg=HDR, fg="#ffffff",
                                font=(FONT, 11), cursor="hand2")
        self.pin_btn.pack(side="right", padx=2)
        self.pin_btn.bind("<Button-1>", lambda e: self._toggle_pin())

        for w in (bar, title):
            w.bind("<Button-1>", self._start_move)
            w.bind("<B1-Motion>", self._on_move)

        # ----- body card (bright) -----
        body = tk.Frame(outer, bg=BG)
        body.pack(fill="both", expand=True)
        self.body = body

        self.status = tk.Label(body, text="connecting…", bg=BG, fg=SUB,
                               font=(FONT, 8), anchor="w")
        self.status.pack(fill="x", padx=12, pady=(8, 2))

        self._sib_rows = {}
        self._build_sibling(body, "eran", "\U0001f50a ER\"N")
        self._build_sibling(body, "yigael", "\U0001f42a YIGAEL")

        tk.Frame(body, bg=LINE, height=1).pack(fill="x", padx=12, pady=(4, 0))

        # ----- fleet row -----
        fl = tk.Frame(body, bg=BG)
        fl.pack(fill="x", padx=12, pady=(8, 4))
        tk.Label(fl, text="\U0001f5a5 FLEET", bg=BG, fg=HDR,
                 font=(FONT, 10, "bold")).pack(side="left")
        self.hot_lbl = tk.Label(fl, text="—", bg=BG, fg=SUB,
                                font=(FONT, 9, "bold"))
        self.hot_lbl.pack(side="right")

        dots = tk.Frame(body, bg=BG)
        dots.pack(fill="x", padx=12, pady=(0, 10))
        self._dots = {}
        for node in ("eran1", "eran2", "eran3", "eran4"):
            cell = tk.Frame(dots, bg=BG)
            cell.pack(side="left", expand=True)
            cv = tk.Canvas(cell, width=14, height=14, bg=BG,
                           highlightthickness=0)
            cv.pack()
            oid = cv.create_oval(2, 2, 12, 12, fill=OFF, outline="")
            tk.Label(cell, text=node, bg=BG, fg=SUB,
                     font=(FONT, 7)).pack()
            self._dots[node] = (cv, oid)

        # offline hint (shown only when backend is down)
        self.hint = tk.Label(body, text="", bg=BG, fg=HOT,
                             font=(FONT, 8), wraplength=330, justify="left")

        root.update_idletasks()
        root.geometry("%dx%d+%d+%d" % (W, root.winfo_reqheight(),
                                       max(0, x), max(0, y)))

    # -- sibling row builder --
    def _build_sibling(self, parent, key, label):
        f = tk.Frame(parent, bg=BG)
        f.pack(fill="x", padx=12, pady=(6, 2))

        top = tk.Frame(f, bg=BG)
        top.pack(fill="x")
        name = tk.Label(top, text=label, bg=BG, fg=HDR,
                        font=(FONT, 11, "bold"))
        name.pack(side="left")
        play = tk.Label(top, text="▶", bg=ACC, fg="#ffffff",
                        font=(FONT, 9, "bold"), cursor="hand2", padx=9, pady=1)
        play.pack(side="right")
        play.bind("<Button-1>", lambda e, k=key: _play_babble(k, self._sib_audio.get(k, "")))

        stat = tk.Label(top, text="—", bg=BG, fg=SUB, font=(FONT, 8))
        stat.pack(side="right", padx=8)

        # step / loss line
        info = tk.Label(f, text="step —  ·  loss —", bg=BG, fg=TXT,
                        font=(FONT, 9), anchor="w")
        info.pack(fill="x")

        # slim progress bar (canvas)
        track = tk.Canvas(f, height=7, bg=TRACK, highlightthickness=0)
        track.pack(fill="x", pady=(3, 0))
        fill = track.create_rectangle(0, 0, 0, 7, fill=ACC, outline="")

        self._sib_rows[key] = {
            "stat": stat, "info": info, "track": track, "fill": fill,
            "play": play,
        }

    # -- window drag --
    def _start_move(self, e):
        self._drag = (e.x, e.y)

    def _on_move(self, e):
        x = self.root.winfo_x() + (e.x - self._drag[0])
        y = self.root.winfo_y() + (e.y - self._drag[1])
        self.root.geometry("+%d+%d" % (x, y))

    def _toggle_pin(self):
        self.pinned = not self.pinned
        self.root.attributes("-topmost", self.pinned)
        self.pin_btn.configure(fg="#ffffff" if self.pinned else "#9fc0e6")

    # -- periodic UI refresh from shared state --
    def refresh(self):
        data, ok, err = _get_state()
        if not ok or not data:
            self.status.configure(
                text="⚠ backend offline", fg=HOT)
            self.hint.configure(
                text="Start the web dashboard:\n"
                     "python web\\master_dashboard.py  (:8790)")
            self.hint.pack(fill="x", padx=12, pady=(0, 10))
            for key in ("eran", "yigael"):
                r = self._sib_rows[key]
                r["info"].configure(text="step —  ·  loss —")
                r["track"].coords(r["fill"], 0, 0, 0, 7)
                r["stat"].configure(text="—", fg=SUB)
            for node, (cv, oid) in self._dots.items():
                cv.itemconfig(oid, fill=OFF)
            self.hot_lbl.configure(text="—", fg=SUB)
            self._reschedule()
            return

        self.hint.pack_forget()
        upd = data.get("updated", "—")
        self.status.configure(text="live · updated %s" % upd, fg=OK)

        target = data.get("target_steps") or TARGET_STEPS
        sib = data.get("siblings", {}) or {}
        for key in ("eran", "yigael"):
            s = sib.get(key, {}) or {}
            r = self._sib_rows[key]
            step = s.get("step")
            total = s.get("total") or target
            loss = s.get("loss")
            done = bool(s.get("done"))
            self._sib_audio[key] = s.get("audio_url", "")

            step_txt = "—" if step is None else str(step)
            loss_txt = "—" if loss is None else ("%.4f" % float(loss))
            r["info"].configure(
                text="step %s / %s   ·   loss %s" % (step_txt, total, loss_txt))

            if step is None:
                pct = 0.0
            else:
                pct = max(0.0, min(1.0, float(step) / float(total or 1)))
            w = max(0, self.body.winfo_width() - 24)
            r["track"].coords(r["fill"], 0, 0, int(w * pct), 7)
            r["track"].itemconfig(r["fill"], fill=OK if done else ACC)

            if done:
                r["stat"].configure(text="✓ done", fg=OK)
            elif step is not None:
                r["stat"].configure(text="training", fg=ACC)
            else:
                r["stat"].configure(text="waiting", fg=SUB)

            # disable play button look if no audio yet
            r["play"].configure(bg=ACC if self._sib_audio[key] else OFF)

        # FLEET dots + hottest temp
        nodes = data.get("nodes", {}) or {}
        hottest = None
        for node, (cv, oid) in self._dots.items():
            n = nodes.get(node)
            cv.itemconfig(oid, fill=_node_dot_color(n))
            if n and n.get("online") and n.get("temp") is not None:
                t = n.get("temp")
                if hottest is None or t > hottest:
                    hottest = t
        if hottest is None:
            self.hot_lbl.configure(text="—", fg=SUB)
        else:
            self.hot_lbl.configure(text="hottest %d°C" % hottest,
                                   fg=_temp_color(hottest))

        self._reschedule()

    def _reschedule(self):
        self.root.after(1000, self.refresh)


def main():
    threading.Thread(target=_poller, daemon=True).start()
    root = tk.Tk()
    w = Widget(root)
    root.after(300, w.refresh)
    root.mainloop()


if __name__ == "__main__":
    main()
