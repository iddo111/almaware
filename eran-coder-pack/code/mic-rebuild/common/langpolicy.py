"""KESHEV language routing — K10 (PHASE2-DESIGN.md sections 2 + 3.1, scars 27/29/30).

The ONE source of routing truth, imported by the worker AND the server
(section 2: common/ is shared client<->server). Backend-agnostic: callers
hand in a backend object; this module never touches a model, a socket, or
a file — which is what makes the scar-29 rules TESTABLE without hardware.

The law (scar 29, measured on real failing clips):
  * the stock multilingual model detects language — NEVER the LoRA (it tags
    English "he" p~=1.0 and transliterates)
  * whitelist {he, en} LOCKED; a failed/off-whitelist detection falls back
    INSIDE the whitelist — `language=None` is unrepresentable ("the single
    line that let noise come back as Icelandic")
  * confidence 0.85; below it -> Hebrew (the `ווי פאי` class)
  * HE -> LoRA decode WITH Silero inner VAD (scar 27 layer 3)
  * EN -> stock decode WITHOUT inner VAD, plus the script-mismatch re-decode
    tie-break: >50% Hebrew chars in an en decode -> re-decode as Hebrew on
    the LoRA (the `טוקינג אינגליש` class)
  * decode guards per common/decode_params.py on EVERY call
  * never context feedback (scar 30 — lint G2 bans the token repo-wide)

Backend protocol (duck-typed; see tests/test_langpolicy.py FakeBackend and
server/stt_server.py FasterWhisperEngine):

    detect_language(audio) -> iterable of (lang, prob), best first
    decode(audio, *, model: str, language: str, vad: bool, **decode_kwargs)
        -> DecodeOutcome
    model_name(role) -> str            (optional; for reporting)
"""
from __future__ import annotations

from dataclasses import dataclass

from common import decode_params

WHITELIST: tuple[str, ...] = ("he", "en")
DEFAULT_LANG = "he"                      # low confidence -> Hebrew (scar 29)
CONFIDENCE = 0.85
SCRIPT_MISMATCH_FRACTION = 0.5           # >50% Hebrew chars in an en decode

# model ROLES — the backend maps them to real models
MODEL_DETECT = "stock"                   # stock multilingual turbo: detects + decodes EN
MODEL_HE = "lora"                        # iddo-lora CT2: decodes HE, NEVER detects

_HEBREW_LO, _HEBREW_HI = 0x0590, 0x05FF


@dataclass(frozen=True)
class DecodeOutcome:
    """What a backend decode returns — raw, unfiltered (textguard is
    client-only, scar 28)."""
    text: str
    avg_logprob: float
    no_speech_prob: float
    compression_ratio: float


@dataclass(frozen=True)
class PolicyResult:
    text: str
    lang: str                            # final language, always in WHITELIST
    lang_prob: float                     # detector confidence for `lang` (1.0 on hint)
    model_role: str                      # MODEL_DETECT | MODEL_HE (final decode)
    detect_reason: str                   # detected|hint|low_conf|detect_failed|script_retry
    retried: bool                        # script-mismatch re-decode happened
    avg_logprob: float
    no_speech_prob: float
    compression_ratio: float


def hebrew_fraction(text: str) -> float:
    """Fraction of ALPHABETIC chars that are Hebrew (punctuation/digits/space
    excluded so '...' or numbers can never mask a script mismatch)."""
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    heb = sum(1 for c in letters if _HEBREW_LO <= ord(c) <= _HEBREW_HI)
    return heb / len(letters)


def choose_language(detection, lang_hint: str = "auto") -> tuple[str, float, str]:
    """(lang, prob, reason) — lang ALWAYS in WHITELIST, never None.

    `detection` is the stock model's (lang, prob) list, or None if detection
    failed (the caller converts exceptions to None so one detector crash can
    never take routing down with it)."""
    if lang_hint not in ("auto", *WHITELIST):
        raise ValueError(f"lang_hint must be one of auto/{'/'.join(WHITELIST)}, got {lang_hint!r}")
    if lang_hint != "auto":
        return lang_hint, 1.0, "hint"
    if detection is None:
        return DEFAULT_LANG, 0.0, "detect_failed"
    in_whitelist = [(str(lg), float(p)) for lg, p in detection if str(lg) in WHITELIST]
    if not in_whitelist:
        return DEFAULT_LANG, 0.0, "detect_failed"
    lang, prob = max(in_whitelist, key=lambda t: t[1])
    if prob >= CONFIDENCE:
        return lang, prob, "detected"
    # LOW CONFIDENCE: use the ARGMAX WE ALREADY HAVE, not a blind DEFAULT_LANG.
    #
    # MEASURED 2026-08-14 on 47 real utterances of Iddo's dictation (stock
    # large-v3-turbo, from his own archived spool): median detection confidence
    # 0.454 against this 0.85 threshold, so 74% of everything he said landed
    # here. Languages seen: en 19, he 14, ja 5, pt 4, ru 3, de 1 -- he
    # code-switches constantly and short mixed clips never reach 0.85.
    #
    # Returning DEFAULT_LANG meant the decoder was then called with
    # language="he" FORCED on English audio. Whisper does not refuse that.
    # It TRANSLATES. Iddo said "so eventually" and KESHEV typed
    # "כלומר, מה שקורה זה..." -- fluent, confident, never spoken. He caught it.
    #
    # The argmax is weak evidence, but it IS evidence and beats discarding it:
    # a wrong argmax gives visibly wrong text in the wrong script, which he can
    # see and fix. Forced Hebrew gives a plausible Hebrew sentence he never
    # said, which he cannot. Visibly wrong beats invisibly wrong (scar 17/18).
    #
    # scar 29 untouched: detection still runs on the STOCK model only, the LoRA
    # still never detects, and lang is still always inside WHITELIST.
    return lang, prob, "low_conf_argmax"


def transcribe(audio, backend, lang_hint: str = "auto") -> PolicyResult:
    """Route one segment through the scar-29 policy. The backend receives a
    whitelist language on EVERY call — no decode is ever used to DISCOVER
    language, and the LoRA never detects."""
    detection = None
    if lang_hint == "auto":
        try:
            detection = list(backend.detect_language(audio))
        except Exception:
            detection = None             # detect_failed -> Hebrew, never None onward
    lang, prob, reason = choose_language(detection, lang_hint)

    guards = decode_params.decode_kwargs()
    if lang == "he":
        # vad=False since 2026-08-14. MEASURED: 8 real-speech segments of Iddo's
        # own dictation (900-2160ms, rms 0.019-0.144) decoded on this box with the
        # LoRA, identical params, only this flag differing:
        #     c36702e2-000540  (EMPTY) -> "תודה."
        #     c36702e2-000543  (EMPTY) -> "תודה."
        #     c36702e2-000743  (EMPTY) -> "הק!"
        # 3 of 8 - 37% of REAL SPEECH - was returned as empty text by the inner
        # Silero VAD. Iddo experienced this as "the mic ate my word"; Claude read
        # it as a clipped recording and asked him to repeat himself.
        # The inner VAD was the LoRA's protection against hallucinating on silence,
        # and the EN path never had it (scar 27/29). That protection now lives on
        # the client, measured and in front of this call: gate_rms 0.008, the blip
        # guard (short AND quiet never leaves the PC), webrtcvad, and the textguard
        # logprob floor at -0.6. Silence no longer arrives here to be protected from.
        # If hallucination-on-silence returns, tighten the CLIENT, not this flag -
        # a VAD that drops 37% of real speech is not a guard, it is a leak.
        out = backend.decode(audio, model=MODEL_HE, language="he", vad=False, **guards)
        return PolicyResult(
            text=out.text, lang="he", lang_prob=prob, model_role=MODEL_HE,
            detect_reason=reason, retried=False, avg_logprob=out.avg_logprob,
            no_speech_prob=out.no_speech_prob, compression_ratio=out.compression_ratio)

    # EN path: stock model, NO inner VAD (scar 27/29)
    out = backend.decode(audio, model=MODEL_DETECT, language="en", vad=False, **guards)
    if hebrew_fraction(out.text) > SCRIPT_MISMATCH_FRACTION:
        # the `טוקינג אינגליש` class: re-decode as Hebrew on the LoRA
        # vad=False for the same measured reason as the main HE path above.
        out = backend.decode(audio, model=MODEL_HE, language="he", vad=False,
                             **decode_params.decode_kwargs())
        return PolicyResult(
            text=out.text, lang="he", lang_prob=prob, model_role=MODEL_HE,
            detect_reason="script_retry", retried=True, avg_logprob=out.avg_logprob,
            no_speech_prob=out.no_speech_prob, compression_ratio=out.compression_ratio)
    return PolicyResult(
        text=out.text, lang="en", lang_prob=prob, model_role=MODEL_DETECT,
        detect_reason=reason, retried=False, avg_logprob=out.avg_logprob,
        no_speech_prob=out.no_speech_prob, compression_ratio=out.compression_ratio)
