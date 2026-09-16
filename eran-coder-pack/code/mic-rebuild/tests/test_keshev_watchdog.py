"""Tests for tools/keshev-watchdog.ps1 -Status and tools/keshev-alarm.ps1.

The watchdog's verdict logic ran UNTESTED from birth (2026-08-15) — and its
own comments record what that cost: its first live run restarted a healthy
process on a dead session's errors (the 14:51 session-scoping bug), and it
printed "healthy — 52 segments in 10 min" for 1h50m of total silence (the
12:21 MUTE bug). Both fixes carry their scars as comments; nothing pinned
them. These tests pin them.

Everything here is READ-ONLY against the machine: `-Status` never restarts,
never writes the log, never shows the alarm — that contract is itself
asserted below. Verdicts are driven through fixture journals via
`-EventsPath` + `-JournalOnly`; no KESHEV process is touched, no device is
opened, no window is shown (`-SelfTest` builds the alarm without ShowDialog
— the focus-courtesy guardrail applies to alarms too).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
WATCHDOG = REPO / "tools" / "keshev-watchdog.ps1"
ALARM = REPO / "tools" / "keshev-alarm.ps1"

PWSH = shutil.which("pwsh") or shutil.which("powershell")


def _ts(minutes_ago: float) -> str:
    """Journal-format timestamp: ISO, milliseconds, local offset (scar 20)."""
    t = datetime.now().astimezone() - timedelta(minutes=minutes_ago)
    return t.isoformat(timespec="milliseconds")


def _line(minutes_ago: float, evt: str, **fields) -> str:
    rec = {"ts": _ts(minutes_ago), "sid": "f00dfeed", "evt": evt, **fields}
    return json.dumps(rec, ensure_ascii=False)


def run_status(journal_lines: list[str]) -> subprocess.CompletedProcess:
    """Write a fixture journal and ask the watchdog -Status what it sees."""
    with tempfile.TemporaryDirectory(prefix="keshev-wd-") as td:
        events = Path(td) / "events.jsonl"
        events.write_text("\n".join(journal_lines) + "\n", encoding="utf-8")
        return subprocess.run(
            [PWSH, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
             str(WATCHDOG), "-Status", "-JournalOnly",
             "-EventsPath", str(events)],
            capture_output=True, text=True, timeout=120)


@unittest.skipUnless(PWSH, "no PowerShell available")
class VerdictTests(unittest.TestCase):
    """Each verdict the watchdog can reach, driven by a crafted journal."""

    def assertVerdict(self, proc, verdict: str, exit_code: int):
        self.assertIn(f"VERDICT: {verdict}", proc.stdout,
                      f"stdout={proc.stdout!r} stderr={proc.stderr!r}")
        self.assertEqual(proc.returncode, exit_code,
                         f"stdout={proc.stdout!r} stderr={proc.stderr!r}")

    def test_healthy_full_chain(self):
        """SEG + DECODE + TYPED inside the window = the mic works end to end."""
        p = run_status([
            _line(20, "SESSION_BEGIN", pid=1234),
            _line(5, "SEG", id="f00dfeed-000001"),
            _line(5, "DECODE", id="f00dfeed-000001", ok=1),
            _line(5, "TYPED", id="f00dfeed-000001", len=12),
            _line(2, "SEG", id="f00dfeed-000002"),
            _line(2, "DECODE", id="f00dfeed-000002", ok=1),
            _line(2, "TYPED", id="f00dfeed-000002", len=30),
        ])
        self.assertVerdict(p, "HEALTHY", 0)
        # the detail must carry all three numbers (the 12:21 lesson: a human
        # skimming "healthy" must see the middle of the pipe, not just SEGs)
        self.assertRegex(p.stdout, r"seg=\d+ decode=\d+ typed=\d+")

    def test_deaf_when_running_and_hearing_nothing(self):
        """The 04:06 scar: process alive, journal silent for the window."""
        p = run_status([_line(30, "SESSION_BEGIN", pid=1234),
                        _line(25, "SEG", id="f00dfeed-000001")])
        self.assertVerdict(p, "DEAF", 1)

    def test_mute_hears_but_never_decodes(self):
        """The 12:21 scar: SEG after SEG, zero DECODE — the old check called
        this healthy for 1h50m."""
        p = run_status(
            [_line(20, "SESSION_BEGIN", pid=1234)] +
            [_line(9 - i, "SEG", id=f"f00dfeed-{i:06d}") for i in range(5)])
        self.assertVerdict(p, "MUTE", 1)

    def test_mute_decodes_but_never_types(self):
        """Understands and does not speak — the third dead-middle shape.
        2026-08-18: this is a FAULT a human must see (exit 1) but NOT a
        restart — MUTE_SOFT. A restart is itself a 60 s break and cannot fix
        the benign causes of this shape."""
        p = run_status(
            [_line(20, "SESSION_BEGIN", pid=1234),
             _line(9, "SEG", id="f00dfeed-000001")] +
            [_line(8 - 0.5 * i, "DECODE", id=f"f00dfeed-{i:06d}", ok=1)
             for i in range(9)])
        self.assertVerdict(p, "MUTE_SOFT", 1)

    def test_decodes_with_gated_or_guard_drop_are_healthy(self):
        """2026-08-18, Iddo's goal 'a mic that NEVER breaks': Iddo away with
        a TV on = many decodes, zero typed, every one GATED (presence guard)
        or GUARD_DROP (noise). That is the mic WORKING. The old rule restarted
        a healthy mic for it."""
        p = run_status(
            [_line(20, "SESSION_BEGIN", pid=1234),
             _line(9, "SEG", id="f00dfeed-000001")] +
            [_line(8 - 0.5 * i, "DECODE", id=f"f00dfeed-{i:06d}", ok=1)
             for i in range(9)] +
            [_line(7.9 - 0.5 * i, "GATED", id=f"f00dfeed-{i:06d}")
             for i in range(9)])
        self.assertVerdict(p, "HEALTHY", 0)

    def test_transient_idle_no_mic_is_starting_not_stuck(self):
        """2026-08-18: every start passes through TRAY_IDLE_NO_MIC for ~1 s
        between DEVICE_OPEN and READY. A tick inside that second must not
        restart a mic that is one second from healthy."""
        p = run_status(
            [_line(1, "SESSION_BEGIN", pid=1234),
             _line(0.02, "STATE", state="TRAY_IDLE_NO_MIC")])
        self.assertVerdict(p, "STARTING", 0)

    def test_starting_grace_for_young_sessions(self):
        """A 2-minute-old session with a quiet journal is a loading worker
        (~95s), not a deaf mic — restarting it would be the restart loop."""
        p = run_status([_line(2, "SESSION_BEGIN", pid=1234)])
        self.assertVerdict(p, "STARTING", 0)

    def test_stuck_device_on_reresolve_errors(self):
        """The 14:06 scar: a device handle that will not reopen."""
        p = run_status(
            [_line(20, "SESSION_BEGIN", pid=1234)] +
            [_line(8 - i, "STATE", state="RERESOLVE_ERROR") for i in range(3)])
        self.assertVerdict(p, "STUCK_DEVICE", 1)

    def test_session_scoping_ignores_the_dead_sessions_journal(self):
        """The 14:51 bug, pinned: rich activity BEFORE the newest
        SESSION_BEGIN belongs to a dead process and proves nothing about the
        live one. A young session on top of an old busy journal is STARTING,
        never HEALTHY and never DEAF."""
        p = run_status(
            [_line(9, "SEG", id="deadbeef-000001"),
             _line(9, "DECODE", id="deadbeef-000001", ok=1),
             _line(8, "TYPED", id="deadbeef-000001", len=40),
             _line(2, "SESSION_BEGIN", pid=5678)])
        self.assertVerdict(p, "STARTING", 0)

    def test_unknown_when_journal_missing(self):
        p = subprocess.run(
            [PWSH, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
             str(WATCHDOG), "-Status", "-JournalOnly",
             "-EventsPath", r"C:\nonexistent\keshev-events.jsonl"],
            capture_output=True, text=True, timeout=120)
        self.assertIn("VERDICT: UNKNOWN", p.stdout)
        self.assertEqual(p.returncode, 0)


@unittest.skipUnless(PWSH, "no PowerShell available")
class StatusIsReadOnly(unittest.TestCase):
    """-Status may LOOK at the live machine but never act on it."""

    def test_status_against_the_live_journal_touches_nothing(self):
        log = REPO / "state" / "watchdog.log"
        stamps = REPO / "state" / "watchdog-restarts.json"
        before = (log.stat().st_mtime_ns if log.exists() else None,
                  stamps.read_bytes() if stamps.exists() else None)
        p = subprocess.run(
            [PWSH, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
             str(WATCHDOG), "-Status"],
            capture_output=True, text=True, timeout=120)
        self.assertIn("VERDICT:", p.stdout)
        self.assertIn(p.returncode, (0, 1))
        self.assertNotIn("RESTART", p.stdout)
        after = (log.stat().st_mtime_ns if log.exists() else None,
                 stamps.read_bytes() if stamps.exists() else None)
        self.assertEqual(before, after,
                         "-Status wrote to the watchdog log or restart "
                         "stamps — it must be read-only")


@unittest.skipUnless(PWSH, "no PowerShell available")
class AlarmTests(unittest.TestCase):
    """The visible alarm builds cleanly and stays silent (Sacred Audio)."""

    def test_selftest_builds_the_window_without_showing_it(self):
        p = subprocess.run(
            [PWSH, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
             str(ALARM), "-SelfTest", "-Verdict", "DEAF",
             "-Detail", "test detail"],
            capture_output=True, text=True, timeout=120)
        self.assertEqual(p.returncode, 0,
                         f"stdout={p.stdout!r} stderr={p.stderr!r}")
        self.assertIn("ALARM-SELFTEST-OK", p.stdout)

    def test_alarm_makes_no_sound_by_construction(self):
        """Sacred Audio Law, enforced as a grep over CODE (comments stripped —
        the script's own header legitimately NAMES the banned calls): no
        Beep, no MessageBox (MessageBoxW plays the system sound), no
        SystemSounds, no SoundPlayer — the alarm is a WINDOW, only a window."""
        src = ALARM.read_text(encoding="utf-8")
        # strip <# ... #> block comments and full/trailing # line comments
        import re
        code = re.sub(r"<#.*?#>", "", src, flags=re.DOTALL)
        code = "\n".join(ln.split("#", 1)[0] for ln in code.splitlines())
        code = code.lower()
        for banned in ("beep", "messagebox", "systemsounds", "soundplayer",
                       ".play"):
            self.assertNotIn(banned, code,
                             f"{banned!r} found in keshev-alarm.ps1 code — "
                             f"the alarm must be visual ONLY (Sacred Audio Law)")


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(PWSH, "no PowerShell available")
class SilentRoomTests(unittest.TestCase):
    """2026-08-18 04:2x — the silent-room bug, found by Iddo asking "why does
    it fall asleep". A sleeping house produces zero segments; the old branch
    read that silence as DEAF and restarted the mic every 12 minutes all
    night — 15 duplicate SESSION_BEGINs in one real journal. A live HEARTBEAT
    with no audio is QUIET = HEALTHY; only heartbeat-silence too is DEAF."""

    def test_quiet_room_with_heartbeat_is_healthy(self):
        lines = [_line(30, "SESSION_BEGIN", pid=1234)]
        for m in range(10, 0, -1):
            lines.append(_line(m, "HEARTBEAT", state="READY", eng="dgx"))
        p = run_status(lines)
        self.assertIn("VERDICT: HEALTHY", p.stdout,
                      f"stdout={p.stdout!r} stderr={p.stderr!r}")
        self.assertIn("QUIET", p.stdout)

    def test_no_heartbeat_and_no_audio_is_deaf(self):
        p = run_status([
            _line(40, "SESSION_BEGIN", pid=1234),
            _line(39, "HEARTBEAT", state="READY"),
        ])
        self.assertIn("VERDICT: DEAF", p.stdout,
                      f"stdout={p.stdout!r} stderr={p.stderr!r}")
