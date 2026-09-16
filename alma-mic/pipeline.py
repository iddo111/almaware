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
import voice_commands
from stt import Transcriber

import os, datetime, json, wave, time as _time
_DBG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mic_debug.log")
_CORPUS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "voice_corpus")
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
        # Items are (enqueue_time, segment). The timestamp is what lets the
        # recognizer skip STALE speech after a decode stall — without it a single
        # 100s decode (GPU contention, 2026-08-12) made the mic type sentences
        # minutes late, which reads as "frozen".
        self._seg_q: "queue.Queue[tuple[float, np.ndarray]]" = queue.Queue(maxsize=8)
        self._stop = threading.Event()
        self._load_lock = threading.Lock()
        self._threads: list[threading.Thread] = []
        self.model_ready = False
        self.device_desc = ""
        # ARMED = may we type into the focused window? Default ON — when type_output
        # is set the mic types as you speak (that's the whole point). Ctrl+Alt+D or the
        # button disarm it to silence typing; Ctrl+Alt+P pauses the whole pipeline.
        self.armed = True

    # ---- lifecycle ----
    def start(self):
        # FRESH Event per generation (zombie-revival fix, 2026-08-12): stop()
        # joins with a 2s timeout, but a recognize thread stuck in the ~2min
        # faster-whisper import can't exit that fast. With a SHARED event,
        # the next start() cleared it and the old "stopped" threads came back
        # to life: two captures on one BRIO, two model loads on the 8GB GPU,
        # every utterance typed twice (log 07:52-07:54, two DEVICE + two LOAD
        # lines in one process, triggered by one pause/resume during load).
        # Old threads keep their own (set) event and die when they can.
        self._stop = threading.Event()
        stop = self._stop
        self._threads = [
            threading.Thread(target=self._capture, args=(stop,),
                             daemon=True, name="alma-capture"),
            threading.Thread(target=self._recognize, args=(stop,),
                             daemon=True, name="alma-stt"),
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
            # AN EXPLICIT CHOICE WINS. If Iddo picked a microphone by name, use
            # it - full stop. Probing it for signal and silently switching away
            # was me overriding his choice: he would select a mic, go quiet for
            # a second, and the app would wander off to the Bluetooth headset.
            # Only fall back when the device is genuinely GONE from the system.
            pinned = audio.find_device(c.mic)
            if pinned is not None:
                return pinned
            return audio.pick_device(c.prefer, c.avoid)
        return audio.pick_device(c.prefer, c.avoid)

    def _capture(self, stop: threading.Event):
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
                while not stop.is_set():
                    frame = cap.read(timeout=0.1)
                    if frame is None:
                        continue
                    rms = float(np.sqrt(np.mean(frame * frame)))
                    seg = v.push(frame)
                    self.on_level(rms, v.in_speech)
                    if seg is not None:
                        try:
                            self._seg_q.put_nowait((_time.time(), seg))
                        except queue.Full:
                            # Recognizer is stalled. Dropping the NEW segment here
                            # threw away whatever Iddo just said and kept old
                            # backlog — the "I speak and nothing happens" freeze.
                            # Keep the newest speech: evict the oldest instead,
                            # and leave a trace (silent drops are undebuggable).
                            try:
                                self._seg_q.get_nowait()
                                self._seg_q.put_nowait((_time.time(), seg))
                                _dbg("QUEUE FULL - evicted oldest segment (recognizer stalled)")
                            except (queue.Empty, queue.Full):
                                _dbg("QUEUE FULL - segment dropped")
        except Exception as e:
            self.on_error(repr(e))

    def _recognize(self, stop: threading.Event):
        try:
            # LOAD LOCK (2026-08-12): two recognize generations racing here both
            # called trans.load() and put TWO models on the 8GB card. Serialize;
            # the loser of the race finds model_ready True and skips.
            with self._load_lock:
                if not self.model_ready:
                    self.on_log("⏳ טוען מודל זיהוי…")
                    t0 = _time.time()
                    def _load_log(msg):
                        self.on_log(msg)
                        _dbg(f"LOAD +{_time.time() - t0:5.1f}s {msg}")
                    self.trans.load(log=_load_log)
                    self.model_ready = True
                    self.on_model(self.trans.desc)
                    _dbg(f"MODEL READY: {self.trans.desc} ({_time.time() - t0:.1f}s)")
            while not stop.is_set():
                try:
                    t_enq, seg = self._seg_q.get(timeout=0.2)
                except queue.Empty:
                    continue
                # STALE GUARD: after a decode stall the backlog is old speech.
                # If this segment has waited >25s AND fresher speech is queued
                # behind it, typing it now would land minutes-late text into
                # whatever window has focus. Skip it, keep the fresh one.
                if (_time.time() - t_enq) > 25.0 and not self._seg_q.empty():
                    _dbg("STALE skip - segment waited %.0fs, fresher speech queued"
                         % (_time.time() - t_enq))
                    continue
                # ENERGY GATE: drop near-silent segments before STT so Whisper never
                # gets the chance to hallucinate on them (saves GPU too). Configurable.
                gate = float(getattr(self.cfg, "speech_rms_gate", 0.0) or 0.0)
                if gate > 0.0:
                    seg_rms = float(np.sqrt(np.mean(np.asarray(seg, dtype=np.float32) ** 2)) + 1e-12)
                    if seg_rms < gate:
                        _dbg(f"GATED silence seg rms={seg_rms:.5f} < {gate}")
                        continue
                # Time the decode. "It takes 500 years to answer" has to become a number
                # or it cannot be fixed - and when three instances were fighting over one
                # 8 GB GPU, this is where that cost showed up.
                _t0 = _time.time()
                text, lang = self.trans.transcribe(seg)
                _ms = int((_time.time() - _t0) * 1000)
                _sec = len(np.asarray(seg)) / 16000.0
                text = self._wake_gate(text)
                if not text:
                    # Was a silent `continue`: speech that passed the RMS gate but
                    # came back empty from VAD/decode vanished with no trace, so the
                    # log showed nothing while Iddo saw "not working". Log it.
                    _dbg("EMPTY decode %.1fs->%dms rms=%.4f (VAD/no-speech dropped it)"
                         % (_sec, _ms,
                            float(np.sqrt(np.mean(np.asarray(seg, dtype=np.float32)**2)) + 1e-12)))
                    continue
                _dbg("TEXT=%r %.1fs->%dms(x%.1f) rms=%.4f lp=%.3f armed=%s"
                     % (text, _sec, _ms, _sec*1000.0/max(_ms,1),
                        float(np.sqrt(np.mean(np.asarray(seg,dtype=np.float32)**2))+1e-12),
                        getattr(self.trans, "last_avg_lp", 0.0), self.armed))
                if self.cfg.type_output and self.armed:   # only type when armed
                    try:
                        typed = voice_commands.apply(text, self.cfg)   # voice slash-commands / keys
                        typer_mod.set_policy(
                            anywhere=getattr(self.cfg, "type_anywhere", False),
                            targets=getattr(self.cfg, "type_targets", []))
                        try:
                            _fg = typer_mod._foreground_target()
                            _mem = typer_mod._last_external.get("target")
                            # Log the EXE, never the window title. Titles are page names,
                            # document names, chat names - a plaintext record of everything
                            # Iddo looks at, sitting on disk forever. The exe is all the
                            # targeting logic actually uses, so nothing is lost.
                            # _Target has image_path, not exe — getattr(...,"exe")
                            # printed '?' forever and made the log lie about focus.
                            def _exe(t):
                                p = getattr(t, "image_path", "") or ""
                                return p.replace("/", "\\").rsplit("\\", 1)[-1] or "?"
                            _dbg("FOCUS fg=%s  watcher=%s"
                                 % (_exe(_fg), (_exe(_mem) if _mem else None)))
                        except Exception:
                            pass
                        n = typer_mod.type_text(typed + " ", enter=self.cfg.auto_enter)
                        _dbg(f"TYPED ok ({n} events)")
                    except Exception as e:
                        self.on_log(f"type failed: {e!r}")
                        _dbg(f"TYPE FAILED: {e!r}")
                else:
                    _dbg("NOT typed (type_output or armed is off)")
                if self.cfg.collect_corpus and self.armed:
                    self._save_corpus(seg, text, lang)   # learn this speaker's voice (LoRA fuel)
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

    def _save_corpus(self, seg, text, lang):
        """Save one (audio, transcript) pair to voice_corpus/ — the training fuel for a
        per-speaker Whisper LoRA. Local + owner-only; the actual fine-tune runs on the DGX,
        never on the PC. A growing corpus.jsonl manifest + one 16 kHz mono wav per utterance."""
        try:
            os.makedirs(_CORPUS_DIR, exist_ok=True)
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            pcm = (np.clip(np.asarray(seg, dtype=np.float32), -1.0, 1.0) * 32767).astype(np.int16)
            with wave.open(os.path.join(_CORPUS_DIR, ts + ".wav"), "wb") as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
                w.writeframes(pcm.tobytes())
            with open(os.path.join(_CORPUS_DIR, "corpus.jsonl"), "a", encoding="utf-8") as f:
                f.write(json.dumps({"wav": ts + ".wav", "text": text,
                                    "lang": lang, "ts": ts}, ensure_ascii=False) + "\n")
        except Exception as e:
            _dbg(f"corpus save failed: {e!r}")
