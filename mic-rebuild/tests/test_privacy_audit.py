"""K11 gate-19 audit tooling tests (PHASE2-DESIGN.md section 9, criterion 19).

Everything here runs OFFLINE on the PC — no ssh, no fleet, no devices.
The live audit itself is `tools/privacy_audit.sh` (driven from the PC),
whose eran1-side half is `server/audit_privacy.sh`; these tests pin the
pure logic both scripts rely on:

  * the journald status-line WHITELIST — the one regex truth lives inside
    server/audit_privacy.sh; its `selftest` subcommand classifies embedded
    good/bad fixtures and exits nonzero on any misclassification, so the
    regex is testable without duplicating it here (one copy, scar 28 style)
  * canary phrases + word extraction + wav->pcm + report verdict logic in
    tools/privacy_canaries.py
  * stt_server quiets the faster_whisper library logger — K10's nohup log
    proved the library emits INFO lines ("Processing audio with duration
    ...") that would pollute journald past the whitelist
"""
from __future__ import annotations

import logging
import shutil
import struct
import subprocess
import sys
import unittest
import wave
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from common import protocol  # noqa: E402
from tools import privacy_canaries as pc  # noqa: E402

AUDIT_SH = REPO / "server" / "audit_privacy.sh"
DRIVER_SH = REPO / "tools" / "privacy_audit.sh"


def _working_bash() -> str | None:
    """A bash that can actually RUN a script — not merely one on PATH.

    Measured on this PC 2026-08-17: `shutil.which("bash")` finds the WSL
    stub (System32\\bash.exe), which exits 1 with 'virtualization is not
    enabled' before reading any script — four tests here failed on the
    messenger. Git Bash is installed and real; prefer it, and PROVE the
    candidate runs before trusting it (health of the tool is real output,
    not presence on PATH)."""
    candidates = [
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files\Git\usr\bin\bash.exe",
        shutil.which("bash"),
    ]
    for cand in candidates:
        if not cand or not Path(cand).is_file():
            continue
        try:
            probe = subprocess.run([cand, "-c", "exit 0"],
                                   capture_output=True, timeout=30)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if probe.returncode == 0:
            return cand
    return None


BASH = _working_bash()


@unittest.skipUnless(BASH, "no WORKING bash available (WSL stub excluded)")
class AuditScriptTests(unittest.TestCase):
    """The eran1-side script exists, parses, and its whitelist self-test
    correctly classifies both good and bad journal lines."""

    def test_scripts_exist(self):
        self.assertTrue(AUDIT_SH.is_file(), AUDIT_SH)
        self.assertTrue(DRIVER_SH.is_file(), DRIVER_SH)

    def test_bash_syntax_audit(self):
        r = subprocess.run([BASH, "-n", str(AUDIT_SH)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_bash_syntax_driver(self):
        r = subprocess.run([BASH, "-n", str(DRIVER_SH)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_whitelist_selftest_passes(self):
        """selftest exits 0 ONLY if every embedded good fixture passes the
        whitelist AND every embedded bad fixture (text= field, raw Hebrew
        transcript line, canary word) is rejected."""
        r = subprocess.run([BASH, str(AUDIT_SH), "selftest"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, f"stdout={r.stdout}\nstderr={r.stderr}")
        self.assertIn("SELFTEST PASS", r.stdout)

    def test_whitelist_rejects_injected_transcript_line(self):
        """Feed one transcript-looking line through `checklines` on stdin —
        the whitelist filter itself, no fixtures — and expect exit 1."""
        bad = "2026-08-12 13:14:12,305 INFO evt=REQ id=deadbeef-000001 text=hello world\n"
        r = subprocess.run([BASH, str(AUDIT_SH), "checklines"],
                           input=bad, capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)

    def test_whitelist_accepts_real_status_lines(self):
        good = (
            "2026-08-12 13:10:38,801 INFO evt=MODELS_LOADED load_s=5.1 "
            "stock=large-v3-turbo-ct2 lora=iddo-lora-run2-ct2\n"
            "2026-08-12 13:10:38,858 INFO evt=CANARY_OK ms=55\n"
            "2026-08-12 13:14:12,321 INFO evt=REQ id=a3f9c2d1-000123 code=200 "
            "bytes=102400 ms=486 rtf=0.16 lang=he lp=-0.28 len=42 reason=detect_he\n"
            "Started keshev-stt.service - KESHEV STT server (faster-whisper CT2) :8737.\n"
        )
        r = subprocess.run([BASH, str(AUDIT_SH), "checklines"],
                           input=good, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, f"stdout={r.stdout}\nstderr={r.stderr}")


class CanaryPhraseTests(unittest.TestCase):
    """5 phrases of distinctive rare words — the things we grep eran1 for."""

    def test_five_phrases(self):
        self.assertEqual(len(pc.CANARY_PHRASES), 5)

    def test_each_phrase_has_two_distinctive_words(self):
        for phrase in pc.CANARY_PHRASES:
            words = pc.distinctive_words(phrase)
            self.assertGreaterEqual(len(words), 2, phrase)
            for w in words:
                self.assertGreaterEqual(len(w), 6, w)
                self.assertTrue(w.isalpha() and w.islower(), w)

    def test_distinctive_words_unique_across_phrases(self):
        seen: set = set()
        for phrase in pc.CANARY_PHRASES:
            for w in pc.distinctive_words(phrase):
                self.assertNotIn(w, seen, "canary words must not repeat")
                seen.add(w)

    def test_distinctive_words_drops_short_and_common(self):
        self.assertEqual(pc.distinctive_words("The cat and a dog ran"), [])

    def test_hits_normalizes_case_and_punctuation(self):
        self.assertEqual(pc.hits("The Zeppelin, marmalade!", ["zeppelin", "marmalade"]),
                         ["zeppelin", "marmalade"])
        self.assertEqual(pc.hits("nothing here", ["zeppelin"]), [])


class WavToPcmTests(unittest.TestCase):
    def _write_wav(self, path: Path, rate=16000, channels=1, width=2, n=1600):
        with wave.open(str(path), "wb") as w:
            w.setnchannels(channels)
            w.setsampwidth(width)
            w.setframerate(rate)
            w.writeframes(struct.pack(f"<{n}h", *([0] * n)))

    def test_round_trip(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "a.wav"
            self._write_wav(p)
            pcm = pc.wav_to_pcm(p)
            self.assertEqual(len(pcm), 1600 * 2)

    def test_wrong_rate_refused(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "a.wav"
            self._write_wav(p, rate=44100)
            with self.assertRaises(ValueError):
                pc.wav_to_pcm(p)

    def test_stereo_refused(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "a.wav"
            self._write_wav(p, channels=2, n=3200)
            with self.assertRaises(ValueError):
                pc.wav_to_pcm(p)


class RequestIdTests(unittest.TestCase):
    def test_session_and_ids_valid_per_protocol(self):
        ids = pc.request_ids(len(pc.CANARY_PHRASES))
        self.assertEqual(len(ids), 5)
        for rid in ids:
            self.assertTrue(protocol.valid_request_id(rid), rid)
        self.assertEqual(len(set(ids)), 5)


class Gate19ReportTests(unittest.TestCase):
    STEPS_PASS = {
        "fs_diff": {"pass": True, "detail": "0 keshev files"},
        "journal_canary": {"pass": True, "detail": "0 hits"},
        "journal_whitelist": {"pass": True, "detail": "31/31 lines"},
        "auth_probes": {"pass": True, "detail": "6/6 401"},
        "bind_check": {"pass": True, "detail": "<lan-ip> only"},
    }

    def test_verdict_pass(self):
        rep = pc.build_report(self.STEPS_PASS)
        self.assertEqual(rep["verdict"], "PASS")
        self.assertEqual(rep["gate"], 19)
        self.assertIn("date", rep)

    def test_any_failed_step_fails_the_gate(self):
        for k in self.STEPS_PASS:
            steps = {n: dict(s) for n, s in self.STEPS_PASS.items()}
            steps[k]["pass"] = False
            rep = pc.build_report(steps)
            self.assertEqual(rep["verdict"], "FAIL", k)

    def test_report_is_json_serializable(self):
        import json
        json.dumps(pc.build_report(self.STEPS_PASS))


class QuietLibrariesTests(unittest.TestCase):
    """K10 evidence: faster_whisper's own logger wrote INFO duration lines
    into the server log. The server must pin that logger to WARNING so
    journald carries our status lines only (scar 55 / section 6)."""

    def test_quiet_libraries_sets_warning(self):
        from server import stt_server
        lg = logging.getLogger("faster_whisper")
        lg.setLevel(logging.NOTSET)
        stt_server._quiet_libraries()
        self.assertEqual(lg.level, logging.WARNING)

    def test_main_path_calls_it(self):
        """Grep-level assertion: main() wires the quieting in."""
        src = (REPO / "server" / "stt_server.py").read_text(encoding="utf-8")
        self.assertIn("_quiet_libraries()", src.split("def main(")[1])


if __name__ == "__main__":
    unittest.main(verbosity=2)
