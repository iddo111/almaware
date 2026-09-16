```python
import json
import os
import threading
from datetime import datetime, timezone
from typing import Any, Dict

VOCAB = frozenset({
    "SESSION_BEGIN",
    "DEVICE_OPEN",
    "SEG",
    "DECODE",
    "TYPED",
    "DROP",
    "GATED",
    "HEARTBEAT",
    "STATE",
    "WORKER_DIED",
    "WORKER_RESPAWN",
    "ALARM"
})

class JournalVocabError(ValueError):
    pass

class Journal:
    def __init__(self, path: str):
        self._path = path
        self._lock = threading.Lock()

    def event(self, name: str, **fields: Any) -> None:
        if name not in VOCAB:
            raise JournalVocabError(f"Unknown event name: {name}")
        with self._lock:
            ts = datetime.now(timezone.utc).isoformat()
            entry = {"ts": ts, "evt": name, **fields}
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")

    def rotate(self, max_bytes: int) -> None:
        if not os.path.exists(self._path):
            return
        with self._lock:
            if os.path.getsize(self._path) >= max_bytes:
                backup_path = self._path + ".1"
                if os.path.exists(backup_path):
                    os.remove(backup_path)
                os.rename(self._path, backup_path)
```


```python
import os
import tempfile
import unittest
import threading
from app.journal import Journal, JournalVocabError, VOCAB

class TestJournal(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.journal_path = os.path.join(self.tmpdir, "journal.log")

    def tearDown(self):
        # Clean up all files created
        for f in os.listdir(self.tmpdir):
            os.remove(os.path.join(self.tmpdir, f))
        os.rmdir(self.tmpdir)

    def test_event_valid_name(self):
        j = Journal(self.journal_path)
        j.event("SESSION_BEGIN", session_id="abc123")
        self.assertTrue(os.path.exists(self.journal_path))

    def test_event_invalid_name_raises(self):
        j = Journal(self.journal_path)
        with self.assertRaises(JournalVocabError):
            j.event("UNKNOWN_EVENT")

    def test_event_round_trip(self):
        j = Journal(self.journal_path)
        j.event("SEG", text="hello", start=0.0, end=1.5)
        with open(self.journal_path, "r", encoding="utf-8") as f:
            line = f.readline().strip()
        import json
        entry = json.loads(line)
        self.assertEqual(entry["evt"], "SEG")
        self.assertEqual(entry["text"], "hello")
        self.assertEqual(entry["start"], 0.0)
        self.assertEqual(entry["end"], 1.5)
        self.assertIn("ts", entry)

    def test_rotation_triggers_at_boundary(self):
        j = Journal(self.journal_path)
        # Write exactly 100 bytes to exceed 100-byte threshold
        j.event("HEARTBEAT", count=1)
        # Ensure file exists and has content
        self.assertTrue(os.path.exists(self.journal_path))
        size = os.path.getsize(self.journal_path)
        # Force rotation at boundary
        j.rotate(max_bytes=size)
        # After rotation, original file should be gone, .1 should exist
        self.assertFalse(os.path.exists(self.journal_path))
        self.assertTrue(os.path.exists(self.journal_path + ".1"))

    def test_rotation_no_file_no_error(self):
        j = Journal(self.journal_path)
        j.rotate(max_bytes=100)  # Should not raise even if file doesn't exist
        self.assertFalse(os.path.exists(self.journal_path))
        self.assertFalse(os.path.exists(self.journal_path + ".1"))

    def test_concurrent_events_no_race(self):
        j = Journal(self.journal_path)
        threads = []
        for i in range(10):
            t = threading.Thread(target=lambda idx=i: j.event("STATE", idx=idx))
            threads.append(t)
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        # Verify all events were written
        with open(self.journal_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        self.assertEqual(len(lines), 10)

    def test_vocab_contains_expected_values(self):
        expected = {
            "SESSION_BEGIN",
            "DEVICE_OPEN",
            "SEG",
            "DECODE",
            "TYPED",
            "DROP",
            "GATED",
            "HEARTBEAT",
            "STATE",
            "WORKER_DIED",
            "WORKER_RESPAWN",
            "ALARM"
        }
        self.assertEqual(VOCAB, expected)

    def test_drop_calls_journal_event(self):
        # Wiring test: verify DROP event can be called without error
        j = Journal(self.journal_path)
        j.event("DROP", reason="silence_detected", duration=0.5)
        self.assertTrue(os.path.exists(self.journal_path))
        with open(self.journal_path, "r", encoding="utf-8") as f:
            line = f.readline().strip()
        import json
        entry = json.loads(line)
        self.assertEqual(entry["evt"], "DROP")
        self.assertEqual(entry["reason"], "silence_detected")
        self.assertEqual(entry["duration"], 0.5)

    def test_gated_calls_journal_event(self):
        # Wiring test: verify GATED event can be called without error
        j = Journal(self.journal_path)
        j.event("GATED", trigger="noise_threshold", level=75)
        self.assertTrue(os.path.exists(self.journal_path))
        with open(self.journal_path, "r", encoding="utf-8") as f:
            line = f.readline().strip()
        import json
        entry = json.loads(line)
        self.assertEqual(entry["evt"], "GATED")
        self.assertEqual(entry["trigger"], "noise_threshold")
        self.assertEqual(entry["level"], 75)
```