"""Phrase-repetition spirals — 2026-08-15, "mic fucked".

THE OUTAGE. Whisper spiralled and Iddo's chat received, verbatim:

    tell me the name of the name of the name of the name of the name of
    the name of the name of ...            (about seventy repetitions)

~700 characters of nothing. He answered "mic fucked".

WHY EVERY EXISTING RULE MISSED IT. The repetition guard asked whether one
TOKEN dominates 60% of the output. In a repeating PHRASE no single token
does: "the" is 70 of 211 tokens, 33%, comfortably under the bar. The
character-run and low-variety rules measure the string with spaces stripped
and were far past their length ceilings. The blocklist never saw a phrase it
knew. So five distinct words arranged into 211 tokens sailed through every
gate the repo had.

Two new shapes, because Whisper spirals in both ways:
  (a) tiny vocabulary over a long output — five distinct words in two hundred
      tokens is not a sentence, whatever the arrangement;
  (b) one n-gram repeated and covering most of the output.

The flexibility half is asserted here too: real speech repeats words all the
time ("כן כן כן", "no no no", a list, a chorus) and must survive.
"""
from __future__ import annotations

import unittest

from client.textguard import hallucination_reason


def dropped(text: str) -> bool:
    return hallucination_reason(text) != ""


THE_ACTUAL_SPIRAL = "tell me " + "the name of " * 70


class TestTheRealSpiral(unittest.TestCase):

    def test_the_verbatim_output_he_received(self):
        self.assertTrue(dropped(THE_ACTUAL_SPIRAL))

    def test_it_is_reported_as_a_loop(self):
        self.assertEqual(hallucination_reason(THE_ACTUAL_SPIRAL), "repeat_loop")

    def test_a_shorter_version_of_the_same_spiral(self):
        self.assertTrue(dropped("tell me " + "the name of " * 8))


class TestPhraseLoops(unittest.TestCase):

    def test_two_word_loop(self):
        self.assertTrue(dropped("thank you " * 12))

    def test_three_word_loop(self):
        self.assertTrue(dropped("I don't know " * 10))

    def test_hebrew_phrase_loop(self):
        self.assertTrue(dropped("אני לא יודע " * 10))

    def test_loop_with_a_real_prefix_still_caught(self):
        """A spiral that starts as a real sentence is still a spiral."""
        self.assertTrue(dropped("okay so " + "and then and then " * 15))


class TestTinyVocabulary(unittest.TestCase):

    def test_long_output_five_distinct_words(self):
        self.assertTrue(dropped(("a b c d e " * 20)))

    def test_short_output_with_few_words_is_left_alone(self):
        """Below the length floor this rule must not fire — short real
        speech is often a handful of words."""
        self.assertFalse(dropped("כן כן כן"))
        self.assertFalse(dropped("no no"))


class TestRealSpeechSurvives(unittest.TestCase):
    """People repeat themselves. A guard that eats emphasis, lists and
    choruses is worse than the spiral it prevents, because he never learns
    what he lost."""

    def test_emphasis_survives(self):
        for t in ("כן כן כן בדיוק ככה",
                  "no no no that is not what I meant at all",
                  "very very very good"):
            with self.subTest(t=t):
                self.assertFalse(dropped(t), f"{t!r} is REAL speech")

    def test_a_list_survives(self):
        self.assertFalse(dropped(
            "put darwish on eran four and the ants on eran four "
            "and the microphone on eran four as well"))

    def test_a_long_real_sentence_survives(self):
        self.assertFalse(dropped(
            "יש לנו מספיק כח חישוב להכל רק צריך לנצל נכון ואני חושב "
            "שהמסלול הנכון הוא להתחיל מוויספר עם לורה על הקול שלי "
            "ובמקביל לאמן מודל משקולות מאפס עד שהוא יהיה טוב מספיק"))

    def test_technical_dictation_survives(self):
        self.assertFalse(dropped(
            "the presence gate refused three room utterances while he was "
            "at the sea and none of them reached the chat"))

    def test_repeated_word_under_the_bar_survives(self):
        """'the' appears often in real English; frequency alone is not a
        loop."""
        self.assertFalse(dropped(
            "the mic and the printer and the fleet are all on the same "
            "network but the printer is not answering right now"))


class TestOldRulesIntact(unittest.TestCase):

    def test_single_token_spiral_still_dropped(self):
        self.assertTrue(dropped("ма ма ма ма"))

    def test_laughter_blob_still_dropped(self):
        self.assertTrue(dropped("חחחח"))

    def test_bye_still_dropped(self):
        self.assertTrue(dropped("Bye."))

    def test_i_love_you_still_survives(self):
        self.assertFalse(dropped("I love you."))


if __name__ == "__main__":
    unittest.main()
