"""alma-mic / gui.py — the visible window: live monitor + transcript + settings.

ALMAWARE-pure: every line ours. tkinter = Python's own GUI (stdlib). Bright design.
All recognition runs in pipeline.py (the one pipeline); this file is just the window:
callbacks from pipeline threads are marshalled onto a UI queue drained by a timer
(the tkinter main loop is the only thread that touches widgets).
"""
from __future__ import annotations
import queue
import threading
import tkinter as tk
from tkinter import scrolledtext, ttk

import audio
import brain
import hotkey as hotkey_mod
from config import Config
from pipeline import Pipeline

# ---- bright theme ----
BG = "#ffffff"; FG = "#1a1a1a"; MUTED = "#6b7280"; TRACK = "#e5e7eb"
GREEN = "#16a34a"; BLUE = "#2563eb"; RED = "#dc2626"; PANEL = "#f9fafb"
AMBER = "#f59e0b"; AMBER_DK = "#d97706"   # pause button
FONT = "Segoe UI"
METER_FULL_RMS = 0.25


def _pretty(name: str) -> str:
    """WDM-KS reports raw driver paths - show something a human can choose from."""
    n = name.strip()
    if "@" in n and (".sys" in n.lower() or ".inf" in n.lower()):
        head = n.split("(")[0].strip()
        return head or n
    return n


class MicWindow:
    def __init__(self):
        self.cfg = Config.load()
        self._model_sig = self._sig()
        self._ui_q: "queue.Queue[tuple]" = queue.Queue()
        self._segments = 0
        self.pipe = Pipeline(self.cfg, **self._cbs())

        self._last_text = ""        # most recent finalized utterance
        # brain_auto guards: never flood headless grok.exe with every STT fragment
        self._brain_busy = False
        self._brain_last_q = ""
        self._brain_last_ts = 0.0

        self.root = tk.Tk()
        self.root.title("ALMA-MIC")
        self.root.configure(bg=BG)
        self.root.geometry("580x880+90+60")   # fixed visible spot (top-left), no focus-steal
        self.root.minsize(520, 720)
        self._build()
        self._render_arm()      # show the default-ON dictation state on the button
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(33, self._poll)

    def _sig(self):
        c = self.cfg
        return (c.model, c.lora_dir, c.device, c.compute_type)

    # callbacks run on pipeline threads -> just enqueue for the UI thread
    def _cbs(self):
        q = lambda *m: self._ui_q.put(m)
        return dict(
            on_level=lambda rms, sp: q("level", rms, sp),
            on_text=lambda t, lang: q("transcript", t, lang),
            on_device=lambda d: q("device", d),
            on_model=lambda d: q("model", d),
            on_error=lambda m: q("error", m),
            on_log=lambda m: q("log", m),
        )

    # ---------------------------------------------------------------- layout
    def _build(self):
        pad = {"padx": 18}
        top = tk.Frame(self.root, bg=BG); top.pack(fill="x", pady=(14, 0), **pad)
        tk.Label(top, text="🎙️  ALMA-MIC", bg=BG, fg=FG,
                 font=(FONT, 22, "bold")).pack(side="left")
        tk.Button(top, text="⚙  הגדרות", font=(FONT, 10), relief="flat", bg=TRACK, fg=FG,
                  activebackground="#d1d5db", cursor="hand2",
                  command=self._open_settings).pack(side="right")

        self.device_var = tk.StringVar(value="מאתר מיקרופון…")
        tk.Label(self.root, textvariable=self.device_var, bg=BG, fg=FG, font=(FONT, 10),
                 wraplength=520, justify="left").pack(anchor="w", pady=(10, 2), **pad)

        self.status_var = tk.StringVar(value="…")
        self.status = tk.Label(self.root, textvariable=self.status_var, bg=BG, fg=GREEN,
                               font=(FONT, 15, "bold"))
        self.status.pack(anchor="w", pady=(2, 4), **pad)

        # --- DICTATION ARM (walkie-talkie): type into the focused window ONLY while ON.
        # Default OFF so the mic never pours ambient speech/noise into your work. ---
        df = tk.Frame(self.root, bg=BG); df.pack(fill="x", pady=(2, 6), **pad)
        self.dict_btn = tk.Button(
            df, text="🔴  הכתבה כבויה — לחץ כדי להקליד  (Ctrl+Alt+D)",
            font=(FONT, 12, "bold"), relief="flat", bg="#fee2e2", fg=RED,
            activebackground="#fecaca", cursor="hand2", command=self._toggle_arm)
        self.dict_btn.pack(fill="x", ipady=3)

        self.meter = tk.Canvas(self.root, width=520, height=26, bg=BG, highlightthickness=0)
        self.meter.pack(anchor="w", **pad)
        self.meter.create_rectangle(0, 5, 520, 21, fill=TRACK, width=0)
        self._fill = self.meter.create_rectangle(0, 5, 0, 21, fill=GREEN, width=0)
        self.rms_var = tk.StringVar(value="RMS 0.00000")
        tk.Label(self.root, textvariable=self.rms_var, bg=BG, fg=MUTED,
                 font=("Consolas", 9)).pack(anchor="w", **pad)

        tk.Label(self.root, text="תמלול חי:", bg=BG, fg=FG,
                 font=(FONT, 11, "bold")).pack(anchor="w", pady=(10, 2), **pad)
        self.transcript = scrolledtext.ScrolledText(
            self.root, height=12, bg=PANEL, fg=FG, font=(FONT, 12), relief="flat",
            borderwidth=1, highlightthickness=1, highlightbackground=TRACK, wrap="word")
        self.transcript.pack(fill="both", expand=True, padx=18, pady=(0, 6))
        self.transcript.configure(state="disabled")

        self.log_var = tk.StringVar(value="")
        tk.Label(self.root, textvariable=self.log_var, bg=BG, fg=MUTED, font=("Consolas", 9),
                 anchor="w").pack(fill="x", **pad)

        # --- BRAIN: ask Grok (primary) with DictaLM-on-DGX Hebrew fallback ---
        bf = tk.LabelFrame(self.root, text="🧠 מוח (Grok · דיקטה)", bg=BG, fg=FG,
                           font=(FONT, 10, "bold"), labelanchor="w")
        bf.pack(fill="x", padx=18, pady=(4, 2))
        row1 = tk.Frame(bf, bg=BG); row1.pack(fill="x", padx=6, pady=(4, 2))
        self.brain_entry = tk.Entry(row1, font=(FONT, 11))
        self.brain_entry.pack(side="left", fill="x", expand=True)
        self.brain_entry.bind("<Return>", lambda e: self._ask_brain())
        self.brain_btn = tk.Button(row1, text="🧠 שאל", font=(FONT, 10, "bold"), relief="flat",
                                   bg=BLUE, fg="white", activebackground="#1d4ed8",
                                   cursor="hand2", command=self._ask_brain)
        self.brain_btn.pack(side="left", padx=(6, 0))
        row2 = tk.Frame(bf, bg=BG); row2.pack(fill="x", padx=6, pady=(0, 4))
        tk.Label(row2, text="מוח:", bg=BG, fg=MUTED, font=(FONT, 9)).pack(side="left")
        self.brain_backend_var = tk.StringVar(value=getattr(self.cfg, "brain_backend", "grok"))
        ttk.Combobox(row2, textvariable=self.brain_backend_var, values=["grok", "dicta"],
                     state="readonly", width=8).pack(side="left", padx=(4, 0))
        self.brain_backend_var.trace_add("write", lambda *a: self._persist_brain())
        self.brain_auto_var = tk.BooleanVar(value=getattr(self.cfg, "brain_auto", False))
        tk.Checkbutton(row2, text="ענה אוטומטית על מה שאמרתי", variable=self.brain_auto_var,
                       bg=BG, fg=FG, activebackground=BG, font=(FONT, 10),
                       command=self._persist_brain).pack(side="left", padx=(10, 0))

        bar = tk.Frame(self.root, bg=BG); bar.pack(fill="x", pady=(6, 2), padx=18)
        self.btn = tk.Button(bar, text="⏸  פאוזה", width=14, font=(FONT, 12, "bold"),
                             command=self._toggle, relief="flat", bg=AMBER, fg="white",
                             activebackground=AMBER_DK, activeforeground="white",
                             cursor="hand2")
        self.btn.pack(side="left")
        tk.Button(bar, text="נקה", width=8, font=(FONT, 10), command=self._clear,
                  relief="flat", bg=BG, fg=MUTED, activebackground=TRACK,
                  cursor="hand2").pack(side="left", padx=8)
        self.count_var = tk.StringVar(value="זוהו: 0")
        tk.Label(bar, textvariable=self.count_var, bg=BG, fg=MUTED,
                 font=(FONT, 10)).pack(side="right")

        self.hotkey_var = tk.StringVar(value="קיצור גלובלי: Ctrl+Alt+P  (פאוזה/המשך מכל חלון)")
        tk.Label(self.root, textvariable=self.hotkey_var, bg=BG, fg=MUTED,
                 font=(FONT, 9)).pack(anchor="w", padx=18, pady=(0, 12))


    # ---------------------------------------------------------------- UI pump
    def _poll(self):
        try:
            while True:
                m = self._ui_q.get_nowait()
                k = m[0]
                if k == "device":
                    self.device_var.set("🎧 " + m[1])
                elif k == "model":
                    self.device_var.set(self.device_var.get() + f"   ·   🧠 {m[1]}")
                elif k == "level":
                    self._set_level(m[1], m[2])
                elif k == "toggle":          # global hotkey → pause/resume
                    self._toggle()
                elif k == "arm_toggle":      # global hotkey → dictation on/off
                    self._toggle_arm()
                elif k == "transcript":
                    self._add_transcript(m[1], m[2])
                elif k == "brain_answer":
                    self._add_brain_line(m[1], m[2])   # (answer, who) — also clears busy
                elif k == "brain_done":
                    self._brain_busy = False
                    try:
                        self.brain_btn.configure(state="normal")
                    except Exception:
                        pass
                elif k == "log":
                    self.log_var.set(m[1])
                elif k == "error":
                    self.status_var.set("⚠️ שגיאה"); self.status.configure(fg=RED)
                    self.log_var.set(f"[error] {m[1]}")
        except queue.Empty:
            pass
        self.root.after(33, self._poll)

    def _set_level(self, rms, in_speech):
        pct = min(1.0, rms / METER_FULL_RMS)
        self.meter.coords(self._fill, 0, 5, int(520 * pct), 21)
        self.rms_var.set(f"RMS {rms:.5f}")
        if not self.pipe.model_ready:
            self.status_var.set("⏳ טוען מודל…"); self.status.configure(fg=MUTED)
            return
        if in_speech:
            self.meter.itemconfigure(self._fill, fill=BLUE)
            self.status_var.set("🗣️  דיבור"); self.status.configure(fg=BLUE)
        else:
            self.meter.itemconfigure(self._fill, fill=GREEN)
            mode = "מילת-הפעלה" if self.cfg.arming == "wakeword" else "אוטומט"
            typ = " · 🟢 מקליד לחלון" if self.pipe.armed else " · 🔴 לא מקליד"
            self.status_var.set(f"🟢  מקשיב ({mode}){typ}"); self.status.configure(fg=GREEN)

    def _toggle_arm(self):
        """Arm/disarm typing into the focused window (default off = listen-only)."""
        self.pipe.armed = not self.pipe.armed
        self._render_arm()

    def _render_arm(self):
        if self.pipe.armed:
            self.dict_btn.configure(text="🟢  הכתבה דלוקה — מקליד לחלון הפעיל  (Ctrl+Alt+D)",
                                    bg="#dcfce7", fg=GREEN, activebackground="#bbf7d0")
        else:
            self.dict_btn.configure(text="🔴  הכתבה כבויה — לחץ כדי להקליד  (Ctrl+Alt+D)",
                                    bg="#fee2e2", fg=RED, activebackground="#fecaca")

    def _add_transcript(self, text, lang):
        self._segments += 1
        self.count_var.set(f"זוהו: {self._segments}")
        self.transcript.configure(state="normal")
        self.transcript.insert("end", f"[{lang}] {text}\n")
        self.transcript.see("end")
        self.transcript.configure(state="disabled")
        self._last_text = text
        if getattr(self, "brain_auto_var", None) is not None and self.brain_auto_var.get():
            self._ask_brain(auto=True)

    # ---------------------------------------------------------------- brain
    def _persist_brain(self):
        self.cfg.brain_backend = self.brain_backend_var.get()
        self.cfg.brain_auto = bool(self.brain_auto_var.get())
        self.cfg.save()

    def _brain_auto_allowed(self, q: str) -> bool:
        """Refuse ambient/noise STT fragments so brain_auto cannot spawn a swarm of grok.exe."""
        import time
        import re
        q = (q or "").strip()
        if len(q) < 12:
            return False
        # ignore pure fillers / very short English noise
        if re.fullmatch(r"[\W\d_]+", q, flags=re.UNICODE):
            return False
        low = q.lower()
        fillers = {
            "oh yeah", "oh, yeah", "ok", "okay", "yeah", "yep", "hmm", "uh", "um",
            "תודה", "תודה רבה", "בסדר", "אה", "אהה",
        }
        if low.rstrip(".!, ") in fillers:
            return False
        # debounce identical + concurrent
        now = time.time()
        if self._brain_busy:
            return False
        if q == self._brain_last_q and (now - self._brain_last_ts) < 8.0:
            return False
        if (now - self._brain_last_ts) < 2.5:
            return False
        return True

    def _ask_brain(self, auto=False):
        q = (self._last_text if auto else self.brain_entry.get()).strip()
        if not q:
            return
        if auto and not self._brain_auto_allowed(q):
            return
        if not auto:
            self.brain_entry.delete(0, "end")
        backend = self.brain_backend_var.get()
        dicta_url = getattr(self.cfg, "dicta_url", "")
        self.brain_btn.configure(state="disabled")
        self._brain_busy = True
        import time as _time
        self._brain_last_q = q
        self._brain_last_ts = _time.time()
        self.log_var.set(f"🧠 שואל ({backend})…")

        def work():
            try:
                ans, who = brain.ask(q, backend=backend, dicta_url=dicta_url, timeout=90.0)
                self._ui_q.put(("brain_answer", ans, who))
            finally:
                self._ui_q.put(("brain_done",))
        threading.Thread(target=work, daemon=True).start()

    def _add_brain_line(self, ans, who):
        self._brain_busy = False
        self.brain_btn.configure(state="normal")
        self.transcript.configure(state="normal")
        self.transcript.insert("end", f"🧠 [{who}] {ans}\n")
        self.transcript.see("end")
        self.transcript.configure(state="disabled")
        self.log_var.set("")

    # ---------------------------------------------------------------- buttons
    def _clear(self):
        self.transcript.configure(state="normal")
        self.transcript.delete("1.0", "end")
        self.transcript.configure(state="disabled")

    def _toggle(self):
        if self.pipe.running:
            self.pipe.stop()
            self.btn.configure(text="▶  המשך", bg=GREEN, activebackground="#15803d")
            self.status_var.set("⏸  מושהה"); self.status.configure(fg=MUTED)
            self._set_level(0.0, False)
        else:
            self.pipe.start()
            self.btn.configure(text="⏸  פאוזה", bg=AMBER, activebackground=AMBER_DK)

    def _on_close(self):
        self.pipe.stop()
        self.root.destroy()

    # ---------------------------------------------------------------- settings
    def _open_settings(self):
        SettingsDialog(self.root, self.cfg, self._apply_settings)

    def _apply_settings(self):
        self.cfg.save()
        was = self.pipe.running
        if was:
            self.pipe.stop()
        if self._sig() != self._model_sig:          # model/device changed -> reload
            self.pipe = Pipeline(self.cfg, **self._cbs())
            self._model_sig = self._sig()
        if was:
            self.pipe.start()
        self._render_arm()      # a recreated pipe starts disarmed — keep the button in sync

    def run(self):
        self.pipe.start()
        # global hotkeys: Ctrl+Alt+P pause/resume the whole pipeline; Ctrl+Alt+D arm/disarm typing
        self.hotkey = hotkey_mod.GlobalHotkey(on_press=lambda: self._ui_q.put(("toggle",)))
        self.hotkey.start()
        self.hotkey_arm = hotkey_mod.GlobalHotkey(
            on_press=lambda: self._ui_q.put(("arm_toggle",)), vk=0x44, label="Ctrl+Alt+D")
        self.hotkey_arm.start()
        self.root.after(800, self._check_hotkey)
        # NOTE: do NOT grab foreground/topmost here — that made the mic steal focus
        # and type into ITSELF instead of the window you're working in.
        self.root.mainloop()

    def _check_hotkey(self):
        if not getattr(self.hotkey, "ok", False):
            self.hotkey_var.set("קיצור גלובלי תפוס במערכת — השתמש בכפתור פאוזה")
            self.hotkey_var_failed = True


class SettingsDialog(tk.Toplevel):
    """Mic / languages / translate / wake-word / model / typing — Iddo's choices."""

    LANGS = ["auto", "he", "en", "ar", "ru", "fr", "es"]
    DEVS = ["auto", "cuda", "cpu"]

    def __init__(self, master, cfg: Config, on_save):
        super().__init__(master)
        self.cfg = cfg; self.on_save = on_save
        self.title("הגדרות ALMA-MIC")
        self.configure(bg=BG)
        self.geometry("470x720")
        self.grab_set()
        self._build()

    def _row(self, label):
        f = tk.Frame(self, bg=BG); f.pack(fill="x", padx=18, pady=5)
        tk.Label(f, text=label, bg=BG, fg=FG, font=(FONT, 11, "bold")).pack(anchor="w")
        return f

    def _build(self):
        tk.Label(self, text="⚙  הגדרות", bg=BG, fg=FG,
                 font=(FONT, 16, "bold")).pack(anchor="w", padx=18, pady=(14, 4))

        f = self._row("מיקרופון")
        # A bare list of names was useless: the same physical mic appears once
        # per host API, and nothing told you which of them actually passes
        # audio. Probe each one and say so. ● = live, ○ = silent.
        self._mic_labels: dict[str, str] = {}      # label -> value stored in config
        self.mic_var = tk.StringVar()
        self.mic_box = ttk.Combobox(f, textvariable=self.mic_var, state="readonly")
        self.mic_box.pack(fill="x")

        row2 = tk.Frame(f, bg=BG); row2.pack(fill="x", pady=(4, 0))
        self.mic_status = tk.Label(row2, text="", bg=BG, fg="#6b7280",
                                   font=(FONT, 9), anchor="e", justify="right")
        self.mic_status.pack(side="right")
        tk.Button(row2, text="🎤 בדוק מיקרופונים", font=(FONT, 9), relief="flat",
                  bg=TRACK, fg=FG, activebackground="#d1d5db", cursor="hand2",
                  command=self._refresh_mics).pack(side="left")
        self._refresh_mics(initial=True)

        f = self._row("שפה")
        self.lang_var = tk.StringVar(value=self.cfg.language)
        ttk.Combobox(f, textvariable=self.lang_var, values=self.LANGS, state="readonly").pack(fill="x")

        f = self._row("תרגום")
        self.translate_var = tk.BooleanVar(value=self.cfg.translate_to_english)
        tk.Checkbutton(f, text="תרגם לאנגלית (Whisper מתרגם רק לאנגלית)",
                       variable=self.translate_var, bg=BG, fg=FG, activebackground=BG,
                       font=(FONT, 10)).pack(anchor="w")

        f = self._row("הפעלה (מילת-חימוש)")
        self.arming_var = tk.StringVar(value=self.cfg.arming)
        tk.Radiobutton(f, text="אוטומט — תמיד מקשיב (VAD)", variable=self.arming_var,
                       value="auto", bg=BG, fg=FG, activebackground=BG,
                       font=(FONT, 10)).pack(anchor="w")
        tk.Radiobutton(f, text="מילת-הפעלה — רק אחרי המילה", variable=self.arming_var,
                       value="wakeword", bg=BG, fg=FG, activebackground=BG,
                       font=(FONT, 10)).pack(anchor="w")
        tk.Label(f, text="מילות-הפעלה (מופרדות בפסיק):", bg=BG, fg=MUTED,
                 font=(FONT, 9)).pack(anchor="w", pady=(4, 0))
        self.wake_var = tk.StringVar(value=", ".join(self.cfg.wake_words))
        tk.Entry(f, textvariable=self.wake_var).pack(fill="x")

        f = self._row("פלט")
        self.type_var = tk.BooleanVar(value=self.cfg.type_output)
        tk.Checkbutton(f, text="הקלד לחלון הפעיל", variable=self.type_var, bg=BG, fg=FG,
                       activebackground=BG, font=(FONT, 10)).pack(anchor="w")
        self.enter_var = tk.BooleanVar(value=self.cfg.auto_enter)
        tk.Checkbutton(f, text="לחץ Enter אחרי כל שורה", variable=self.enter_var, bg=BG,
                       fg=FG, activebackground=BG, font=(FONT, 10)).pack(anchor="w")

        self.anywhere_var = tk.BooleanVar(value=getattr(self.cfg, "type_anywhere", False))
        tk.Checkbutton(f, text="הקלד לכל חלון (לא רק ChatGPT/Claude/Codex)",
                       variable=self.anywhere_var, bg=BG, fg=FG,
                       activebackground=BG, font=(FONT, 10)).pack(anchor="w")

        f = self._row("מודל זיהוי")
        self.model_var = tk.StringVar(value=self.cfg.model)
        tk.Entry(f, textvariable=self.model_var).pack(fill="x")
        tk.Label(f, text="לורה עברית משלנו (תיקיית ct2, אופציונלי):", bg=BG, fg=MUTED,
                 font=(FONT, 9)).pack(anchor="w", pady=(4, 0))
        self.lora_var = tk.StringVar(value=self.cfg.lora_dir)
        tk.Entry(f, textvariable=self.lora_var).pack(fill="x")
        f2 = tk.Frame(f, bg=BG); f2.pack(fill="x", pady=(4, 0))
        tk.Label(f2, text="מעבד:", bg=BG, fg=MUTED, font=(FONT, 9)).pack(side="left")
        self.device_var = tk.StringVar(value=self.cfg.device)
        ttk.Combobox(f2, textvariable=self.device_var, values=self.DEVS, state="readonly",
                     width=8).pack(side="left", padx=6)

        f = self._row("מוח: כתובת DictaLM על DGX (פולבק עברי, אופציונלי)")
        self.dicta_var = tk.StringVar(value=getattr(self.cfg, "dicta_url", ""))
        tk.Entry(f, textvariable=self.dicta_var).pack(fill="x")
        tk.Label(f, text="למשל http://eran1:8090/v1/chat/completions — משמש כשגרוק לא מספיק",
                 bg=BG, fg=MUTED, font=(FONT, 9)).pack(anchor="w")

        bar = tk.Frame(self, bg=BG); bar.pack(fill="x", padx=18, pady=16)
        tk.Button(bar, text="שמור והחל", font=(FONT, 11, "bold"), relief="flat", bg=GREEN,
                  fg="white", activebackground="#15803d", cursor="hand2",
                  command=self._save).pack(side="left")
        tk.Button(bar, text="ביטול", font=(FONT, 10), relief="flat", bg=TRACK, fg=FG,
                  activebackground="#d1d5db", cursor="hand2",
                  command=self.destroy).pack(side="left", padx=8)

    def _refresh_mics(self, initial: bool = False):
        """Probe every input and label it live or silent, so the choice is informed."""
        self.mic_status.config(text="בודק…")
        self.update_idletasks()
        labels, live_n = ["auto  —  בחר לבד את הכי חזק"], 0
        self._mic_labels = {labels[0]: "auto"}
        seen = set()
        for d in audio.list_input_devices():
            nl = d.name.lower()
            # "Sound Mapper" / "Primary Sound Capture" are Windows ALIASES, not
            # devices - offering them as a choice is offering a redirect.
            if any(nd in nl for nd in audio._NOT_DEVICES):
                continue
            key = _pretty(d.name).lower()
            if key in seen:            # same mic on 4 host APIs - show it once
                continue
            seen.add(key)
            try:
                rms = audio.probe_rms(d.index, 0.25)
            except Exception:
                rms = 0.0
            live = rms >= audio.LIVE_RMS_FLOOR
            live_n += 1 if live else 0
            lab = "%s %s  ·  %s" % ("●" if live else "○", _pretty(d.name),
                                    "פעיל rms %.4f" % rms if live else "שקט")
            labels.append(lab)
            self._mic_labels[lab] = d.name
        self.mic_box.config(values=labels)

        cur = self.cfg.mic
        match = next((l for l, v in self._mic_labels.items() if v == cur), labels[0])
        if initial or self.mic_var.get() not in self._mic_labels:
            self.mic_var.set(match)
        self.mic_status.config(
            text="%d מיקרופונים · %d פעילים" % (len(labels) - 1, live_n))

    def _save(self):
        c = self.cfg
        c.mic = self._mic_labels.get(self.mic_var.get(), self.mic_var.get()) or "auto"
        c.language = self.lang_var.get()
        c.translate_to_english = self.translate_var.get()
        c.arming = self.arming_var.get()
        c.wake_words = [w.strip() for w in self.wake_var.get().split(",") if w.strip()]
        c.type_output = self.type_var.get()
        c.auto_enter = self.enter_var.get()
        c.type_anywhere = self.anywhere_var.get()
        c.model = self.model_var.get().strip() or c.model
        c.lora_dir = self.lora_var.get().strip()
        c.device = self.device_var.get()
        c.dicta_url = self.dicta_var.get().strip()
        self.on_save()
        self.destroy()


def _selftest_hook():
    """If a .selftest flag file is present, prove typing works and exit.

    The app is launched by a scheduled task so it runs ELEVATED (see
    selftest_uipi.py for why). That makes it the only easy way to run code at
    HIGH integrity without a UAC prompt - so this hook lets the self-test ride
    in on the same launch. Drop the flag file, start the task, read the proof.
    Guarded: any failure here must never stop the real app from starting.
    """
    import os
    flag = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".selftest")
    if not os.path.exists(flag):
        return False
    try:
        os.remove(flag)          # one-shot; never leaves the app stuck in test mode
    except Exception:
        pass
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uipi_proof.txt")
    try:
        import sys
        import traceback
        import selftest_uipi
        with open(out, "w", encoding="utf-8") as f:
            sys.stdout = sys.stderr = f
            code = selftest_uipi.main()
            f.write("\nexit=%d\n" % code)
    except Exception:
        import traceback
        try:
            with open(out, "a", encoding="utf-8") as f:
                f.write("selftest crashed:\n" + traceback.format_exc())
        except Exception:
            pass
    return True


if __name__ == "__main__":
    if not _selftest_hook():
        MicWindow().run()
