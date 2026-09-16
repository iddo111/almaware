"""K4 acceptance tests for client/mutexguard.py — written FIRST (TDD).

PHASE2-DESIGN.md K4 row + section 7, scar 1 (PHASE1-INQUIRY.md section 2):

  * named kernel mutex Global\\ALMAWARE_KESHEV_SINGLE, held for process life
  * a second instance exits <1s with exactly ONE log line, exit code 11
  * kernel object is OS-released on death — no lock files anywhere
  * CRITERION 7: 5 concurrent REAL processes -> exactly 1 survivor,
    4 logged refusals, each loser gone in <1s
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from client import mutexguard  # noqa: E402

PYTHON = sys.executable
ENTRYPOINT = REPO / "tests" / "dummy_entrypoint.py"


def _unique_name() -> str:
    """A unique Global\\ name per test so tests never collide with each other."""
    return f"Global\\ALMAWARE_KESHEV_TEST_{uuid.uuid4().hex[:12]}"


class MutexAcquireTests(unittest.TestCase):
    """In-process unit tests (release helper is TEST-ONLY; production never releases)."""

    def test_default_name_is_the_design_name(self):
        self.assertEqual(mutexguard.MUTEX_NAME, "Global\\ALMAWARE_KESHEV_SINGLE")

    def test_exit_code_constant(self):
        self.assertEqual(mutexguard.EXIT_DUPLICATE, 11)

    def test_first_acquire_wins(self):
        name = _unique_name()
        h = mutexguard.acquire(name)
        try:
            self.assertFalse(h.already_exists)
            self.assertTrue(h.handle)
        finally:
            mutexguard._release_for_test(h)

    def test_second_acquire_same_name_reports_duplicate(self):
        name = _unique_name()
        h1 = mutexguard.acquire(name)
        h2 = mutexguard.acquire(name)
        try:
            self.assertFalse(h1.already_exists)
            self.assertTrue(h2.already_exists)
        finally:
            mutexguard._release_for_test(h2)
            mutexguard._release_for_test(h1)

    def test_release_frees_the_name(self):
        name = _unique_name()
        h1 = mutexguard.acquire(name)
        mutexguard._release_for_test(h1)
        h2 = mutexguard.acquire(name)
        try:
            self.assertFalse(h2.already_exists)
        finally:
            mutexguard._release_for_test(h2)

    def test_acquire_or_exit_duplicate_exits_11_with_one_log_line(self):
        name = _unique_name()
        h1 = mutexguard.acquire(name)
        lines: list[str] = []
        try:
            with self.assertRaises(SystemExit) as cm:
                mutexguard.acquire_or_exit(name=name, log=lines.append)
            self.assertEqual(cm.exception.code, 11)
            self.assertEqual(len(lines), 1, "exactly ONE log line (scar 1)")
            self.assertIn("KESHEV", lines[0])
            self.assertIn("exit 11", lines[0])
        finally:
            mutexguard._release_for_test(h1)

    def test_acquire_or_exit_winner_returns_handle_and_logs_nothing(self):
        name = _unique_name()
        lines: list[str] = []
        h = mutexguard.acquire_or_exit(name=name, log=lines.append)
        try:
            self.assertFalse(h.already_exists)
            self.assertEqual(lines, [])
        finally:
            mutexguard._release_for_test(h)

    def test_no_lock_files_mechanism(self):
        """scar 1: kernel mutex, not lock files — the module writes NO files."""
        src = (REPO / "client" / "mutexguard.py").read_text(encoding="utf-8")
        for banned in ("open(", "Path(", "os.remove", "unlink", "tempfile"):
            self.assertNotIn(banned, src,
                             f"mutexguard must not touch the filesystem ({banned})")


class Criterion7Tests(unittest.TestCase):
    """5 concurrent REAL processes -> exactly ONE survivor, 4 refusals, <1s each."""

    def test_five_concurrent_launches(self):
        name = _unique_name()  # unique name: never collides with a real KESHEV
        with tempfile.TemporaryDirectory(prefix="keshev-c7-") as td:
            procs = []
            t_start = {}
            for _ in range(5):
                p = subprocess.Popen(
                    [PYTHON, str(ENTRYPOINT), td, "--hold", "8", "--name", name],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    cwd=str(REPO), text=True,
                )
                t_start[p.pid] = time.perf_counter()
                procs.append(p)

            # parent-side sanity: 4 losers must be GONE within 3s of launch
            # (the precise <1s bar is each loser's own in-process elapsed below)
            deadline = time.perf_counter() + 3.0
            while time.perf_counter() < deadline:
                if sum(1 for p in procs if p.poll() is not None) >= 4:
                    break
                time.sleep(0.02)
            exited_fast = sum(1 for p in procs if p.poll() is not None)
            self.assertGreaterEqual(exited_fast, 4,
                                    "4 losers must exit within 3s of launch")

            results = []
            for p in procs:
                out, err = p.communicate(timeout=30)
                results.append((p.pid, p.returncode,
                                time.perf_counter() - t_start[p.pid], out, err))

            winners = [r for r in results if r[1] == 0]
            losers = [r for r in results if r[1] == 11]

            self.assertEqual(len(winners), 1,
                             f"exactly ONE survivor required, got {results}")
            self.assertEqual(len(losers), 4,
                             f"exactly FOUR refusals required, got {results}")
            self.assertIn("WINNER", winners[0][3])

            # every loser: refusal log file with exactly one line, containing exit 11
            refusal_files = sorted(Path(td).glob("refusal-*.log"))
            self.assertEqual(len(refusal_files), 4,
                             f"4 refusal log files required, found {refusal_files}")
            loser_pids = {r[0] for r in losers}
            for f in refusal_files:
                pid = int(f.stem.split("-")[1])
                self.assertIn(pid, loser_pids)
                content = f.read_text(encoding="utf-8").strip().splitlines()
                self.assertEqual(len(content), 1, "exactly one log line per refusal")
                self.assertIn("exit 11", content[0])
                # the <1s bar (scar 1): in-process lifetime, interpreter top
                # to refusal, self-measured by the loser itself
                elapsed = float(content[0].split("elapsed_s=")[1])
                self.assertLess(elapsed, 1.0,
                                f"loser pid={pid} lived {elapsed:.3f}s (>1s)")


if __name__ == "__main__":
    unittest.main(verbosity=2)
