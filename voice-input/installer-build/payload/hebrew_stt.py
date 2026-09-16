"""hebrew_stt.py - shared Hebrew (he-IL) speech-to-text helper for all of Iddo's apps.

ONE import, any app gets Hebrew voice input:

    from hebrew_stt import listen, transcribe_file, HebrewSTT

    text = listen()                      # push-to-talk-ish: records until silence, returns Hebrew text
    text = listen(mode="vad")            # auto: waits for speech, stops on silence
    text = transcribe_file("clip.wav")   # transcribe an existing 16k mono wav

Engine: faster-whisper (local, offline). Model default "small" (fast, usable Hebrew);
pass model="medium" or "large-v3" for higher accuracy at more cost. Device "auto" tries
CUDA (cu121 torch present on this PC) and silently falls back to CPU int8 on any failure,
honouring the GPU-over-CPU preference without risking an OOM freeze.

Hebrew accuracy note: 'small' gives usable but imperfect Hebrew (good for short commands /
dictation; expect occasional spelling + homophone errors). 'medium'/'large-v3' markedly
better, slower. Hallucinated filler ("תודה רבה", "thanks for watching") is filtered out.

Mic capture uses sounddevice with a device-fallback chain that *verifies* real signal
(a silent device is treated as dead) so apps never record nothing.

לזכרה של עלמה ז"ל - iddoperez.ai
"""
from __future__ import annotations

import logging
import os
import re
import tempfile
import threading
import time
import wave

logger = logging.getLogger("hebrew_stt")

# ── CUDA DLL search path (cuBLAS 12 + cuDNN 9 for CTranslate2 GPU) ────────────
# faster-whisper / CTranslate2 4.x need cublas64_12.dll + cudnn*_9.dll on the DLL
# search path. They are NOT pip-installed for this interpreter, but a complete
# matched set ships with the local torch build; register those dirs so GPU STT
# loads instead of dying with "cublas64_12.dll is not found". Best-effort — a
# missing dir is skipped, and device="auto" still falls back to CPU if all fail.
# THIS interpreter's OWN torch build ships the cublas/cudnn set that MATCHES the
# installed CTranslate2 — try it FIRST. The pinokio/miniconda sets are fallbacks
# and can version-mismatch, yielding the intermittent "cublas64_12.dll ... cannot
# be loaded" STT crash even though a cublas64_12.dll exists somewhere on PATH.
# DISTRIBUTABLE BUILD: derive the torch/lib dir from THIS running interpreter so
# the matched cuBLAS/cuDNN set is found on ANY machine (no hardcoded user path).
# Resolves to <venv>/Lib/site-packages/torch/lib when torch is installed; best-
# effort, missing dirs are skipped and CPU still works.
def _find_torch_lib():
    try:
        import importlib.util
        spec = importlib.util.find_spec("torch")
        if spec and spec.submodule_search_locations:
            cand = os.path.join(list(spec.submodule_search_locations)[0], "lib")
            if os.path.isdir(cand):
                return cand
    except Exception:
        pass
    # fallback: alongside this interpreter's site-packages
    try:
        import site
        for sp in site.getsitepackages():
            cand = os.path.join(sp, "torch", "lib")
            if os.path.isdir(cand):
                return cand
    except Exception:
        pass
    return ""

_TORCH_LIB = _find_torch_lib()
_CUDA_DLL_DIRS = [d for d in (
    _TORCH_LIB,
    # optional system CUDA fallbacks (skipped silently if absent):
    os.path.join(os.environ.get("CUDA_PATH", ""), "bin") if os.environ.get("CUDA_PATH") else "",
) if d]
for _d in _CUDA_DLL_DIRS:
    try:
        if os.path.isdir(_d):
            os.add_dll_directory(_d)
            os.environ["PATH"] = _d + os.pathsep + os.environ.get("PATH", "")
    except Exception:
        pass

# Deterministic cuBLAS/cuDNN load: PRELOAD the matched set from this interpreter's
# torch/lib by FULL PATH, in dependency order, BEFORE CTranslate2 loads. Once a DLL
# is in the process by name, CTranslate2's later load-by-name resolves to it — so
# GPU STT stops failing intermittently with "cublas64_12.dll ... cannot be loaded".
# Pure best-effort; any miss is swallowed and the CPU path still works.
try:
    import ctypes as _ctypes
    for _dll in ("cublasLt64_12.dll", "cublas64_12.dll",
                 "cudnn_ops64_9.dll", "cudnn_cnn64_9.dll",
                 "cudnn_graph64_9.dll", "cudnn64_9.dll"):
        try:
            _ctypes.WinDLL(os.path.join(_TORCH_LIB, _dll))
        except Exception:
            pass
except Exception:
    pass

# ── audio constants ──────────────────────────────────────────────────────────
SAMPLE_RATE = 16000
CHANNELS = 1
DTYPE = "int16"
SAMPLE_WIDTH = 2
_TEMP = os.path.join(tempfile.gettempdir(), "hebrew_stt")

DEFAULTS = {
    # ivrit-ai turbo CT2: Hebrew WER ~5-10% vs ~25% generic. Default on GPU.
    # On a no-GPU host this name won't resolve as a HF model id offline, so the
    # CPU path drops to a generic faster-whisper size (see _resolve_model).
    "model": "ivrit-ai/whisper-large-v3-turbo-ct2",
    "cpu_model": "base",       # fallback model for CPU-only hosts
    "device": "auto",          # auto | cuda | cpu
    "language": "he",          # he-IL Hebrew
    # ── dual-model language ID + routing ─────────────────────────────────────
    # The ivrit-ai fine-tune is a superb Hebrew transcriber but a BROKEN language
    # detector: it tags everything 'he' p=1.00 and renders English as Hebrew
    # transliteration gibberish ("Wi-Fi" -> "ווי פאי"). The stock multilingual
    # large-v3-turbo separates he/en cleanly. So with lang_detect="dual" we:
    #   1) DETECT language with the base multilingual model (reliable he/en split)
    #   2) ROUTE -> he: transcribe with ivrit-ai (best Hebrew)
    #               en/other: transcribe with the base model (correct English)
    # "single" restores the legacy one-model behaviour. Any error in the dual
    # path falls back to the legacy single-model transcribe (crash-safe).
    # NOTE: only active when no explicit `language` is forced (language=None).
    "lang_detect": "single",
    # base multilingual model for detection + non-Hebrew transcription.
    "base_model": "mobiuslabsgmbh/faster-whisper-large-v3-turbo",
    # min detection probability to trust the base model's verdict; below this we
    # treat the utterance as Hebrew (the common case for this user) so a noisy
    # low-confidence clip doesn't get routed to the wrong engine.
    "lang_detect_min_prob": 0.55,
    # auto-detect ONLY routes to these languages; anything else (Greek/Japanese/
    # a false-positive Arabic on Hebrew audio) defaults to Hebrew. Other languages
    # remain available on demand via the "Claude <language>" voice command.
    "lang_whitelist": ["he", "en", "ar", "fr", "es", "it", "ru", "de", "pt"],
    "input_device": None,      # name substring, e.g. "BRIO"; None = system default
    # wired-only mic chain; BT headset deliberately absent (see never_use_devices)
    "fallback_devices": ["BRIO", "Scarlett"],
    # mics we must NEVER grab (BT can't do HQ A2DP music + SCO mic together)
    "never_use_devices": ["WH-1000XM4", "Hands-Free", "Headset", "Bluetooth"],
    # if no good wired mic verifies signal, IDLE instead of grabbing anything
    "idle_if_no_good_mic": True,
    "beam_size": 5,
    "max_secs": 30,
    "silence_secs": 1.0,
    "min_secs": 0.6,           # drop utterances shorter than this (noise blips)
    "vad_rms_threshold": 650,
    # Whisper segment-level rejection thresholds (reject silence/noise/hallucination)
    "max_no_speech_prob": 0.6,
    "min_avg_logprob": -1.0,
    # NO bias prompt: a Hebrew initial_prompt (a) biases English audio toward
    # Hebrew and (b) gets HALLUCINATED verbatim onto short/quiet clips ("...תמלול
    # מדויק של דיבור טבעי" appended to real speech). Empty = clean + multilingual-safe.
    "initial_prompt": "",
}

# initial-prompt echo fragments Whisper sometimes injects on short/quiet clips —
# stripped from the output even when no prompt is set (belt-and-suspenders).
_PROMPT_ECHOES = ("תמלול מדויק של דיבור טבעי", "שיחה בעברית")

# ── hallucination filter (Whisper invents these on silence) ──────────────────
# Known Whisper filler / training-set artifacts that appear on silence or noise.
_HALLUC = {
    "תודה", "תודה רבה", "תודה רבה לך", "תודה רבה אדוני", "תודה רבה לך אדוני",
    "תודה שצפיתם", "תודה שצפיתם בסרטון", "תודה לכם", "להתראות", "שלום",
    "כתוביות", "תרגום וכתוביות", "הכתוביות נעשו על ידי", "עריכת כתוביות",
    "thank you", "thank you for watching", "thanks for watching", "you",
    "bye", "bye bye", "okay", "ok", ".", "..", "...", "subscribe", "אמן",
}
# repeated-filler / punctuation-only lines
_REPEAT = re.compile(
    r"^(?:[.\s,!?\-]|תודה|רבה|לך|אדוני|שצפיתם|כתוביות|thank you|you|bye|okay?)+$",
    re.I)

# recurring Whisper hallucination phrases that get APPENDED to real speech (esp. on
# music / background) — strip them from anywhere in the text, keeping the real words.
_HALLUC_STRIP = re.compile(
    r"מ?ה?אהוב\s*,?\s*זה כבר נורא בכלל"
    r"|זה כבר נורא בכלל"
    r"|מהאהוב|מה אהוב"
    r"|א?מאה אחוז אבל ממש לא"
    r"|אני מוצא מאוד",
    re.I)


def strip_halluc(t: str) -> str:
    """Remove recurring hallucination phrases from anywhere in text (keep real words)."""
    if not t:
        return t
    return re.sub(r"\s+", " ", _HALLUC_STRIP.sub(" ", t)).strip(" .,!?־-")


# The ivrit turbo model's known "attractor" hallucination: a fixed, long,
# GRAMMATICAL Hebrew block it emits verbatim on low-info audio (music bleed /
# silence). It is confident + grammatical, so it survives every other heuristic
# (char-runs, token loops, no_speech/logprob gates) and gets typed — the user
# experiences it as "the mic transcribes my old conversation from 400 years ago".
# Fingerprint it ONLY by NONSENSE anchors that never occur in real speech — NOT
# by the address fragments ("דיזנגלוף / בן גוריון / 59"), which Iddo genuinely
# says when giving directions. Any one nonsense anchor is enough to reject the
# whole utterance.
_ATTRACTOR = re.compile(
    r"אתה לא רוצה לראות קצת פה"
    r"|שאתם ילכו לכאן"
    r"|א?מאה אחוז אבל ממש לא\s*,?\s*אני מוצא מאוד",
    re.I)


def is_hallucination(t: str) -> bool:
    c = (t or "").strip()
    if not c:
        return True
    # known model "attractor" block — reject the whole confident-but-garbage
    # utterance (its nonsense anchors never appear in real speech).
    if _ATTRACTOR.search(c):
        return True
    low = c.lower()
    stripped = low.rstrip(".!?, ").strip()
    if stripped in _HALLUC or low in _HALLUC:
        return True
    if _REPEAT.match(low):
        return True
    # a single short token with no spaces is almost always noise/filler
    if len(stripped) <= 2 and " " not in stripped:
        return True
    # sustained-sound / char-run noise: any character repeated 4+ times in a row
    # ("אהההה", "חשששש", "יאומןהההה") — Whisper rendering a held vowel/hum/laugh.
    if re.search(r"(.)\1{3,}", stripped):
        return True
    # a short phrase repeated 4+ times in a row = hallucination loop ("X X X X …")
    if re.search(r"\b(.{2,20}?)\b(?:\s+\1){3,}", stripped):
        return True
    # separator-joined / glued repetition Whisper renders as ONE token:
    # "אה-אה-אה-אה", "האהאהאה", "lalala" → a short 1-4 char unit repeated over
    # the whole utterance. (Multi-word loops with a real-ish prefix → rule below.)
    compact = re.sub(r"[\s\-_.,!?־–]+", "", stripped)
    if len(compact) >= 4 and re.fullmatch(r"(.{1,4}?)\1{2,}", compact):
        return True
    # repeated-token gibberish: Whisper LOOPS one short word on unclear/quiet
    # audio ("מצוין ומצוין ומצוין…", "חחח חחח חחח"). If one token (ignoring a
    # leading Hebrew "ו" connector) dominates a multi-word utterance, it is a
    # hallucination loop, not real speech.
    words = stripped.split()
    if len(words) >= 3:
        norm = [w.lstrip("ו") for w in words]
        # (a) 3+ of the SAME token in a row = a Whisper loop, regardless of any
        #     leading gibberish ("…שם מצוין ומצוין ומצוין ומצוין").
        run = 1
        for i in range(1, len(norm)):
            if norm[i] and norm[i] == norm[i - 1]:
                run += 1
                if run >= 3:
                    return True
            else:
                run = 1
        # (b) one token dominating the whole utterance (>=40%).
        from collections import Counter
        nz = [w for w in norm if w]
        if nz:
            top = Counter(nz).most_common(1)[0][1]
            if top >= 3 and top >= len(words) * 0.4:
                return True
    return False


def _audio():
    import numpy as np
    import sounddevice as sd
    return sd, np


# ── microphone capture ───────────────────────────────────────────────────────
def list_input_devices():
    sd, _ = _audio()
    return [(i, d["name"]) for i, d in enumerate(sd.query_devices())
            if d.get("max_input_channels", 0) > 0]


def _probe(idx, secs=0.8) -> int:
    sd, np = _audio()
    try:
        rec = sd.rec(int(SAMPLE_RATE * secs), samplerate=SAMPLE_RATE,
                     channels=CHANNELS, dtype=DTYPE, device=idx)
        sd.wait()
        return int(np.abs(rec).max())
    except Exception as e:  # noqa: BLE001
        logger.debug("probe failed dev=%s: %s", idx, e)
        return -1


def _is_banned(name: str, never: list[str]) -> bool:
    n = (name or "").lower()
    return any(b.lower() in n for b in (never or []))


def resolve_device(primary=None, fallbacks=None, verify=True,
                   never_use=None, idle_if_no_good_mic=True):
    """Resolve a working input device index by name substring, priority order.

    - NEVER selects a device whose name matches `never_use` (e.g. the BT XM4) —
      protects music quality (BT can't do HQ A2DP + SCO mic at once).
    - Skips devices that open but capture silence (verify=True).
    - If nothing in the chain verifies and `idle_if_no_good_mic` is True, returns
      (None, None, note) signalling the caller to IDLE rather than grabbing the
      system default (which on this PC is the banned BT headset).

    Returns (index, name, note). index None + name None => IDLE (no good mic).
    index None + name 'default' => fall back to system default mic."""
    never = list(never_use or [])
    devs = list_input_devices()
    chain = [c for c in ([primary] + list(fallbacks or [])) if c]
    notes = []
    for hint in chain:
        h = hint.lower()
        for idx, name in devs:
            if h in name.lower():
                if _is_banned(name, never):
                    notes.append(f"{name!r} BANNED(never_use)")
                    break
                if not verify:
                    return idx, name, f"selected {name!r}"
                peak = _probe(idx)
                if peak > 30:
                    return idx, name, f"using {name!r} (peak={peak})"
                notes.append(f"{name!r} silent(peak={peak})")
                break
    msg = "no good wired mic: " + "; ".join(notes) if notes else \
          "no configured device matched"
    if idle_if_no_good_mic:
        return None, None, msg + " -> IDLE (refusing to grab banned/default mic)"
    return None, "default", msg + " -> system default mic"


def record_ptt(device, stop_event: threading.Event, max_secs=30):
    """Push-to-talk: record from now until stop_event set or max_secs. WAV path or None."""
    sd, np = _audio()
    frames, peak = [], 0
    start = time.monotonic()
    with sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS,
                        dtype=DTYPE, device=device) as st:
        while not stop_event.is_set() and time.monotonic() - start < max_secs:
            block, _ = st.read(int(SAMPLE_RATE * 0.1))
            frames.append(block.copy())
            if len(block):
                peak = max(peak, int(np.abs(block).max()))
    if not frames or peak < 60:
        return None
    return _write_wav(np.concatenate(frames, axis=0), np)


def record_until_silence(device, on_start=None, on_end=None, rms_threshold=220,
                         silence_secs=1.4, max_secs=30):
    """VAD: wait for speech, record until silence_secs of quiet, return WAV path or None."""
    sd, np = _audio()
    frames, peak = [], 0
    spoke = False
    speech_start = silence_start = 0.0
    started_at = time.monotonic()
    with sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS,
                        dtype=DTYPE, device=device) as st:
        while True:
            block, _ = st.read(int(SAMPLE_RATE * 0.1))
            now = time.monotonic()
            rms = int(np.sqrt(np.mean(block.astype(np.float64) ** 2))) if len(block) else 0
            if spoke:
                frames.append(block.copy())
                peak = max(peak, rms)
            if rms > rms_threshold:
                if not spoke:
                    if speech_start == 0.0:
                        speech_start = now
                    elif now - speech_start >= 0.2:
                        spoke = True
                        frames.append(block.copy())
                        if on_start:
                            on_start()
                silence_start = 0.0
            elif spoke:
                if silence_start == 0.0:
                    silence_start = now
                elif now - silence_start >= silence_secs:
                    break
            if spoke and now - speech_start >= max_secs:
                break
            if not spoke and now - started_at >= max_secs:
                return None
    if on_end:
        on_end()
    if not frames or peak < rms_threshold:
        return None
    return _write_wav(np.concatenate(frames, axis=0), np)


def _write_wav(audio, np) -> str:
    os.makedirs(_TEMP, exist_ok=True)
    path = os.path.join(_TEMP, f"rec_{time.strftime('%Y%m%d_%H%M%S_%f')}.wav")
    with wave.open(path, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(SAMPLE_WIDTH)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(audio.tobytes())
    return path


# ── engine (faster-whisper singleton) ────────────────────────────────────────
class HebrewSTT:
    """Reusable Hebrew STT engine. Construct once, call .listen()/.transcribe_file()."""

    _shared = None  # process-wide default instance

    def __init__(self, **overrides):
        self.cfg = {**DEFAULTS, **overrides}
        self._model = None
        self._model_key = None
        self._base_model = None      # cached base multilingual model (detection)
        self._base_model_key = None

    # --- model loading ---
    def _pick_device(self):
        dev = (self.cfg.get("device") or "auto").lower()
        if dev in ("cpu", "cuda"):
            return dev
        # auto: prefer cuda if torch sees a GPU, else cpu
        try:
            import torch
            if torch.cuda.is_available():
                return "cuda"
        except Exception:  # noqa: BLE001
            pass
        return "cpu"

    # Local snapshot of ivrit-ai turbo (avoids needing network at load time).
    _IVRIT_LOCAL = r"D:\CLAUDE\models\ivrit-ai\whisper-large-v3-turbo-ct2"
    # Local snapshot of the stock multilingual large-v3-turbo (CTranslate2). Used
    # for reliable language detection + correct non-Hebrew transcription. The HF
    # cache layout is models--<org>--<name>/snapshots/<rev>/ ; we resolve the
    # newest snapshot dir at load time so a re-download with a new rev still works.
    _BASE_HF_CACHE = (r"D:\CLAUDE\models\huggingface\hub"
                      r"\models--mobiuslabsgmbh--faster-whisper-large-v3-turbo")

    @classmethod
    def _base_local_dir(cls):
        """Return the on-disk snapshot dir for the base model, or None.
        Picks the newest snapshot under the HF cache so a fresh download wins."""
        snaps = os.path.join(cls._BASE_HF_CACHE, "snapshots")
        try:
            if os.path.isdir(snaps):
                dirs = [os.path.join(snaps, d) for d in os.listdir(snaps)]
                dirs = [d for d in dirs
                        if os.path.isfile(os.path.join(d, "model.bin"))]
                if dirs:
                    return max(dirs, key=os.path.getmtime)
        except Exception:  # noqa: BLE001
            pass
        return None

    def _resolve_model(self, device):
        """Pick the model id/path for the device.
        CUDA -> ivrit-ai turbo (local snapshot if present, else HF id).
        CPU  -> cfg['cpu_model'] (generic small/base/tiny) for speed + no big DL."""
        name = self.cfg.get("model", "ivrit-ai/whisper-large-v3-turbo-ct2")
        if device == "cpu":
            return self.cfg.get("cpu_model", "base")
        if "ivrit" in str(name).lower() and os.path.isdir(self._IVRIT_LOCAL):
            return self._IVRIT_LOCAL
        return name

    def _resolve_base_model(self):
        """Path/id for the base multilingual model (detection + non-he).
        Prefer the local HF-cache snapshot (offline-safe); else the HF id so
        faster-whisper downloads it on first use (~1.6GB)."""
        local = self._base_local_dir()
        if local:
            return local
        return self.cfg.get("base_model",
                            "mobiuslabsgmbh/faster-whisper-large-v3-turbo")

    def _load_base(self):
        """Load + cache the base multilingual model (detection / non-he).
        Same device/compute policy as the primary model. Returns the model or
        None if it cannot be loaded (caller then falls back to single-model)."""
        from faster_whisper import WhisperModel
        device = self._pick_device()
        name = self._resolve_base_model()
        key = (name, device)
        if self._base_model is not None and self._base_model_key == key:
            return self._base_model
        ct = "int8" if device == "cpu" else "int8_float16"
        logger.info("loading base multilingual model %s on %s (%s)",
                    name, device, ct)
        try:
            self._base_model = WhisperModel(name, device=device, compute_type=ct)
            self._base_model_key = key
            return self._base_model
        except Exception as e:  # noqa: BLE001
            logger.warning("base model GPU load failed (%s) -> CPU int8", e)
            try:
                self._base_model = WhisperModel(name, device="cpu",
                                                compute_type="int8")
                self._base_model_key = (name, "cpu")
                return self._base_model
            except Exception as e2:  # noqa: BLE001
                logger.warning("base model CPU load failed (%s); "
                               "dual-detect disabled this run", e2)
                self._base_model = None
                self._base_model_key = None
                return None

    def _load(self):
        from faster_whisper import WhisperModel
        device = self._pick_device()
        name = self._resolve_model(device)
        key = (name, device)
        if self._model is not None and self._model_key == key:
            return self._model
        ct = "int8" if device == "cpu" else "int8_float16"  # GPU: int8_float16 fits 8GB
        logger.info("loading faster-whisper %s on %s (%s)", name, device, ct)
        try:
            self._model = WhisperModel(name, device=device, compute_type=ct)
            self._model_key = key
        except Exception as e:  # noqa: BLE001
            logger.warning("GPU load failed (%s) -> CPU int8 %s", e,
                           self.cfg.get("cpu_model", "base"))
            cpu_name = self.cfg.get("cpu_model", "base")
            self._model = WhisperModel(cpu_name, device="cpu", compute_type="int8")
            self._model_key = (cpu_name, "cpu")
        return self._model

    def warmup(self):
        """Pre-load the model (call at app start to avoid first-utterance lag).
        In dual mode also pre-loads the base multilingual model so the first
        detection doesn't pay the load cost."""
        self._load()
        if (str(self.cfg.get("lang_detect", "single")).lower() == "dual"
                and not (self.cfg.get("language") or None)):
            try:
                self._load_base()
            except Exception:  # noqa: BLE001
                pass
        return self

    # --- transcription ---
    def _wav_duration(self, wav_path: str) -> float:
        try:
            with wave.open(wav_path, "rb") as wf:
                return wf.getnframes() / float(wf.getframerate() or SAMPLE_RATE)
        except Exception:  # noqa: BLE001
            return 0.0

    # --- segment filtering + post-processing (shared by both models) ---
    def _segs_to_text(self, segs) -> str:
        """Join kept segments into text, dropping silence/low-confidence ones."""
        max_nsp = float(self.cfg.get("max_no_speech_prob", 0.6))
        min_lp = float(self.cfg.get("min_avg_logprob", -1.0))
        kept = []
        for s in segs:
            nsp = getattr(s, "no_speech_prob", 0.0) or 0.0
            lp = getattr(s, "avg_logprob", 0.0) or 0.0
            if nsp > max_nsp:
                continue                # mostly silence
            if lp < min_lp:
                continue                # low-confidence -> likely hallucination
            kept.append(s.text.strip())
        return " ".join(t for t in kept if t).strip()

    def _postprocess(self, text: str) -> tuple[str, str]:
        """Apply initial-prompt-echo + hallucination filters. Returns (text, reason)."""
        reason = ""
        # strip any echoed prompt fragment (partial or full) from anywhere in text
        if text:
            for echo in _PROMPT_ECHOES:
                if echo in text:
                    text = text.replace(echo, " ")
            text = _HALLUC_STRIP.sub(" ", text)   # remove recurring hallucination phrases
            text = re.sub(r"\s+", " ", text).strip(" .,!?־-")
        ip = (self.cfg.get("initial_prompt") or "").strip()
        if ip and text:
            norm_t = re.sub(r"\s+", " ", text).strip(" .,!?")
            norm_ip = re.sub(r"\s+", " ", ip).strip(" .,!?")
            if norm_t == norm_ip or norm_t in norm_ip or norm_ip in norm_t:
                return "", "echoed_initial_prompt"
        if not text:
            reason = "no_speech/low_conf"
        elif is_hallucination(text):
            return "", "hallucination_filter"
        return text, reason

    def _transcribe_kwargs(self, language=None, use_prompt=True):
        # condition_on_previous_text=False is CRITICAL for an always-on mic.
        # Default True makes faster-whisper CARRY PRIOR TEXT across utterances, so
        # on quiet/unclear audio it REGURGITATES earlier dictation — this is the
        # "the mic reads back an old conversation" bug. Off = each
        # utterance is independent. (Already flagged as critical in STT_CHOICE.md.)
        kwargs = {
            "beam_size": self.cfg.get("beam_size", 5),
            "condition_on_previous_text": False,
            # Anti-hallucination decoder guards (faster-whisper / CTranslate2,
            # build-to-standard). The ivrit turbo model emits a fixed "attractor"
            # Hebrew block on low-information audio (Bluetooth-music bleed,
            # silence, hums). Passing these explicitly engages Whisper's upstream
            # guards: the repetitive/low-confidence attractor trips the
            # compression-ratio + logprob checks and is dropped/retried at the
            # SOURCE instead of being returned as confident garbage. Wrapped by
            # the caller's try/except, so any kwarg an older CT2 rejects is safe.
            "temperature": [0.0, 0.2, 0.4, 0.6, 0.8],
            "compression_ratio_threshold": 2.4,
            "log_prob_threshold": -1.0,
            "no_speech_threshold": 0.6,
            # vad_filter skips silence/noise INSIDE the clip so Whisper can't
            # hallucinate filler onto it ("מצוין ומצוין…", stray English like
            # "Marcel Vogel"/"ala ala ala"). Mandatory for an always-on mic.
            "vad_filter": bool(self.cfg.get("stt_vad_filter", True)),
            "vad_parameters": dict(
                min_silence_duration_ms=int(self.cfg.get("stt_vad_min_silence_ms", 500)),
                threshold=float(self.cfg.get("stt_vad_threshold", 0.5)),
            ),
        }
        if language:
            kwargs["language"] = language
        if use_prompt:
            ip = self.cfg.get("initial_prompt")
            if ip:
                kwargs["initial_prompt"] = ip
        return kwargs

    @staticmethod
    def _decode_audio(wav_path):
        """Decode a wav to a 1D float32 16kHz numpy array (faster-whisper input).
        Returns the array, or None if decoding is unavailable/fails."""
        try:
            from faster_whisper import decode_audio
            return decode_audio(wav_path, sampling_rate=SAMPLE_RATE)
        except Exception:  # noqa: BLE001
            return None

    def _detect_language(self, wav_path, audio=None):
        """Detect language with the base multilingual model (reliable he/en split).
        Returns (lang, prob, base_model) or (None, 0.0, None) if unavailable.
        `audio` may be a pre-decoded float array to avoid re-decoding.
        Crash-safe: any failure returns the no-detection sentinel."""
        try:
            base = self._load_base()
            if base is None:
                return None, 0.0, None
            # Preferred: detect_language() on the decoded waveform (fast, no full
            # transcription). It needs a 1D float array, NOT a path.
            snd = audio if audio is not None else self._decode_audio(wav_path)
            if snd is not None and hasattr(base, "detect_language"):
                lang, prob, _ = base.detect_language(audio=snd)
                return lang, float(prob or 0.0), base
            # Fallback: a beam_size=1 transcribe still fills info.language/.prob.
            _segs, info = base.transcribe(wav_path, beam_size=1)
            return (getattr(info, "language", None),
                    float(getattr(info, "language_probability", 0.0) or 0.0),
                    base)
        except Exception as e:  # noqa: BLE001
            logger.warning("language detection failed (%s) -> single-model", e)
            return None, 0.0, None

    def transcribe_file(self, wav_path: str) -> dict:
        """Transcribe a wav file. Returns {ok, text, lang, reason}.
        text='' when rejected as silence / noise / hallucination (reason says why).

        When cfg['lang_detect']=='dual' AND no explicit cfg['language'] is forced,
        the language is first detected with the stock multilingual model and the
        utterance is routed: Hebrew -> ivrit-ai (best Hebrew), else -> base model
        (correct English/other). Any failure in this path falls back to the legacy
        single-model transcribe so dictation never crashes."""
        try:
            # reject clips shorter than min_secs (noise blips)
            min_secs = float(self.cfg.get("min_secs", 0.6) or 0)
            dur = self._wav_duration(wav_path)
            if min_secs and dur and dur < min_secs:
                return {"ok": True, "text": "", "lang": None,
                        "reason": f"too_short({dur:.2f}s<{min_secs}s)"}

            forced = self.cfg.get("language") or None
            dual = str(self.cfg.get("lang_detect", "single")).lower() == "dual"

            # ── DUAL: detect language, then route to the best engine ──────────
            if dual and not forced:
                routed = self._transcribe_dual(wav_path)
                if routed is not None:
                    return routed
                # routed is None -> detection/base unavailable; fall through to
                # the legacy single-model path below (crash-safe).

            # ── SINGLE (legacy) path ──────────────────────────────────────────
            m = self._load()
            kwargs = self._transcribe_kwargs(language=forced)
            segs, info = m.transcribe(wav_path, **kwargs)
            text = self._segs_to_text(segs)
            text, reason = self._postprocess(text)
            return {"ok": True, "text": text, "reason": reason,
                    "lang": getattr(info, "language", forced)}
        except Exception as e:  # noqa: BLE001
            logger.error("STT failed: %s", e, exc_info=True)
            return {"ok": False, "text": "", "error": str(e)}

    def _transcribe_dual(self, wav_path: str):
        """Detection + routed transcription. Returns a result dict, or None to
        signal the caller to fall back to the legacy single-model path."""
        # Decode once; reuse the waveform for detection AND transcription.
        audio = self._decode_audio(wav_path)
        src = audio if audio is not None else wav_path
        lang, prob, base = self._detect_language(wav_path, audio=audio)
        if base is None:
            return None  # base model unavailable -> legacy fallback
        min_prob = float(self.cfg.get("lang_detect_min_prob", 0.55))
        # Language whitelist: only route to a non-Hebrew engine for languages the
        # user actually speaks (default he/en). This stops the multilingual model
        # from WANDERING to Greek/Japanese/Arabic etc. on unclear audio and
        # rendering gibberish. Other languages stay available on demand via the
        # explicit "Claude <language>" voice command (which forces `language`,
        # bypassing this auto-detect path entirely).
        whitelist = set(self.cfg.get("lang_whitelist") or [])
        off_whitelist = bool(whitelist) and lang != "he" and lang not in whitelist
        # Trust 'he', or a confident in-whitelist non-he. Low-confidence non-he
        # (short noise/filler) OR an off-whitelist verdict -> default to Hebrew,
        # this user's primary language, so a noisy blip never garbles into a
        # random foreign script.
        is_he = (lang == "he") or (lang != "he" and prob < min_prob) or off_whitelist
        if is_he:
            m = self._load()                      # ivrit-ai: best Hebrew
            kwargs = self._transcribe_kwargs(language="he")
            routed_lang = "he"
        else:
            m = base                              # base model: correct en/other
            kwargs = self._transcribe_kwargs(language=lang, use_prompt=False)
            routed_lang = lang
        segs, info = m.transcribe(src, **kwargs)
        text = self._segs_to_text(segs)
        text, reason = self._postprocess(text)
        out_lang = getattr(info, "language", routed_lang) or routed_lang
        return {"ok": True, "text": text, "reason": reason, "lang": out_lang,
                "detected": lang, "detect_prob": round(prob, 3)}

    # --- capture + transcribe in one call ---
    def listen(self, mode="vad", stop_event=None, on_start=None, on_end=None,
               keep_wav=False) -> str:
        """Record from the mic and return Hebrew text ('' if nothing/hallucination).

        mode="vad" (default): waits for speech, stops on silence.
        mode="ptt": records until stop_event is set (you must pass a threading.Event).
        """
        idx, name, note = resolve_device(
            self.cfg.get("input_device"),
            self.cfg.get("fallback_devices"),
            never_use=self.cfg.get("never_use_devices"),
            idle_if_no_good_mic=self.cfg.get("idle_if_no_good_mic", True))
        logger.info("mic: %s", note)
        if idx is None and name is None:
            return ""   # IDLE: no good wired mic, refuse to grab banned/default
        if mode == "ptt":
            if stop_event is None:
                raise ValueError("mode='ptt' requires stop_event (threading.Event)")
            wav = record_ptt(idx, stop_event, self.cfg.get("max_secs", 30))
        else:
            wav = record_until_silence(
                idx, on_start=on_start, on_end=on_end,
                rms_threshold=self.cfg.get("vad_rms_threshold", 220),
                silence_secs=self.cfg.get("silence_secs", 1.4),
                max_secs=self.cfg.get("max_secs", 30))
        if not wav:
            return ""
        try:
            return self.transcribe_file(wav).get("text", "")
        finally:
            if not keep_wav:
                try:
                    os.remove(wav)
                except OSError:
                    pass


# ── module-level convenience (uses a shared singleton) ───────────────────────
def get_engine(**overrides) -> HebrewSTT:
    """Return the process-wide shared engine (created on first call)."""
    if HebrewSTT._shared is None or overrides:
        HebrewSTT._shared = HebrewSTT(**overrides)
    return HebrewSTT._shared


def listen(mode="vad", **overrides) -> str:
    """One-liner: record + return Hebrew text. Extra kwargs override config once."""
    eng = get_engine(**overrides) if overrides else get_engine()
    return eng.listen(mode=mode)


def transcribe_file(wav_path: str, **overrides) -> str:
    """One-liner: transcribe a wav file, return Hebrew text."""
    eng = get_engine(**overrides) if overrides else get_engine()
    return eng.transcribe_file(wav_path).get("text", "")


def warmup(**overrides) -> HebrewSTT:
    return get_engine(**overrides).warmup()


# ── CLI smoke test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    import json
    import sys
    try:  # Windows console defaults to cp1252 and chokes on Hebrew
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if len(sys.argv) > 1 and sys.argv[1] not in ("--mic", "--listen"):
        # transcribe a provided wav file
        print(json.dumps(get_engine().transcribe_file(sys.argv[1]),
                         ensure_ascii=False, indent=2))
    elif len(sys.argv) > 1 and sys.argv[1] == "--listen":
        print("מדבר עכשיו... (דבר בעברית, עצור בשתיקה)")
        print("→", listen() or "[שום דבר נקלט]")
    else:
        # device + model sanity
        print("Input devices:")
        for i, n in list_input_devices():
            print(f"  #{i}  {n}")
        idx, name, note = resolve_device(DEFAULTS["input_device"],
                                         DEFAULTS["fallback_devices"])
        print(f"\nResolved mic: #{idx} {name}\n  {note}")
        print("\nLoading model...")
        warmup()
        print("Model loaded OK. Run with --listen to test live Hebrew mic input,")
        print("or pass a wav path to transcribe a file.")
