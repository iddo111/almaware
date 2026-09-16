"""voice_input_xplat.py - cross-platform (macOS + Linux) always-on Hebrew mic.

This is the PORT of voice_input.py to Mac/Linux. It deliberately REUSES the
existing, already-working pieces instead of duplicating them:

  * mic.py            - capture / device-fallback / VAD  (pure sounddevice — already cross-platform)
  * transcribe.py     - the STT shim that delegates to the shared hebrew_stt.py engine
  * config.json       - same config (override per-OS with config.mac.json / config.linux.json)
  * backends/         - the OS input layer (mac.py / linux.py) for typing, paste,
                        window focus, undo, audio ducking, beep, open-file

The big Windows voice_input.py inlines Win32 (ctypes SendInput, EnumWindows,
os.startfile, MessageBeep) and imports the Windows-only router.py / typer.py /
ducking.py (pycaw). Rather than rewire that risky file, this runtime talks ONLY
to the clean InputBackend contract (backends/base.py), so the same dictation
loop runs identically on macOS (AppleScript/System Events) and Linux (xdotool/
ydotool + wmctrl + pactl).

What this runtime supports on Mac/Linux:
  * VAD always-on dictation into the FOCUSED window (config default_target="focused")
  * Paste-based Hebrew injection (clipboard paste = reliable for RTL bursts) with
    a char-by-char type fallback
  * The Hebrew voice commands that are OS-portable (target switch, prompt mode,
    fast mode, clipboard-only, translate on/off, silent, undo, history, arm/disarm,
    language switch)
  * Per-utterance language tag (he/en/…) from the dual-model STT
  * Crash-safe always-on loop with mic-loss recovery + per-utterance guards
    (one bad utterance / mic unplug / STT hiccup never kills the loop)

Honest limitations vs. Windows:
  * Window ROUTING by app name (router.DEFAULT_TARGETS / "שירי קלוד") is Win32-
    specific. On Mac/Linux we type into whatever window is FOCUSED. That is the
    LKG Windows default anyway (config default_target="focused"), so day-to-day
    behaviour matches. Voice "switch to <app>" is a no-op note on these OSes.
  * Wayland (Linux): the compositor blocks arbitrary window enum/focus; typing
    needs ydotool + a running ydotoold. X11 is fully supported via xdotool.
  * macOS: typing/paste require Accessibility permission for the terminal/python.
  * Voice shortcuts that shell out (config "shortcuts") run via the shell — the
    git/npm ones are cross-platform; "python run" assumes a main.py in cwd.

Run it:
    VOICEINPUT_BACKEND auto-selects by OS, but you can force it:
      VOICEINPUT_BACKEND=mac   python voice_input_xplat.py
      VOICEINPUT_BACKEND=linux python voice_input_xplat.py
    Use run_mac.sh / run_linux.sh which set up the venv + deps + config and launch.

 · ALMAWARE · iddoperez.ai
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

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
HISTORY_DIR = os.path.join(HERE, "history")
os.makedirs(HISTORY_DIR, exist_ok=True)

# Reuse the existing cross-platform capture + STT modules unchanged.
import mic
import transcribe as stt

# The OS input layer — typing, paste, focus, undo, duck, beep, open-file.
from backends import get_backend

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("voiceinput.xplat")

# ── config loading (config.json + optional per-OS override) ──────────────────
def _load_json(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def load_cfg() -> dict:
    """Load config.json, then deep-merge an optional per-OS override file
    (config.mac.json / config.linux.json) if present, then apply CLI flags.

    You can also point at an explicit config with --config <path>."""
    cfg = _load_json(os.path.join(HERE, "config.json"))

    # explicit override file via flag
    override_path = None
    if "--config" in sys.argv:
        i = sys.argv.index("--config")
        if i + 1 < len(sys.argv):
            override_path = sys.argv[i + 1]
    else:
        # auto per-OS override
        if sys.platform == "darwin":
            cand = os.path.join(HERE, "config.mac.json")
        else:
            cand = os.path.join(HERE, "config.linux.json")
        if os.path.exists(cand):
            override_path = cand

    if override_path and os.path.exists(override_path):
        try:
            ov = _load_json(override_path)
            cfg.update(ov)
            log.info("config override: %s (+%d keys)", override_path, len(ov))
        except Exception as e:
            log.warning("config override %s failed: %s", override_path, e)

    if "--vad" in sys.argv:
        cfg["mode"] = "vad"
    if "--ptt" in sys.argv:
        cfg["mode"] = "ptt"
    if "--enter" in sys.argv:
        cfg["auto_enter"] = True
    if "--no-enter" in sys.argv:
        cfg["auto_enter"] = False
    if "--cpu" in sys.argv:
        cfg["device"] = "cpu"
    return cfg

_silent_mode = False

def indicator(state: str, extra: str = ""):
    icons = {
        "IDLE": "[idle]", "LISTENING": "[mic]", "DUCKED": "[duck]",
        "TYPING": "[type]", "READY": "[ready]", "ARMED": "[on]",
        "PAUSED": "[paused]", "PROMPT": "[prompt]", "FAST": "[fast]",
        "TRANSLATE": "[xlate]",
    }
    if not _silent_mode:
        print(f"{icons.get(state, '·')} [{state}] {extra}", flush=True)

def _lang_badge(lang) -> str:
    try:
        code = (lang or "").strip().lower()
    except Exception:
        return ""
    return f"({code})" if code else ""

def _write_history(text: str, mode: str = "dictation"):
    try:
        today = datetime.date.today().isoformat()
        path = os.path.join(HISTORY_DIR, f"{today}.txt")
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] [{mode}] {text}\n")
    except Exception as e:
        log.debug("history write failed: %s", e)

# ── minimal cross-platform command router ────────────────────────────────────
# Window ROUTING by app-name is Win32-only (router.py). On Mac/Linux we always
# type into the FOCUSED window, so the only commands we parse are the OS-portable
# control commands. We keep the exact Hebrew triggers from voice_input.py so the
# user's muscle memory carries over.
_CMD_TABLE = {
    "__prompt_start__": ("שירי פרומפט", "claude prompt", "siri prompt"),
    "__prompt_end__":   ("פרומפט סוף", "prompt end", "סיום פרומפט"),
    "__fast_start__":   ("שירי מהיר", "fast mode", "מצב מהיר"),
    "__fast_send__":    ("שירי שלח", "send fast", "שלח עכשיו"),
    "__clipboard__":    ("שירי קליפבורד", "to clipboard", "קליפבורד"),
    "__silent__":       ("שירי שקט", "silent mode", "מצב שקט"),
    "__undo__":         ("שירי בטל", "undo that", "בטל פעולה"),
    "__history__":      ("שירי היסטוריה", "open history", "היסטוריה"),
    "__disarm__":       ("שירי סוף", "stop mic", "עצור הקלדה"),
    "__arm__":          ("שירי התחל", "start mic", "הפעל מיקרופון", "מיקרופון"),
    "__translate_off__": ("שירי בלי תרגום", "translate off", "בטל תרגום"),
}
# language switch: "<wake> <language>" — keep the small set we localize.
_LANG_TRIGGERS = {
    "אנגלית": "en", "english": "en",
    "עברית": "he", "hebrew": "he",
    "ערבית": "ar", "arabic": "ar",
    "רוסית": "ru", "russian": "ru",
    "צרפתית": "fr", "french": "fr",
    "אוטומטי": "auto", "auto": "auto", "automatic": "auto",
}
_WAKE = ("שירי", "claude", "siri")

def _norm(t: str) -> str:
    return " ".join((t or "").lower().split())

def parse_command(text: str):
    """Return (cmd, extra) or (None, None). cmd is one of the __...__ tokens
    or '__lang__' (extra = code) — mirrors voice_input.py's router contract for
    just the OS-portable subset."""
    n = _norm(text)
    if not n:
        return None, None
    # exact-ish control commands (substring match like the Win router)
    for cmd, triggers in _CMD_TABLE.items():
        for trig in triggers:
            if _norm(trig) in n:
                return cmd, ""
    # language switch: a wake word followed by a known language word
    toks = n.split()
    if toks and toks[0] in _WAKE:
        for w in toks[1:]:
            if w in _LANG_TRIGGERS:
                return "__lang__", _LANG_TRIGGERS[w]
    return None, None

def strip_over(text: str):
    """'over'/'עבור' at end → strip + force Enter (walkie-talkie)."""
    n = (text or "").rstrip(" .!?")
    for tok in ("עבור", "over"):
        if n.lower().endswith(tok):
            return n[: -len(tok)].rstrip(" ,.;:") , True
    return text, False

class VoiceInputXPlat:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.be = get_backend()
        log.info("backend: %s (platform=%s)", self.be.name, sys.platform)

        self.dev_idx, self.dev_name, note = mic.resolve_device(
            cfg.get("input_device"), cfg.get("fallback_devices", []),
            never_use=cfg.get("never_use_devices"),
            idle_if_no_good_mic=cfg.get("idle_if_no_good_mic", True))
        log.info("MIC: %s", note)
        self.no_mic = (self.dev_idx is None and self.dev_name is None)

        # mode state
        self.armed = True
        self.translate_to = None
        self.silent_mode = False
        self.clipboard_next = False

        self.prompt_mode = False
        self.prompt_buffer: list[str] = []
        self.fast_mode = False
        self.fast_buffer: list[str] = []

        self.shortcuts: dict[str, str] = cfg.get("shortcuts", {})
        self._last_raw_text = ""

        # smart engines (corrector / iqbrainz / learner) — optional, same graceful
        # fallback as the Windows app. They are pure-python so they work here too,
        # but we never let an import or a call kill the always-on loop.
        self.iq = None
        self.profile = None
        username = os.getenv("USER") or os.getenv("USERNAME") or "default"
        profiles_dir = os.path.join(HERE, "profiles")
        try:
            from iqbrainz import IQBrainz
            pdir = os.path.join(profiles_dir, username)
            os.makedirs(pdir, exist_ok=True)
            self.iq = IQBrainz(profile_dir=pdir)
            log.info("IQBrainz: loaded (vocab=%d)", len(getattr(self.iq, "vocab", {})))
        except Exception as e:
            log.info("IQBrainz unavailable (%s) — raw text", e)
        try:
            from learner import VoiceProfile
            self.profile = VoiceProfile(username=username, profiles_dir=profiles_dir)
            log.info("PROFILE: %s — %d samples", username, self.profile.sample_count())
        except Exception as e:
            log.info("VoiceProfile unavailable (%s)", e)

        log.info("STT: warming up '%s' on %s ...", cfg.get("model"), cfg.get("device"))
        stt.load(cfg)
        indicator("READY", f"mic={self.dev_name}  mode={cfg.get('mode')}  "
                           f"target=focused  auto_enter={cfg.get('auto_enter')}")

    # ── helpers ──────────────────────────────────────────────────────────────
    def _set_armed(self, armed: bool):
        self.armed = armed
        if armed:
            indicator("ARMED", "פעיל — say שירי סוף to pause")
        else:
            indicator("PAUSED", "מושהה — say מיקרופון to resume")

    def _enter_prompt_mode(self):
        self.prompt_mode = True
        self.prompt_buffer = []
        indicator("PROMPT", "speak freely, say פרומפט סוף to send")

    def _send_prompt(self):
        if not self.prompt_buffer:
            self.prompt_mode = False
            indicator("IDLE", "prompt buffer empty")
            return
        full = " ".join(self.prompt_buffer)
        self.prompt_mode = False
        self.prompt_buffer = []
        _write_history(full, mode="prompt")
        indicator("TYPING", f"sending prompt ({len(full.split())} words)…")
        self._inject(full, enter=True)
        indicator("IDLE")

    def _set_language(self, code: str):
        lang = None if code in ("auto", None, "") else code
        self.cfg["language"] = lang
        disp = "AUTO" if lang is None else lang
        indicator("READY", f"language → {disp} (loading…)")
        try:
            stt.load(self.cfg)
            indicator("READY", f"language = {disp}")
        except Exception as e:
            log.warning("language switch reload failed (continuing): %s", e)

    def _translate(self, text: str, target: str) -> str:
        try:
            prompt = (f"Translate the following into {target}. "
                      f"Output ONLY the translation — no quotes, no notes:\n{text}")
            out = subprocess.run(["claude", "-p", prompt], capture_output=True,
                                 text=True, timeout=30, encoding="utf-8")
            return (out.stdout or "").strip() or text
        except Exception as e:
            log.warning("translate failed (%s) — typing original", e)
            return text

    def _run_shortcut(self, text: str) -> bool:
        low = text.lower()
        for trigger, cmd in self.shortcuts.items():
            if trigger.lower() in low:
                log.info("SHORTCUT: %r -> %r", trigger, cmd)
                indicator("TYPING", f"shortcut: {cmd}")
                try:
                    subprocess.Popen(cmd, shell=True)
                except Exception as e:
                    log.warning("shortcut failed: %s", e)
                return True
        return False

    def _inject(self, text: str, enter: bool):
        """Type/paste `text` into the FOCUSED window via the OS backend.
        Paste is preferred for Hebrew bursts; the backend itself falls back to
        char-by-char typing if no clipboard tool is available."""
        if not text:
            if enter:
                # send a bare Enter
                self.be.type_text("", enter=True)
            return
        if self.cfg.get("use_clipboard_paste", True):
            self.be.paste_text(text, enter=enter)
        else:
            self.be.type_text(text, enter=enter)

    # ── main utterance handler ───────────────────────────────────────────────
    def _handle_wav(self, wav: str | None):
        if not wav:
            indicator("IDLE", "nothing captured")
            return

        r = stt.transcribe(wav, self.cfg)
        raw_text = (r.get("text") or "").strip()
        if not raw_text:
            tag = _lang_badge(r.get("lang"))
            indicator("IDLE", f"dropped ({r.get('reason') or 'no speech'}) {tag}".rstrip())
            return
        if stt.is_hallucination(raw_text):
            indicator("IDLE", "dropped (hallucination)")
            log.info("STT dropped hallucination: %s", raw_text)
            return
        log.info("STT raw: %s", raw_text)

        # IQBrainz auto-correct (guarded — degrade to raw on any failure)
        text = raw_text
        if self.iq:
            try:
                result = self.iq.process(raw_text)
                text = result.text
                if getattr(result, "changes", None):
                    log.info("IQ auto-fixed: %s", result.changes)
                if getattr(result, "is_spelling", False):
                    text = result.spelling_word
                    indicator("IDLE", f"spelled: '{text}'")
                self.cfg["initial_prompt"] = ""   # never prime Whisper (echo bug)
            except Exception as e:
                log.warning("IQBrainz.process failed (degrading to raw): %s", e)
                text = raw_text

        self._last_raw_text = raw_text
        _write_history(text)
        if self.profile and wav:
            try:
                self.profile.log_sample(wav, text)
            except Exception as e:
                log.warning("profile.log_sample failed (continuing): %s", e)

        # walkie-talkie "over"/"עבור"
        text, force_enter = strip_over(text)

        cmd, extra = parse_command(text)

        if cmd == "__lang__":
            self._set_language(extra)
            return
        if cmd == "__disarm__":
            self._set_armed(False)
            return
        if cmd == "__arm__":
            self._set_armed(True)
            return
        if cmd == "__prompt_start__":
            self._enter_prompt_mode()
            return
        if cmd == "__prompt_end__":
            self._send_prompt()
            return
        if cmd == "__fast_start__":
            self.fast_mode = True
            self.fast_buffer = []
            indicator("FAST", "say שירי שלח to send all")
            return
        if cmd == "__fast_send__":
            if self.fast_buffer:
                full = " ".join(self.fast_buffer)
                self.fast_buffer = []
                _write_history(full, mode="fast")
                self._inject(full, enter=True)
            self.fast_mode = False
            indicator("IDLE", "fast buffer sent")
            return
        if cmd == "__clipboard__":
            self.clipboard_next = True
            indicator("IDLE", "next utterance → clipboard only")
            return
        if cmd == "__silent__":
            global _silent_mode
            self.silent_mode = not self.silent_mode
            _silent_mode = self.silent_mode
            if not self.silent_mode:
                indicator("IDLE", "silent mode OFF")
            return
        if cmd == "__translate_off__":
            self.translate_to = None
            indicator("READY", "translation OFF")
            return
        if cmd == "__undo__":
            self.be.send_undo(self.be.get_foreground_window())
            indicator("IDLE", "undo sent")
            return
        if cmd == "__history__":
            today = datetime.date.today().isoformat()
            path = os.path.join(HISTORY_DIR, f"{today}.txt")
            if os.path.exists(path):
                self.be.open_path(path)
            else:
                indicator("IDLE", "no history today yet")
            return

        if not self.armed:
            log.info("PAUSED: dropping %r", text)
            return

        if self.translate_to:
            indicator("TRANSLATE", f"→ {self.translate_to}…")
            text = self._translate(text, self.translate_to)
            if not text:
                indicator("IDLE", "translation empty")
                return

        if self.prompt_mode:
            self.prompt_buffer.append(text)
            wc = sum(len(s.split()) for s in self.prompt_buffer)
            indicator("PROMPT", f"+{len(text.split())} words ({wc} total)")
            return

        if self.fast_mode:
            self.fast_buffer.append(text)
            wc = sum(len(s.split()) for s in self.fast_buffer)
            indicator("FAST", f"buffered: {wc} words")
            return

        if self.clipboard_next:
            self.clipboard_next = False
            self.be.set_clipboard(text)
            indicator("IDLE", f"copied: {text[:60]}")
            return

        if self._run_shortcut(text):
            return

        # normal dictation → focused window
        ae = bool(self.cfg.get("auto_enter", False) or force_enter)
        tag = _lang_badge(r.get("lang"))
        indicator("TYPING", f"→ focused {tag}: {text}"
                            f"{' (over)' if force_enter else ''}")
        # trailing space when not pressing Enter (matches Windows behaviour)
        self._inject(text + ("" if ae else " "), enter=ae)
        indicator("IDLE")

    # ── VAD always-on loop (crash-safe, mic-loss recovery) ───────────────────
    def run_vad(self):
        if self.no_mic:
            indicator("IDLE", "no good mic — plug in a USB/wired mic")
            # wait for a mic to appear
            while True:
                time.sleep(8)
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
            self.no_mic = True
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
                    log.warning("mic recovery resolve failed: %s", e)
                    idx, name = None, None
                if idx is not None:
                    self.dev_idx, self.dev_name, self.no_mic = idx, name, False
                    indicator("READY", f"mic recovered: {name}")
                    return
                time.sleep(min(backoff, 15.0))
                backoff = min(backoff * 1.5, 15.0)

        def loop():
            consecutive_errors = 0
            while not stop.is_set():
                try:
                    wav = mic.record_vad(
                        self.dev_idx,
                        on_speech_start=lambda: (indicator("DUCKED", "speech…"),
                                                 self.be.duck()),
                        on_speech_end=lambda: (self.be.restore(),
                                               indicator("LISTENING", "processing…")),
                        on_level=None,
                        rms_threshold=self.cfg.get("vad_rms_threshold", 220),
                        silence_secs=self.cfg.get("silence_secs", 1.4),
                        max_secs=self.cfg.get("max_secs", 30))
                except Exception as e:
                    consecutive_errors += 1
                    log.warning("record_vad failed (#%d): %s", consecutive_errors, e)
                    try:
                        self.be.restore()
                    except Exception:
                        pass
                    _recover_mic()
                    consecutive_errors = 0
                    continue
                if stop.is_set():
                    break
                try:
                    self._handle_wav(wav)
                    consecutive_errors = 0
                except Exception as e:
                    consecutive_errors += 1
                    log.exception("_handle_wav crashed (#%d) — continuing: %s",
                                  consecutive_errors, e)
                    indicator("IDLE", "recovered from error — listening")
                    try:
                        self.be.restore()
                    except Exception:
                        pass
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
            try:
                self.be.restore()
            except Exception:
                pass

    # ── PTT (push-to-talk) — Mac/Linux variant ───────────────────────────────
    def run_ptt(self):
        """Hold the hotkey to talk. Uses the `keyboard` lib if available; note
        that on macOS/Linux global hotkeys usually need root/extra permissions,
        so VAD (always-on) is the recommended mode on these OSes."""
        try:
            import keyboard  # noqa: F401
        except Exception as e:
            log.warning("PTT needs the `keyboard` package + (often) root on "
                        "Mac/Linux (%s). Falling back to VAD.", e)
            self.run_vad()
            return
        import keyboard
        hk = self.cfg.get("hotkey", "ctrl+alt+space")
        busy = threading.Lock()
        indicator("IDLE", f"HOLD {hk} to talk. Ctrl+C to quit.")

        def on_talk():
            if not busy.acquire(blocking=False):
                return
            try:
                self.be.duck()
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
                self.be.restore()
                self._handle_wav(buf.get("wav"))
            finally:
                busy.release()

        keyboard.add_hotkey(hk, on_talk, suppress=False, trigger_on_release=False)
        try:
            keyboard.wait()
        except KeyboardInterrupt:
            try:
                self.be.restore()
            except Exception:
                pass

def main():
    cfg = load_cfg()
    vi = VoiceInputXPlat(cfg)
    log.info("Hebrew Mic (xplat) ready: mic=%s mode=%s backend=%s",
             vi.dev_name, cfg.get("mode"), vi.be.name)
    if cfg.get("mode") == "ptt":
        vi.run_ptt()
    else:
        vi.run_vad()

if __name__ == "__main__":
    main()
