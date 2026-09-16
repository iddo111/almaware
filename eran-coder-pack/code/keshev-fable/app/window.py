# window.py — THE VISIBLE SURFACE. Sentence of the 18:47 inquiry.
#
# The inquiry's finding: a mic with no window repeats species #2 — an alarm
# with nowhere to be seen. This window is small, always-on-top-able, honest:
#   ● state light   green=listening · blue=decoding · orange=gated/quiet ·
#                   red=fault/park  · grey=idle-no-mic
#   ● last line     the latest text that actually TYPED (truncated)
#   ● counters      seg / typed / gated since launch
#   ● owner cos     the clause-4 shadow number, live
#   ● pause button  same effect as ctrl+alt+m
# Tkinter (stdlib), runs on the MAIN thread; the pipeline reports via a
# thread-safe queue — the audio thread never touches Tk.
from __future__ import annotations

import queue
import tkinter as tk

COLORS = {
    "listen": "#2e7d32", "decode": "#1565c0", "quiet": "#ef6c00",
    "fault": "#c62828", "idle": "#616161",
}


class StatusWindow:
    def __init__(self, on_pause=None, sensitivity=None) -> None:
        self.events: queue.Queue = queue.Queue()
        self.on_pause = on_pause
        self.sensitivity = sensitivity     # live gate; slider/AUTO drive it
        self.paused = False
        self._seg = self._typed = self._gated = 0
        self._level = 0.0

        self.root = tk.Tk()
        self.root.title("קשב · KESHEV")
        self.root.geometry("340x196+40+40")
        self.root.attributes("-topmost", True)
        self.root.configure(bg="#101418")
        self.root.protocol("WM_DELETE_WINDOW", self.root.iconify)  # never die by X

        top = tk.Frame(self.root, bg="#101418"); top.pack(fill="x", padx=10, pady=(8, 2))
        self.light = tk.Canvas(top, width=18, height=18, bg="#101418",
                               highlightthickness=0)
        self._dot = self.light.create_oval(2, 2, 16, 16, fill=COLORS["idle"])
        self.light.pack(side="left")
        self.state_lbl = tk.Label(top, text="נדלק…", fg="#eceff1", bg="#101418",
                                  font=("Segoe UI", 11, "bold"))
        self.state_lbl.pack(side="left", padx=8)
        self.pause_btn = tk.Button(top, text="⏸ השהה", command=self._toggle,
                                   bg="#263238", fg="#eceff1", relief="flat",
                                   activebackground="#37474f")
        self.pause_btn.pack(side="right")

        self.text_lbl = tk.Label(self.root, text="", fg="#b0bec5", bg="#101418",
                                 font=("Segoe UI", 10), anchor="e",
                                 justify="right", wraplength=320)
        self.text_lbl.pack(fill="x", padx=10, pady=2)

        self.stats_lbl = tk.Label(self.root, text="", fg="#607d8b", bg="#101418",
                                  font=("Consolas", 9), anchor="w")
        self.stats_lbl.pack(fill="x", padx=10, pady=(0, 2))

        # --- the sensitivity strip: live colour meter + slider + AUTO ---------
        self.meter = tk.Canvas(self.root, height=16, bg="#0a0d10",
                               highlightthickness=0)
        self.meter.pack(fill="x", padx=10, pady=(2, 2))
        self._bar = self.meter.create_rectangle(0, 0, 0, 16, width=0)
        self._gate_mark = self.meter.create_line(0, 0, 0, 16, fill="#eceff1", width=2)

        row = tk.Frame(self.root, bg="#101418"); row.pack(fill="x", padx=10, pady=(0, 6))
        from .sensitivity import GATE_MAX, GATE_MIN
        self.slider = tk.Scale(row, from_=GATE_MIN, to=GATE_MAX, resolution=0.001,
                               orient="horizontal", showvalue=False, length=210,
                               bg="#101418", fg="#b0bec5", troughcolor="#263238",
                               highlightthickness=0, command=self._slide)
        if self.sensitivity is not None:
            self.slider.set(self.sensitivity.gate)
        self.slider.pack(side="left")
        tk.Label(row, text="רגישות", fg="#607d8b", bg="#101418",
                 font=("Segoe UI", 8)).pack(side="left", padx=(6, 2))
        self.auto_btn = tk.Button(row, text="AUTO", command=self._auto,
                                  bg="#263238", fg="#eceff1", relief="flat",
                                  font=("Segoe UI", 8, "bold"),
                                  activebackground="#37474f")
        self.auto_btn.pack(side="right")

        self.root.after(80, self._pump)

    # ------------------------------------------------------- pipeline API --
    # Any thread may call these; they only enqueue.
    def set_state(self, kind: str, label: str) -> None:
        self.events.put(("state", kind, label))

    def typed(self, text: str) -> None:
        self.events.put(("typed", text))

    def seg(self) -> None:
        self.events.put(("seg",))

    def gated(self) -> None:
        self.events.put(("gated",))

    def owner_cos(self, cos: float) -> None:
        self.events.put(("cos", cos))

    def level(self, rms: float) -> None:
        """Live input loudness, 0..1 — the colour bar. Called from the audio thread."""
        if self.sensitivity is not None:
            self.sensitivity.observe(rms)
        self.events.put(("level", rms))

    # ------------------------------------------------------------ internal --
    def _slide(self, val) -> None:
        if self.sensitivity is not None:
            self.sensitivity.set(float(val))
        self.auto_btn.config(relief="flat", fg="#eceff1")   # a hand off AUTO

    def _auto(self) -> None:
        if self.sensitivity is None:
            return
        self.sensitivity.auto = not self.sensitivity.auto
        self.auto_btn.config(fg="#3fb950" if self.sensitivity.auto else "#eceff1")
        if self.sensitivity.auto:
            self.sensitivity.gate = self.sensitivity.recommend()
            self.slider.set(self.sensitivity.gate)

    def _draw_meter(self) -> None:
        w = max(1, self.meter.winfo_width())
        from .sensitivity import GATE_MAX
        # log-ish scale so quiet speech is visible; full bar ~ GATE_MAX*3
        frac = min(1.0, self._level / (GATE_MAX * 3))
        gate = self.sensitivity.gate if self.sensitivity is not None else 0.008
        over = self._level >= gate
        colour = "#3fb950" if over else "#37474f"           # green when it would open
        if over and self._level > gate * 3:
            colour = "#e0a13c"                              # loud = amber
        self.meter.coords(self._bar, 0, 0, int(w * frac), 16)
        self.meter.itemconfig(self._bar, fill=colour)
        gx = int(w * min(1.0, gate / (GATE_MAX * 3)))
        self.meter.coords(self._gate_mark, gx, 0, gx, 16)   # the threshold marker
    def _toggle(self) -> None:
        self.paused = not self.paused
        self.pause_btn.config(text="▶ המשך" if self.paused else "⏸ השהה")
        if self.on_pause:
            self.on_pause(self.paused)
        self.set_state("fault" if self.paused else "listen",
                       "מושהה ביד" if self.paused else "מאזין")

    def _pump(self) -> None:
        try:
            while True:
                ev = self.events.get_nowait()
                if ev[0] == "state":
                    self.light.itemconfig(self._dot,
                                          fill=COLORS.get(ev[1], "#616161"))
                    self.state_lbl.config(text=ev[2])
                elif ev[0] == "typed":
                    self._typed += 1
                    t = ev[1]
                    self.text_lbl.config(
                        text=(t[:90] + "…") if len(t) > 90 else t)
                elif ev[0] == "seg":
                    self._seg += 1
                elif ev[0] == "gated":
                    self._gated += 1
                elif ev[0] == "cos":
                    self.stats_lbl.config(
                        text=self._stats() + f"   owner={ev[1]:.2f}")
                elif ev[0] == "level":
                    self._level = ev[1]
                    if self.sensitivity is not None and self.sensitivity.auto:
                        self.slider.set(self.sensitivity.gate)   # follow AUTO
        except queue.Empty:
            pass
        self.stats_lbl.config(text=self._stats())
        self._draw_meter()
        self.root.after(80, self._pump)

    def _stats(self) -> str:
        return f"seg {self._seg}   typed {self._typed}   gated {self._gated}"

    def run(self) -> None:
        """Blocks — main() calls this LAST, on the main thread."""
        self.root.mainloop()
