"""ui_toggle.py - floating toggle panel for the Hebrew mic.

Mic picker · live VU meter · target buttons · Choose-Window picker · arm/pause.

"""
from __future__ import annotations

import os
import threading
import tkinter as tk
from tkinter import ttk
from typing import Callable

# When the desktop icon is clicked, the launcher .exe just TOUCHES this file.
# The running UI polls for it and surfaces its own window (clean & native — no
# fragile ctypes from the frozen exe, and it's user-initiated so not a hijack).
SHOW_REQUEST = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".show_request")

import sounddevice as sd

try:
    import router  # for enumerating open windows in the picker
except Exception:
    router = None

def _list_input_devices() -> list[tuple[int, str]]:
    devs = []
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0:
            devs.append((i, d["name"]))
    return devs

def run(
    ui_state: dict,
    lock: threading.Lock,
    targets: dict,
    callback: Callable[[str, str], None],
):
    root = tk.Tk()
    root.title("🎤 Hebrew Mic")
    root.attributes("-topmost", True)
    root.resizable(True, True)          # real window: minimize + MAXIMIZE (the 'middle' button) + close
    root.minsize(400, 320)
    root.configure(bg="#1e1e2e")

    FONT      = ("Segoe UI", 10)
    FONT_BOLD = ("Segoe UI", 10, "bold")
    FONT_MONO = ("Consolas", 9)
    BG        = "#1e1e2e"
    FG        = "#cdd6f4"
    FG_DIM    = "#6c7086"
    BLUE      = "#89b4fa"
    GREEN     = "#a6e3a1"
    RED       = "#f38ba8"
    YELLOW    = "#f9e2af"
    PURPLE    = "#cba6f7"
    INACTIVE  = "#313244"

    for c in range(5):
        root.columnconfigure(c, weight=1)

    row = 0

    # ── Mic picker ────────────────────────────────────────────────────────────
    tk.Label(root, text="🎤", font=FONT_BOLD, bg=BG, fg=FG).grid(
        row=row, column=0, padx=(8, 2), pady=(8, 2), sticky="w")
    mic_var = tk.StringVar()
    mic_devices = _list_input_devices()
    mic_names = [name for _, name in mic_devices]
    with lock:
        cur_mic = ui_state.get("mic_name") or ""
    default_mic = next((n for n in mic_names if cur_mic and cur_mic.lower() in n.lower()), "")
    mic_var.set(default_mic or (mic_names[0] if mic_names else ""))
    mic_combo = ttk.Combobox(root, textvariable=mic_var, values=mic_names,
                              state="readonly", width=26, font=FONT)
    mic_combo.grid(row=row, column=1, columnspan=4, padx=(2, 8), pady=(8, 2), sticky="ew")
    mic_combo.bind("<<ComboboxSelected>>", lambda e: callback("mic", mic_var.get()))
    row += 1

    # ── Live VU meter ─────────────────────────────────────────────────────────
    tk.Label(root, text="VU", font=FONT_MONO, bg=BG, fg=FG_DIM).grid(
        row=row, column=0, padx=(8, 2), pady=(2, 2), sticky="w")
    vu_canvas = tk.Canvas(root, height=14, bg=INACTIVE, highlightthickness=0)
    vu_canvas.grid(row=row, column=1, columnspan=3, padx=(2, 2), pady=(2, 2), sticky="ew")
    vu_bar = vu_canvas.create_rectangle(0, 0, 0, 14, fill=GREEN, outline="")
    # threshold marker line (drawn in poll once width known)
    vu_thr = vu_canvas.create_line(0, 0, 0, 14, fill="#f5e0dc", width=2)
    vu_txt = tk.Label(root, text="0", font=FONT_MONO, bg=BG, fg=FG_DIM, width=5)
    vu_txt.grid(row=row, column=4, padx=(0, 8), sticky="e")
    row += 1

    # ── Target picker ─────────────────────────────────────────────────────────
    tk.Label(root, text="🪟", font=FONT_BOLD, bg=BG, fg=FG).grid(
        row=row, column=0, padx=(8, 2), pady=(6, 2), sticky="w")
    target_var = tk.StringVar()
    with lock:
        target_var.set(ui_state.get("target", "claude"))
    target_btns: dict[str, tk.Button] = {}

    def on_target(name: str):
        target_var.set(name)
        _refresh_targets()
        callback("target", name)

    def _refresh_targets():
        cur = target_var.get()
        for name, btn in target_btns.items():
            btn.configure(bg=BLUE if name == cur else INACTIVE,
                          fg="#1e1e2e" if name == cur else FG)

    for col, name in enumerate(targets.keys()):
        btn = tk.Button(root, text=name.capitalize(), font=FONT,
                        bg=INACTIVE, fg=FG, relief="flat", padx=4, pady=2,
                        command=lambda n=name: on_target(n))
        btn.grid(row=row, column=col + 1, padx=2, pady=(6, 2), sticky="ew")
        target_btns[name] = btn
    _refresh_targets()
    row += 1

    # ── Choose-Window picker (type into ANY open window) ──────────────────────
    def open_window_picker():
        if router is None:
            return
        try:
            wins = router._enum_windows()  # [(hwnd, title, proc), ...]
        except Exception:
            wins = []
        # de-dup + drop our own panel + blank titles
        seen, items = set(), []
        for hwnd, title, proc in wins:
            t = (title or "").strip()
            if not t or t in seen or t == "🎤 Hebrew Mic":
                continue
            seen.add(t)
            items.append((hwnd, t, proc))
        items.sort(key=lambda x: x[1].lower())

        top = tk.Toplevel(root)
        top.title("Choose window to type into")
        top.attributes("-topmost", True)
        top.configure(bg=BG)
        top.geometry("460x420")
        tk.Label(top, text="Pick a window — dictation will type there:",
                 font=FONT_BOLD, bg=BG, fg=FG).pack(padx=10, pady=(10, 4), anchor="w")
        # filter box
        filt = tk.StringVar()
        ent = tk.Entry(top, textvariable=filt, font=FONT, bg=INACTIVE, fg=FG,
                       insertbackground=FG, relief="flat")
        ent.pack(fill="x", padx=10, pady=(0, 6))
        lb = tk.Listbox(top, font=FONT_MONO, bg="#181825", fg=FG, relief="flat",
                        selectbackground=BLUE, selectforeground="#1e1e2e",
                        activestyle="none", height=16)
        lb.pack(fill="both", expand=True, padx=10, pady=(0, 6))

        def populate(flt=""):
            lb.delete(0, tk.END)
            lb._rows = []
            f = flt.lower()
            for hwnd, t, proc in items:
                if f and f not in t.lower() and f not in (proc or "").lower():
                    continue
                lb._rows.append((hwnd, t))
                label = t if len(t) <= 52 else t[:49] + "…"
                lb.insert(tk.END, f"{label}   [{proc}]")
        populate()
        filt.trace_add("write", lambda *a: populate(filt.get()))

        def choose(_e=None):
            sel = lb.curselection()
            if not sel:
                return
            hwnd, t = lb._rows[sel[0]]
            callback("window", f"{hwnd}|{t}")
            top.destroy()
        lb.bind("<Double-Button-1>", choose)
        ent.bind("<Return>", lambda e: (lb.selection_clear(0, tk.END),
                                        lb.selection_set(0), choose()))
        btns = tk.Frame(top, bg=BG)
        btns.pack(fill="x", padx=10, pady=(0, 10))
        tk.Button(btns, text="✓ Use this window", font=FONT_BOLD, bg=GREEN,
                  fg="#1e1e2e", relief="flat", padx=8, pady=4,
                  command=choose).pack(side="left")
        tk.Button(btns, text="↻ Refresh", font=FONT, bg=INACTIVE, fg=FG,
                  relief="flat", padx=8, pady=4,
                  command=lambda: (top.destroy(), open_window_picker())).pack(side="left", padx=6)
        tk.Button(btns, text="Cancel", font=FONT, bg=INACTIVE, fg=FG,
                  relief="flat", padx=8, pady=4,
                  command=top.destroy).pack(side="right")
        ent.focus_set()

    choose_btn = tk.Button(root, text="🪟 Choose window to type in…", font=FONT_BOLD,
                           bg=PURPLE, fg="#1e1e2e", relief="flat", padx=8, pady=4,
                           command=open_window_picker)
    choose_btn.grid(row=row, column=0, columnspan=5, padx=8, pady=(4, 4), sticky="ew")
    row += 1

    # ── Language mode (auto-detect whitelist) ─────────────────────────────────
    ALL_LANGS = [("he", "עברית"), ("en", "English"), ("ar", "العربية"),
                 ("fr", "Français"), ("es", "Español"), ("it", "Italiano"),
                 ("ru", "Русский"), ("de", "Deutsch"), ("pt", "Português"),
                 ("zh", "中文"), ("ja", "日本語"), ("nl", "Nederlands")]
    DEFAULT_WL = ["he", "en", "ar", "fr", "es", "it", "ru", "de", "pt"]

    def open_lang_dialog():
        top = tk.Toplevel(root)
        top.title("Languages")
        top.attributes("-topmost", True)
        top.configure(bg=BG)
        top.geometry("310x470")
        tk.Label(top, text="🌍 Language detection", font=FONT_BOLD, bg=BG, fg=FG).pack(
            padx=12, pady=(12, 4), anchor="w")
        with lock:
            cur = ui_state.get("lang_whitelist")
        mode = tk.StringVar(value=("all" if not cur else "custom"))
        tk.Radiobutton(top, text="All languages (auto-detect everything)", variable=mode,
                       value="all", bg=BG, fg=FG, selectcolor=INACTIVE, font=FONT, anchor="w",
                       activebackground=BG, activeforeground=FG).pack(fill="x", padx=12)
        tk.Radiobutton(top, text="Only the languages I pick:", variable=mode, value="custom",
                       bg=BG, fg=FG, selectcolor=INACTIVE, font=FONT, anchor="w",
                       activebackground=BG, activeforeground=FG).pack(fill="x", padx=12, pady=(0, 2))
        boxf = tk.Frame(top, bg=BG)
        boxf.pack(fill="both", expand=True, padx=26, pady=2)
        curset = set(cur or DEFAULT_WL)
        langvars = {}
        for code, name in ALL_LANGS:
            v = tk.BooleanVar(value=(code in curset))
            langvars[code] = v
            tk.Checkbutton(boxf, text=f"{name}  ({code})", variable=v, bg=BG, fg=FG,
                           selectcolor=INACTIVE, font=FONT, anchor="w",
                           activebackground=BG, activeforeground=FG).pack(fill="x")

        def apply_langs():
            if mode.get() == "all":
                callback("langmode", "all")
            else:
                sel = [c for c, _ in ALL_LANGS if langvars[c].get()]
                callback("langmode", ",".join(sel) if sel else "he,en")
            top.destroy()

        bf = tk.Frame(top, bg=BG)
        bf.pack(fill="x", padx=12, pady=10)
        tk.Button(bf, text="✓ Apply", font=FONT_BOLD, bg=GREEN, fg="#1e1e2e", relief="flat",
                  padx=10, pady=4, command=apply_langs).pack(side="left")
        tk.Button(bf, text="he+en", font=FONT, bg=INACTIVE, fg=FG, relief="flat", padx=8, pady=4,
                  command=lambda: (callback("langmode", "he,en"), top.destroy())).pack(side="left", padx=6)
        tk.Button(bf, text="Cancel", font=FONT, bg=INACTIVE, fg=FG, relief="flat", padx=8, pady=4,
                  command=top.destroy).pack(side="right")

    lang_btn = tk.Button(root, text="🌍 Languages…", font=FONT_BOLD, bg=BLUE, fg="#1e1e2e",
                         relief="flat", padx=8, pady=4, command=open_lang_dialog)
    lang_btn.grid(row=row, column=0, columnspan=5, padx=8, pady=(0, 4), sticky="ew")
    row += 1

    # ── Mode + arm/pause ──────────────────────────────────────────────────────
    mode_label = tk.Label(root, text="", font=FONT_BOLD, bg=BG, anchor="w")
    mode_label.grid(row=row, column=0, columnspan=3, padx=8, pady=(4, 2), sticky="ew")
    arm_btn = tk.Button(root, text="", font=FONT, relief="flat", padx=8, pady=3)
    arm_btn.grid(row=row, column=3, columnspan=2, padx=(2, 8), pady=(4, 2), sticky="ew")
    row += 1

    # ── Translate toggle (deliberate ON/OFF; defaults OFF, can't get stuck) ───
    translate_btn = tk.Button(root, text="🌐 Translate: OFF", font=FONT, relief="flat",
                              bg=INACTIVE, fg=FG, padx=8, pady=3)
    translate_btn.grid(row=row, column=0, columnspan=5, padx=8, pady=(0, 2), sticky="ew")
    row += 1
    def _refresh_translate(on, code=""):
        if on:
            translate_btn.configure(text=f"🌐 Translate: ON  →  {code or 'en'}", bg=BLUE,
                                    fg="#1e1e2e", command=lambda: callback("translate", ""))
        else:
            translate_btn.configure(text="🌐 Translate: OFF  (transcribe)", bg=INACTIVE, fg=FG,
                                    command=lambda: callback("translate", "en"))
    _refresh_translate(False)

    # ── Prompt-mode send ──────────────────────────────────────────────────────
    prompt_frame = tk.Frame(root, bg=BG)
    prompt_frame.grid(row=row, columnspan=5, padx=8, pady=(2, 2), sticky="ew")
    prompt_label = tk.Label(prompt_frame, text="", font=FONT_MONO, bg=BG, fg=PURPLE, anchor="w")
    prompt_label.pack(side="left", fill="x", expand=True)
    send_prompt_btn = tk.Button(prompt_frame, text="📤 Send", font=FONT, bg=PURPLE,
                                fg="#1e1e2e", relief="flat", padx=6,
                                command=lambda: callback("mode", "prompt_send"))
    row += 1

    # ── Status line ───────────────────────────────────────────────────────────
    status_label = tk.Label(root, text="", font=FONT_MONO, bg=BG, fg=FG_DIM, anchor="w")
    status_label.grid(row=row, columnspan=5, padx=8, pady=(0, 4), sticky="ew")
    row += 1

    # ── Live dictation transcript (what was just typed) ───────────────────────
    tk.Label(root, text="📝 dictation (live)", font=FONT_MONO, bg=BG, fg=FG_DIM).grid(
        row=row, column=0, columnspan=5, padx=8, sticky="w")
    row += 1
    transcript_lbl = tk.Label(root, text="", font=("Segoe UI", 11), bg="#181825",
                              fg=GREEN, anchor="ne", justify="right",
                              wraplength=330, height=5, padx=6, pady=4)
    transcript_lbl.grid(row=row, column=0, columnspan=5, padx=8, pady=(0, 8), sticky="ew")

    def _refresh_arm(armed: bool):
        if armed:
            arm_btn.configure(text="⏸ Pause", bg=RED, fg="#1e1e2e",
                              command=lambda: callback("disarm", ""))
        else:
            arm_btn.configure(text="▶ Resume", bg=GREEN, fg="#1e1e2e",
                              command=lambda: callback("arm", ""))

    MODE_DISPLAY = {
        "normal":    ("🟢 NORMAL", FG),
        "prompt":    ("📝 PROMPT", PURPLE),
        "fast":      ("⚡ FAST", YELLOW),
        "translate": ("🌐 TRANSLATE", BLUE),
        "clipboard": ("📋 CLIPBOARD", GREEN),
    }
    THR_NORM = 150.0 / 1500.0  # threshold as fraction of the VU scale (rms/1500)

    def poll():
        with lock:
            armed    = ui_state.get("armed", True)
            status   = ui_state.get("status", "")
            target   = ui_state.get("target", "claude")
            mic_name = ui_state.get("mic_name") or ""
            mode     = ui_state.get("mode", "normal")
            translate_to = ui_state.get("translate_to")
            rms      = ui_state.get("rms_level", 0.0)
            rms_raw  = ui_state.get("rms_raw", 0)
            last_lang = ui_state.get("last_lang", "")
            transcript = list(ui_state.get("transcript", []))

        w = max(vu_canvas.winfo_width(), 1)
        bar_w = int(w * min(rms, 1.0))
        color = GREEN if rms < 0.6 else (YELLOW if rms < 0.85 else RED)
        vu_canvas.coords(vu_bar, 0, 0, bar_w, 14)
        vu_canvas.itemconfig(vu_bar, fill=color)
        thr_x = int(w * THR_NORM)
        vu_canvas.coords(vu_thr, thr_x, 0, thr_x, 14)
        vu_txt.configure(text=str(int(rms_raw)),
                         fg=GREEN if rms_raw >= 150 else FG_DIM)

        _refresh_arm(armed)
        _refresh_translate(bool(translate_to), translate_to or "")
        label_text, label_color = MODE_DISPLAY.get(mode, ("🟢 NORMAL", FG))
        mode_label.configure(text=label_text, fg=label_color)

        if mode == "prompt":
            send_prompt_btn.pack(side="right")
        else:
            send_prompt_btn.pack_forget()

        # reflect custom-window target on the picker button
        if isinstance(target, str) and target.startswith("win:"):
            choose_btn.configure(text="🪟 " + target[4:] + "  (change…)")
        target_var.set(target)
        _refresh_targets()
        lang_tag = f"  🌐 {last_lang}" if last_lang else ""
        status_label.configure(text=f"[{status}]{lang_tag}  {mic_name}")
        transcript_lbl.configure(text="\n".join(transcript[-5:]))

        # Desktop-icon "show me" request: the launcher touches .show_request.
        # Surface the window (the user clicked the icon → not a focus-hijack),
        # then clear the flag. Wrapped so a glitch here can never freeze the UI.
        try:
            if os.path.exists(SHOW_REQUEST):
                os.remove(SHOW_REQUEST)
                root.deiconify()
                _pin_top_right()
                root.lift()
        except Exception:
            pass

        root.after(120, poll)

    # Pin to the TOP-RIGHT corner of the PRIMARY monitor and stay on top, WITHOUT
    # stealing keyboard focus (2026-06-15, Iddo: "icon top-right corner, lock it
    # there"; 2026-06-16: it was landing on the LEFT — a pre-mainloop geometry()
    # gets overridden by the window manager on first map, so we MUST re-pin AFTER
    # the window is mapped). We anchor to the primary monitor's work-area right
    # edge via Win32 (SPI_GETWORKAREA), and use reqwidth (valid pre-map) so the
    # math is right even before the window has a real winfo_width().
    def _pin_top_right():
        try:
            root.deiconify()            # ensure it's shown (never stuck minimized / "no window")
            root.update_idletasks()
            ww = root.winfo_width()
            if ww <= 1:
                ww = root.winfo_reqwidth() or 360
            right = root.winfo_screenwidth()
            top = 0
            try:
                import ctypes
                from ctypes import wintypes
                rect = wintypes.RECT()
                # SPI_GETWORKAREA = 0x0030 -> PRIMARY monitor work area (excl. taskbar)
                if ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0):
                    right, top = rect.right, rect.top
            except Exception:
                pass
            root.geometry(f"+{max(right - ww - 16, 0)}+{top + 12}")
            root.attributes("-topmost", True)
        except Exception:
            pass

    # Re-pin after the WM has mapped the window (300ms) and once more after the
    # layout settles (1500ms), so it reliably lands and stays top-right.
    # Closing the window with [X] should HIDE it (withdraw), not destroy the UI
    # thread — otherwise the mic keeps running with no way to get the window back
    # ("the mic without a window is on"). Clicking the desktop icon re-shows it
    # via the .show_request poll above. The mic engine keeps running regardless.
    def _on_close():
        try:
            root.withdraw()
        except Exception:
            pass
    root.protocol("WM_DELETE_WINDOW", _on_close)

    root.after(300, _pin_top_right)
    root.after(1500, _pin_top_right)
    root.after(120, poll)
    root.mainloop()
