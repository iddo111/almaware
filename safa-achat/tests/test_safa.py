# -*- coding: utf-8 -*-
"""Unit tests for Safa Achat. Run:  python -m unittest discover -s tests -v"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from safa.bytetok import byte_jaccard, to_bytes
from safa.cognates import LIKELY, POSSIBLE, all_pairs, score_pair
from safa.comparative import recurring_correspondences
from safa.data import load_wordlist
from safa.distance import align, levenshtein, norm_sim
from safa.phonology import consonant_skeleton, normalize_ipa


def entry(concept, lang):
    for e in ENTRIES:
        if e.concept == concept and e.lang == lang:
            return e
    raise KeyError((concept, lang))


ENTRIES = load_wordlist()


class TestData(unittest.TestCase):
    def test_wordlist_complete(self):
        # 21 concepts x 6 languages, every row transcribed
        self.assertEqual(len(ENTRIES), 21 * 6)
        concepts = {e.concept for e in ENTRIES}
        self.assertEqual(len(concepts), 21)
        for c in concepts:
            langs = {e.lang for e in ENTRIES if e.concept == c}
            self.assertEqual(len(langs), 6, f"concept {c} missing languages")
        for e in ENTRIES:
            self.assertTrue(e.ipa, f"missing IPA for {e.concept}/{e.lang}")
            self.assertTrue(e.orthography)

    def test_scripts_survive_byte_roundtrip(self):
        heb = entry("peace", "heb").orthography
        arb = entry("peace", "arb").orthography
        self.assertEqual(to_bytes(heb).decode("utf-8"), heb)
        self.assertEqual(to_bytes(arb).decode("utf-8"), arb)


class TestPrimitives(unittest.TestCase):
    def test_levenshtein(self):
        self.assertEqual(levenshtein("kitten", "sitting"), 3)
        self.assertEqual(levenshtein("", "abc"), 3)
        self.assertEqual(levenshtein("abc", "abc"), 0)

    def test_norm_sim_bounds(self):
        self.assertEqual(norm_sim("abc", "abc"), 1.0)
        self.assertEqual(norm_sim("abc", "xyz"), 0.0)

    def test_align_length(self):
        cols = align("ktb", "ktv")
        self.assertEqual(len(cols), 3)
        self.assertEqual(cols[0], ("k", "k"))

    def test_sound_classes(self):
        # shalom and salaam share the S-R-M skeleton
        self.assertEqual(consonant_skeleton("ʃalom"), "SRM")
        self.assertEqual(consonant_skeleton("salaːm"), "SRM")
        # normalization strips length marks
        self.assertEqual(normalize_ipa("maːʔ"), "maʔ")

    def test_byte_jaccard_scriptbound(self):
        # identical Hebrew strings match; cross-script is ~0 by design
        self.assertEqual(byte_jaccard("שלום", "שלום"), 1.0)
        self.assertEqual(byte_jaccard("שלום", "salam"), 0.0)


class TestCognates(unittest.TestCase):
    def test_known_semitic_cognates_score_high(self):
        for concept in ("peace", "dog", "house", "sun", "eye"):
            p = score_pair(entry(concept, "heb"), entry(concept, "arb"))
            self.assertGreaterEqual(
                p.combined, LIKELY, f"{concept}: {p.combined:.2f}"
            )
            self.assertEqual(p.verdict, "likely cognate (within family)")

    def test_sound_law_rules_recover_cognates(self):
        # Latin pater ~ English father needs Grimm's law (f->p, dh->t)
        raw = score_pair(entry("father", "lat"), entry("father", "eng"), use_rules=False)
        ruled = score_pair(entry("father", "lat"), entry("father", "eng"), use_rules=True)
        self.assertGreater(ruled.combined, raw.combined)
        self.assertGreaterEqual(ruled.combined, LIKELY)
        # Hebrew ozen ~ Arabic udhn needs the Proto-Semitic *dh reflex (dh->z)
        ear = score_pair(entry("ear", "heb"), entry("ear", "arb"), use_rules=True)
        self.assertGreaterEqual(ear.combined, POSSIBLE)

    def test_non_cognates_score_low(self):
        # Hebrew lev vs Arabic qalb: same meaning, DIFFERENT Semitic roots
        p = score_pair(entry("heart", "heb"), entry("heart", "arb"))
        self.assertLess(p.combined, LIKELY)
        # Hebrew mayim vs English water: unrelated
        p2 = score_pair(entry("water", "heb"), entry("water", "eng"))
        self.assertLess(p2.combined, POSSIBLE)

    def test_cross_family_lookalikes_never_claimed_as_cognate(self):
        # THE honesty invariant: no cross-family pair may receive the
        # "likely cognate" verdict, no matter how similar it looks.
        for p in all_pairs(ENTRIES):
            if not p.same_family:
                self.assertNotIn("likely cognate", p.verdict, str(p))

    def test_family_separation(self):
        scores = all_pairs(ENTRIES)
        same = [p.combined for p in scores if p.same_family]
        cross = [p.combined for p in scores if not p.same_family]
        self.assertGreater(
            sum(same) / len(same), sum(cross) / len(cross) + 0.15,
            "same-family pairs must clearly outscore cross-family pairs",
        )


class TestComparative(unittest.TestCase):
    def test_recurring_hebrew_arabic_identity_correspondences(self):
        rec = recurring_correspondences(ENTRIES, "heb", "arb", min_count=2)
        self.assertIn(("m", "m"), rec)  # m : m recurs (water, name, mother...)
        self.assertIn(("l", "l"), rec)

    def test_sparse_cross_family_correspondences(self):
        heb_arb = recurring_correspondences(ENTRIES, "heb", "arb", min_count=3)
        heb_eng = recurring_correspondences(ENTRIES, "heb", "eng", min_count=3)
        self.assertGreater(
            len(heb_arb), len(heb_eng),
            "related languages must show more recurring correspondences",
        )


class TestDemo(unittest.TestCase):
    def test_demo_runs_and_passes_honesty_check(self):
        import demo

        self.assertEqual(demo.main(), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
