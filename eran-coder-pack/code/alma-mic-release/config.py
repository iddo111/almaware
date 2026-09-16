"""alma-mic / config.py — one small, explicit settings store.

ALMAWARE-pure: ours. Plain dataclass <-> JSON (config.json next to this file).
Holds the choices Iddo asked for: which mic, which languages / translate, wake-word
(arm) behaviour, and which recognition model (Whisper + our Hebrew LoRA).
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
import json
import os
import sys


def app_dir() -> str:
    """The app's own writable folder — next to the exe when frozen (cx_Freeze MSI:
    __file__ then points INSIDE library.zip, and writing there crashes on launch),
    next to the sources when run from Python."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


CONFIG_PATH = os.path.join(app_dir(), "config.json")


@dataclass
class Config:
    # --- microphone ---
    mic: str = "auto"                       # "auto" = pick a live one; else a name substring
    prefer: list[str] = field(default_factory=lambda: ["brio", "scarlett"])
    avoid: list[str] = field(default_factory=lambda:
                             ["usbaudio", "wh-1000xm4", "hands-free", "headset", "bluetooth", "mix"])

    # --- language / translation ---
    language: str = "he"                    # "he" | "en" | "auto" | ... — "he" is the family default:
                                            # on a CPU-only laptop "auto" pays 2-3 extra full decodes per
                                            # utterance (language detect + probes); pick "auto"/"en" in ⚙
    lang_whitelist: list[str] = field(default_factory=lambda: ["he", "en"])
    translate_to_english: bool = False      # Whisper's translate task only targets English
    # auto language-ID tuning (only used when language == "auto"):
    auto_detect_langs: int = 2              # how many segments to vote over for the first-pass language guess
    lang_confidence: float = 0.6            # below this, the whitelist acts as a SOFT prior (not a hard lock)
    code_switch: bool = True                # re-detect language per segment during decode (he/en mid-utterance)
    lang_lock: bool = True                  # CONSTRAIN auto-detect to lang_whitelist (he/en) — stops the
                                            # silence-hallucination drift into ar/ru/ja/… ; off = legacy any-language

    # --- anti-hallucination decode guards (fix for Whisper-on-silence) ---
    speech_rms_gate: float = 0.006          # drop any segment whose RMS is below this (pure silence/noise) BEFORE STT; 0 = off
    no_speech_threshold: float = 0.6        # Whisper: prob(no-speech) above this → segment suppressed
    log_prob_threshold: float = -1.0        # drop decodes whose avg log-prob is below this (low-confidence = invented)
    compression_ratio_threshold: float = 2.4  # repetitive junk → high gzip ratio → rejected
    vad_threshold: float = 0.5              # Silero VAD speech probability threshold (higher = stricter)
    vad_min_silence_ms: int = 500           # Silero VAD: min silence to split (longer = less spill of non-speech)
    vad_speech_pad_ms: int = 100            # Silero VAD: padding kept around detected speech

    # --- arming (wake word) ---
    arming: str = "auto"                    # "auto" = always-on (VAD) | "wakeword"
    wake_words: list[str] = field(default_factory=lambda: ["ערן", "קלוד", "claude"])

    # --- recognition model (a MODEL, like Eran — allowed under the purity law) ---
    model: str = "ivrit-ai/whisper-large-v3-turbo-ct2"   # Hebrew-finetuned Whisper
    lora_dir: str = ""                      # OUR LoRA, merged+converted to ct2 (optional)
    device: str = "auto"                    # "auto" | "cuda" | "cpu"
    compute_type: str = "auto"              # "auto" | "float16" | "int8"

    # --- output ---
    type_output: bool = True                # type recognized text into the focused window (the app's point;
                                            # the 🔴/🟢 arm button + Ctrl+Alt+D still gate it live)
    auto_enter: bool = False                # press Enter after typing a line

    # --- voice learning (smart weight-training data collection) ---
    collect_corpus: bool = False            # OPT-IN: save (audio,transcript) pairs to voice_corpus/ as
                                            # training fuel for a per-speaker Whisper LoRA. Off by default —
                                            # the app must never quietly record the speaker to disk.

    # --- brain (ask an AI from the mic): Grok primary, DictaLM-on-DGX Hebrew fallback ---
    brain_backend: str = "grok"             # "grok" (primary, auto-falls-back to dicta) | "dicta" (force Hebrew)
    brain_auto: bool = False                # auto-ask the brain about each finalized utterance
    dicta_url: str = ""                     # OpenAI-compatible DictaLM endpoint on a DGX node,
                                            # e.g. http://your-llm-host:8090/v1/chat/completions (heavy 7B lives on DGX)

    # --- voice slash-commands (drive commands by voice, He + En) ---
    enable_voice_commands: bool = True      # say "slash X" -> "/X"; map phrases -> commands
    voice_commands: dict = field(default_factory=lambda: {
        "by the way": "/btw", "דרך אגב": "/btw", "ביי דה וויי": "/btw",
        "new line": "\n", "שורה חדשה": "\n", "new paragraph": "\n\n",
    })

    @classmethod
    def load(cls) -> "Config":
        c = cls()
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, encoding="utf-8") as f:
                    data = json.load(f)
                for k, v in data.items():
                    if hasattr(c, k):
                        setattr(c, k, v)
            except Exception:
                pass  # corrupt config -> fall back to defaults (and rewrite on save)
        else:
            c.save()
        return c

    def save(self) -> None:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, ensure_ascii=False, indent=2)
