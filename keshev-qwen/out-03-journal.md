FILE: app/journal.py
```python
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path


class JournalEvent:
    """Closed vocabulary of allowed journal events."""
    BOOT = "boot"
    MICROPHONE_OPENED = "microphone_opened"
    MICROPHONE_CLOSED = "microphone_closed"
    AUDIO_CAPTURED = "audio_captured"
    AUDIO_SAVED = "audio_saved"
    TRANSCRIPTION_REQUEST_SENT = "transcription_request_sent"
    TRANSCRIPTION_RESPONSE_RECEIVED = "transcription_response_received"
    TRANSCRIPTION_ERROR = "transcription_error"
    TEXT_TYPED = "text_typed"
    TEXT_REJECTED = "text_rejected"
    ROTATION_STARTED = "rotation_started"
    ROTATION_COMPLETED = "rotation_completed"


# Validate that all event names are known
_ALLOWED_EVENTS = {getattr(JournalEvent, attr) for attr in dir(JournalEvent) if not attr.startswith('_')}


class JournalWriter:
    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.Lock()

    def write(self, event: str, **kwargs):
        if event not in _ALLOWED_EVENTS:
            raise ValueError(f"Unknown journal event: {event}")

        timestamp = datetime.now(timezone.utc).astimezone().isoformat(timespec='milliseconds')

        entry = {
            "timestamp": timestamp,
            "event": event,
            **kwargs
        }

        line = json.dumps(entry, ensure_ascii=False)

        with self.lock:
            with open(self.path, 'a', encoding='utf-8') as f:
                f.write(line + '\n')


class JournalReader:
    def __init__(self, path: Path):
        self.path = path

    def read_events(self):
        if not self.path.exists():
            return

        with open(self.path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    # Skip torn lines
                    continue

```

FILE: tests/test_journal.py
```python
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

from app.journal import JournalWriter, JournalReader, JournalEvent


class TestJournal(unittest.TestCase):

    def test_unknown_event_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            journal_path = Path(tmpdir) / "journal.jsonl"
            writer = JournalWriter(journal_path)
            with self.assertRaises(ValueError) as cm:
                writer.write("unknown_event", data="test")
            self.assertIn("Unknown journal event: unknown_event", str(cm.exception))

    def test_valid_event_does_not_raise(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            journal_path = Path(tmpdir) / "journal.jsonl"
            writer = JournalWriter(journal_path)
            # Should not raise
            writer.write(JournalEvent.BOOT, version="1.0")

    def test_thread_safety(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            journal_path = Path(tmpdir) / "journal.jsonl"
            writer = JournalWriter(journal_path)

            def write_entry(i):
                writer.write(JournalEvent.AUDIO_CAPTURED, index=i)

            threads = []
            for i in range(100):
                t = threading.Thread(target=write_entry, args=(i,))
                threads.append(t)
                t.start()

            for t in threads:
                t.join()

            reader = JournalReader(journal_path)
            events = list(reader.read_events())
            self.assertEqual(len(events), 100)

    def test_torn_line_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            journal_path = Path(tmpdir) / "journal.jsonl"

            # Manually create a torn line
            with open(journal_path, 'w', encoding='utf-8') as f:
                f.write('{"timestamp": "2023-01-01T10:00:00.000+03:00", "event": "boot"}\n')
                f.write('{"timestamp": "2023-01-01T10:00:01.000+03:00", "event": "audio_captured", "size": 1024')
                # Missing closing brace and newline

            reader = JournalReader(journal_path)
            events = list(reader.read_events())
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["event"], "boot")

    def test_timestamp_format(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            journal_path = Path(tmpdir) / "journal.jsonl"
            writer = JournalWriter(journal_path)
            writer.write(JournalEvent.MICROPHONE_OPENED, device="USB Mic")

            reader = JournalReader(journal_path)
            events = list(reader.read_events())
            self.assertEqual(len(events), 1)
            event = events[0]
            self.assertIn("timestamp", event)
            # Basic check for ISO format with timezone
            self.assertRegex(event["timestamp"], r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}[+-]\d{2}:\d{2}")

    def test_all_required_events_are_defined(self):
        required_events = {
            "boot",
            "microphone_opened",
            "microphone_closed",
            "audio_captured",
            "audio_saved",
            "transcription_request_sent",
            "transcription_response_received",
            "transcription_error",
            "text_typed",
            "text_rejected",
            "rotation_started",
            "rotation_completed"
        }
        defined_events = {getattr(JournalEvent, attr) for attr in dir(JournalEvent) if not attr.startswith('_')}
        self.assertEqual(defined_events, required_events)


if __name__ == '__main__':
    unittest.main()

```