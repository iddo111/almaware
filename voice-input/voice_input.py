"""voice_input.py - hands-free Hebrew voice input for Claude Code.

FLOW: VAD speech-onset → capture → STT → route/command → type or act

Modes (config.mode):
  ptt      - hold hotkey to talk
  vad      - always listening (default)

Voice commands:
  שירי [target]     - switch window target
  שירי פרומפט       - enter prompt mode (accumulate, send on פרומפט סוף)
  פרומפט סוף        - send accumulated prompt + exit prompt mode
  שירי תרגם         - toggle Hebrew→English translation
  שירי מהיר         - fast mode: accumulate without Enter
  שירי שלח          - send fast buffer now
  שירי קליפבורד     - copy next utterance to clipboard only
  שירי שקט          - toggle silent mode (suppress indicators)
  שירי בטל          - undo (Ctrl+Z) in current window
  שירי היסטוריה     - open today's transcript log
  שירי סוף          - disarm mic (stop typing)
  שירי / מיקרופון   - arm mic (resume typing)

"""
from __future__ import annotations

import datetime
import json
import logging
import os
import subprocess
import sys
import threading
import time

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
HISTORY_DIR = os.path.join(HERE, "history")
os.makedirs(HISTORY_DIR, exist_ok=True)

import mic
import router
import transcribe as stt
import typer as kbd
from ducking import Ducker

# smart engines — graceful fallback if deps missing
try:
    from corrector import detect_spelled_word, parse_correction, log_correction, maybe_fix_phonetic
    _HAS_CORRECTOR = True
except Exception:
    _HAS_CORRECTOR = False
    def detect_spelled_word(t): return None
    def parse_correction(t, l): return None
    def log_correction(o, c, d): pass
    def maybe_fix_phonetic(t): return t

try:
    from iqbrainz import IQBrainz
    _HAS_IQ = True
except Exception:
    _HAS_IQ = False
    IQBrainz = None

try:
    from learner import VoiceProfile
    _HAS_LEARNER = True
except Exception:
    _HAS_LEARNER = False
    VoiceProfile = None

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("voiceinput")

def load_cfg() -> dict:
    with open(os.path.join(HERE, "config.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    if "--vad" in sys.argv:
        cfg["mode"] = "vad"
    if "--ptt" in sys.argv:
        cfg["mode"] = "ptt"
    if "--enter" in sys.argv:
        cfg["auto_enter"] = True
    return cfg

_silent_mode = False

def indicator(state: str, extra: str = "", ui_state: dict | None = None):
    icons = {
        "IDLE": "🟢", "LISTENING": "🎤", "DUCKED": "🔉", "TYPING": "⌨️",
        "READY": "✅", "ARMED": "🔴", "PAUSED": "⏸️",
        "PROMPT": "📝", "FAST": "⚡", "TRANSLATE": "🌐",
    }
    if not _silent_mode:
        print(f"{icons.get(state, '·')} [{state}] {extra}", flush=True)
    if ui_state is not None:
        ui_state["status"] = state

def _lang_badge(lang) -> str:
    """Tiny per-utterance language tag for the indicator/popup, e.g. '🌐 he'.

    Dual-mode STT returns result["lang"] ("he"/"en"/…) so the user can see
    which language was detected per utterance. Crash-safe: result["lang"] may
    be None — returns '' in that case (and never raises)."""
    try:
        code = (lang or "").strip().lower()
    except Exception:
        return ""
    return f"🌐 {code}" if code else ""

def toast(title: str, msg: str):
    try:
        import ctypes
        ctypes.windll.user32.MessageBeep(0)
    except Exception:
        pass
    log.info("%s - %s", title, msg)

def _write_history(text: str, mode: str = "dictation"):
    try:
        today = datetime.date.today().isoformat()
        path = os.path.join(HISTORY_DIR, f"{today}.txt")
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] [{mode}] {text}\n")
    except Exception as e:
        log.debug("history write failed: %s", e)

def _send_ctrl_z(hwnd):
    import ctypes
    VK_Z = 0x5A
    KEYEVENTF_KEYUP = 0x0002

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort),
                    ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong),
                    ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]

    class INPUT(ctypes.Structure):
        class _INPUT(ctypes.Union):
            _fields_ = [("ki", KEYBDINPUT)]
        _anonymous_ = ("_input",)
        _fields_ = [("type", ctypes.c_ulong), ("_input", _INPUT)]

    def key(vk, flags=0):
        i = INPUT()
        i.type = 1
        i.ki.wVk = vk
        i.ki.dwFlags = flags
        ctypes.windll.user32.SendInput(1, ctypes.byref(i), ctypes.sizeof(i))

    router.focus_window(hwnd)
    time.sleep(0.05)
    key(0x11)        # Ctrl down
    key(VK_Z)        # Z down
    key(VK_Z, KEYEVENTF_KEYUP)
    key(0x11, KEYEVENTF_KEYUP)

class VoiceInput:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.ducker = Ducker(duck_pct=cfg.get("duck_pct", 10),
                             exclude=set(cfg.get("duck_exclude", [])),
                             enabled=cfg.get("ducking_enabled", True))

        self.dev_idx, self.dev_name, note = mic.resolve_device(
            cfg.get("input_device"), cfg.get("fallback_devices", []),
            never_use=cfg.get("never_use_devices"),
            idle_if_no_good_mic=cfg.get("idle_if_no_good_mic", True))
        log.info("MIC: %s", note)
        self.no_mic = (self.dev_idx is None and self.dev_name is None)

        self.targets = router.DEFAULT_TARGETS
        self.target = cfg.get("default_target", "claude")

        # ── mode state ────────────────────────────────────────────────────────
        self.armed = True
        self.translate_to = None     # None = off (type spoken language); else target lang code
        self.silent_mode = False
        self.clipboard_next = False  # next utterance → clipboard only
        self._custom_hwnd = None     # explicit window chosen from the UI picker
        self._custom_title = ""

        # prompt mode: accumulate utterances, send all on פרומפט סוף
        self.prompt_mode = False
        self.prompt_buffer: list[str] = []

        # fast mode: accumulate without Enter, send on שירי שלח
        self.fast_mode = False
        self.fast_buffer: list[str] = []

        # voice shortcuts from config
        self.shortcuts: dict[str, str] = cfg.get("shortcuts", {})

        # smart engines
        self._last_raw_text = ""   # for correction ("fix that") context
        username = os.getenv("USERNAME", "default")
        profiles_dir = os.path.join(HERE, "profiles")

        self.profile: VoiceProfile | None = None
        if _HAS_LEARNER and VoiceProfile:
            self.profile = VoiceProfile(username=username, profiles_dir=profiles_dir)
            log.info("PROFILE: %s — %d samples, %d corrections, adapter=%s",
                     username, self.profile.sample_count(),
                     self.profile.correction_count(),
                     bool(self.profile.get_adapter_path()))

        self.iq: IQBrainz | None = None
        if _HAS_IQ and IQBrainz:
            profile_dir = os.path.join(profiles_dir, username)
            os.makedirs(profile_dir, exist_ok=True)
            self.iq = IQBrainz(profile_dir=profile_dir)
            log.info("IQBrainz: loaded (vocab=%d words)", len(getattr(self.iq, 'vocab', {})))

        # shared state for UI
        self._ui_lock = threading.Lock()
        self.ui_state: dict = {
            "status": "READY",
            "armed": True,
            "target": self.target,
            "mic_name": self.dev_name,
            "mic_idx": self.dev_idx,
            "mode": "normal",        # normal / prompt / fast / translate / clipboard
            "prompt_words": 0,
            "fast_words": 0,
            "rms_level": 0.0,
            "transcript": [],        # rolling last-N dictated lines (shown in widget)
            "last_text": "",
            "last_lang": "",         # per-utterance detected language ("he"/"en"/…)
            "lang_whitelist": cfg.get("lang_whitelist"),
        }

        # Show the GUI WINDOW IMMEDIATELY — BEFORE the slow (~4 min) model load — so the
        # mic is never "running with no window" during warmup. The panel shows live status.
        self._start_ui()

        log.info("STT: warming up '%s' on %s ...", cfg.get("model"), cfg.get("device"))
        stt.load(cfg)
        indicator("READY", f"mic={self.dev_name}  mode={cfg.get('mode')}  "
                           f"target={self.target}  auto_enter={cfg.get('auto_enter')}")

        # auto-focus startup target
        auto_target = cfg.get("auto_focus_target", self.target)
        if auto_target:
            ok, title = router.focus_target(auto_target, self.targets)
            log.info("AUTO-FOCUS: %r -> %s (%s)", auto_target,
                     "ok" if ok else "not found", title)

        self._start_memory_janitor()
        self._start_dashboard_publisher()

    # ── UI ─────────────────────────────────────────────────────────────────────
    def _start_ui(self):
        try:
            import ui_toggle
            th = threading.Thread(
                target=ui_toggle.run,
                args=(self.ui_state, self._ui_lock, self.targets, self._ui_callback),
                daemon=True)
            th.start()
            log.info("UI: toggle window launched")
        except Exception as e:
            log.info("UI: not available (%s) — headless", e)

    def _start_memory_janitor(self):
        """Periodic memory cleanup so the always-on mic never bloats over long
        sessions: Python GC + (Windows) trim the working set back to the OS.
        Interval from cfg['cache_cleanup_secs'] (default 30s for aggressive cleanup, 0 = off)."""
        import gc, os
        interval = int(self.cfg.get("cache_cleanup_secs", 30))
        if interval <= 0:
            return
        def _janitor():
            while True:
                time.sleep(interval)
                try:
                    # Three-level cleanup: (1) trigger full collection
                    gc.collect()
                    # (2) force unreachable objects to be freed immediately
                    gc.collect()
                    # (3) on Windows, trim working set (physical RAM) back to OS
                    if os.name == "nt":
                        import ctypes
                        ctypes.windll.psapi.EmptyWorkingSet(
                            ctypes.windll.kernel32.GetCurrentProcess())
                except Exception as e:  # noqa: BLE001
                    log.debug("memory janitor: %s", e)
        threading.Thread(target=_janitor, daemon=True).start()
        log.info("memory janitor on (every %ss, + post-WAV collection)", interval)

    def _start_dashboard_publisher(self):
        """Publish the LIVE mic state (vu / last_text / transcript / status) to the
        ALMAWARE Voice Dashboard's state dir, so the web UI at :8099 shows the REAL
        microphone — not the trainer's sample playback. Guarded daemon thread with
        atomic writes; must NEVER break the always-on loop (any error is swallowed).
        Disable via config.json {"dashboard_publish": false}."""
        import json
        if not self.cfg.get("dashboard_publish", True):
            return
        out_dir = self.cfg.get("dashboard_state_dir",
                               r"D:\CLAUDE\almaware-voice-dashboard\state")
        out_path = os.path.join(out_dir, "mic.json")
        tmp_path = out_path + ".tmp"
        interval = float(self.cfg.get("dashboard_publish_secs", 0.15))

        def _pub():
            while True:
                time.sleep(interval)
                try:
                    if not os.path.isdir(out_dir):
                        continue
                    with self._ui_lock:
                        snap = {
                            "ts":         time.time(),
                            "status":     self.ui_state.get("status", ""),
                            "armed":      self.ui_state.get("armed", True),
                            "mic_name":   self.ui_state.get("mic_name", ""),
                            "mode":       self.ui_state.get("mode", "normal"),
                            "vu":         float(self.ui_state.get("rms_level", 0.0) or 0.0),
                            "rms_raw":    self.ui_state.get("rms_raw", 0),
                            "last_text":  self.ui_state.get("last_text", ""),
                            "last_lang":  self.ui_state.get("last_lang", ""),
                            "transcript": list(self.ui_state.get("transcript", []))[-8:],
                        }
                    with open(tmp_path, "w", encoding="utf-8") as f:
                        json.dump(snap, f, ensure_ascii=False)
                    os.replace(tmp_path, out_path)
                except Exception as e:  # noqa: BLE001 — never kill the always-on loop
                    log.debug("dashboard publisher: %s", e)

        threading.Thread(target=_pub, daemon=True).start()
        log.info("dashboard publisher on -> %s", out_path)

    def _ui_callback(self, action: str, value: str):
        if action == "target":
            self._switch_target(value)
        elif action == "window":
            self._set_custom_window(value)
        elif action == "mic":
            self._hot_swap_mic(value)
        elif action == "arm":
            self._set_armed(True)
        elif action == "disarm":
            self._set_armed(False)
        elif action == "mode":
            if value == "prompt":
                self._enter_prompt_mode()
            elif value == "prompt_send":
                self._send_prompt()
        elif action == "langmode":
            self._set_lang_mode(value)
        elif action == "translate":
            # Deliberate ON/OFF translate toggle from the UI button.
            # value = target lang code ("en") to turn ON; "" / None to turn OFF.
            self.translate_to = (value or None)
            self._update_ui(mode=("translate" if self.translate_to else "normal"),
                            translate_to=self.translate_to)
            indicator("READY", (f"🌐 translate ON → {self.translate_to}"
                                 if self.translate_to else "🌐 translate OFF — transcribing"))

    def _set_lang_mode(self, value: str):
        """value = comma-joined whitelist ('he,en,ar') or 'all' (empty = all
        languages auto-detected). Applied live, no model reload."""
        wl = [] if value in ("all", "", None) else [c.strip() for c in value.split(",") if c.strip()]
        self.cfg["lang_whitelist"] = wl
        try:
            stt.set_lang_whitelist(wl)
        except Exception as e:
            log.warning("set_lang_whitelist failed: %s", e)
        disp = "ALL languages" if not wl else "/".join(wl)
        indicator("READY", f"🌍 languages: {disp}")
        self._update_ui(lang_mode=disp, lang_whitelist=wl)

    def _set_custom_window(self, value: str):
        """value = '<hwnd>|<title>' — type dictation into ANY chosen window."""
        try:
            hwnd_s, _, title = value.partition("|")
            self._custom_hwnd = int(hwnd_s)
            self._custom_title = title or "window"
            self.target = "__custom__"
            self._update_ui(target=f"win:{self._custom_title[:24]}")
            router.focus_window(self._custom_hwnd)
            indicator("READY", f"🪟 typing into: {self._custom_title}")
            log.info("CUSTOM WINDOW target -> hwnd=%s title=%r",
                     self._custom_hwnd, self._custom_title)
        except Exception as e:
            log.warning("set custom window failed: %s", e)

    # ── helpers ───────────────────────────────────────────────────────────────
    def _update_ui(self, **kw):
        with self._ui_lock:
            self.ui_state.update(kw)

    def _cleanup_wav(self, wav_path: str | None):
        """Remove a WAV file cleanly. Guarded to never crash the always-on loop."""
        if not wav_path:
            return
        try:
            if os.path.exists(wav_path):
                os.remove(wav_path)
                log.debug("cleaned wav: %s", wav_path)
        except Exception as e:
            log.debug("wav cleanup failed (not critical): %s", e)

    def _push_transcript(self, text: str, lang: str | None = None):
        """Show what was dictated, live, in the widget panel (with lang tag)."""
        with self._ui_lock:
            tr = self.ui_state.get("transcript", [])
            tag = _lang_badge(lang)
            item = f"{tag}  {text}" if tag else text
            tr.append(item)
            tr = tr[-8:]  # keep only the last 8 lines — the slice IS the bound
            self.ui_state["transcript"] = tr
            self.ui_state["last_text"] = text
            self.ui_state["last_lang"] = lang or ""

    def _hot_swap_mic(self, device_name: str):
        idx, name, note = mic.resolve_device(
            device_name, [], never_use=self.cfg.get("never_use_devices"),
            idle_if_no_good_mic=False)
        if idx is None:
            return
        # Guard: the UI combobox can fire a SPURIOUS device-select at startup to
        # whatever is first in the device list (e.g. MME 'Sound Mapper', which is
        # SILENT for this USB mic — it delivers audio on DirectSound, not MME).
        # Never abandon a working LIVE device for a quiet/dead one we didn't
        # deliberately pick. A user selecting a genuinely live mic still swaps
        # (its note says 'using LIVE'); a quiet device is rejected here.
        if "quiet" in (note or "") and not getattr(self, "no_mic", False) \
                and getattr(self, "dev_idx", None) is not None:
            log.info("MIC: ignoring spurious hot-swap to quiet device %r (keeping %r)",
                     name, self.dev_name)
            return
        self.dev_idx, self.dev_name = idx, name
        self._update_ui(mic_name=name, mic_idx=idx)
        indicator("READY", f"🎤 mic → {name}")

    def _reresolve_mic(self, reason: str = ""):
        """One-shot re-resolve to the loudest LIVE device — the automatic equivalent
        of the manual 'pause then resume' that revives capture. The device picked at
        process start can be wrong / not-yet-live (USB + BT enumerate async, model
        warmup delays it, the UI may hot-swap), and a silent-but-OPEN device never
        raises, so the VAD loop would otherwise sit stuck on it forever ('start it and
        it's not working until I pause+resume'). Only switches when a DIFFERENT device
        is genuinely LIVE, so it never thrashes during real silence. Never raises out."""
        try:
            idx, name, note = mic.resolve_device(
                self.cfg.get("input_device"), self.cfg.get("fallback_devices", []),
                never_use=self.cfg.get("never_use_devices"),
                idle_if_no_good_mic=False)
        except Exception as e:
            log.warning("re-resolve (%s) failed: %s", reason, e)
            return
        if idx is not None and "LIVE" in (note or "") \
                and idx != getattr(self, "dev_idx", None):
            self.dev_idx, self.dev_name = idx, name
            self.no_mic = False
            self._update_ui(mic_name=name, mic_idx=idx)
            indicator("READY", f"🎤 mic → {name}")
            log.info("MIC: %s re-resolve -> %s", reason, note)

    def _set_armed(self, armed: bool):
        self.armed = armed
        self._update_ui(armed=armed)
        if armed:
            indicator("ARMED", "פעיל — say שירי סוף to pause")
        else:
            indicator("PAUSED", "מושהה — say שירי or microphone to resume")

    def _switch_target(self, target: str):
        if target == "__no_target__":
            indicator("IDLE", "לא זוהה יעד — try 'שירי קלוד'")
            return
        self.target = target
        self._update_ui(target=target)
        if target in ("focused", "__focused__"):
            indicator("READY", "→ typing into the window you're using")
            return
        ok, title = router.focus_target(target, self.targets)
        indicator("READY", f"→ {target} ({'✓' if ok else '⚠ no window'})")

    def _target_hwnd(self):
        """Resolve (hwnd, title) for the current dictation target.
        'focused' = whatever window the user is in RIGHT NOW — no focus-stealing,
        so dictation types where the user is looking (the LKG default behaviour)."""
        if self.target in ("focused", "__focused__"):
            import ctypes
            h = ctypes.windll.user32.GetForegroundWindow()
            return (h, "(focused)") if h else (None, None)
        if self.target == "__custom__" and self._custom_hwnd:
            return self._custom_hwnd, self._custom_title
        found = router.find_window(self.target, self.targets)
        return found if found else (None, None)

    _LANG_NAMES = {"en": "English", "he": "עברית", "fr": "Français", "ru": "Русский",
                   "ar": "العربية", "de": "Deutsch", "es": "Español", "it": "Italiano",
                   "zh": "中文", "ja": "日本語", "pt": "Português"}

    def _set_language(self, code: str):
        """Voice command 'Claude <language>' → force that STT language (or auto)."""
        lang = None if code in ("auto", None, "") else code
        self.cfg["language"] = lang
        disp = "AUTO (all languages)" if lang is None else self._LANG_NAMES.get(lang, lang)
        indicator("READY", f"🌐 language → {disp} (loading…)")
        self._update_ui(status="READY", lang=(lang or "auto"))
        try:
            stt.load(self.cfg)   # reload the engine for the new language hint
            indicator("READY", f"🌐 language = {disp}")
        except Exception as e:
            log.warning("language switch reload failed (continuing): %s", e)

    def _translate(self, text: str, target: str) -> str:
        """Translate `text` into the target language via the Claude CLI (best-effort).
        Returns the original text if the CLI is unavailable / not logged in."""
        import os, shutil
        try:
            lang = self._LANG_NAMES.get(target, target)
            prompt = (f"Translate the following into {lang}. "
                      f"Output ONLY the translation — no quotes, no notes:\n{text}")
            # Resolve the real claude executable. On Windows the npm `claude` shim is a
            # .cmd, which CreateProcess cannot launch from a bare ["claude", ...] list —
            # that was the silent bug: translate fell straight through to the original
            # text. Run it via `cmd /c` (args still passed as a list → no shell injection).
            exe = shutil.which("claude") or "claude"
            if os.name == "nt" and exe.lower().endswith((".cmd", ".bat")):
                cmd = ["cmd", "/c", exe, "-p", prompt]
            else:
                cmd = [exe, "-p", prompt]
            out = subprocess.run(cmd, capture_output=True, text=True,
                                 timeout=60, encoding="utf-8")
            res = (out.stdout or "").strip()
            if not res:
                log.warning("translate: empty output (rc=%s, stderr=%r)",
                            out.returncode, (out.stderr or "")[:200])
            return res or text
        except Exception as e:
            log.warning("translate failed (%s) — typing original", e)
            return text

    def _enter_prompt_mode(self):
        self.prompt_mode = True
        self.prompt_buffer = []
        self._update_ui(mode="prompt", prompt_words=0)
        indicator("PROMPT", "📝 prompt mode — speak freely, say פרומפט סוף to send")

    def _send_prompt(self):
        if not self.prompt_buffer:
            indicator("IDLE", "prompt buffer empty")
            self.prompt_mode = False
            self._update_ui(mode="normal")
            return
        full = " ".join(self.prompt_buffer)
        self.prompt_mode = False
        self.prompt_buffer = []
        self._update_ui(mode="normal", prompt_words=0)
        _write_history(full, mode="prompt")
        indicator("TYPING", f"📝 sending prompt ({len(full.split())} words)…")
        hwnd, _ = self._target_hwnd()
        if not hwnd:
            log.warning("prompt: no target window")
            return
        kbd.send_to_window(hwnd, full,
                           use_clipboard=self.cfg.get("use_clipboard_paste", True),
                           auto_enter=True,
                           char_delay=self.cfg.get("char_delay", 0.004),
                           terminal_paste=self.cfg.get("terminal_paste", False))
        indicator("IDLE")

    def _run_shortcut(self, text: str) -> bool:
        for trigger, cmd in self.shortcuts.items():
            if trigger.lower() in text.lower():
                log.info("SHORTCUT: %r -> %r", trigger, cmd)
                indicator("TYPING", f"⚡ shortcut: {cmd}")
                subprocess.Popen(cmd, shell=True)
                return True
        return False

    # ── main wav handler ──────────────────────────────────────────────────────
    def _handle_wav(self, wav: str | None):
        if not wav:
            indicator("IDLE", "nothing captured")
            return

        # Remember the wav path for cleanup at the end of this function.
        wav_to_cleanup = wav

        # ── SPEAKER-ID OWNER-ONLY GATE (optional; off unless config owner_only=true) ──
        # When config.json has {"owner_only": true}, type ONLY when this clip is
        # Iddo's voice — friends / music / TV get dropped (not typed). The check
        # is a lazy, CPU, sub-100ms cosine match vs profiles/iddo1/voiceprint.npy
        # (built one-time by `python speaker_id.py enroll`). Guarded so a failing
        # speaker-id NEVER crashes the always-on loop, and it fails OPEN (types)
        # only if the voiceprint is missing — set owner_only after enrolling.
        if self.cfg.get("owner_only"):
            try:
                import speaker_id
                spk = speaker_id.identify(wav, self.cfg.get("owner_user", "iddo1"))
                if not spk["is_owner"]:
                    indicator("IDLE", f"🔒 not owner (score {spk['score']}) — dropped")
                    log.info("owner_only: dropped non-owner clip %s", spk)
                    # Clean up wav file immediately on rejection
                    self._cleanup_wav(wav_to_cleanup)
                    return
                log.info("owner_only: owner match %s", spk)
            except FileNotFoundError as e:
                log.warning("owner_only: no voiceprint — run `python speaker_id.py "
                            "enroll`; passing through. (%s)", e)
            except Exception as e:
                log.warning("owner_only: speaker-id failed (passing through): %s", e)

        # always transcribe in the SPOKEN language (English stays English, etc.)
        r = stt.transcribe(wav, self.cfg)

        raw_text = (r.get("text") or "").strip()
        raw_text = stt.strip_halluc(raw_text)   # peel recurring hallucination phrases (ALL engine paths)
        if not raw_text:
            tag = _lang_badge(r.get("lang"))
            indicator("IDLE", f"dropped ({r.get('reason') or 'no speech'})"
                              + (f"  {tag}" if tag else ""))
            self._cleanup_wav(wav_to_cleanup)
            return
        # belt-and-suspenders: drop hallucination loops BEFORE they can be typed,
        # regardless of which engine path produced the text. The dual-model path
        # was leaking repetition gibberish ("אה-אה-אה", "מצוין ומצוין ומצוין…")
        # straight into the focused window. This guard runs the same filter again.
        if stt.is_hallucination(raw_text):
            indicator("IDLE", "dropped (hallucination)")
            log.info("STT dropped hallucination: %s", raw_text)
            self._cleanup_wav(wav_to_cleanup)
            return
        log.info("STT raw: %s", raw_text)

        # ── IQBrainz pipeline ────────────────────────────────────────────────
        # smart engine guarded: a failing IQBrainz degrades to raw/phonetic text
        # instead of crashing the always-on loop (diamond: never let an engine kill us)
        text = raw_text
        if self.iq:
            try:
                result = self.iq.process(raw_text)
                text = result.text
                if result.changes:
                    log.info("IQ auto-fixed: %s", result.changes)
                if result.is_spelling:
                    indicator("IDLE", f"🔤 spelled: '{result.spelling_word}'")
                    text = result.spelling_word
                # BUG FIX (2026-06-14): do NOT feed result.context_hint back as
                # the Whisper initial_prompt. Whisper REGURGITATES its prompt
                # verbatim on quiet/unclear audio, so recent dictation (even a
                # whole prior conversation) got "read back" into later utterances.
                # IQBrainz still helps via its own phonetic/vocab corrections —
                # just never by priming Whisper. Keep the prompt empty.
                self.cfg["initial_prompt"] = ""
            except Exception as e:
                log.warning("IQBrainz.process failed (degrading to raw): %s", e)
                text = raw_text
        else:
            try:
                text = maybe_fix_phonetic(raw_text)
            except Exception as e:
                log.warning("maybe_fix_phonetic failed (degrading to raw): %s", e)
                text = raw_text

        # ── correction detection ("fix that" / "לא, אמרתי X") ───────────────
        # smart engine guarded: a failing corrector must not crash the loop
        #
        # DISABLED BY DEFAULT (2026-06-16): parse_correction fires on bare
        # "לא"/"אמרתי" — extremely common in natural Hebrew speech — and the
        # branch below then (a) learns last_raw_text→payload as a permanent
        # rules.json rule and (b) Ctrl+Z's + retypes the last text. This
        # poisoned rules.json with 125 garbage pairs and corrupted live
        # dictation. Per Iddo's voice-training rule (clean owner-verified
        # batches only, never auto-feed real-time), live auto-correction is
        # off unless explicitly enabled via config "live_corrections": true.
        if self.cfg.get("live_corrections", False):
            try:
                correction = parse_correction(text, self._last_raw_text)
            except Exception as e:
                log.warning("parse_correction failed (skipping correction): %s", e)
                correction = None
        else:
            correction = None
        if correction is not None:
            if correction:
                log.info("CORRECTION: %r → %r", self._last_raw_text, correction)
                try:
                    if self.iq:
                        self.iq.learn_correction(self._last_raw_text, correction)
                    if self.profile:
                        self.profile.log_correction(self._last_raw_text, correction)
                    log_correction(self._last_raw_text, correction,
                                   self.profile.profile_dir if self.profile else HERE)
                except Exception as e:
                    log.warning("correction logging failed (continuing): %s", e)
                # retype the corrected text (delete last + retype)
                found = router.find_window(self.target, self.targets)
                if found:
                    hwnd, _ = found
                    _send_ctrl_z(hwnd)
                    time.sleep(0.05)
                    kbd.send_to_window(hwnd, correction,
                                       use_clipboard=True, auto_enter=False,
                                       char_delay=self.cfg.get("char_delay", 0.004),
                                       terminal_paste=False)
                indicator("IDLE", f"✏️ corrected → {correction}")
            else:
                indicator("IDLE", "awaiting re-dictation…")
            self._cleanup_wav(wav_to_cleanup)
            return

        self._last_raw_text = raw_text

        # ── always write to history + log sample ────────────────────────────
        _write_history(text)
        # smart engine guarded: log_sample does shutil.copy2 which raises on
        # disk-full / permission — must NOT bubble up and kill always-on
        if self.profile and wav:
            try:
                self.profile.log_sample(wav, text)
            except Exception as e:
                log.warning("profile.log_sample failed (continuing): %s", e)

        # ── "by the way"/"דרך אגב" at start → "/btw" ──────────────────────────
        text = router.apply_text_shortcuts(text)

        # ── walkie-talkie: "over"/"עבור" at end → strip + send immediately ────
        text, force_enter = router.strip_over(text)

        cmd, extra = router.parse_command(text, self.targets)

        # ── language switch: "Claude <language>" / "שירי אנגלית" ──────────────
        if cmd == "__lang__":
            self._set_language(extra)
            self._cleanup_wav(wav_to_cleanup)
            return

        # ── disarm / arm ─────────────────────────────────────────────────────
        if cmd == "__disarm__":
            self._set_armed(False)
            self._cleanup_wav(wav_to_cleanup)
            return
        if cmd == "__arm__":
            self._set_armed(True)
            self._cleanup_wav(wav_to_cleanup)
            return

        # ── prompt mode controls ─────────────────────────────────────────────
        if cmd == "__prompt_start__":
            self._enter_prompt_mode()
            self._cleanup_wav(wav_to_cleanup)
            return
        if cmd == "__prompt_end__":
            self._send_prompt()
            self._cleanup_wav(wav_to_cleanup)
            return

        # ── translation toggle (target language; default OFF) ────────────────
        if cmd == "__translate_to__":
            self.translate_to = extra
            disp = self._LANG_NAMES.get(extra, extra)
            indicator("TRANSLATE", f"🌐 translating → {disp}")
            self._update_ui(mode="translate", translate_to=extra)
            self._cleanup_wav(wav_to_cleanup)
            return
        if cmd == "__translate_off__":
            self.translate_to = None
            indicator("READY", "translation OFF — typing the spoken language")
            self._update_ui(mode="normal", translate_to=None)
            self._cleanup_wav(wav_to_cleanup)
            return

        if cmd == "__fast_start__":
            self.fast_mode = True
            self.fast_buffer = []
            self._update_ui(mode="fast", fast_words=0)
            indicator("FAST", "⚡ fast mode — say שירי שלח to send all")
            self._cleanup_wav(wav_to_cleanup)
            return

        if cmd == "__fast_send__":
            if self.fast_buffer:
                full = " ".join(self.fast_buffer)
                self.fast_buffer = []
                self.fast_mode = False
                self._update_ui(mode="normal", fast_words=0)
                _write_history(full, mode="fast")
                hwnd, _ = self._target_hwnd()
                if hwnd:
                    kbd.send_to_window(hwnd, full,
                                       use_clipboard=self.cfg.get("use_clipboard_paste", True),
                                       auto_enter=True,
                                       char_delay=self.cfg.get("char_delay", 0.004),
                                       terminal_paste=self.cfg.get("terminal_paste", False))
            self.fast_mode = False
            indicator("IDLE", "⚡ fast buffer sent")
            self._cleanup_wav(wav_to_cleanup)
            return

        if cmd == "__clipboard__":
            self.clipboard_next = True
            indicator("IDLE", "📋 next utterance → clipboard only")
            self._cleanup_wav(wav_to_cleanup)
            return

        if cmd == "__silent__":
            global _silent_mode
            self.silent_mode = not self.silent_mode
            _silent_mode = self.silent_mode
            if not self.silent_mode:
                indicator("IDLE", "silent mode OFF")
            self._cleanup_wav(wav_to_cleanup)
            return

        if cmd == "__undo__":
            hwnd, _ = self._target_hwnd()
            if hwnd:
                _send_ctrl_z(hwnd)
                indicator("IDLE", "↩ undo sent")
            self._cleanup_wav(wav_to_cleanup)
            return

        if cmd == "__history__":
            today = datetime.date.today().isoformat()
            path = os.path.join(HISTORY_DIR, f"{today}.txt")
            if os.path.exists(path):
                os.startfile(path)
            else:
                indicator("IDLE", "no history today yet")
            self._cleanup_wav(wav_to_cleanup)
            return

        # ── target routing ────────────────────────────────────────────────────
        if cmd is not None:
            self._switch_target(cmd)
            text = (extra or "").strip()
            if not text:
                self._cleanup_wav(wav_to_cleanup)
                return

        # ── if disarmed, drop utterance ───────────────────────────────────────
        if not self.armed:
            log.info("PAUSED: dropping %r", text)
            self._cleanup_wav(wav_to_cleanup)
            return

        # ── translate to the chosen target language (if translation is ON) ────
        if self.translate_to:
            indicator("TRANSLATE", f"🌐 → {self._LANG_NAMES.get(self.translate_to, self.translate_to)}…")
            text = self._translate(text, self.translate_to)
            if not text:
                indicator("IDLE", "translation empty")
                self._cleanup_wav(wav_to_cleanup)
                return

        # ── prompt mode accumulation ──────────────────────────────────────────
        if self.prompt_mode:
            self.prompt_buffer.append(text)
            wc = sum(len(s.split()) for s in self.prompt_buffer)
            self._update_ui(prompt_words=wc)
            indicator("PROMPT", f"📝 +{len(text.split())} words ({wc} total) — say פרומפט סוף to send")
            self._cleanup_wav(wav_to_cleanup)
            return

        # ── fast mode accumulation ────────────────────────────────────────────
        if self.fast_mode:
            self.fast_buffer.append(text)
            wc = sum(len(s.split()) for s in self.fast_buffer)
            self._update_ui(fast_words=wc)
            indicator("FAST", f"⚡ buffered: {wc} words — say שירי שלח to send")
            self._cleanup_wav(wav_to_cleanup)
            return

        # ── clipboard-only mode ───────────────────────────────────────────────
        if self.clipboard_next:
            self.clipboard_next = False
            try:
                import pyperclip
                pyperclip.copy(text)
            except Exception:
                import ctypes
                ctypes.windll.user32.OpenClipboard(0)
                ctypes.windll.user32.EmptyClipboard()
                cf_unicode = 13
                h = ctypes.windll.kernel32.GlobalAlloc(0x42, len(text.encode("utf-16-le")) + 2)
                p = ctypes.windll.kernel32.GlobalLock(h)
                ctypes.cdll.msvcrt.wcsncpy(ctypes.c_wchar_p(p), text, len(text) + 1)
                ctypes.windll.kernel32.GlobalUnlock(h)
                ctypes.windll.user32.SetClipboardData(cf_unicode, h)
                ctypes.windll.user32.CloseClipboard()
            indicator("IDLE", f"📋 copied: {text[:60]}")
            self._cleanup_wav(wav_to_cleanup)
            return

        # ── voice shortcut check ──────────────────────────────────────────────
        if self._run_shortcut(text):
            self._cleanup_wav(wav_to_cleanup)
            return

        # ── normal dictation → type into the resolved target window ───────────
        hwnd, title = self._target_hwnd()
        if not hwnd:
            indicator("IDLE", f"⚠ no target window — said: {text}")
            self._cleanup_wav(wav_to_cleanup)
            return
        if not text:
            self._cleanup_wav(wav_to_cleanup)
            return
        ae = self.cfg.get("auto_enter", False) or force_enter
        tag = _lang_badge(r.get("lang"))
        indicator("TYPING", f"→ {title}{f' {tag}' if tag else ''}: "
                            f"{text}{' (over)' if force_enter else ''}")
        self._push_transcript(text, r.get("lang"))
        ok = kbd.send_to_window(
            hwnd, text + ("" if ae else " "),
            use_clipboard=self.cfg.get("use_clipboard_paste", True),
            auto_enter=ae,
            char_delay=self.cfg.get("char_delay", 0.004),
            terminal_paste=self.cfg.get("terminal_paste", False))
        if not ok:
            log.warning("focus failed for %r; text NOT typed", self.target)
        indicator("IDLE")

        # Explicit cleanup: release wav file to prevent memory leak
        self._cleanup_wav(wav_to_cleanup)

        # Post-WAV cleanup: force GC to free audio arrays + temp objects
        # immediately (don't wait for the 30s janitor interval).
        try:
            import gc
            gc.collect()
        except Exception:
            pass  # Fail silently; GC is best-effort

    # ── PTT ───────────────────────────────────────────────────────────────────
    def run_ptt(self):
        import keyboard
        hk = self.cfg.get("hotkey", "ctrl+alt+space")
        busy = threading.Lock()
        indicator("IDLE", f"HOLD {hk} to talk. Esc×2 to quit.")

        def on_talk():
            if not busy.acquire(blocking=False):
                return
            try:
                self.ducker.duck()
                indicator("LISTENING", "talk now")
                stop = threading.Event()
                buf = {}
                def rec():
                    buf["wav"] = mic.record_ptt(self.dev_idx, stop,
                                                 self.cfg.get("max_secs", 30))
                t = threading.Thread(target=rec, daemon=True)
                t.start()
                while keyboard.is_pressed(hk):
                    time.sleep(0.03)
                stop.set()
                t.join(timeout=self.cfg.get("max_secs", 30) + 2)
                self.ducker.restore()
                self._handle_wav(buf.get("wav"))
            finally:
                busy.release()

        keyboard.add_hotkey(hk, on_talk, suppress=False, trigger_on_release=False)
        self._wait_quit()

    # ── VAD ───────────────────────────────────────────────────────────────────
    def run_vad(self):
        if self.no_mic:
            indicator("IDLE", "no wired mic — plug in BRIO/Scarlett")
            while True:
                time.sleep(15)
                idx, name, _ = mic.resolve_device(
                    self.cfg.get("input_device"), self.cfg.get("fallback_devices", []),
                    never_use=self.cfg.get("never_use_devices"),
                    idle_if_no_good_mic=True)
                if idx is not None:
                    self.dev_idx, self.dev_name, self.no_mic = idx, name, False
                    indicator("READY", f"mic appeared: {name}")
                    break

        indicator("IDLE", "VAD: start talking. Ctrl+C to quit.")
        stop = threading.Event()

        def _recover_mic():
            """Mid-run mic-loss recovery: re-resolve the device with backoff until a
            mic verifies again, then resume capture. Called when record_vad raises
            (e.g. PortAudioError on unplug). Never raises out."""
            self.no_mic = True
            self._update_ui(status="PAUSED")
            indicator("IDLE", "mic lost — re-resolving device…")
            backoff = 2.0
            while not stop.is_set():
                try:
                    idx, name, _ = mic.resolve_device(
                        self.cfg.get("input_device"),
                        self.cfg.get("fallback_devices", []),
                        never_use=self.cfg.get("never_use_devices"),
                        idle_if_no_good_mic=True)
                except Exception as e:
                    log.warning("mic recovery resolve_device failed: %s", e)
                    idx, name = None, None
                if idx is not None:
                    self.dev_idx, self.dev_name, self.no_mic = idx, name, False
                    self._update_ui(mic_name=name, mic_idx=idx, status="READY")
                    indicator("READY", f"mic recovered: {name}")
                    return
                time.sleep(min(backoff, 15.0))
                backoff = min(backoff * 1.5, 15.0)

        def loop():
            # Diamond always-on: the per-utterance body is fully guarded so NOTHING —
            # a PortAudioError on mic unplug, an STT crash, a typer focus failure, or a
            # smart-engine raising — can ever kill this thread. One bad utterance must
            # never take down always-on. Consecutive hard errors back off + re-resolve.
            consecutive_errors = 0
            idle_cycles = 0
            captured_once = False
            while not stop.is_set():
                try:
                    wav = mic.record_vad(
                        self.dev_idx,
                        on_speech_start=lambda: (
                            self._update_ui(status="LISTENING"),
                            indicator("DUCKED", "speech…"),
                            self.ducker.duck()),
                        on_speech_end=lambda: (
                            self.ducker.restore(),
                            indicator("LISTENING", "processing…")),
                        on_level=lambda r: self._update_ui(
                            rms_level=min(r / 1500.0, 1.0), rms_raw=r),
                        rms_threshold=self.cfg.get("vad_rms_threshold", 220),
                        silence_secs=self.cfg.get("silence_secs", 1.4),
                        max_secs=self.cfg.get("max_secs", 30))
                except Exception as e:
                    # capture-side failure (almost always mic disconnect) — try to
                    # restore ducking, then enter the resolve/backoff recovery loop
                    consecutive_errors += 1
                    log.warning("record_vad failed (#%d): %s", consecutive_errors, e)
                    try:
                        self.ducker.restore()
                    except Exception:
                        pass
                    _recover_mic()
                    consecutive_errors = 0
                    continue
                if stop.is_set():
                    break
                if wav is None:
                    # nothing captured this cycle — UNTIL capture has ever worked we may
                    # be stuck on a wrong/silent cold-start device, so auto re-resolve to
                    # the live mic (the automatic 'pause/resume'). Stops once capture works
                    # so we never probe-thrash a healthy, genuinely-idle mic.
                    idle_cycles += 1
                    if not captured_once and idle_cycles >= 1:
                        idle_cycles = 0
                        self._reresolve_mic("idle")
                else:
                    idle_cycles = 0
                    captured_once = True
                try:
                    self._handle_wav(wav)
                    consecutive_errors = 0
                except Exception as e:
                    # handling-side failure (STT / typer / smart engine that escaped its
                    # own guard) — log and CONTINUE; never let it propagate out of loop()
                    consecutive_errors += 1
                    log.exception("_handle_wav crashed (#%d) — continuing: %s",
                                  consecutive_errors, e)
                    indicator("IDLE", "recovered from error — listening")
                    try:
                        self.ducker.restore()
                    except Exception:
                        pass
                    # if we're stuck failing in a tight loop, back off so we don't spin
                    if consecutive_errors >= 5:
                        log.warning("%d consecutive errors — backing off 3s",
                                    consecutive_errors)
                        time.sleep(3.0)

        th = threading.Thread(target=loop, daemon=True)
        th.start()
        try:
            while th.is_alive():
                time.sleep(0.3)
        except KeyboardInterrupt:
            stop.set()
            self.ducker.restore()

    def _wait_quit(self):
        import keyboard
        last = [0.0]
        def on_esc():
            now = time.time()
            if now - last[0] < 0.6:
                self.ducker.restore()
                os._exit(0)
            last[0] = now
        keyboard.add_hotkey("esc", on_esc)
        try:
            keyboard.wait()
        except KeyboardInterrupt:
            self.ducker.restore()

def main():
    cfg = load_cfg()
    vi = VoiceInput(cfg)
    toast("Hebrew Mic ready", f"mic={vi.dev_name} mode={cfg.get('mode')}")
    if cfg.get("mode") == "vad":
        vi.run_vad()
    else:
        vi.run_ptt()

if __name__ == "__main__":
    main()
