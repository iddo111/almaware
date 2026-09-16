"""alma-mic / config.py — one small, explicit settings store.

ALMAWARE-pure: ours. Plain dataclass <-> JSON (config.json next to this file).
Holds the choices Iddo asked for: which mic, which languages / translate, wake-word
(arm) behaviour, and which recognition model (Whisper + our Hebrew LoRA).
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
import json
import os

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")


@dataclass
class Config:
    # --- microphone ---
    mic: str = "auto"                       # "auto" = pick a live one; else a name substring
    prefer: list[str] = field(default_factory=lambda: ["brio", "scarlett"])
    avoid: list[str] = field(default_factory=lambda:
                             ["usbaudio", "wh-1000xm4", "hands-free", "headset", "bluetooth", "mix"])

    # --- language / translation ---
    language: str = "auto"                  # "auto" | "he" | "en" | ...
    lang_whitelist: list[str] = field(default_factory=lambda: ["he", "en"])
    translate_to_english: bool = False      # Whisper's translate task only targets English

    # --- arming (wake word) ---
    arming: str = "auto"                    # "auto" = always-on (VAD) | "wakeword"
    wake_words: list[str] = field(default_factory=lambda: ["ערן", "קלוד", "claude"])

    # --- recognition model (a MODEL, like Eran — allowed under the purity law) ---
    model: str = "ivrit-ai/whisper-large-v3-turbo-ct2"   # Hebrew-finetuned Whisper
    lora_dir: str = ""                      # OUR LoRA, merged+converted to ct2 (optional)
    device: str = "auto"                    # "auto" | "cuda" | "cpu"
    compute_type: str = "auto"              # "auto" | "float16" | "int8"

    # --- output ---
    type_output: bool = False               # type recognized text into the focused window
    auto_enter: bool = False                # press Enter after typing a line

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
