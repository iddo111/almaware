"""transcribe.py - Hebrew STT for voice-input.

WIRED to the shared helper D:\\CLAUDE\\hebrew-voice\\hebrew_stt.py (2026-05-31).
This file is now a thin compatibility shim: it keeps the original
`transcribe(wav_path, cfg)` / `load(cfg)` / `is_hallucination(t)` API that
voice_input.py depends on, but delegates the actual work to the shared
faster-whisper engine so every app shares one Hebrew STT codebase.

voice-input's CPU-first policy is preserved: cfg["device"] (default "cpu") is
passed straight through, so this app does NOT touch the GPU unless its own
config says so.

"""
from __future__ import annotations

import logging
import os
import sys

# Wire shared STT engine — sibling ../hebrew-voice first, then known installs.
_HERE = os.path.dirname(os.path.abspath(__file__))
for _hv in (
    os.path.normpath(os.path.join(_HERE, "..", "hebrew-voice")),
    r"D:\CLAUDE\hebrew-voice",
    r"D:\claude\hebrew-voice",
):
    if os.path.isfile(os.path.join(_hv, "hebrew_stt.py")):
        if _hv not in sys.path:
            sys.path.insert(0, _hv)
        break
else:
    raise ImportError(
        "hebrew_stt not found — expected hebrew-voice/hebrew_stt.py "
        f"(checked from {_HERE})"
    )

import hebrew_stt  # shared helper (also wired via site-packages/hebrew_stt.pth)
from hebrew_stt import is_hallucination, strip_halluc  # re-exported for API compatibility

logger = logging.getLogger("voiceinput.stt")

_engine = None
_engine_key = None

def _engine_for(cfg: dict) -> "hebrew_stt.HebrewSTT":
    global _engine, _engine_key
    # lang_detect ("dual"/"single") + base_model are part of the cache key so a
    # config change rebuilds the engine.
    key = (cfg.get("model", "small"),
           cfg.get("device", "cpu"),
           cfg.get("language", "he"),
           cfg.get("lang_detect", "single"),
           cfg.get("base_model"))
    if _engine is not None and _engine_key == key:
        return _engine
    overrides = dict(
        model=cfg.get("model", "small"),
        device=cfg.get("device", "cpu"),   # voice-input stays CPU-first
        language=cfg.get("language", "he"),
        beam_size=cfg.get("beam_size", 5),
    )
    # Forward the dual-model language-ID knobs only when present so we keep the
    # shared DEFAULTS otherwise.
    for k in ("lang_detect", "base_model", "lang_detect_min_prob",
              "lang_whitelist", "cpu_model", "min_secs", "max_no_speech_prob",
              "min_avg_logprob", "initial_prompt"):
        if k in cfg:
            overrides[k] = cfg[k]
    _engine = hebrew_stt.HebrewSTT(**overrides)
    _engine_key = key
    return _engine

def set_lang_whitelist(wl):
    """Update the live engine's auto-detect language whitelist with NO model
    reload (the engine reads cfg['lang_whitelist'] per utterance). Empty/None =
    accept ALL detected languages (full multilingual auto). Safe if no engine
    is loaded yet — the next load() will pick up the config value."""
    if _engine is not None:
        _engine.cfg["lang_whitelist"] = list(wl) if wl else []

def load(cfg: dict):
    return _engine_for(cfg).warmup()

def transcribe(wav_path: str, cfg: dict) -> dict:
    return _engine_for(cfg).transcribe_file(wav_path)

if __name__ == "__main__":
    import json
    import os
    import sys
    logging.basicConfig(level=logging.INFO)
    cfg = json.load(open(os.path.join(os.path.dirname(__file__), "config.json"),
                        encoding="utf-8"))
    if len(sys.argv) > 1:
        print(json.dumps(transcribe(sys.argv[1], cfg), ensure_ascii=False))
    else:
        load(cfg)
        print("model loaded")
