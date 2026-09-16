"""KESHEV / client/window.py — the visible window.

WHY THIS FILE EXISTS. K15 shipped the tray's whole brain — states, icons,
tooltips, balloons, menu — and no pixels: PystrayBackend refuses to construct
rather than draw nothing and call itself real. That refusal is correct and it
stays. But it left Iddo dictating into a program he cannot see. This window is
the pixels, and it draws the SAME truth the tray derives — it holds no state of
its own and computes no status: every field on screen comes from one
`Tray.update()` per tick, which pulls one fresh `TrayInputs` off the live app.
If the window and the tray ever disagree, that is a bug in one render, not two
opinions about whether the mic is working.

Reuses the bright ALMAWARE look of alma-mic/gui.py (tkinter, stdlib only,
Segoe UI, white ground) — the shell Iddo already recognises — over KESHEV's
architecture rather than alma-mic's.

SACRED AUDIO: this file plays nothing. No `bell()`, no sound of any kind, and
it never touches an output device. Deafness announces itself by FLASHING, in
alarm red, in his eyeline.

THREADING: tkinter's main loop is the only thread that touches widgets. It runs
on the process main thread (client/app.py main()); every KeshevApp thread keeps
running underneath it untouched. Closing the window does NOT stop dictation —
it asks the app to stop, exactly as the tray's Quit does, so there is one way to
end the program and one only.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable

from client import tray as tray_mod

# ---- bright theme (alma-mic/gui.py) ----
BG = "#ffffff"
FG = "#1a1a1a"
MUTED = "#6b7280"
TRACK = "#e5e7eb"
PANEL = "#f9fafb"
FONT = "Segoe UI"

TICK_MS = 500                 # window refresh; the tray thread ticks separately
FLASH_MS = 600                # alarm-state blink period
LAMP = 118                    # status lamp diameter


def _hex(rgb: tuple[int, int, int]) -> str:
    return "#%02x%02x%02x" % rgb


class KeshevWindow:
    """A read-only window over one live Tray. Buttons go through
    Tray.invoke(), so an action with nothing behind it says so out loud
    instead of quietly doing nothing."""

    def __init__(self, tray: tray_mod.Tray, *, on_quit: Callable[[], Any],
                 level_fn: Callable[[], Any] | None = None,
                 title: str = "KESHEV קשב") -> None:
        self._tray = tray
        self._on_quit = on_quit
        # Iddo, 2026-08-15: "should have the soundbar". Returns the live
        # capture RMS, or None when there is no stream. None and 0.0 are drawn
        # differently on purpose — "no stream" and "a stream full of silence"
        # are different failures, and the second one is scar 25.
        self._level_fn = level_fn
        self._peak = 0.0                  # decaying peak-hold for the bar
        self._phase = 0
        self._closing = False

        self.root = tk.Tk()
        self.root.title(title)
        self.root.configure(bg=BG)
        self.root.minsize(520, 520)
        self.root.protocol("WM_DELETE_WINDOW", self._quit)

        style = ttk.Style(self.root)
        # A missing theme costs looks, not truth — but it is recorded, not
        # swallowed, so "the window looks wrong" has an answer in the ledger.
        self.theme_error = ""
        try:
            style.theme_use("clam")
        except tk.TclError as exc:                # pragma: no cover - theme present
            self.theme_error = str(exc)
        style.configure("K.TButton", font=(FONT, 10), padding=6)

        # ---- the lamp: the one thing visible from across the room ----
        head = tk.Frame(self.root, bg=BG)
        head.pack(fill="x", padx=18, pady=(18, 6))
        self._canvas = tk.Canvas(head, width=LAMP, height=LAMP, bg=BG,
                                 highlightthickness=0)
        self._canvas.pack(side="left")
        self._lamp = self._canvas.create_oval(6, 6, LAMP - 6, LAMP - 6,
                                              fill=TRACK, outline="")
        self._glyph = self._canvas.create_text(LAMP // 2, LAMP // 2, text="",
                                               fill="#ffffff",
                                               font=(FONT, 40, "bold"))

        txt = tk.Frame(head, bg=BG)
        txt.pack(side="left", fill="both", expand=True, padx=(16, 0))
        self._state_lbl = tk.Label(txt, text="—", bg=BG, fg=FG,
                                   font=(FONT, 26, "bold"), anchor="w")
        self._state_lbl.pack(fill="x")
        self._engine_lbl = tk.Label(txt, text="", bg=BG, fg=MUTED,
                                    font=(FONT, 11), anchor="w")
        self._engine_lbl.pack(fill="x")
        self._mic_lbl = tk.Label(txt, text="", bg=BG, fg=MUTED,
                                 font=(FONT, 11), anchor="w", wraplength=330,
                                 justify="left")
        self._mic_lbl.pack(fill="x")

        # ---- PLAY / PAUSE: the biggest button, because it is the one he
        #      reaches for mid-sentence. Pause stops TYPING, not hearing.
        ctl = tk.Frame(self.root, bg=BG)
        ctl.pack(fill="x", padx=18, pady=(4, 2))
        self._playpause = tk.Button(
            ctl, text="⏸  PAUSE", font=(FONT, 15, "bold"),
            bg="#111827", fg="#ffffff", activebackground="#374151",
            activeforeground="#ffffff", relief="flat", bd=0, padx=22, pady=10,
            cursor="hand2", command=self._toggle_pause)
        self._playpause.pack(side="left")
        self._pause_note = tk.Label(ctl, text="", bg=BG, fg=MUTED,
                                    font=(FONT, 10), anchor="w")
        self._pause_note.pack(side="left", padx=(14, 0))

        # ---- THE SOUNDBAR: live input level, so "is it hearing me?" is
        #      answered by looking, not by dictating a test sentence.
        meter = tk.Frame(self.root, bg=BG)
        meter.pack(fill="x", padx=18, pady=(6, 2))
        tk.Label(meter, text="level", bg=BG, fg=MUTED,
                 font=(FONT, 9)).pack(side="left", padx=(0, 8))
        self._bar = tk.Canvas(meter, height=26, bg=TRACK, highlightthickness=0)
        self._bar.pack(side="left", fill="x", expand=True)
        self._bar_fill = self._bar.create_rectangle(0, 0, 0, 26, fill="#22c55e",
                                                    outline="")
        self._bar_peak = self._bar.create_rectangle(0, 0, 0, 26, fill="#065f46",
                                                    outline="")
        # The gate line: speech must clear this to be sent. Drawn so a bar that
        # moves but never reaches it explains itself.
        self._bar_gate = self._bar.create_line(0, 0, 0, 26, fill="#9ca3af",
                                               dash=(3, 2))
        self._bar_txt = self._bar.create_text(8, 13, anchor="w", text="",
                                              fill=FG, font=("Consolas", 9))

        # ---- the tooltip, in full: the tray's own words, nothing rephrased ----
        panel = tk.Frame(self.root, bg=PANEL, highlightbackground=TRACK,
                         highlightthickness=1)
        panel.pack(fill="both", expand=True, padx=18, pady=6)
        self._detail = tk.Label(panel, text="", bg=PANEL, fg=FG,
                                font=("Consolas", 10), anchor="nw",
                                justify="left", wraplength=520)
        self._detail.pack(fill="both", expand=True, padx=12, pady=12)

        # ---- the menu, as buttons ----
        self._btns: dict[str, ttk.Button] = {}
        bar = tk.Frame(self.root, bg=BG)
        bar.pack(fill="x", padx=18, pady=(6, 18))
        for key in tray_mod.MENU_KEYS:
            if key in tray_mod._DISPLAY_ONLY:     # engine/mic are readouts above
                continue
            b = ttk.Button(bar, text=key, style="K.TButton",
                           command=lambda k=key: self._invoke(k))
            b.pack(side="left", padx=(0, 6))
            self._btns[key] = b

    # ------------------------------------------------------------------ loop

    def run(self) -> None:
        """Blocks on the tkinter main loop until the window closes."""
        self._tick()
        self.root.mainloop()

    def _tick(self) -> None:
        if self._closing:
            return
        self._phase += 1
        try:
            vis = self._tray.update()
            self._paint(vis)
        except Exception as exc:                  # noqa: BLE001 - a blind window SAYS so
            self._state_lbl.config(text="UNKNOWN")
            self._canvas.itemconfig(self._lamp, fill=_hex((150, 70, 230)))
            self._detail.config(
                text=f"the window could not read the app:\n"
                     f"{type(exc).__name__}: {exc}")
        self.root.after(TICK_MS, self._tick)

    def _paint(self, vis) -> None:
        # A flashing state blinks between its frames; a steady one does not.
        # Same rule as the tray: len(frames) > 1 IS the flash.
        frames = tray_mod.icon_frames(vis.state)
        icon = frames[(self._phase * TICK_MS // FLASH_MS) % len(frames)]
        self._canvas.itemconfig(self._lamp, fill=_hex(icon.rgb))
        self._canvas.itemconfig(self._glyph, text=icon.glyph)
        self._state_lbl.config(text=vis.state.replace("_", " "))
        self._engine_lbl.config(text=f"engine: {vis.engine}")

        lines = vis.tooltip.splitlines()
        self._mic_lbl.config(text=lines[1] if len(lines) > 1 else "")
        self._detail.config(text=vis.tooltip)

        for item in self._tray.menu():
            b = self._btns.get(item.key)
            if b is not None:
                b.config(text=item.label,
                         state=("normal" if item.enabled else "disabled"))

        self._paint_playpause(vis)
        self._paint_level()

    # ------------------------------------------------------- play / pause

    def _paint_playpause(self, vis) -> None:
        paused = str(vis.state).upper() == "PAUSED" or bool(
            getattr(vis, "paused", False))
        if paused:
            self._playpause.config(text="▶  RESUME", bg="#b45309")
            self._pause_note.config(
                text="typing is held — speech is still heard and parked")
        else:
            self._playpause.config(text="⏸  PAUSE", bg="#111827")
            self._pause_note.config(text="")

    def _toggle_pause(self) -> None:
        self._tray.toggle_pause()
        self._paint(self._tray.update())

    # ------------------------------------------------------------- level

    def _paint_level(self) -> None:
        """Draw the live input level. Honest about three different states:
        no stream at all, a stream delivering digital silence, and audio."""
        w = max(1, int(self._bar.winfo_width()))
        level = None
        if self._level_fn is not None:
            try:
                level = self._level_fn()
            except Exception as exc:              # a blind meter SAYS so
                self._bar.itemconfig(self._bar_txt,
                                     text=f"level unavailable: "
                                          f"{type(exc).__name__}")
                self._bar.coords(self._bar_fill, 0, 0, 0, 26)
                return

        if level is None:
            self._peak = 0.0
            self._bar.coords(self._bar_fill, 0, 0, 0, 26)
            self._bar.coords(self._bar_peak, 0, 0, 0, 26)
            self._bar.itemconfig(self._bar_txt, text="no stream")
            return

        # Log scale: speech (0.03) and room tone (0.003) are a factor of ten
        # apart and both must be visible on the same bar.
        import math
        lvl = max(float(level), 1e-6)
        frac = min(1.0, max(0.0, (math.log10(lvl) + 4.0) / 4.0))   # 1e-4..1
        self._peak = max(frac, self._peak - 0.02)                  # peak-hold

        gate_frac = min(1.0, max(0.0, (math.log10(0.008) + 4.0) / 4.0))
        colour = "#22c55e" if frac >= gate_frac else "#9ca3af"
        self._bar.itemconfig(self._bar_fill, fill=colour)
        self._bar.coords(self._bar_fill, 0, 0, int(w * frac), 26)
        self._bar.coords(self._bar_peak, max(0, int(w * self._peak) - 3), 0,
                         int(w * self._peak), 26)
        self._bar.coords(self._bar_gate, int(w * gate_frac), 0,
                         int(w * gate_frac), 26)
        self._bar.itemconfig(
            self._bar_txt,
            text=("SILENT — stream open, no audio" if lvl <= 1e-5
                  else f"rms {lvl:.4f}"))

    # --------------------------------------------------------------- actions

    def _invoke(self, key: str) -> None:
        if key == "quit":
            self._quit()
            return
        self._tray.invoke(key)

    def _quit(self) -> None:
        """Closing the window ends the program — the same one exit the tray's
        Quit uses. It is never a hide: a mic still capturing behind a window
        Iddo believes he closed is the silent-loss class this rebuild exists
        to kill."""
        if self._closing:
            return
        self._closing = True
        try:
            self._on_quit()
        finally:
            self.root.destroy()
