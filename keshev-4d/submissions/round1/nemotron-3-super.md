

```python
# app/textguard.py
from __future__ import annotations

WHITELIST = ('he', 'en')
FLOOR = -0.6
HALLUCINATIONS = frozenset({
    'thank you.',
    'thanks for watching!',
    'you',
    'תודה רבה.',
    'תודה שצפיתם',
})

def verdict(text: str, avg_logprob: float | None, lang: str | None) -> tuple[bool, str]:
    from . import journal  # type: ignore[import-not-found]

    # 1. empty/whitespace
    if not text or text.isspace():
        journal.event('empty')
        return False, 'empty'

    # 2. language whitelist
    if lang not in WHITELIST:
        journal.event('lang')
        return False, 'lang'

    # 3. logprob floor
    if avg_logprob is not None and avg_logprob < FLOOR:
        journal.event('logprob')
        return False, 'logprob'

    # 4. hallucinations
    stripped = text.strip().casefold()
    if stripped in HALLUCINATIONS:
        journal.event('hallucination')
        return False, 'hallucination'

    # 5. ok
    return True, 'ok'
```

```python
# tests/test_textguard.py
import unittest
from unittest.mock import patch, call

from app.textguard import verdict


class TestTextGuard(unittest.TestCase):
    @patch('app.textguard.journal.event')
    def test_empty_text(self, mock_event):
        self.assertEqual(verdict('', None, 'en'), (False, 'empty'))
        mock_event.assert_called_once_with('empty')

    @patch('app.textguard.journal.event')
    def test_whitespace_text(self, mock_event):
        self.assertEqual(verdict('   \t\n', None, 'he'), (False, 'empty'))
        mock_event.assert_called_once_with('empty')

    @patch('app.textguard.journal.event')
    def test_lang_invalid(self, mock_event):
        self.assertEqual(verdict('hello', -0.2, 'fr'), (False, 'lang'))
        mock_event.assert_called_once_with('lang')

    @patch('app.textguard.journal.event')
    def test_lang_none(self, mock_event):
        self.assertEqual(verdict('hello', -0.2, None), (False, 'lang'))
        mock_event.assert_called_once_with('lang')

    @patch('app.textguard.journal.event')
    def test_logprob_below_floor(self, mock_event):
        self.assertEqual(verdict('hello', -0.7, 'en'), (False, 'logprob'))
        mock_event.assert_called_once_with('logprob')

    @patch('app.textguard.journal.event')
    def test_logprob_above_floor(self, mock_event):
        self.assertEqual(verdict('hello', -0.1, 'en'), (True, 'ok'))
        mock_event.assert_not_called()

    @patch('app.textguard.journal.event')
    def test_logprob_none(self, mock_event):
        self.assertEqual(verdict('hello', None, 'en'), (True, 'ok'))
        mock_event.assert_not_called()

    @patch('app.textguard.journal.event')
    def test_hallucination_english(self, mock_event):
        self.assertEqual(verdict('thank you.', -0.2, 'en'), (False, 'hallucination'))
        mock_event.assert_called_once_with('hallucination')

    @patch('app.textguard.journal.event')
    def test_hallucination_hebrew(self, mock_event):
        self.assertEqual(verdict('תודה רבה.', -0.2, 'he'), (False, 'hallucination'))
        mock_event.assert_called_once_with('hallucination')

    @patch('app.textguard.journal.event')
    def test_ok_path(self, mock_event):
        self.assertEqual(verdict('The quick brown fox', -0.3, 'en'), (True, 'ok'))
        mock_event.assert_not_called()


if __name__ == '__main__':
    unittest.main()
```