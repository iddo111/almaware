"""Core module tests — journal, lawbook, spool.

Every guard gets a reachability test (it CAN fire on realistic input) and a
wiring test (the public path actually consults it). INSIGHTS §2 law: present,
correct, not-in-the-path is a build failure.
"""
from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.journal import Journal, JournalVocabError, VOCAB  # noqa: E402
from app.lawbook import _NEVER_MIC, ALLOWED_SUBSTRINGS, choose_device, is_forbidden  # noqa: E402
from app.spool import Spool  # noqa: E402


class Tmp(unittest.TestCase):
    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self._td.name)
        self.addCleanup(self._td.cleanup)


# ------------------------------------------------------------------ journal
class JournalTests(Tmp):
    def test_written_line_round_trips(self):
        j = Journal(self.dir / "e.jsonl")
        rec = j.event("SEG", id="x-1", ms=1200)
        line = (self.dir / "e.jsonl").read_text(encoding="utf-8").strip()
        self.assertEqual(json.loads(line)["id"], "x-1")
        self.assertEqual(rec["evt"], "SEG")

    def test_unknown_event_raises_at_the_writer(self):
        """Reachability: the vocabulary guard fires on the realistic mistake —
        a typo'd name invented at a call site."""
        j = Journal(self.dir / "e.jsonl")
        with self.assertRaises(JournalVocabError):
            j.event("SEGG", id="x-1")
        self.assertFalse((self.dir / "e.jsonl").exists(),
                         "a refused event must write NOTHING")

    def test_three_gates_three_names(self):
        """The 09:46 lesson is structural: the three presence-family verdicts
        exist as three distinct events."""
        for name in ("PRESENCE_REJ", "ARM_REJ", "FOCUS_REJ"):
            self.assertIn(name, VOCAB)

    def test_torn_last_line_skipped_by_reader(self):
        j = Journal(self.dir / "e.jsonl")
        j.event("SEG", id="ok-1")
        with open(j.path, "a", encoding="utf-8") as f:
            f.write('{"ts": "2026-08-18T06:00:00", "evt": "DEC')  # died mid-write
        tail = j.tail()
        self.assertEqual(len(tail), 1)
        self.assertEqual(tail[0]["id"], "ok-1")

    def test_rotate_renames_never_deletes(self):
        j = Journal(self.dir / "e.jsonl")
        for i in range(50):
            j.event("SEG", id=f"x-{i}", pad="y" * 100)
        self.assertTrue(j.rotate(max_bytes=1000))
        self.assertTrue((self.dir / "e.jsonl.1").exists(),
                        "rotation must PRESERVE the old journal")
        j.event("SEG", id="after")
        self.assertEqual(j.tail()[0]["id"], "after")


# ------------------------------------------------------------------ lawbook
class LawbookTests(unittest.TestCase):
    def test_law_is_source_level(self):
        self.assertIsInstance(_NEVER_MIC, tuple)
        self.assertIn("WH-1000", _NEVER_MIC)
        self.assertIn("Bluetooth", _NEVER_MIC)

    def test_brio_passes(self):
        got = choose_device(["Microphone (Logitech BRIO)"])
        self.assertEqual(got, "Microphone (Logitech BRIO)")

    def test_headset_refused_even_with_malicious_allowlist(self):
        """Wiring: the forbidden check outranks the allowed parameter — the
        exact attack INSIGHTS §1.5 forbids (config re-exposing Bluetooth)."""
        got = choose_device(
            ["Microphone (WH-1000XM4 Hands-Free AG Audio)"],
            allowed=("WH-1000",))
        self.assertIsNone(got)

    def test_no_usb_mic_is_idle_not_error(self):
        self.assertIsNone(choose_device([]))
        self.assertIsNone(choose_device(["Speakers (Realtek)"]))

    def test_is_forbidden_case_insensitive(self):
        self.assertTrue(is_forbidden("microphone (bluetooth hands-free)"))
        self.assertFalse(is_forbidden("Microphone (Logitech BRIO)"))

    def test_allowed_defaults_are_usb_only(self):
        for name in ALLOWED_SUBSTRINGS:
            self.assertFalse(is_forbidden(name))


# -------------------------------------------------------------------- spool
class _MemJournal:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def event(self, name: str, **fields: object) -> dict:
        self.events.append((name, fields))
        return {"evt": name, **fields}


class SpoolTests(Tmp):
    def setUp(self) -> None:
        super().setUp()
        self.j = _MemJournal()
        self.spool = Spool(self.dir, self.j, max_records=3)

    def test_admit_writes_files_before_returning(self):
        wav, sidecar = self.spool.admit("r-1", b"RIFFxxxx", {"ms": 900})
        self.assertTrue(wav.exists() and sidecar.exists())
        self.assertEqual(json.loads(sidecar.read_text(encoding="utf-8"))["id"], "r-1")

    def test_evict_drops_record_keeps_files(self):
        for i in range(4):  # max 3 → the oldest is evicted
            self.spool.admit(f"r-{i}", b"x", {})
        self.assertNotIn("r-0", self.spool.pending())
        self.assertTrue((self.dir / "r-0.wav").exists(),
                        "evict must NEVER delete his voice")
        names = [n for n, _ in self.j.events]
        self.assertIn("SPOOL_EVICT", names)

    def test_sweep_recovers_after_crash(self):
        self.spool.admit("r-1", b"x", {"ms": 500})
        # simulate crash: a new process, empty memory, same dir
        s2 = Spool(self.dir, self.j, max_records=10)
        recovered = s2.sweep()
        self.assertEqual(recovered, ["r-1"])
        self.assertIn("r-1", s2.pending())

    def test_sweep_is_o_new(self):
        """The 15-second-stall scar: a second sweep must not re-open sidecars
        it has already seen."""
        self.spool.admit("r-1", b"x", {})
        s2 = Spool(self.dir, self.j, max_records=10)
        s2.sweep()
        opened: list[str] = []
        orig = pathlib.Path.read_text

        def counting_read_text(self_path, *a, **k):
            if self_path.suffix == ".json":
                opened.append(self_path.name)
            return orig(self_path, *a, **k)

        pathlib.Path.read_text = counting_read_text  # type: ignore[assignment]
        try:
            again = s2.sweep()
        finally:
            pathlib.Path.read_text = orig  # type: ignore[assignment]
        self.assertEqual(again, [])
        self.assertEqual(opened, [], "second sweep re-read an already-seen sidecar")

    def test_orphan_wav_without_sidecar_ignored(self):
        (self.dir / "ghost.wav").write_bytes(b"x")
        s2 = Spool(self.dir, self.j)
        self.assertEqual(s2.sweep(), [])


if __name__ == "__main__":
    unittest.main()
