"""K4 acceptance tests for tools/install_client.ps1 — written FIRST (TDD).

PHASE2-DESIGN.md K4 row + section 7, scars 2/56:

  * refuses to install beside live alma-mic without -Coexist (exit 3)
  * audit journal lists every rival mic persistence found (JSONL in _genizah)
  * -DryRun changes NOTHING (proven: rival task states identical before/after)
  * idempotent: two dry-runs find the identical rival set
  * the ONE Scheduled Task pattern: logon trigger, restart-on-failure
    3 times / 10 minutes, single trigger — proven register -> verify ->
    UNREGISTER (guardrail: no persistent task is left behind)

HARD GUARDRAILS honored here:
  * the running alma-mic (task/process/config) is NEVER touched — the live
    system is only READ; all mutation paths run against a throwaway task
    name (KESHEV-K4TEST) or in -DryRun
  * alma-mic liveness is SIMULATED (-SimulateAlmaMic Alive|Dead) so the
    refusal test is deterministic and touch-free
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "tools" / "install_client.ps1"
TEST_TASK = "KESHEV-K4TEST"

PWSH = shutil.which("pwsh") or shutil.which("powershell")


def run_installer(*args: str, genizah: str) -> subprocess.CompletedProcess:
    cmd = [PWSH, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT),
           "-GenizahRoot", genizah, *args]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=120)


def summary_of(proc: subprocess.CompletedProcess) -> dict:
    """The installer prints ONE machine-readable JSON summary line prefixed SUMMARY:"""
    for line in proc.stdout.splitlines():
        if line.startswith("SUMMARY:"):
            return json.loads(line[len("SUMMARY:"):])
    raise AssertionError(f"no SUMMARY line in output:\n{proc.stdout}\n{proc.stderr}")


def task_xml(name: str) -> str | None:
    p = subprocess.run(["schtasks", "/query", "/tn", name, "/xml"],
                       capture_output=True, text=True)
    return p.stdout if p.returncode == 0 else None


RIVAL_MARKERS = ("alma-mic", "voice-input", "heb-mic", "start-mic")


def rival_task_states() -> dict[str, str]:
    """Read-only snapshot of every MIC-RIVAL task's state (the no-touch proof).

    Scoped to rival names only: unrelated system tasks legitimately flip
    Ready/Running between snapshots and are not what guardrail 1 protects.
    """
    p = subprocess.run(["schtasks", "/query", "/fo", "csv"],
                       capture_output=True, text=True)
    states = {}
    for line in p.stdout.splitlines()[1:]:
        parts = line.strip('"').split('","')
        if len(parts) >= 3 and any(m in parts[0].lower() for m in RIVAL_MARKERS):
            states[parts[0]] = parts[2]
    return states


class RefusalTests(unittest.TestCase):
    """scar 56: refuses beside live alma-mic without -Coexist."""

    def test_alive_without_coexist_refused_exit_3(self):
        with tempfile.TemporaryDirectory(prefix="keshev-inst-") as td:
            p = run_installer("-DryRun", "-SimulateAlmaMic", "Alive", genizah=td)
            self.assertEqual(p.returncode, 3, f"expected exit 3, got {p.returncode}: {p.stdout} {p.stderr}")
            self.assertIn("REFUSED", p.stdout)
            self.assertIn("alma-mic", p.stdout.lower())

    def test_alive_with_coexist_proceeds(self):
        with tempfile.TemporaryDirectory(prefix="keshev-inst-") as td:
            p = run_installer("-DryRun", "-Coexist", "-SimulateAlmaMic", "Alive", genizah=td)
            self.assertEqual(p.returncode, 0, f"{p.stdout} {p.stderr}")
            s = summary_of(p)
            self.assertTrue(s["coexist"])
            self.assertFalse(s["refused"])


class DryRunInventoryTests(unittest.TestCase):
    """scar 2: audit journal lists every rival persistence; dry-run touches nothing."""

    def test_dry_run_inventories_and_changes_nothing(self):
        before = rival_task_states()
        with tempfile.TemporaryDirectory(prefix="keshev-inst-") as td:
            p = run_installer("-DryRun", "-SimulateAlmaMic", "Dead", genizah=td)
            self.assertEqual(p.returncode, 0, f"{p.stdout} {p.stderr}")
            s = summary_of(p)
            self.assertTrue(s["dry_run"])
            # this machine is known to carry alma-mic persistence — the scan
            # must FIND rivals (finding zero on this box would be a lie)
            self.assertGreater(len(s["rivals"]), 0,
                               "rival scan found nothing on a machine with ALMA-MIC persistence")
            for r in s["rivals"]:
                self.assertEqual(r["action"], "WOULD-ARCHIVE",
                                 f"dry-run must not act: {r}")
            # journal exists and holds one JSONL line per rival
            jpath = Path(s["journal"])
            self.assertTrue(jpath.is_file(), f"journal missing: {jpath}")
            entries = [json.loads(x) for x in
                       jpath.read_text(encoding="utf-8").splitlines() if x.strip()]
            journal_rivals = [e for e in entries if e.get("kind") != "run"]
            self.assertEqual(len(journal_rivals), len(s["rivals"]))
            # task must NOT have been registered in dry-run
            self.assertIsNone(task_xml(s["task_name"]))
        after = rival_task_states()
        self.assertEqual(before, after, "dry-run altered live task state (guardrail 1)")

    def test_dry_run_is_idempotent(self):
        with tempfile.TemporaryDirectory(prefix="keshev-inst-") as td:
            p1 = run_installer("-DryRun", "-SimulateAlmaMic", "Dead", genizah=td)
            p2 = run_installer("-DryRun", "-SimulateAlmaMic", "Dead", genizah=td)
            self.assertEqual(p1.returncode, 0)
            self.assertEqual(p2.returncode, 0)
            r1 = {(r["kind"], r["name"]) for r in summary_of(p1)["rivals"]}
            r2 = {(r["kind"], r["name"]) for r in summary_of(p2)["rivals"]}
            self.assertEqual(r1, r2, "two dry-runs must find the identical rival set")


class TaskPatternTests(unittest.TestCase):
    """The ONE Scheduled Task pattern — register -> verify -> UNREGISTER.

    Guardrail 4: no persistent task is left; the throwaway name KESHEV-K4TEST
    is used, and -Coexist keeps rival archiving journal-only (nothing touched).
    """

    def tearDown(self):
        # belt-and-braces: never leave the test task behind, even on failure
        subprocess.run(["schtasks", "/delete", "/tn", TEST_TASK, "/f"],
                       capture_output=True)

    def test_register_verify_unregister(self):
        with tempfile.TemporaryDirectory(prefix="keshev-inst-") as td:
            p = run_installer("-Coexist", "-SimulateAlmaMic", "Dead",
                              "-TaskName", TEST_TASK, genizah=td)
            self.assertEqual(p.returncode, 0, f"{p.stdout} {p.stderr}")
            s = summary_of(p)
            self.assertTrue(s["task_registered"])
            self.assertEqual(s["task_name"], TEST_TASK)

            xml = task_xml(TEST_TASK)
            self.assertIsNotNone(xml, "task not found after register")
            ns = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
            root = ET.fromstring(xml)
            # exactly ONE trigger, and it is the logon trigger (scar 2)
            triggers = root.find("t:Triggers", ns)
            self.assertEqual(len(list(triggers)), 1, "exactly one trigger")
            self.assertIsNotNone(triggers.find("t:LogonTrigger", ns))
            # restart-on-failure: 3 times / 10 minutes (section 7 — the only
            # respawn mechanism; scar 3's OS-provided circuit breaker)
            rof = root.find(".//t:RestartOnFailure", ns)
            self.assertIsNotNone(rof, "RestartOnFailure settings missing")
            self.assertEqual(rof.find("t:Count", ns).text, "3")
            self.assertEqual(rof.find("t:Interval", ns).text, "PT10M")
            # only one instance policy (defense in depth beside the mutex)
            mip = root.find(".//t:MultipleInstancesPolicy", ns)
            self.assertEqual(mip.text, "IgnoreNew")
            # run level recorded honestly in the summary (Highest needs an
            # elevated session; the test records what was achievable)
            self.assertIn(s["run_level"], ("Highest", "Limited"))

            # idempotent: registering again replaces, does not duplicate/fail
            p2 = run_installer("-Coexist", "-SimulateAlmaMic", "Dead",
                               "-TaskName", TEST_TASK, genizah=td)
            self.assertEqual(p2.returncode, 0, f"{p2.stdout} {p2.stderr}")
            self.assertIsNotNone(task_xml(TEST_TASK))

            # UNREGISTER and verify GONE (guardrail 4)
            p3 = run_installer("-Uninstall", "-TaskName", TEST_TASK, genizah=td)
            self.assertEqual(p3.returncode, 0, f"{p3.stdout} {p3.stderr}")
            self.assertIsNone(task_xml(TEST_TASK), "task must be gone after uninstall")

            # uninstall is idempotent too
            p4 = run_installer("-Uninstall", "-TaskName", TEST_TASK, genizah=td)
            self.assertEqual(p4.returncode, 0, f"{p4.stdout} {p4.stderr}")

    def test_no_persistent_keshev_task_exists(self):
        """Guardrail 4 standing check: the real KESHEV task must NOT exist yet."""
        self.assertIsNone(task_xml("KESHEV"),
                          "a persistent KESHEV task exists before cutover (guardrail 4)")


if __name__ == "__main__":
    unittest.main(verbosity=2)
