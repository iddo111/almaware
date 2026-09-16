

```python
from . import journal

class Gate:
    def __init__(self, hang_ms, min_ms, max_ms):
        self.hang_ms = hang_ms
        self.min_ms = min_ms
        self.max_ms = max_ms
        self.gate = True
        self.timer = 0
        self.speech_started = False
        self.speech_duration = 0

    def feed(self, is_speech, chunk_ms=20):
        if not self.gate:
            return False
        if is_speech:
            self.timer = 0
            if not self.speech_started:
                self.speech_started = True
                self.speech_duration = 0
            self.speech_duration += chunk_ms
            if self.speech_duration > self.max_ms:
                self.gate = False
                journal.event('drop')
                return False
            return True
        else:
            self.timer += chunk_ms
            if self.speech_started:
                self.speech_duration += chunk_ms
            if self.timer >= self.hang_ms:
                self.gate = False
                journal.event('drop')
                return False
            return True
```

```python
import sys
import unittest
from unittest.mock import patch

# Ensure the app package is importable
sys.path.insert(0, r'D:\CLAUDE\keshev-4d')

from app.gates import Gate

class TestGate(unittest.TestCase):
    def setUp(self):
        # Typical values for testing
        self.hang_ms = 200
        self.min_ms = 100
        self.max_ms = 2000
        self.chunk_ms = 20

    def test_pass_through_speech_and_silence_within_limits(self):
        gate = Gate(self.hang_ms, self.min_ms, self.max_ms)
        with patch('app.gates.journal.event') as mock_journal:
            # Speech chunk
            self.assertTrue(gate.feed(True, self.chunk_ms))
            # Silence chunk within hang period
            self.assertTrue(gate.feed(False, self.chunk_ms))
            mock_journal.assert_not_called()

    def test_hang_timeout_triggers_drop_and_journal_once(self):
        gate = Gate(self.hang_ms, self.min_ms, self.max_ms)
        # Start speech
        gate.feed(True, self.chunk_ms)
        # Add enough silence to exceed hang_ms
        needed = self.hang_ms // self.chunk_ms + 1
        with patch('app.gates.journal.event') as mock_journal:
            for _ in range(needed):
                gate.feed(False, self.chunk_ms)
            self.assertFalse(gate.gate)  # gate closed
            mock_journal.assert_called_once_with('drop')

    def test_max_length_exceeded_triggers_drop_and_journal_once(self):
        gate = Gate(self.hang_ms, self.min_ms, self.max_ms)
        # Feed speech chunks until exceeding max_ms
        needed = self.max_ms // self.chunk_ms + 1
        with patch('app.gates.journal.event') as mock_journal:
            for i in range(needed):
                gate.feed(True, self.chunk_ms)
            self.assertFalse(gate.gate)  # gate closed
            mock_journal.assert_called_once_with('drop')

    def test_closed_gate_does_not_call_journal_on_subsequent_feeds(self):
        gate = Gate(self.hang_ms, self.min_ms, self.max_ms)
        # Force gate closed by exceeding max_ms
        needed = self.max_ms // self.chunk_ms + 1
        for _ in range(needed):
            gate.feed(True, self.chunk_ms)
        self.assertFalse(gate.gate)
        with patch('app.gates.journal.event') as mock_journal:
            # Further feeds should return False and not call journal
            self.assertFalse(gate.feed(True, self.chunk_ms))
            self.assertFalse(gate.feed(False, self.chunk_ms))
            mock_journal.assert_not_called()

    def test_public_api_wiring(self):
        gate = Gate(self.hang_ms, self.min_ms, self.max_ms)
        with patch('app.gates.journal.event') as mock_journal:
            # Call feed and ensure the method is executed
            result = gate.feed(True, self.chunk_ms)
            self.assertTrue(result)
            # Ensure journal was not called for normal operation
            mock_journal.assert_not_called()

if __name__ == '__main__':
    unittest.main()
```