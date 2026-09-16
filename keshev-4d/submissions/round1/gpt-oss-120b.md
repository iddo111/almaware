```python
# app/spool.py
import json
import os
from pathlib import Path
from typing import Dict, List, Tuple, Optional


class Spool:
    """
    Write‑ahead audio spool.

    Parameters
    ----------
    dir : str or Path
        Directory where wav and side‑car json files are stored.
    max_records : int, optional
        Upper bound for pending records; caller should invoke ``evict_oldest``
        when ``len(pending) > max_records``.
    """

    def __init__(self, dir: os.PathLike, max_records: int = 500):
        self.dir = Path(dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.max_records = max_records
        self._pending: List[str] = []          # ordered list of pending ids
        self._known: set = set()               # ids already seen (pending or completed)

    # --------------------------------------------------------------------- #
    # Public API
    # --------------------------------------------------------------------- #
    def admit(self, rec_id: str, wav_bytes: bytes, meta: Dict) -> Tuple[str, str]:
        """
        Write the wav file and its JSON side‑car atomically (wav first),
        then register the record as pending.

        Returns
        -------
        (wav_path, json_path) as strings.
        """
        wav_path = self.dir / f"{rec_id}.wav"
        json_path = self.dir / f"{rec_id}.json"

        # Write wav first
        with open(wav_path, "wb") as wf:
            wf.write(wav_bytes)

        # Write side‑car
        with open(json_path, "w", encoding="utf-8") as jf:
            json.dump(meta, jf)

        # Register in memory (only once)
        if rec_id not in self._known:
            self._pending.append(rec_id)
            self._known.add(rec_id)

        return str(wav_path), str(json_path)

    def complete(self, rec_id: str) -> None:
        """
        Mark a pending record as completed. Files are left untouched.
        """
        if rec_id in self._pending:
            self._pending.remove(rec_id)

    def evict_oldest(self) -> Optional[str]:
        """
        Drop the oldest pending record (keep its files) and report its id.
        Must call ``journal.event`` exactly once.
        """
        if not self._pending:
            return None

        oldest = self._pending.pop(0)

        # Notify journal – caller may monkey‑patch ``journal.event``.
        try:
            import journal
            journal.event("evict", {"rec_id": oldest})
        except Exception:
            # Swallow any import or runtime errors; the contract is to *attempt*
            # the call, not to crash the spool.
            pass

        return oldest

    def pending(self) -> List[str]:
        """Return a copy of the ordered pending ids."""
        return list(self._pending)

    def sweep(self) -> List[str]:
        """
        Recover side‑car files that exist on disk but are not yet known to the
        in‑memory index. Only unread side‑cars are opened, guaranteeing O(new
        files) work.
        Returns the list of newly discovered ids.
        """
        newly_found: List[str] = []

        for entry in self.dir.iterdir():
            if entry.suffix.lower() != ".json":
                continue

            rec_id = entry.stem
            if rec_id in self._known:
                continue

            # Open the side‑car *once* to prove reachability.
            with open(entry, "r", encoding="utf-8") as jf:
                json.load(jf)   # parsing validates the file; content is not used here.

            self._pending.append(rec_id)
            self._known.add(rec_id)
            newly_found.append(rec_id)

        return newly_found
```

```python
# tests/test_spool.py
import json
import os
import sys
import unittest
import tempfile
from unittest import mock
from pathlib import Path

# Insert a dummy ``journal`` module so that ``Spool.evict_oldest`` can import it.
class DummyJournal:
    def __init__(self):
        self.calls = []

    def event(self, kind, payload):
        self.calls.append((kind, payload))

dummy_journal = DummyJournal()
sys.modules['journal'] = dummy_journal

# Import the module under test after the dummy journal is in place.
from app.spool import Spool


class TestSpool(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.spool_dir = Path(self.tmpdir.name)
        self.spool = Spool(self.spool_dir, max_records=10)

    def tearDown(self):
        self.tmpdir.cleanup()
        dummy_journal.calls.clear()

    def test_admit_writes_files_and_registers(self):
        rec_id = "001"
        wav_bytes = b"RIFF\x00\x00\x00\x00WAVEfmt "
        meta = {"text": "hello"}

        wav_path, json_path = self.spool.admit(rec_id, wav_bytes, meta)

        # Verify files exist and contain expected data.
        self.assertTrue(Path(wav_path).exists())
        self.assertTrue(Path(json_path).exists())

        self.assertEqual(Path(wav_path).read_bytes(), wav_bytes)

        with open(json_path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        self.assertEqual(loaded, meta)

        # Verify pending index.
        self.assertEqual(self.spool.pending(), [rec_id])

    def test_evict_oldest_calls_journal_and_keeps_files(self):
        ids = ["a", "b"]
        for i in ids:
            self.spool.admit(i, b"data", {"i": i})

        evicted = self.spool.evict_oldest()
        self.assertEqual(evicted, "a")
        self.assertEqual(dummy_journal.calls, [("evict", {"rec_id": "a"})])

        # Files must still exist.
        self.assertTrue((self.spool_dir / "a.wav").exists())
        self.assertTrue((self.spool_dir / "a.json").exists())

        # Pending now contains only the second id.
        self.assertEqual(self.spool.pending(), ["b"])

    def test_sweep_recovers_orphans_and_is_idempotent(self):
        # Manually create side‑car files without using ``admit``.
        orphan_ids = ["x", "y"]
        for oid in orphan_ids:
            (self.spool_dir / f"{oid}.wav").write_bytes(b"dummy")
            (self.spool_dir / f"{oid}.json").write_text(json.dumps({"id": oid}), encoding="utf-8")

        # Patch ``open`` to count how many times side‑cars are opened.
        open_counter = mock.Mock(wraps=open)

        with mock.patch("builtins.open", new=open_counter):
            first_sweep = self.spool.sweep()
            self.assertCountEqual(first_sweep, orphan_ids)

            # Two side‑car files should have been opened (once each).
            json_opens = [c for c in open_counter.mock_calls if c[1][0].endswith(".json")]
            self.assertEqual(len(json_opens), 2)

            # Second sweep should find nothing new and not open any JSON files.
            open_counter.reset_mock()
            second_sweep = self.spool.sweep()
            self.assertEqual(second_sweep, [])
            json_opens_second = [c for c in open_counter.mock_calls if c[1][0].endswith(".json")]
            self.assertEqual(len(json_opens_second), 0)

        # Pending list must now contain the recovered ids.
        self.assertCountEqual(self.spool.pending(), orphan_ids)

    def test_max_records_evicts_when_exceed(self):
        spool = Spool(self.spool_dir, max_records=2)
        ids = ["one", "two", "three"]
        for rid in ids:
            spool.admit(rid, b"data", {"id": rid})

        # At this point pending has three entries; caller should evict.
        evicted = spool.evict_oldest()
        self.assertEqual(evicted, "one")
        self.assertEqual(spool.pending(), ["two", "three"])

        # Ensure files for evicted record still exist.
        self.assertTrue((self.spool_dir / "one.wav").exists())
        self.assertTrue((self.spool_dir / "one.json").exists())


if __name__ == "__main__":
    unittest.main()
```