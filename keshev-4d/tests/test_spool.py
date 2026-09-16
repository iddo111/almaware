# tests/test_spool.py
import json
import unittest
import unittest.mock
import tempfile
from pathlib import Path

from app.spool import Spool


class TestSpool(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        # Use a small max_records to test auto‑eviction.
        self.spool = Spool(self.dir, max_records=2)

    def tearDown(self):
        self.tmp.cleanup()

    def test_admit_writes_files_before_return(self):
        rec_id = "rec1"
        wav = b"dummy wav data"
        meta = {"speaker": "alice", "duration": 3.2}
        wav_path, json_path = self.spool.admit(rec_id, wav, meta)

        self.assertTrue(wav_path.is_file())
        self.assertTrue(json_path.is_file())
        self.assertEqual(wav_path.read_bytes(), wav)
        self.assertEqual(json.loads(json_path.read_text()), meta)

    def test_evict_does_not_delete_files_and_calls_journal(self):
        rec_id = "rec2"
        wav = b"some bytes"
        meta = {}
        with unittest.mock.patch("journal.event") as mock_event:
            self.spool.admit(rec_id, wav, meta)
            evicted = self.spool.evict_oldest()
            self.assertEqual(evicted, rec_id)

            # Files must still exist.
            self.assertTrue((self.dir / f"{rec_id}.wav").exists())
            self.assertTrue((self.dir / f"{rec_id}.json").exists())

            # journal.event called exactly once with a dict containing rec_id.
            mock_event.assert_called_once()
            arg = mock_event.call_args[0][0]
            self.assertIsInstance(arg, dict)
            self.assertIn(rec_id, str(arg))

    def test_sweep_recovers_orphans_and_is_idempotent(self):
        # Simulate a crash: create files without registering them.
        orphan_ids = ["orphan1", "orphan2"]
        for rid in orphan_ids:
            (self.dir / f"{rid}.wav").write_bytes(b"x")
            (self.dir / f"{rid}.json").write_text(json.dumps({"id": rid}))

        # First sweep should discover both.
        self.spool.sweep()
        self.assertCountEqual(self.spool.pending(), orphan_ids)

        # Second sweep must not duplicate entries.
        self.spool.sweep()
        self.assertCountEqual(self.spool.pending(), orphan_ids)

    def test_auto_evict_when_exceed_max(self):
        # Fill up to the limit.
        self.spool.admit("r1", b"1", {})
        self.spool.admit("r2", b"2", {})

        # Next admit triggers auto‑eviction of the oldest (r1).
        with unittest.mock.patch("journal.event") as mock_event:
            self.spool.admit("r3", b"3", {})
            # Pending should now contain r2 and r3 in order.
            self.assertListEqual(self.spool.pending(), ["r2", "r3"])
            mock_event.assert_called_once()
            evicted_info = mock_event.call_args[0][0]
            self.assertIn("r1", str(evicted_info))

    def test_pending_order_and_complete(self):
        self.spool.admit("a", b"", {})
        self.spool.admit("b", b"", {})
        self.assertListEqual(self.spool.pending(), ["a", "b"])

        self.spool.complete("a")
        self.assertListEqual(self.spool.pending(), ["b"])


if __name__ == "__main__":
    unittest.main()
