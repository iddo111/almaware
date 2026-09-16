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
    prefer: list[str] = field(default_factory=lambda: ["brio", "scarlett", "usbaudio"])
    # "usbaudio" used to sit in this avoid list. On this PC the ONLY physically
    # present microphone is "Microphone (USBAudio1.0)", so the default config
    # rejected the only device it could ever use, then fell back and gated
    # everything as silence. Avoid Bluetooth/hands-free profiles and loopback
    # mixes - never a generic class name that a real device might carry.
    avoid: list[str] = field(default_factory=lambda:
                             ["wh-1000xm4", "hands-free", "headset", "bluetooth", "mix"])

    # --- language / translation ---
    language: str = "auto"                  # "auto" | "he" | "en" | ...
    lang_whitelist: list[str] = field(default_factory=lambda: ["he", "en"])
    translate_to_english: bool = False      # Whisper's translate task only targets English
    # auto language-ID tuning (only used when language == "auto"):
    auto_detect_langs: int = 2              # how many segments to vote over for the first-pass language guess
    lang_confidence: float = 0.85           # below this, the whitelist acts as a SOFT prior (not a hard lock).
                                            # RAISED 0.6 -> 0.85 (2026-08-08): at 0.6 a barely-confident "en" guess
                                            # on Hebrew speech was trusted outright and decoded as English garbage
                                            # ("flying corals", "karma karma", "036"). At 0.85 an unsure guess goes
                                            # to the he/en re-decode tie-break instead, which picks the language the
                                            # model is actually at home in. Mixed he/en dictation still works.
    code_switch: bool = True                # re-detect language per segment during decode (he/en mid-utterance)
    lang_lock: bool = True                  # CONSTRAIN auto-detect to lang_whitelist (he/en) — stops the
                                            # silence-hallucination drift into ar/ru/ja/… ; off = legacy any-language

    # --- anti-hallucination decode guards (fix for Whisper-on-silence) ---
    speech_rms_gate: float = 0.070          # drop any segment whose RMS is below this (pure silence/noise) BEFORE STT; 0 = off
    autogain_rms_floor: float = 0.004       # auto-gain only amplifies segments whose ORIGINAL rms clears this;
                                            # below it = ambient (measured 0.001-0.0024) — never lift noise into
                                            # the decoder, that is how silence typed 'חחח' (laughfix 2026-08-08)
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

    # --- English decoder + router (enfix 2026-08-10) ---
    # The ivrit-ai fine-tune is a superb HEBREW transcriber but a BROKEN language
    # detector: it tags English speech 'he' (measured p≈1.0 on this morning's
    # failing clips) and then TRANSLITERATES English into Hebrew letters
    # ('סיד אוטושרנט סלילס...', log 06:13). The stock multilingual large-v3-turbo
    # separates he/en cleanly (same finding as the retired voice-input rig, see
    # archive/hebrew-voice/hebrew_stt.py "dual" mode). So when en_model is set:
    #   detect with en_model  ->  he: decode on ivrit (UNCHANGED Hebrew path)
    #                             en: decode on en_model (real English)
    # Empty string = old single-model behaviour.
    # DEFAULT IS NON-EMPTY ON PURPOSE: the app rewrites config.json from asdict()
    # on exit, so a still-running old-schema mic drops unknown keys on its way
    # out; if the default were "" that exit would silently turn the fix off.
    en_model: str = "mobiuslabsgmbh/faster-whisper-large-v3-turbo"
    en_detect_min_prob: float = 0.55        # trust a non-he verdict only above this; below -> Hebrew
                                            # (Iddo's primary language; same semantics the old rig proved)
    en_vad_filter: bool = False             # inner Silero VAD OFF for English decodes — the measured
                                            # quirk: en + inner-VAD yields transliteration ('טוקינג אינגליש'),
                                            # en without it yields real English (stt.py script-retry note)
    # Decode width. 5 = beam search (slow), 1 = greedy (fast, barely worse for
    # dictation). This MUST be a dataclass field: the app rewrites config.json
    # from asdict() on exit, so any key that is not a field is silently dropped
    # on the next save - which is how this setting kept reverting.
    beam_size: int = 1
    device: str = "auto"                    # "auto" | "cuda" | "cpu"
    compute_type: str = "auto"              # "auto" | "float16" | "int8"

    # --- output ---
    type_output: bool = False               # type recognized text into the focused window
    auto_enter: bool = False
    # Where dictation is allowed to land. The guard used to hard-code
    # ChatGPT/Claude/Codex, so typing into Notepad or a terminal was refused.
    type_anywhere: bool = False        # True = any focused window
    type_targets: list[str] = field(default_factory=list)   # extra title substrings

    # --- voice learning (smart weight-training data collection) ---
    collect_corpus: bool = True             # auto-save (audio,transcript) pairs to voice_corpus/ as
                                            # training fuel for a per-speaker Whisper LoRA (trained on the DGX, not the PC)

    # --- brain (ask an AI from the mic): Grok primary, DictaLM-on-DGX Hebrew fallback ---
    brain_backend: str = "grok"             # "grok" (primary, auto-falls-back to dicta) | "dicta" (force Hebrew)
    brain_auto: bool = False                # auto-ask the brain about each finalized utterance
                                            # DANGER if True without guards: every STT fragment
                                            # spawns a headless grok.exe (alma_grok_* temp dirs).
    dicta_url: str = ""                     # OpenAI-compatible DictaLM endpoint on a DGX node,
                                            # e.g. http://eran1:8090/v1/chat/completions (heavy 7B lives on DGX)

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
