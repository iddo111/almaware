"""Bare sign-offs, pleasantry-padding and phrase DOMINANCE — 2026-08-15.

Three holes closed, all found in Iddo's live journal and recovered.txt that
morning while he was sitting at the machine talking to me:

  1. "Bye." was TYPED into his chat twice while he was still there (journal:
     TYPED len=4, 13:58:23). I believed it and began saying goodbye; he had to
     tell me "there is a 'bye' typo — hallucination i think". "bye bye" was
     already blocklisted; the BARE token never was — the identical oversight
     to "thank you" vs "you".

  2. "Oh, thank you so much." reached the transcript. "thank you" was already
     blocklisted, but the containment branch only fires when
     len(norm) <= len(phrase) + 4, and politeness padding is cheap in
     characters. Fixed by stripping content-free filler and re-testing.

  3. "Well, I'll see you next time." reached the transcript the same way.
     Fixed by requiring the phrase to DOMINATE the utterance (>= half of it).

A FOURTH fix is asserted here too: the laughter-blob test was case-sensitive,
so "Mmm." survived as M-m-m while "mmm" was caught — and Whisper capitalises
the first letter of every hallucination it emits.

WHAT WAS TRIED AND REJECTED, deliberately recorded so nobody re-tries it:
substring-anywhere matching for a hand-picked list of "specific" phrases. The
repo's own test killed it — test_sentence_that_merely_mentions_a_blocklist_
phrase_passes, with "please subscribe him to the mailing list tomorrow
morning". That test encodes scar 28 (match the FULL text, never
substring-anywhere) and it is right: no hand-picked list is safe, because a
real sentence can always contain the phrase. Dominance is the honest rule.

The flexibility half matters as much as the blocking half — Iddo's order was
"תשנה את החוקים שהכל יעבוד - שמור על גמישות". TestFlexibility below is the
class that must never regress: losing his real words is worse than receiving
a hallucination, because he does not know what he lost.
"""
from __future__ import annotations

import unittest

from client.textguard import hallucination_reason


def dropped(text: str) -> bool:
    return hallucination_reason(text) != ""


class TestBareSignOffs(unittest.TestCase):
    """Hole 1 — the one that cost a real conversation."""

    def test_bye_is_dropped(self):
        self.assertTrue(dropped("Bye."))

    def test_bye_variants(self):
        for t in ("Bye", "bye.", "BYE!", "Goodbye.", "goodbye", "Bye bye."):
            with self.subTest(t=t):
                self.assertTrue(dropped(t), f"{t!r} should be dropped")

    def test_voila(self):
        for t in ("Voila.", "voilà"):
            with self.subTest(t=t):
                self.assertTrue(dropped(t))


class TestPleasantryPadding(unittest.TestCase):
    """Hole 2 — a blocklisted phrase wearing nothing but filler."""

    def test_thank_you_so_much(self):
        self.assertTrue(dropped("Oh, thank you so much."))

    def test_padding_variants(self):
        for t in ("Oh, thank you.", "Well, thank you very much.",
                  "yeah, thank you so much really"):
            with self.subTest(t=t):
                self.assertTrue(dropped(t))

    def test_padding_never_invents_a_drop(self):
        """Stripping filler must not turn real speech into a blocklist hit."""
        for t in ("so you should really check the ants now",
                  "well then, the transcription is just wrong"):
            with self.subTest(t=t):
                self.assertFalse(dropped(t))


class TestDominance(unittest.TestCase):
    """Hole 3 — the phrase must be at least half the utterance."""

    def test_see_you_next_time_wrapped(self):
        # 17 of 29 chars = 0.59 -> dominates
        self.assertTrue(dropped("Well, I'll see you next time."))

    def test_hebrew_wrapped_credits(self):
        for t in ("אל תשכחו להירשם לערוץ שלנו", "עריכת כתוביות: אבי כהן"):
            with self.subTest(t=t):
                self.assertTrue(dropped(t))

    def test_a_phrase_that_does_not_dominate_is_left_alone(self):
        """THE scar-28 case, verbatim from the repo's own suite. A real
        sentence that merely mentions a blocklist phrase must pass."""
        self.assertFalse(
            dropped("please subscribe him to the mailing list tomorrow morning"))


class TestCasefold(unittest.TestCase):
    """Hole 4 — Whisper capitalises what it invents."""

    def test_capitalised_blob(self):
        # One character repeated — the blob rule's actual shape. "Ohhh" is
        # deliberately absent: it is o+hhh, not a single repeated char, so it
        # is not a blob and this rule was never meant to catch it.
        for t in ("Mmm.", "Hmm.", "Aaaa"):
            with self.subTest(t=t):
                self.assertTrue(dropped(t), f"{t!r} should be dropped")

    def test_lowercase_still_dropped(self):
        self.assertTrue(dropped("mmm"))


class TestFlexibilityHisRealSpeechSurvives(unittest.TestCase):
    """THE half that must never regress. Every string here is the kind of
    thing Iddo actually dictates — several are verbatim from 2026-08-15."""

    def test_sentences_containing_generic_blocklist_words(self):
        for t in ("thank you for fixing the microphone",
                  "I want to thank you and then move on",
                  "you should put Darwish on eran4",
                  "the ants are not talking",
                  "did you see the report"):
            with self.subTest(t=t):
                self.assertFalse(dropped(t), f"{t!r} is REAL speech")

    def test_hebrew_real_speech_verbatim_from_that_day(self):
        for t in ("תודה לך על העזרה עם המיקרופון",
                  "שים את דרוויש על ערן ארבע",
                  "יש לנו מספיק כח חישוב להכל רק צריך לנצל נכון",
                  "אני אלך לים בסביבות חמש כשיותר קריר",
                  "בהצלחה עם הבנייה של קשב"):
            with self.subTest(t=t):
                self.assertFalse(dropped(t), f"{t!r} is REAL speech")

    def test_words_he_says_about_this_very_system(self):
        """He talks about transcription, subtitles and channels constantly —
        those words are his WORK, not credit junk."""
        for t in ("the transcription is wrong again",
                  "check the subtitles on the movie",
                  "open the channel to eran two"):
            with self.subTest(t=t):
                self.assertFalse(dropped(t), f"{t!r} is REAL speech")

    def test_aba_ima_still_pass(self):
        for t in ("אבא", "אמא", "אמא שלי"):
            with self.subTest(t=t):
                self.assertFalse(dropped(t))

    def test_i_love_you_survives(self):
        """13:47:29 — the first sentence he ever spoke through the rebuilt
        mic. It contains 'you'. If a rule ever eats this, the rule is wrong."""
        self.assertFalse(dropped("I love you."))

    def test_yeah_survives(self):
        """He really does say this. Blocking it would be the cheap fix and
        the wrong one — losing his words is the worse failure."""
        self.assertFalse(dropped("Yeah."))


class TestNoRegressionOnOldRules(unittest.TestCase):

    def test_bare_you_still_dropped(self):
        self.assertTrue(dropped("you"))

    def test_laughter_blob_still_dropped(self):
        self.assertTrue(dropped("חחחח"))

    def test_repeat_loop_still_dropped(self):
        self.assertTrue(dropped("ма ма ма ма"))

    def test_empty_is_not_a_hallucination(self):
        self.assertEqual(hallucination_reason(""), "")


class TestKnownResidualGap(unittest.TestCase):
    """Honest ledger of what still gets through, so it is a FACT in the repo
    rather than a surprise later (ALMA standard: proof, honest).

    A credit phrase buried in a long hallucination does NOT dominate and is
    NOT dropped here. Foreign-language credit junk is caught one layer up by
    langpolicy's whitelist, not by this guard. Tightening either would break
    the scar-28 property above, so the cost is accepted deliberately."""

    def test_long_wrapped_junk_still_passes_this_layer(self):
        self.assertFalse(dropped("thanks for watching everyone see you soon"),
                         "documents a KNOWN gap — not an endorsement")


if __name__ == "__main__":
    unittest.main()
