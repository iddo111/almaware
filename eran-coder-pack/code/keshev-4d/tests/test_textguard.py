# tests/test_textguard.py
import unittest
from app.textguard import verdict

class TestTextGuard(unittest.TestCase):
    # Wiring test: ensure the public API can be called
    def test_public_api_callable(self):
        result = verdict('test', -0.1, 'en')
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)

    # Reachability: empty/whitespace
    def test_empty_whitespace_branch(self):
        self.assertEqual(verdict('', None, 'en'), (False, 'empty'))
        self.assertEqual(verdict('   \t\n', None, 'he'), (False, 'empty'))
        # empty check precedes language check
        self.assertEqual(verdict('', None, 'fr'), (False, 'empty'))

    # Reachability: language not in whitelist
    def test_lang_branch(self):
        self.assertEqual(verdict('hello', None, 'fr'), (False, 'lang'))
        self.assertEqual(verdict('hello', None, None), (False, 'lang'))
        # language check precedes logprob check
        self.assertEqual(verdict('hello', -0.9, 'fr'), (False, 'lang'))

    # Reachability: logprob below floor
    def test_logprob_branch(self):
        self.assertEqual(verdict('hello', -0.7, 'en'), (False, 'logprob'))
        self.assertEqual(verdict('hello', -0.6, 'en'), (True, 'ok'))  # not < FLOOR
        self.assertEqual(verdict('hello', None, 'en'), (True, 'ok'))  # None passes
        # logprob check precedes hallucination check
        self.assertEqual(verdict('thank you.', -0.7, 'en'), (False, 'logprob'))

    # Reachability: hallucination
    def test_hallucination_branch(self):
        hallucinations = [
            'thank you.',
            'thanks for watching!',
            'you',
            'תודה רבה.',
            'תודה שצפיתם'
        ]
        for phrase in hallucinations:
            self.assertEqual(verdict(phrase, None, 'en'), (False, 'hallucination'))
            self.assertEqual(verdict(f'  {phrase}  ', None, 'en'), (False, 'hallucination'))
        # hallucination check precedes ok
        self.assertEqual(verdict('thank you.', -0.1, 'en'), (False, 'hallucination'))

    # Reachability: ok path
    def test_ok_branch(self):
        self.assertEqual(verdict('hello world', -0.1, 'en'), (True, 'ok'))
        self.assertEqual(verdict('שלום', -0.5, 'he'), (True, 'ok'))
        self.assertEqual(verdict('foo bar', None, 'en'), (True, 'ok'))

if __name__ == '__main__':
    unittest.main()
