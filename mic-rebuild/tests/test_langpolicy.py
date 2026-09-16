"""K10 acceptance tests for common/langpolicy.py — written FIRST (TDD).

PHASE2-DESIGN.md section 3.1 (server-side decode policy) + scars 27/29/30
(PHASE1-INQUIRY.md). The module is the ONE source of routing truth shared
by the worker AND the server, so it is backend-agnostic: every test drives
it through a recording fake backend — no model, no network, no device.

The known failing clip CLASSES (design K10 row, scar 29 'all measured on
real failing clips'), AS AMENDED by the two measured 2026-08-14 changes that
went live on eran1 (commit e3ea475 pulled the live file back; these tests
caught up 2026-08-17):

  * low-confidence detection -> WHITELIST ARGMAX, not blind Hebrew.
    Measured on 47 real utterances: median detection confidence 0.454, so
    74% of everything Iddo said landed in the low-confidence branch, and
    language="he" FORCED on English audio makes Whisper TRANSLATE — fluent
    Hebrew he never spoke, invisible to him. A wrong argmax is visibly
    wrong in the wrong script; he sees it and fixes it. The `ווי פאי`
    protection moved up to the router (lang_hint / dual-decode), not here.
  * inner VAD is OFF on every decode path. Measured: Silero inside the HE
    decode returned EMPTY for 3 of 8 real-speech segments (37%) — "the mic
    ate my word". Silence defense lives on the CLIENT (gate_rms, blip
    guard, webrtcvad, logprob floor), in front of this module.
  * `flying corals` class — real English: detector says en at high
    confidence -> stock model, comes out Latin script
  * `טוקינג אינגליש` class — en decode whose output is majority-Hebrew
    script -> script-mismatch re-decode as Hebrew on the LoRA
  * detection failure / off-whitelist-only detection (the Icelandic
    incident) — language=None is UNREPRESENTABLE: the backend receives a
    whitelist language on every call, always

Scar 29: the LoRA is NEVER the detector. Scar 30: the banned
context-feedback kwarg never reaches a backend call (lint G2 bans the token
repo-wide; the test asserts at the call boundary too).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from common import decode_params, langpolicy  # noqa: E402

BANNED_KWARG = "initial" + "_prompt"  # assembled so lint G2 never fires here


class FakeBackend:
    """Records every call; returns scripted results.

    detect_language is the STOCK model's detector (scar 29 — langpolicy has
    no way to ask the LoRA for language, and the test asserts none appears).
    """

    def __init__(self, detect=None, detect_raises=None, decode_texts=None):
        self._detect = detect if detect is not None else [("he", 0.97)]
        self._detect_raises = detect_raises
        # map (model, language) -> text to return
        self._texts = decode_texts or {}
        self.detect_calls = []
        self.decode_calls = []

    def detect_language(self, audio):
        self.detect_calls.append(audio)
        if self._detect_raises is not None:
            raise self._detect_raises
        return self._detect

    def decode(self, audio, *, model, language, vad, **kw):
        self.decode_calls.append(
            {"model": model, "language": language, "vad": vad, "kwargs": kw})
        text = self._texts.get((model, language), "טקסט לדוגמה" if language == "he" else "sample text")
        return langpolicy.DecodeOutcome(
            text=text, avg_logprob=-0.3, no_speech_prob=0.02,
            compression_ratio=1.4)


AUDIO = object()  # langpolicy must treat audio as opaque


class TestHebrewFraction(unittest.TestCase):
    def test_pure_hebrew(self):
        self.assertEqual(langpolicy.hebrew_fraction("שלום עולם"), 1.0)

    def test_pure_latin(self):
        self.assertEqual(langpolicy.hebrew_fraction("flying corals"), 0.0)

    def test_mixed(self):
        f = langpolicy.hebrew_fraction("שלום world")
        self.assertGreater(f, 0.3)
        self.assertLess(f, 0.7)

    def test_empty_and_punct_only(self):
        self.assertEqual(langpolicy.hebrew_fraction(""), 0.0)
        self.assertEqual(langpolicy.hebrew_fraction("... 123 !"), 0.0)


class TestRouting(unittest.TestCase):
    def test_confident_hebrew_goes_to_lora_without_inner_vad(self):
        be = FakeBackend(detect=[("he", 0.97)])
        res = langpolicy.transcribe(AUDIO, be)
        self.assertEqual(res.lang, "he")
        self.assertEqual(len(be.decode_calls), 1)
        call = be.decode_calls[0]
        self.assertEqual(call["model"], langpolicy.MODEL_HE)      # the LoRA
        self.assertEqual(call["language"], "he")
        # vad=False since 2026-08-14, MEASURED: the inner Silero VAD returned
        # EMPTY for 37% of real speech (c36702e2-000540/543/743 — "the mic
        # ate my word"). Flipping this back True must fail here first.
        self.assertFalse(call["vad"])
        self.assertEqual(res.lang_prob, 0.97)

    def test_confident_english_goes_to_stock_without_inner_vad(self):
        # the `flying corals` class
        be = FakeBackend(detect=[("en", 0.95)],
                         decode_texts={(langpolicy.MODEL_DETECT, "en"): "flying corals"})
        res = langpolicy.transcribe(AUDIO, be)
        self.assertEqual(res.lang, "en")
        self.assertEqual(res.text, "flying corals")
        call = be.decode_calls[0]
        self.assertEqual(call["model"], langpolicy.MODEL_DETECT)  # stock decodes EN
        self.assertFalse(call["vad"])                             # NO inner VAD on EN
        self.assertFalse(res.retried)
        # Latin script preserved — no Hebrew chars
        self.assertEqual(langpolicy.hebrew_fraction(res.text), 0.0)

    def test_low_confidence_uses_the_whitelist_argmax(self):
        # AMENDED 2026-08-14 (measured, see module docstring): below 0.85 the
        # policy now follows the whitelist ARGMAX instead of forcing Hebrew.
        # Forced he on English audio made Whisper TRANSLATE — Iddo said "so
        # eventually" and KESHEV typed "כלומר, מה שקורה זה..." — fluent,
        # confident, never spoken. Visibly wrong beats invisibly wrong.
        be = FakeBackend(detect=[("en", 0.55), ("he", 0.45)])
        res = langpolicy.transcribe(AUDIO, be)
        self.assertEqual(res.lang, "en")
        self.assertEqual(res.detect_reason, "low_conf_argmax")
        self.assertEqual(be.decode_calls[0]["model"], langpolicy.MODEL_DETECT)

    def test_low_confidence_hebrew_still_hebrew(self):
        be = FakeBackend(detect=[("he", 0.6), ("en", 0.4)])
        res = langpolicy.transcribe(AUDIO, be)
        self.assertEqual(res.lang, "he")

    def test_detection_failure_falls_back_to_hebrew_never_none(self):
        # the Icelandic incident — `language=None` must be unrepresentable
        be = FakeBackend(detect_raises=RuntimeError("detector exploded"))
        res = langpolicy.transcribe(AUDIO, be)
        self.assertEqual(res.lang, "he")
        self.assertEqual(res.detect_reason, "detect_failed")
        for call in be.decode_calls:
            self.assertIn(call["language"], langpolicy.WHITELIST)

    def test_empty_detection_falls_back_to_hebrew(self):
        be = FakeBackend(detect=[])
        res = langpolicy.transcribe(AUDIO, be)
        self.assertEqual(res.lang, "he")

    def test_off_whitelist_winner_filtered_inside_whitelist(self):
        # detector's top pick is off-whitelist -> choose within {he,en} only.
        # AMENDED 2026-08-14: the whitelist ARGMAX wins (en 0.06 > he 0.04),
        # weak evidence but evidence — never the off-whitelist ru, never None.
        be = FakeBackend(detect=[("ru", 0.90), ("en", 0.06), ("he", 0.04)])
        res = langpolicy.transcribe(AUDIO, be)
        self.assertIn(res.lang, langpolicy.WHITELIST)
        self.assertEqual(res.lang, "en")
        self.assertEqual(res.detect_reason, "low_conf_argmax")
        for call in be.decode_calls:
            self.assertIn(call["language"], langpolicy.WHITELIST)

    def test_script_mismatch_retry(self):
        # the `טוקינג אינגליש` class: a confident-en decode that comes out
        # majority-Hebrew script re-decodes as Hebrew on the LoRA
        be = FakeBackend(
            detect=[("en", 0.99)],
            decode_texts={(langpolicy.MODEL_DETECT, "en"): "טוקינג אינגליש",
                          (langpolicy.MODEL_HE, "he"): "טוקינג אינגליש נכון"})
        res = langpolicy.transcribe(AUDIO, be)
        self.assertTrue(res.retried)
        self.assertEqual(res.lang, "he")
        self.assertEqual(res.text, "טוקינג אינגליש נכון")
        self.assertEqual(len(be.decode_calls), 2)
        self.assertEqual(be.decode_calls[0]["model"], langpolicy.MODEL_DETECT)
        self.assertEqual(be.decode_calls[1]["model"], langpolicy.MODEL_HE)
        # vad=False on the retry too (2026-08-14 measurement, module docstring)
        self.assertFalse(be.decode_calls[1]["vad"])

    def test_latin_english_does_not_retry(self):
        be = FakeBackend(detect=[("en", 0.99)],
                         decode_texts={(langpolicy.MODEL_DETECT, "en"): "hello there"})
        res = langpolicy.transcribe(AUDIO, be)
        self.assertFalse(res.retried)
        self.assertEqual(len(be.decode_calls), 1)


class TestHints(unittest.TestCase):
    def test_he_hint_bypasses_detection(self):
        be = FakeBackend()
        res = langpolicy.transcribe(AUDIO, be, lang_hint="he")
        self.assertEqual(be.detect_calls, [])
        self.assertEqual(res.lang, "he")
        self.assertEqual(res.detect_reason, "hint")

    def test_en_hint_bypasses_detection_but_keeps_script_guard(self):
        be = FakeBackend(decode_texts={(langpolicy.MODEL_DETECT, "en"): "אני מדבר עברית",
                                       (langpolicy.MODEL_HE, "he"): "אני מדבר עברית"})
        res = langpolicy.transcribe(AUDIO, be, lang_hint="en")
        self.assertEqual(be.detect_calls, [])
        self.assertTrue(res.retried)          # script mismatch still protects
        self.assertEqual(res.lang, "he")

    def test_bad_hint_rejected(self):
        be = FakeBackend()
        with self.assertRaises(ValueError):
            langpolicy.transcribe(AUDIO, be, lang_hint="ru")


class TestScar29And30(unittest.TestCase):
    def test_lora_never_detects(self):
        """Scar 29: detection happens via detect_language (the stock model's
        detector) — there is no code path that decodes on the LoRA to decide
        language. Proven across every scenario in this file's matrix."""
        scenarios = [
            FakeBackend(detect=[("he", 0.97)]),
            FakeBackend(detect=[("en", 0.95)]),
            FakeBackend(detect=[]),
            FakeBackend(detect_raises=ValueError("x")),
        ]
        for be in scenarios:
            langpolicy.transcribe(AUDIO, be)
            for call in be.decode_calls:
                # every decode call carries an explicit whitelist language:
                # no decode is ever used to DISCOVER language
                self.assertIn(call["language"], langpolicy.WHITELIST)

    def test_decode_guards_applied_on_every_call(self):
        be = FakeBackend(detect=[("en", 0.99)],
                         decode_texts={(langpolicy.MODEL_DETECT, "en"): "טוקינג",
                                       (langpolicy.MODEL_HE, "he"): "טוקינג"})
        langpolicy.transcribe(AUDIO, be)
        self.assertEqual(len(be.decode_calls), 2)  # retry path: both calls guarded
        for call in be.decode_calls:
            kw = call["kwargs"]
            self.assertEqual(kw["temperature"], decode_params.TEMPERATURE)
            self.assertEqual(kw["beam_size"], decode_params.BEAM_SIZE)
            self.assertFalse(kw["condition_on_previous_text"])
            self.assertEqual(kw["compression_ratio_threshold"],
                             decode_params.COMPRESSION_RATIO_THRESHOLD)
            self.assertEqual(kw["no_speech_threshold"],
                             decode_params.NO_SPEECH_THRESHOLD)

    def test_banned_context_kwarg_never_reaches_backend(self):
        be = FakeBackend()
        langpolicy.transcribe(AUDIO, be)
        for call in be.decode_calls:
            self.assertNotIn(BANNED_KWARG, call["kwargs"])


class TestDecodeParams(unittest.TestCase):
    """Section 2: common/decode_params.py — temp[0,0.2], beam 1,
    cond_prev=False, compression 2.4, no_speech 0.6."""

    def test_design_constants(self):
        self.assertEqual(decode_params.TEMPERATURE, (0.0, 0.2))
        self.assertEqual(decode_params.BEAM_SIZE, 1)
        self.assertFalse(decode_params.CONDITION_ON_PREVIOUS_TEXT)
        self.assertEqual(decode_params.COMPRESSION_RATIO_THRESHOLD, 2.4)
        self.assertEqual(decode_params.NO_SPEECH_THRESHOLD, 0.6)

    def test_kwargs_dict_matches_constants(self):
        kw = decode_params.decode_kwargs()
        self.assertEqual(kw["temperature"], (0.0, 0.2))
        self.assertEqual(kw["beam_size"], 1)
        self.assertFalse(kw["condition_on_previous_text"])
        self.assertEqual(kw["compression_ratio_threshold"], 2.4)
        self.assertEqual(kw["no_speech_threshold"], 0.6)
        self.assertNotIn(BANNED_KWARG, kw)
        # a fresh dict each call — callers can't mutate the shared truth
        self.assertIsNot(decode_params.decode_kwargs(), kw)


if __name__ == "__main__":
    unittest.main(verbosity=2)
