FILE: app/filter.py
```python
import re
from typing import Optional, Tuple


class TranscriptionFilter:
    # ASSUMED: Based on observed logprobs from real transcriptions.
    # Real Hebrew ranges from -0.02 to -0.5; confident English garbage on Hebrew
    # audio lands at -0.6 to -1.5. We set a conservative floor to catch garbage
    # while allowing legitimate low-confidence Hebrew through.
    CONFIDENCE_FLOOR = -1.0

    LANGUAGE_WHITELIST = {'he', 'en', 'ru'}

    NEAR_SILENCE_HALLUCINATIONS = {
        "",  # Empty string edge case
        "you",
        "thank you",
        "thanks for watching",
        "bye",
        "so",
        "subtitles by the amara.org community",
        "תודה",
        "תודה רבה",
        "תודה שצפיתם",
        "כתוביות"
    }

    @staticmethod
    def _normalize_text(text: str) -> str:
        """Normalize text for comparison: strip, lowercase, remove trailing punctuation."""
        return re.sub(r'[.,!?;:"]*$', '', text.strip().casefold())

    @staticmethod
    def _is_yawn(text: str, max_run_length: int = 5) -> bool:
        """
        Detect a yawn: a long run of the same character in a single token.
        Tokens are split by whitespace.
        """
        if not text:
            return False
        words = text.split()
        for word in words:
            if len(word) < max_run_length:
                continue
            # Check for any run of same character >= max_run_length
            for i in range(len(word) - max_run_length + 1):
                if all(c == word[i] for c in word[i:i + max_run_length]):
                    return True
        return False

    @staticmethod
    def _detect_repetition_loops(text: str, min_ngram_len: int = 3, max_ngram_len: int = 20) -> bool:
        """
        Detect repetition loops using n-gram analysis and vocabulary collapse.
        Returns True if a loop is detected.
        """
        if not text:
            return False

        # Vocabulary collapse check: too few unique words for length
        words = text.split()
        if len(words) < 10:
            return False  # Not enough words to reliably detect collapse
        unique_words = set(words)
        if len(unique_words) / len(words) < 0.2:
            return True  # Likely vocabulary collapse

        # N-gram cycling detection
        text_lower = text.lower()
        for n in range(min_ngram_len, min(max_ngram_len + 1, len(words))):
            ngrams = [tuple(words[i:i+n]) for i in range(len(words) - n + 1)]
            ngram_counts = {}
            for ng in ngrams:
                ngram_counts[ng] = ngram_counts.get(ng, 0) + 1
                if ngram_counts[ng] >= 3:  # Seen 3+ times
                    # Verify actual substring repetition in raw text
                    ngram_str = ' '.join(ng)
                    if text_lower.count(ngram_str) >= 3:
                        return True
        return False

    def filter_transcription(self, text: str, lang: Optional[str], avg_logprob: Optional[float]) \
            -> Tuple[bool, Optional[str]]:
        """
        Determine if a transcription should be allowed or rejected.

        Args:
            text: The transcription text.
            lang: Detected language (may be None).
            avg_logprob: Average log probability (may be None).

        Returns:
            Tuple of (allowed: bool, reason: Optional[str]).
            If allowed is False, reason contains a machine-readable rejection cause.
        """
        # Normalize text for comparisons
        normalized_text = self._normalize_text(text)

        # Rule: Language whitelist and None rejection
        if lang is None:
            return False, "LANGUAGE_NONE"
        if lang not in self.LANGUAGE_WHITELIST:
            return False, f"LANGUAGE_NOT_WHITELISTED_{lang}"

        # Rule: Confidence floor
        if avg_logprob is not None and avg_logprob < self.CONFIDENCE_FLOOR:
            return False, f"CONFIDENCE_BELOW_FLOOR_{avg_logprob:.3f}"

        # Rule: Near-silence hallucinations
        if normalized_text in self.NEAR_SILENCE_HALLUCINATIONS:
            return False, f"HALLUCINATION_NEAR_SILENCE_{normalized_text}"

        # Rule: Yawn detection
        if self._is_yawn(text):
            return False, "YAWN_DETECTED"

        # Rule: Repetition loops
        if self._detect_repetition_loops(text):
            return False, "REPETITION_LOOP_DETECTED"

        # Passed all filters
        return True, None

```

FILE: tests/test_filter.py
```python
import unittest
from app.filter import TranscriptionFilter


class TestTranscriptionFilter(unittest.TestCase):

    def setUp(self):
        self.filt = TranscriptionFilter()

    def test_hallucination_you(self):
        allowed, reason = self.filt.filter_transcription("you", "en", -0.5)
        self.assertFalse(allowed)
        self.assertEqual(reason, "HALLUCINATION_NEAR_SILENCE_you")

    def test_hallucination_thank_you(self):
        allowed, reason = self.filt.filter_transcription("Thank you.", "en", -0.5)
        self.assertFalse(allowed)
        self.assertEqual(reason, "HALLUCINATION_NEAR_SILENCE_thank you")

    def test_hallucination_subtitles_by_amara(self):
        text = "Subtitles by the Amara.org community"
        allowed, reason = self.filt.filter_transcription(text, "en", -0.5)
        self.assertFalse(allowed)
        self.assertEqual(reason, "HALLUCINATION_NEAR_SILENCE_subtitles by the amara.org community")

    def test_hallucination_hebrew_toda(self):
        allowed, reason = self.filt.filter_transcription("תודה", "he", -0.3)
        self.assertFalse(allowed)
        self.assertEqual(reason, "HALLUCINATION_NEAR_SILENCE_תודה")

    def test_hallucination_hebrew_toda_raba(self):
        allowed, reason = self.filt.filter_transcription("תודה רבה", "he", -0.3)
        self.assertFalse(allowed)
        self.assertEqual(reason, "HALLUCINATION_NEAR_SILENCE_תודה רבה")

    def test_hallucination_hebrew_ktuviot(self):
        allowed, reason = self.filt.filter_transcription("כתוביות", "he", -0.3)
        self.assertFalse(allowed)
        self.assertEqual(reason, "HALLUCINATION_NEAR_SILENCE_כתוביות")

    def test_yawn_detected_long_aaaaa(self):
        text = " ".join(["word"] * 10 + ["אההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההההه"])
        allowed, reason = self.filt.filter_transcription(text, "he", -0.3)
        self.assertFalse(allowed)
        self.assertEqual(reason, "YAWN_DETECTED")

    def test_no_false_positive_on_short_runs(self):
        text = "This is a test with a short run like aaa but not too long."
        allowed, reason = self.filt.filter_transcription(text, "en", -0.5)
        self.assertTrue(allowed)
        self.assertIsNone(reason)

    def test_repetition_loop_vocabulary_collapse(self):
        text = " ".join(["this is the one who is"] * 20)
        allowed, reason = self.filt.filter_transcription(text, "en", -0.5)
        self.assertFalse(allowed)
        self.assertEqual(reason, "REPETITION_LOOP_DETECTED")

    def test_repetition_loop_exact_ngram(self):
        phrase = "the quick brown fox jumps over the lazy dog"
        text = " ".join([phrase] * 5)
        allowed, reason = self.filt.filter_transcription(text, "en", -0.5)
        self.assertFalse(allowed)
        self.assertEqual(reason, "REPETITION_LOOP_DETECTED")

    def test_language_none_rejected(self):
        allowed, reason = self.filt.filter_transcription("Some text", None, -0.5)
        self.assertFalse(allowed)
        self.assertEqual(reason, "LANGUAGE_NONE")

    def test_language_not_whitelisted_rejected(self):
        allowed, reason = self.filt.filter_transcription("Some text", "ic", -0.5)
        self.assertFalse(allowed)
        self.assertEqual(reason, "LANGUAGE_NOT_WHITELISTED_ic")

    def test_confidence_floor_fires(self):
        # This simulates real-shaped data where a very low logprob indicates garbage
        allowed, reason = self.filt.filter_transcription("Gobbledygook nonsense", "en", -1.2)
        self.assertFalse(allowed)
        self.assertIn("CONFIDENCE_BELOW_FLOOR", reason)

    def test_real_hebrew_passes_with_low_but_valid_confidence(self):
        # Real-world example: valid Hebrew with slightly negative logprob
        allowed, reason = self.filt.filter_transcription("אני מרגיש טוב", "he", -0.4)
        self.assertTrue(allowed)
        self.assertIsNone(reason)

    def test_real_english_passes(self):
        allowed, reason = self.filt.filter_transcription("This is a valid sentence.", "en", -0.3)
        self.assertTrue(allowed)
        self.assertIsNone(reason)

    def test_empty_text_handled(self):
        allowed, reason = self.filt.filter_transcription("", "en", -0.5)
        self.assertFalse(allowed)
        self.assertEqual(reason, "HALLUCINATION_NEAR_SILENCE_")

    def test_case_and_punctuation_insensitive_hallucination_match(self):
        allowed, reason = self.filt.filter_transcription("  THANK YOU!  ", "en", -0.5)
        self.assertFalse(allowed)
        self.assertEqual(reason, "HALLUCINATION_NEAR_SILENCE_thank you")


if __name__ == '__main__':
    unittest.main()
```