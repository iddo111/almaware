"""Journal laws: closed vocabulary, privacy-unrepresentable fields,
required fields, atomic append — and every rule proven REACHABLE."""
from __future__ import annotations

import json
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from k2 import journal


class Vocabulary(unittest.TestCase):

    def _mk(self, td):
        return journal.Journal(td, "abcd1234")

    def test_unknown_event_raises_before_write(self):
        with TemporaryDirectory() as td:
            j = self._mk(td)
            with self.assertRaises(journal.UnknownEventError):
                j.event("MADE_UP_EVENT", x=1)
            self.assertEqual(Path(td, "events.jsonl").read_bytes(), b"")
            j.close()

    def test_device_prefix_family_is_open(self):
        with TemporaryDirectory() as td:
            j = self._mk(td)
            j.event("DEVICE_LOST", exe="x")
            with self.assertRaises(journal.UnknownEventError):
                j.event("DEVICE_")          # bare prefix is not a name
            j.close()

    def test_k2_extension_events_exist(self):
        """The K2 block (D-001) is real vocabulary, not DEVICE_* smuggling."""
        with TemporaryDirectory() as td:
            j = self._mk(td)
            j.event("RIVAL_ALIVE", via="mutex", detail="held")
            j.event("RIVAL_CLEAR", via="mutex+journal", provable=True,
                    detail="absent")
            j.event("CONFIG_STALE", key="armed_mode", revision=2,
                    takes_effect="restart")
            j.event("SCRIPT_RETRY", hint_from="he", hint_to="en")
            j.close()

    def test_a_vocabulary_inherited_verbatim(self):
        """D-001: nothing from A's closed set was dropped."""
        for evt in ("PRESENCE_REJ", "ARM_ON", "ARM_OFF", "ARM_REJ",
                    "DUP_DISCARD", "TYPE_FAIL_PARKED", "GATE_UNAVAILABLE",
                    "HEARTBEAT", "SESSION_BEGIN", "SESSION_END"):
            self.assertIn(evt, journal.EVENT_VOCABULARY)


class Privacy(unittest.TestCase):

    def test_transcript_text_is_unrepresentable(self):
        with TemporaryDirectory() as td:
            j = journal.Journal(td, "abcd1234")
            for field in ("text", "title", "transcript"):
                with self.assertRaises(journal.TelemetryFieldError):
                    j.event("TYPED", **{field: "secret words"})
            self.assertEqual(Path(td, "events.jsonl").read_bytes(), b"")
            j.close()


class RequiredFields(unittest.TestCase):

    def test_rival_alive_requires_via(self):
        """A verdict that does not name its detector is refused (D-001)."""
        with TemporaryDirectory() as td:
            j = journal.Journal(td, "abcd1234")
            with self.assertRaises(journal.TelemetryFieldError):
                j.event("RIVAL_ALIVE", detail="held")
            j.close()

    def test_script_retry_requires_both_hints(self):
        with TemporaryDirectory() as td:
            j = journal.Journal(td, "abcd1234")
            with self.assertRaises(journal.TelemetryFieldError):
                j.event("SCRIPT_RETRY", hint_from="he")
            j.close()

    def test_owner_rej_still_scored(self):
        """A's REQUIRED_FIELDS survived the inheritance."""
        with TemporaryDirectory() as td:
            j = journal.Journal(td, "abcd1234")
            with self.assertRaises(journal.TelemetryFieldError):
                j.event("OWNER_REJ", score=0.4)
            j.event("OWNER_REJ", score=0.4, theta=0.6, mode="corpus",
                    len_ms=900)
            j.close()


class Ledger(unittest.TestCase):

    def test_lines_are_json_with_ts_sid_evt(self):
        with TemporaryDirectory() as td:
            j = journal.Journal(td, "abcd1234")
            j.session_begin(mode="shadow")
            j.event("STATE", state="SHADOW_READY")
            j.session_end()
            j.close()
            lines = Path(td, "events.jsonl").read_text(
                encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 3)
            for line in lines:
                entry = json.loads(line)
                self.assertEqual(entry["sid"], "abcd1234")
                self.assertIn("T", entry["ts"])      # full ISO date, scar 20
                self.assertIn("evt", entry)

    def test_concurrent_appends_never_interleave(self):
        with TemporaryDirectory() as td:
            j = journal.Journal(td, "abcd1234")

            def spam(n):
                for _ in range(50):
                    j.event("STATE", state=f"t{n}")

            threads = [threading.Thread(target=spam, args=(i,))
                       for i in range(8)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            j.close()
            lines = Path(td, "events.jsonl").read_text(
                encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 400)
            for line in lines:
                json.loads(line)                     # every line parses

    def test_heartbeat_missing_field_is_typeerror(self):
        with TemporaryDirectory() as td:
            j = journal.Journal(td, "abcd1234")
            with self.assertRaises(TypeError):
                j.heartbeat(q=0, spool_n=0)          # deliberately partial
            j.close()

    def test_closed_journal_refuses(self):
        with TemporaryDirectory() as td:
            j = journal.Journal(td, "abcd1234")
            j.close()
            with self.assertRaises(RuntimeError):
                j.event("STATE", state="x")


if __name__ == "__main__":
    unittest.main()
