"""alma-mic / pipeline.py — THE one pipeline: capture -> VAD -> STT -> (wake-gate) -> out.

ALMAWARE-pure: ours. This is the single source of truth for the dictation loop —
the GUI, the headless app, and the soak test all use it (no second pipeline, no
fallback spaghetti). Two threads, both stop on one Event, bounded queue (no leak):

  CAPTURE thread : device -> AudioCapture -> VAD ; emits level + speech segments
  RECOGNIZE thread: load model once -> drain segments -> transcribe -> wake-gate
                    -> optionally type into the focused window -> on_text callback

Callbacks are invoked from worker threads; a GUI must marshal them to its UI thread.
"""
from __future__ import annotations
import queue
import threading

import numpy as np

import audio
import vad
import typer as typer_mod
from stt import Transcriber

import os, datetime
_DBG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mic_debug.log")
def _dbg(m):
    try:
        with open(_DBG_PATH, "a", encoding="utf-8") as f:
            f.write(datetime.datetime.now().strftime("%H:%M:%S ") + str(m) + "\n")
    except Exception:
        pass


def _noop(*_a, **_k):
    return None


class Pipeline:
    def __init__(self, cfg, *, on_level=_noop, on_text=_noop, on_device=_noop,
                 on_model=_noop, on_error=_noop, on_log=_noop):
        self.cfg = cfg
        self.on_level = on_level
        self.on_text = on_text
        self.on_device = on_device
        self.on_model = on_model
        self.on_error = on_error
        self.on_log = on_log
        self.trans = Transcriber(cfg)
        self._seg_q: "queue.Queue[np.ndarray]" = queue.Queue(maxsize=8)
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self.model_ready = False
        self.device_desc = ""
        # ARMED = may we type into the focused window? Default ON — when type_output
        # is set the mic types as you speak (that's the whole point). Ctrl+Alt+D or the
        # button disarm it to silence typing; Ctrl+Alt+P pauses the whole pipeline.
        self.armed = True

    # ---- lifecycle ----
    def start(self):
        self._stop.clear()
        self._threads = [
            threading.Thread(target=self._capture, daemon=True, name="alma-capture"),
            threading.Thread(target=self._recognize, daemon=True, name="alma-stt"),
        ]
        for t in self._threads:
            t.start()

    def stop(self):
        self._stop.set()
        for t in self._threads:
            t.join(timeout=2.0)
        self._threads = []

    @property
    def running(self) -> bool:
        return any(t.is_alive() for t in self._threads)

    # ---- threads ----
    def _pick_device(self):
        c = self.cfg
        if c.mic != "auto":
            return audio.find_device(c.mic) or audio.pick_device(c.prefer, c.avoid)
        return audio.pick_device(c.prefer, c.avoid)

    def _capture(self):
        try:
            dev = self._pick_device()
            if dev is None:
                self.on_error("לא נמצא מיקרופון")
                return
            self.device_desc = f"{dev.name}  ·  [{dev.hostapi}]  #{dev.index}"
            self.on_device(self.device_desc)
            _dbg(f"DEVICE: {self.device_desc}")
            v = vad.VAD()
            with audio.AudioCapture(dev.index,
                                    fallbacks=audio.same_mic_indices(dev)) as cap:
                while not self._stop.is_set():
                    frame = cap.read(timeout=0.1)
                    if frame is None:
                        continue
                    rms = float(np.sqrt(np.mean(frame * frame)))
                    seg = v.push(frame)
                    self.on_level(rms, v.in_speech)
                    if seg is not None:
                        try:
                            self._seg_q.put_nowait(seg)
                        except queue.Full:
                            pass  # recognizer busy; bounded -> never grows
        except Exception as e:
            self.on_error(repr(e))

    def _recognize(self):
        try:
            if not self.model_ready:
                self.on_log("⏳ טוען מודל זיהוי…")
                self.trans.load(log=self.on_log)
                self.model_ready = True
                self.on_model(self.trans.desc)
                _dbg(f"MODEL READY: {self.trans.desc}")
            while not self._stop.is_set():
                try:
                    seg = self._seg_q.get(timeout=0.2)
                except queue.Empty:
                    continue
                text, lang = self.trans.transcribe(seg)
                text = self._wake_gate(text)
                if not text:
                    continue
                _dbg(f"TEXT={text!r} armed={self.armed} type_output={self.cfg.type_output} auto_enter={self.cfg.auto_enter}")
                if self.cfg.type_output and self.armed:   # only type when armed
                    try:
                        n = typer_mod.type_text(text + " ", enter=self.cfg.auto_enter)
                        _dbg(f"TYPED ok ({n} events)")
                    except Exception as e:
                        self.on_log(f"type failed: {e!r}")
                        _dbg(f"TYPE FAILED: {e!r}")
                else:
                    _dbg("NOT typed (type_output or armed is off)")
                self.on_text(text, lang or "?")
        except Exception as e:
            self.on_error(repr(e))

    def _wake_gate(self, text: str):
        text = (text or "").strip()
        if not text:
            return None
        if self.cfg.arming != "wakeword":
            return text
        low = text.lower()
        for w in self.cfg.wake_words:
            w = w.strip()
            if w and w.lower() in low:
                i = low.find(w.lower())
                return (text[:i] + text[i + len(w):]).strip(" ,.-")
        return None
