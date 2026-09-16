"""Correctness tests for the sequence-level knowledge probes."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import sequence_probes as sp


def reference_edit(a, b) -> int:
    """Textbook Levenshtein, used only to check the vectorised version."""
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            current.append(min(previous[j - 1] + (ca != cb),
                               previous[j] + 1, current[j - 1] + 1))
        previous = current
    return previous[-1]


def reference_substring(query, text) -> int:
    """Minimum edit distance from `query` to any contiguous window of `text`."""
    return min(
        (reference_edit(query, text[i:j])
         for i in range(len(text) + 1) for j in range(i, len(text) + 1)),
        default=len(query),
    )


class BatchedEditDistance(unittest.TestCase):
    def test_matches_reference_on_random_sequences(self):
        rng = np.random.default_rng(11)
        for trial in range(40):
            query = rng.integers(0, 5, rng.integers(1, 12))
            bank_sequences = [rng.integers(0, 5, rng.integers(1, 14)) for _ in range(7)]
            bank, lengths = sp.pack(bank_sequences)
            got = sp.edit_to_bank(query, bank, lengths)
            for i, s in enumerate(bank_sequences):
                with self.subTest(trial=trial, row=i):
                    self.assertEqual(int(got[i]), reference_edit(list(query), list(s)))

    def test_padding_cannot_change_a_shorter_row(self):
        short = np.array([1, 2, 3])
        alone, la = sp.pack([short])
        padded, lp = sp.pack([short, np.array([9] * 40)])
        query = np.array([1, 4, 3, 3])
        self.assertEqual(int(sp.edit_to_bank(query, alone, la)[0]),
                         int(sp.edit_to_bank(query, padded, lp)[0]))

    def test_identical_sequences_have_similarity_one(self):
        s = [np.array([3, 1, 4, 1, 5]), np.array([2, 7])]
        m = sp.edit_similarity_matrix(s, s)
        self.assertTrue(np.allclose(np.diag(m), 1.0))
        self.assertTrue(np.all(m <= 1.0 + 1e-12) and np.all(m >= -1e-12))

    def test_substring_matches_reference(self):
        rng = np.random.default_rng(5)
        for trial in range(25):
            query = rng.integers(0, 4, rng.integers(1, 7))
            texts = [rng.integers(0, 4, rng.integers(1, 11)) for _ in range(4)]
            bank, lengths = sp.pack(texts)
            got = sp.substring_edit_to_bank(query, bank, lengths)
            for i, t in enumerate(texts):
                with self.subTest(trial=trial, row=i):
                    self.assertEqual(int(got[i]),
                                     reference_substring(list(query), list(t)))

    def test_substring_of_a_containing_text_is_zero(self):
        text = np.array([8, 8, 1, 2, 3, 9])
        bank, lengths = sp.pack([text])
        self.assertEqual(int(sp.substring_edit_to_bank(np.array([1, 2, 3]),
                                                       bank, lengths)[0]), 0)


class Collapse(unittest.TestCase):
    def test_runs_collapse(self):
        got = sp.collapse(np.array([2, 2, 2, 5, 5, 1, 2, 2]))
        self.assertEqual(list(got), [2, 5, 1, 2])

    def test_empty_is_safe(self):
        self.assertEqual(len(sp.collapse(np.array([], dtype=np.int64))), 0)


class SpeechSpan(unittest.TestCase):
    def test_finds_the_burst_and_drops_the_pad(self):
        x = np.full((60, 14), -12.0, dtype=np.float32)
        x[20:35, 0] = -4.0
        x[:, 0] = np.where(np.arange(60) < 20, -12.0, x[:, 0])
        x[35:, 0] = -12.0
        a, b = sp.speech_span(x)
        self.assertEqual((a, b), (20, 35))

    def test_flat_input_keeps_everything(self):
        x = np.zeros((30, 14), dtype=np.float32)
        self.assertEqual(sp.speech_span(x), (0, 30))


class Separation(unittest.TestCase):
    def test_random_labels_give_zero_separation_and_half_auc(self):
        rng = np.random.default_rng(3)
        n = 90
        s = rng.random((n, n))
        s = (s + s.T) / 2
        labels = [f"c{i % 9}" for i in range(n)]
        bases = [f"x/b{i}" for i in range(n)]
        got = sp.separation(s, labels, bases)
        self.assertLess(abs(got["separation"]), 0.05)
        self.assertLess(abs(got["auc"] - 0.5), 0.06)

    def test_perfect_structure_gives_auc_one(self):
        labels = [f"c{i // 5}" for i in range(20)]
        y = np.asarray(labels)
        s = (y[:, None] == y[None, :]).astype(float)
        got = sp.separation(s, labels, [f"x/b{i}" for i in range(20)])
        self.assertEqual(got["auc"], 1.0)
        self.assertEqual(got["separation"], 1.0)


class Classification(unittest.TestCase):
    def test_chance_in_chance_out(self):
        rng = np.random.default_rng(17)
        classes = [f"c{i}" for i in range(22)]
        train = [classes[i % 22] for i in range(220)]
        test = [classes[i % 22] for i in range(110)]
        s = rng.random((110, 220))
        got = sp.nn_classify(s, train, test, classes)
        self.assertLess(got["top1"], 0.16)  # chance is 0.045
        self.assertEqual(int(got["confusion"].sum()), 110)

    def test_mean_link_ignores_a_single_hijacking_neighbour(self):
        classes = ["a", "b"]
        train = ["a", "a", "a", "b", "b", "b"]
        # one 'b' token is spuriously the single closest to the 'a' test item,
        # but 'a' as a class is closer on average
        s = np.array([[0.6, 0.6, 0.6, 0.9, 0.0, 0.0]])
        got = sp.nn_classify(s, train, ["a"], classes, top_n=2)
        self.assertEqual(got["top1"], 0.0)
        self.assertEqual(got["meanlink_top1"], 1.0)

    def test_perfect_signal_is_perfect(self):
        classes = ["a", "b", "c"]
        train, test = ["a", "b", "c"], ["c", "a", "b"]
        s = np.array([[0.0, 0.0, 1.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
        got = sp.nn_classify(s, train, test, classes)
        self.assertEqual(got["top1"], 1.0)

    def test_permutation_null_sits_at_chance(self):
        rng = np.random.default_rng(23)
        classes = [f"c{i}" for i in range(22)]
        train = [classes[i % 22] for i in range(220)]
        test = [classes[i % 22] for i in range(110)]
        s = rng.random((110, 220))
        null = sp.permutation_null(s, train, test, classes, seed=1, draws=60)
        self.assertLess(abs(null["mean"] - 1 / 22), 0.04)


class Words(unittest.TestCase):
    def test_final_letters_map_to_their_base_form(self):
        glyphs = {"ש": "sha", "ל": "la", "ו": "va", "מ": "ma"}
        self.assertEqual(sp.word_constituents("שלום", glyphs),
                         ["sha", "la", "va", "ma"])

    def test_binomial_tail_is_exact(self):
        self.assertAlmostEqual(sp.binomial_tail(12, 12), 1 / 4096)
        self.assertAlmostEqual(sp.binomial_tail(0, 5), 1.0)


if __name__ == "__main__":
    unittest.main()
