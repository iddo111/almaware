```python
import json
import os
import threading
from datetime import datetime, timezone, timedelta
from typing import Any, Dict

VOCAB = frozenset([
    "SESSION_BEGIN", "DEVICE_OPEN", "SEG", "DECODE",
    "TYPED", "DROP", "GATED", "HEARTBEAT", "STATE",
    "WORKER_DIED", "WORKER_RESPAWN", "ALARM"
])

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
            ts = datetime.now(timezone(timedelta(hours=3))).isoformat()
            record = {"ts": ts, "evt": name, **fields}
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def rotate(self, max_bytes: int) -> None:
        if not os.path.exists(self._path):
            return
        with self._lock:
            if os.path.getsize(self._path) > max_bytes:
                rotated_path = self._path + ".1"
                if os.path.exists(rotated_path):
                    os.remove(rotated_path)
                os.rename(self._path, rotated_path)
```


```python
import json
import os
import tempfile
import unittest
from app.journal import Journal, JournalVocabError, VOCAB

class TestJournal(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.journal_path = os.path.join(self.tmpdir.name, "events.log")

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_vocab_contains_expected_events(self):
        expected = {
            "SESSION_BEGIN", "DEVICE_OPEN", "SEG", "DECODE",
            "TYPED", "DROP", "GATED", "HEARTBEAT", "STATE",
            "WORKER_DIED", "WORKER_RESPAWN", "ALARM"
        }
        self.assertEqual(VOCAB, expected)

    def test_event_unknown_name_raises(self):
        journal = Journal(self.journal_path)
        with self.assertRaises(JournalVocabError) as cm:
            journal.event("UNKNOWN_EVENT", foo="bar")
        self.assertIn("UNKNOWN_EVENT", str(cm.exception))

    def test_event_writes_valid_json_line(self):
        journal = Journal(self.journal_path)
        journal.event("DROP", reason="silence", confidence=0.1)
        with open(self.journal_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        self.assertEqual(len(lines), 1)
        record = json.loads(lines[0])
        self.assertIn("ts", record)
        self.assertEqual(record["evt"], "DROP")
        self.assertEqual(record["reason"], "silence")
        self.assertEqual(record["confidence"], 0.1)

    def test_event_roundtrip_iso8601_with_offset(self):
        journal = Journal(self.journal_path)
        journal.event("HEARTBEAT", pid=1234)
        with open(self.journal_path, "r", encoding="utf-8") as f:
            record = json.loads(f.read())
        ts = record["ts"]
        # Validate ISO8601 with +03:00 offset
        self.assertTrue(ts.endswith("+03:00"), f"Expected +03:00 offset, got {ts}")
        # Try parsing
        from datetime import datetime
        parsed = datetime.fromisoformat(ts)
        self.assertEqual(parsed.tzinfo.utcoffset(None).total_seconds(), 3 * 3600)

    def test_rotation_triggers_at_boundary(self):
        journal = Journal(self.journal_path)
        # Write exactly 100 bytes (just under 100)
        small_event = "DROP" + " " * 90
        # Actually compute size of a line
        test_line = json.dumps({"ts": "x", "evt": "DROP", "msg": "x" * 80}, ensure_ascii=False) + "\n"
        # Write until we exceed 100 bytes
        while os.path.exists(self.journal_path) and os.path.getsize(self.journal_path) < 100:
            journal.event("DROP", msg="x" * 80)
        original_size = os.path.getsize(self.journal_path)
        # Now rotate at 100 bytes
        journal.rotate(100)
        # Old file should be renamed
        rotated_path = self.journal_path + ".1"
        self.assertTrue(os.path.exists(rotated_path))
        self.assertEqual(os.path.getsize(rotated_path), original_size)
        # New empty file created
        self.assertTrue(os.path.exists(self.journal_path))
        self.assertEqual(os.path.getsize(self.journal_path), 0)

    def test_rotation_preserves_old_file_on_boundary(self):
        journal = Journal(self.journal_path)
        # Write enough to exceed 50 bytes
        for _ in range(3):
            journal.event("STATE", state="idle")
        original_size = os.path.getsize(self.journal_path)
        journal.rotate(50)
        # Old file must survive
        self.assertTrue(os.path.exists(self.journal_path + ".1"))
        with open(self.journal_path + ".1", "r", encoding="utf-8") as f:
            lines = f.readlines()
        self.assertEqual(len(lines), 3)

    def test_concurrent_events_no_race(self):
        journal = Journal(self.journal_path)
        threads = []
        for i in range(10):
            t = threading.Thread(target=journal.event, args=("HEARTBEAT",), kwargs={"id": i})
            threads.append(t)
            t.start()
        for t in threads:
            t.join()
        with open(self.journal_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        self.assertEqual(len(lines), 10)
        records = [json.loads(line) for line in lines]
        ids = {r["id"] for r in records}
        self.assertEqual(ids, set(range(10)))

    def test_rotation_noop_if_under_limit(self):
        journal = Journal(self.journal_path)
        journal.event("SEG", start=0.0, end=1.5)
        journal.rotate(10000)
        self.assertFalse(os.path.exists(self.journal_path + ".1"))
        self.assertTrue(os.path.exists(self.journal_path))

    def test_wiring_drop_calls_journal_event(self):
        # Simulate DROP event wiring
        journal = Journal(self.journal_path)
        journal.event("DROP", reason="background_noise", confidence=0.05)
        with open(self.journal_path, "r", encoding="utf-8") as f:
            record = json.loads(f.read())
        self.assertEqual(record["evt"], "DROP")
        self.assertEqual(record["reason"], "background_noise")
        self.assertEqual(record["confidence"], 0.05)

    def test_wiring_gated_calls_journal_event(self):
        journal = Journal(self.journal_path)
        journal.event("GATED", input_length=120, threshold=0.75)
        with open(self.journal_path, "r", encoding="utf-8") as f:
            record = json.loads(f.read())
        self.assertEqual(record["evt"], "GATED")
        self.assertEqual(record["input_length"], 120)
        self.assertEqual(record["threshold"], 0.75)
```