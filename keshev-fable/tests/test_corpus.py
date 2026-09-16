"""corpus tests — the format contract with eran4's nightly LoRA.

The contract is NOT ours to invent: tools/corpus-push.ps1 (mic-rebuild) tars
state/corpus/ to eran4 every night at 03:00 and keshev-lora.timer trains on
it. The shape it expects is what KESHEV A's client/corpus.py wrote, pinned
here against a real pushed archive (state/corpus-sent/20260819-030350):

    <root>/<sid>/<rec_id>.wav      16 kHz mono s16le
    <root>/manifest.jsonl          one line per utterance:
    {"id","sid","ts","wav","text","ms","engine","source"}  (this exact order)

e.g. {"id": "b1fe2518-000314", "sid": "b1fe2518",
      "ts": "2026-08-18T06:10:46+0300",
      "wav": "b1fe2518/b1fe2518-000314.wav",
      "text": "...", "ms": 2640, "engine": "dgx", "source": "typed"}

Any drift here starves the trainer silently — which is the exact bug this
module exists to fix (the 2026-08-18 cutover left state/corpus/ empty).
"""
from __future__ import annotations

import json
import pathlib
import re
import shutil
import sys
import tempfile
import time
import unittest
import wave

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.corpus import Corpus  # noqa: E402


class _MemJournal:
    def __init__(self):
        self.events = []

    def event(self, name, **fields):
        self.events.append((name, fields))
        return {"evt": name, **fields}

    def names(self):
        return [n for n, _ in self.events]


PCM_2S = b"\x01\x00" * 32000          # 2 s of 16 kHz s16le
TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{4}$")


class CorpusFormatTests(unittest.TestCase):
    """The wire format — one wav + one manifest line, byte-compatible with
    what corpus-push.ps1 shipped on 2026-08-19."""

    def setUp(self):
        self.td = tempfile.mkdtemp()
        self.root = pathlib.Path(self.td) / "corpus"
        self.j = _MemJournal()
        self.c = Corpus(self.root, journal=self.j, enabled=True,
                        clock=lambda: 1755490246.0)

    def tearDown(self):
        shutil.rmtree(self.td, ignore_errors=True)

    def _one_line(self):
        lines = (self.root / "manifest.jsonl").read_text(
            encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)
        return lines[0]

    def test_wav_lands_under_sid_dir_with_rec_id_name(self):
        self.assertTrue(self.c.add("b1fe2518-000314", PCM_2S, "שלום עולם"))
        p = self.root / "b1fe2518" / "b1fe2518-000314.wav"
        self.assertTrue(p.exists())

    def test_wav_is_16k_mono_s16le_holding_exactly_the_pcm(self):
        self.c.add("b1fe2518-000314", PCM_2S, "שלום")
        with wave.open(str(self.root / "b1fe2518" / "b1fe2518-000314.wav")) as w:
            self.assertEqual(w.getnchannels(), 1)
            self.assertEqual(w.getsampwidth(), 2)
            self.assertEqual(w.getframerate(), 16000)
            self.assertEqual(w.readframes(w.getnframes()), PCM_2S)

    def test_manifest_line_matches_the_pushed_archive_shape(self):
        self.c.add("b1fe2518-000314", PCM_2S, "שלום עולם")
        rec = json.loads(self._one_line())
        self.assertEqual(list(rec.keys()),
                         ["id", "sid", "ts", "wav", "text",
                          "ms", "engine", "source"],
                         "key order pinned to the 20260819-030350 archive")
        self.assertEqual(rec["id"], "b1fe2518-000314")
        self.assertEqual(rec["sid"], "b1fe2518")
        self.assertEqual(rec["wav"], "b1fe2518/b1fe2518-000314.wav",
                         "forward slashes, relative to the corpus root")
        self.assertEqual(rec["text"], "שלום עולם")
        self.assertEqual(rec["ms"], 2000)
        self.assertEqual(rec["engine"], "dgx")
        self.assertEqual(rec["source"], "typed")
        self.assertRegex(rec["ts"], TS_RE)
        self.assertEqual(
            rec["ts"],
            time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(1755490246.0)))

    def test_hebrew_is_written_raw_not_escaped(self):
        self.c.add("b1fe2518-000314", PCM_2S, "מה קורה?")
        self.assertIn("מה קורה?", self._one_line(),
                      "ensure_ascii=False — eran4 reads the text as written")

    def test_manifest_appends_and_wavs_share_the_sid_dir(self):
        self.c.add("b1fe2518-000314", PCM_2S, "אחת")
        self.c.add("b1fe2518-000315", PCM_2S, "שתיים")
        lines = (self.root / "manifest.jsonl").read_text(
            encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 2)
        self.assertEqual(len(list((self.root / "b1fe2518").glob("*.wav"))), 2)
        self.assertEqual(self.c.written, 2)

    def test_survives_the_0300_push_moving_everything_away(self):
        """corpus-push.ps1 MOVES the sid dirs + manifest to corpus-sent at
        03:00 while the mic keeps running. The next add must rebuild."""
        self.c.add("b1fe2518-000314", PCM_2S, "לפני")
        shutil.rmtree(self.root / "b1fe2518")
        (self.root / "manifest.jsonl").unlink()
        self.assertTrue(self.c.add("b1fe2518-000315", PCM_2S, "אחרי"))
        rec = json.loads(self._one_line())
        self.assertEqual(rec["id"], "b1fe2518-000315")
        self.assertTrue(
            (self.root / "b1fe2518" / "b1fe2518-000315.wav").exists())

    def test_rec_id_without_a_dash_goes_to_unknown(self):
        self.c.add("weird", PCM_2S, "בלי מקף")
        rec = json.loads(self._one_line())
        self.assertEqual(rec["sid"], "unknown")
        self.assertEqual(rec["wav"], "unknown/weird.wav")


class CorpusRefusalTests(unittest.TestCase):
    """Every refusal returns False, journals one ALARM, and never raises —
    a corpus problem must never cost a typed sentence."""

    def setUp(self):
        self.td = tempfile.mkdtemp()
        self.root = pathlib.Path(self.td) / "corpus"
        self.j = _MemJournal()

    def tearDown(self):
        shutil.rmtree(self.td, ignore_errors=True)

    def _alarms(self):
        return [f for n, f in self.j.events if n == "ALARM"]

    def test_disabled_is_a_hard_silent_noop(self):
        c = Corpus(self.root, journal=self.j, enabled=False)
        self.assertFalse(c.add("b1fe2518-000314", PCM_2S, "שלום"))
        self.assertFalse(self.root.exists(), "no directory, no manifest")
        self.assertEqual(self.j.events, [], "disabled is intent, not a fault")

    def test_empty_text_refused_with_alarm(self):
        c = Corpus(self.root, journal=self.j, enabled=True)
        self.assertFalse(c.add("b1fe2518-000314", PCM_2S, "   "))
        self.assertEqual(len(self._alarms()), 1)
        self.assertEqual(self._alarms()[0]["kind"], "corpus")
        self.assertEqual(c.skipped, 1)

    def test_empty_pcm_refused_with_alarm(self):
        c = Corpus(self.root, journal=self.j, enabled=True)
        self.assertFalse(c.add("b1fe2518-000314", b"", "שלום"))
        self.assertEqual(len(self._alarms()), 1)

    def test_full_corpus_refuses_new_but_keeps_old(self):
        c = Corpus(self.root, journal=self.j, enabled=True,
                   max_bytes=len(PCM_2S) + 10)
        self.assertTrue(c.add("b1fe2518-000314", PCM_2S, "נכנס"))
        self.assertFalse(c.add("b1fe2518-000315", PCM_2S, "מלא"))
        self.assertTrue(
            (self.root / "b1fe2518" / "b1fe2518-000314.wav").exists(),
            "nothing was deleted to make room, on purpose")
        alarm = self._alarms()[0]
        self.assertIn("full", alarm["err"])

    def test_oserror_returns_false_never_raises(self):
        blocker = pathlib.Path(self.td) / "blocker"
        blocker.write_text("a file where a directory must go")
        c = Corpus(blocker / "corpus", journal=self.j, enabled=True)
        self.assertFalse(c.add("b1fe2518-000314", PCM_2S, "שלום"))
        self.assertEqual(len(self._alarms()), 1)


if __name__ == "__main__":
    unittest.main()
