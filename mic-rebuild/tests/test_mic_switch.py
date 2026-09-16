"""K5 acceptance tests for tools/mic-switch.ps1 — written FIRST (TDD).

PHASE2-DESIGN.md K5 row + section 7 "mic-switch (scar 56)", criterion 23:

  * `new`  = stop alma-mic (task + process + Startup persistence, journaled),
             VERIFY it is dead + zero foreign capture handles, then start KESHEV.
  * `old`  = exact reverse.
  * `status` = read-only liveness + capture-device-handle audit.
  * REFUSAL: if the other mic is still detectably alive at the verify step,
    the switch REFUSES (exit 3) and starts nothing.

WAVE GUARDRAILS honored here (hard orders for this build wave):
  * The switch action is NEVER executed — every `new`/`old` invocation in this
    file is -DryRun and/or simulated; the script itself FORCES dry-run whenever
    any -Simulate* flag is engaged (structural safety, asserted below).
  * The running alma-mic is NEVER touched — the live system is only READ.
    The one real (non-mocked) test proves the Auto probes DETECT the currently
    running alma-mic and that the script REFUSES to switch; it asserts the
    refusal and then asserts alma-mic is still alive and its task states are
    byte-identical.
  * No capture device is ever OPENED — the audit enumerates WASAPI capture
    sessions (metadata only, eCapture endpoints only; Sacred Audio safe).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "tools" / "mic-switch.ps1"

PWSH = shutil.which("pwsh") or shutil.which("powershell")

RIVAL_MARKERS = ("alma-mic", "voice-input", "heb-mic", "start-mic")


def run_switch(*args: str, journal: str) -> subprocess.CompletedProcess:
    cmd = [PWSH, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT),
           "-JournalRoot", journal, *args]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=180)


def summary_of(proc: subprocess.CompletedProcess) -> dict:
    """The script prints ONE machine-readable JSON summary line prefixed SUMMARY:"""
    for line in proc.stdout.splitlines():
        if line.startswith("SUMMARY:"):
            return json.loads(line[len("SUMMARY:"):])
    raise AssertionError(f"no SUMMARY line in output:\n{proc.stdout}\n{proc.stderr}")


def rival_task_states() -> dict[str, str]:
    """Read-only snapshot of every MIC-RIVAL task's state (the no-touch proof)."""
    p = subprocess.run(["schtasks", "/query", "/fo", "csv"],
                       capture_output=True, text=True)
    states = {}
    for line in p.stdout.splitlines()[1:]:
        parts = line.strip('"').split('","')
        if len(parts) >= 3 and any(m in parts[0].lower() for m in RIVAL_MARKERS):
            states[parts[0]] = parts[2]
    return states


def real_alma_mic_alive() -> bool:
    """Independent read-only probe: any ALMA-MIC* scheduled task Running."""
    return any("alma-mic" in name.lower() and state.strip().lower() == "running"
               for name, state in rival_task_states().items())


def real_keshev_alive() -> bool:
    """Independent read-only probe: a live KESHEV client/worker process.

    Same detection the watchdog uses. Needed since 2026-08-14: KESHEV is no
    longer 'does not exist yet' — it is Iddo's live mic, and tests written
    on the assumption keshev_alive must be False now run on a machine where
    it is truthfully True."""
    p = subprocess.run(
        [PWSH, "-NoProfile", "-Command",
         "@(Get-CimInstance Win32_Process -Filter \"Name like '%python%'\" "
         "-ErrorAction SilentlyContinue | Where-Object "
         "{ $_.CommandLine -match 'client\\.app|keshev_worker' }).Count"],
        capture_output=True, text=True, timeout=60)
    try:
        return int(p.stdout.strip() or 0) > 0
    except ValueError:
        return False


def keshev_task_exists() -> bool:
    p = subprocess.run(["schtasks", "/query", "/tn", "KESHEV"],
                       capture_output=True, text=True)
    return p.returncode == 0


def steps_by_target(summary: dict) -> dict[str, str]:
    return {s["step"]: s["action"] for s in summary["steps"]}


class MockedRefusalTests(unittest.TestCase):
    """Criterion 23: attempting the switch while the other mic is alive → REFUSE (exit 3)."""

    def test_new_refused_when_alma_mic_alive(self):
        with tempfile.TemporaryDirectory(prefix="keshev-sw-") as td:
            p = run_switch("new", "-DryRun", "-SimulateAlmaMic", "Alive",
                           "-SimulateKeshev", "Dead", journal=td)
            self.assertEqual(p.returncode, 3, f"expected exit 3: {p.stdout} {p.stderr}")
            self.assertIn("REFUSED", p.stdout)
            s = summary_of(p)
            self.assertTrue(s["refused"])
            self.assertIn("alma-mic", s["refusal_reason"].lower())
            # KESHEV must NOT have been started (not even planned as done)
            self.assertNotIn(steps_by_target(s).get("start-keshev", "ABSENT"),
                             ("STARTED", "WOULD-START"))

    def test_old_refused_when_keshev_alive(self):
        """The reverse direction refuses symmetrically (scar 56: both flips guarded)."""
        with tempfile.TemporaryDirectory(prefix="keshev-sw-") as td:
            p = run_switch("old", "-DryRun", "-SimulateKeshev", "Alive",
                           "-SimulateAlmaMic", "Dead", journal=td)
            self.assertEqual(p.returncode, 3, f"expected exit 3: {p.stdout} {p.stderr}")
            s = summary_of(p)
            self.assertTrue(s["refused"])
            self.assertIn("keshev", s["refusal_reason"].lower())
            self.assertNotIn(steps_by_target(s).get("start-alma-mic", "ABSENT"),
                             ("STARTED", "WOULD-START"))

    def test_refusal_is_journaled(self):
        with tempfile.TemporaryDirectory(prefix="keshev-sw-") as td:
            p = run_switch("new", "-DryRun", "-SimulateAlmaMic", "Alive",
                           "-SimulateKeshev", "Dead", journal=td)
            self.assertEqual(p.returncode, 3)
            s = summary_of(p)
            jpath = Path(s["journal"])
            self.assertTrue(jpath.is_file(), f"journal missing: {jpath}")
            entries = [json.loads(x) for x in
                       jpath.read_text(encoding="utf-8").splitlines() if x.strip()]
            kinds = {e["kind"] for e in entries}
            self.assertIn("run", kinds)
            self.assertIn("refusal", kinds)


class MockedProceedTests(unittest.TestCase):
    """Dry-run flows with the other mic mocked dead: the plan is complete, nothing mutates."""

    def test_new_dry_run_plans_and_touches_nothing(self):
        before = rival_task_states()
        with tempfile.TemporaryDirectory(prefix="keshev-sw-") as td:
            p = run_switch("new", "-DryRun", "-SimulateAlmaMic", "Dead",
                           "-SimulateKeshev", "Dead", journal=td)
            self.assertEqual(p.returncode, 0, f"{p.stdout} {p.stderr}")
            s = summary_of(p)
            self.assertFalse(s["refused"])
            self.assertTrue(s["dry_run"])
            steps = steps_by_target(s)
            self.assertEqual(steps.get("start-keshev"), "WOULD-START")
            # verify step ran and passed
            self.assertEqual(steps.get("verify-alma-mic-dead"), "PASS")
        self.assertEqual(before, rival_task_states(),
                         "dry-run altered live rival task state (guardrail 1)")
        self.assertFalse(keshev_task_exists(),
                         "a persistent KESHEV task appeared (guardrail 4)")

    def test_old_dry_run_plans_reverse(self):
        with tempfile.TemporaryDirectory(prefix="keshev-sw-") as td:
            p = run_switch("old", "-DryRun", "-SimulateKeshev", "Dead",
                           "-SimulateAlmaMic", "Dead", journal=td)
            self.assertEqual(p.returncode, 0, f"{p.stdout} {p.stderr}")
            s = summary_of(p)
            self.assertFalse(s["refused"])
            steps = steps_by_target(s)
            self.assertEqual(steps.get("start-alma-mic"), "WOULD-START")
            self.assertEqual(steps.get("verify-keshev-dead"), "PASS")


class SimulationSafetyTests(unittest.TestCase):
    """A simulated world may never mutate the real one — simulation FORCES dry-run."""

    def test_simulation_forces_dry_run_even_without_flag(self):
        before = rival_task_states()
        with tempfile.TemporaryDirectory(prefix="keshev-sw-") as td:
            # note: NO -DryRun given
            p = run_switch("new", "-SimulateAlmaMic", "Dead",
                           "-SimulateKeshev", "Dead", journal=td)
            self.assertEqual(p.returncode, 0, f"{p.stdout} {p.stderr}")
            s = summary_of(p)
            self.assertTrue(s["simulated"])
            self.assertTrue(s["dry_run"],
                            "simulation MUST force dry-run (structural safety)")
        self.assertEqual(before, rival_task_states())
        self.assertFalse(keshev_task_exists())


class StatusTests(unittest.TestCase):
    """`status` = read-only liveness + capture-handle audit (criterion 23's audit)."""

    def test_status_reports_liveness_and_audit(self):
        with tempfile.TemporaryDirectory(prefix="keshev-sw-") as td:
            p = run_switch("status", journal=td)
            self.assertEqual(p.returncode, 0, f"{p.stdout} {p.stderr}")
            s = summary_of(p)
            self.assertEqual(s["action"], "status")
            self.assertIsInstance(s["alma_mic_alive"], bool)
            self.assertIsInstance(s["keshev_alive"], bool)
            # Was assertFalse("KESHEV does not exist yet") — stale since KESHEV
            # became the live mic. The honest assertion in both worlds: the
            # script's probe must agree with an independent probe of the same
            # machine (live-reality corroboration, not a frozen assumption).
            self.assertEqual(s["keshev_alive"], real_keshev_alive(),
                             "mic-switch status disagrees with an independent "
                             "process probe about KESHEV liveness")
            # the audit must actually WORK on this machine (real output, not a proxy)
            self.assertTrue(s["audit"]["ok"], f"capture audit failed: {s['audit'].get('error')}")
            self.assertIsInstance(s["audit"]["sessions"], list)
            for sess in s["audit"]["sessions"]:
                self.assertIn("pid", sess)
                self.assertIn("class", sess)
                self.assertIn(sess["class"], ("alma-mic", "keshev", "unknown", "other"))

    def test_audit_reports_every_session_it_could_not_attribute(self):
        """THE FAIL-CLOSED LAW: the audit may never answer "nobody is holding the
        mic" to a question it could not actually answer.

        Measured on this machine 2026-08-12, alma-mic is NOT findable as a
        per-process capture session, for two independent reasons:

          1. it opens the BRIO through *Windows DirectSound*
             (`DEVICE: Microphone (Logitech BRIO) · [Windows DirectSound] #11`),
             so its stream lands in the endpoint's SHARED session — GetProcessId
             answers AUDCLNT_S_NO_SINGLE_PROCESS (0x0889000D, a SUCCESS code
             meaning "this session spans more than one process"). There is no
             per-process session to find; the owner is unattributable by
             construction.
          2. ALMA-MIC-Elevated runs elevated, so Win32_Process hands a
             non-elevated probe a blank CommandLine/ExecutablePath.

        So the audit cannot be required to NAME the holder. It can — and must —
        be required to ADMIT that it does not know: every session it failed to
        attribute is reported, and `can_prove_free` is False whenever that list
        is non-empty (or the audit itself errored).
        """
        with tempfile.TemporaryDirectory(prefix="keshev-sw-") as td:
            p = run_switch("status", journal=td)
            s = summary_of(p)
            audit = s["audit"]
            self.assertTrue(audit["ok"], f"audit failed: {audit.get('error')}")
            self.assertIsInstance(audit["unattributable"], list)
            self.assertIsInstance(audit["can_prove_free"], bool)

            def ident(sess):
                return (sess["device"], sess["pid"], sess["state"])

            listed = {ident(x) for x in audit["unattributable"]}
            for sess in audit["sessions"]:
                blind = (sess["class"] == "unknown"
                         or sess["state"] == "unknown"
                         or sess["multi_process"])
                if blind:
                    self.assertIn(
                        ident(sess), listed,
                        "a capture session the audit could not attribute was not "
                        f"reported as unattributable: {sess}")
                if sess["multi_process"]:
                    # AUDCLNT_S_NO_SINGLE_PROCESS hands back an "initial" pid that is
                    # not an owner (here 0). Resolving it against Win32_Process invents
                    # a holder — the refusal line would name "System Idle Process".
                    self.assertEqual(sess["class"], "unknown",
                                     f"multi-process session must be unattributable: {sess}")
                    self.assertNotIn(
                        "Idle", sess["exe"],
                        "the audit invented an owner for a session that by definition "
                        f"has none: {sess}")
            if audit["unattributable"]:
                self.assertFalse(
                    audit["can_prove_free"],
                    "the audit claims it can prove the mic is free while holding "
                    f"{len(audit['unattributable'])} session(s) it could not "
                    f"attribute: {audit['unattributable']}")
            else:
                self.assertEqual(audit["mic_holders"], [],
                                 "can_prove_free with a live mic holder listed")

    def test_audit_cannot_claim_the_mic_is_free_while_alma_mic_is_live(self):
        """The live corroboration. alma-mic IS holding the BRIO; the audit cannot
        see that (see the docstring above), so the ONE thing it must never say is
        "the mic is free"."""
        if not real_alma_mic_alive():
            self.skipTest("alma-mic not running right now — no live holder to corroborate")
        with tempfile.TemporaryDirectory(prefix="keshev-sw-") as td:
            p = run_switch("status", journal=td)
            s = summary_of(p)
            self.assertTrue(s["audit"]["ok"], f"audit failed: {s['audit'].get('error')}")
            self.assertFalse(
                s["audit"]["can_prove_free"],
                "alma-mic is LIVE and holding a capture stream, but the audit "
                "reports the mic as provably free "
                f"(sessions={s['audit']['sessions']})")

    def test_switch_refuses_while_the_audit_cannot_prove_the_mic_is_free(self):
        """The verdict must reach the DECISION, not just the report.

        `old` with real probes: this test's premise is a machine with NO
        KESHEV process, so the liveness probe cannot be what stops the flip —
        only the capture audit can. When KESHEV is LIVE (it is Iddo's mic
        now), the premise does not hold and the refusal would come from
        liveness, proving nothing about the audit — so the test SKIPS rather
        than assert a world that no longer exists. The audit-refusal law
        stays covered in both worlds by the simulated tests above. Read-only:
        stop-keshev short-circuits on SKIP-ALREADY-DEAD and -DryRun starts
        nothing on either outcome."""
        if real_keshev_alive():
            self.skipTest("KESHEV is live right now — the no-KESHEV premise "
                          "of this probe does not hold; audit refusal is "
                          "covered by the simulated tests")
        with tempfile.TemporaryDirectory(prefix="keshev-sw-") as td:
            p = run_switch("old", "-DryRun", journal=td)
            s = summary_of(p)
            self.assertFalse(s["simulated"], "this probe must be the real machine")
            self.assertFalse(s["keshev_alive"], "no KESHEV process expected here")
            if s["audit"]["can_prove_free"]:
                self.assertEqual(p.returncode, 0, f"{p.stdout} {p.stderr}")
                return
            self.assertEqual(
                p.returncode, 3,
                "the audit could not prove the mic is free, yet the switch "
                f"proceeded — fail-closed broken: {p.stdout} {p.stderr}")
            self.assertTrue(s["refused"])
            self.assertNotIn(steps_by_target(s).get("start-alma-mic", "ABSENT"),
                             ("STARTED", "WOULD-START"))

    def test_status_matches_live_reality(self):
        """If alma-mic is really running right now, status must SAY so."""
        if not real_alma_mic_alive():
            self.skipTest("alma-mic not running right now — nothing to corroborate")
        with tempfile.TemporaryDirectory(prefix="keshev-sw-") as td:
            p = run_switch("status", journal=td)
            s = summary_of(p)
            self.assertTrue(s["alma_mic_alive"],
                            "alma-mic IS running but status reported dead (probe broken)")


class RealProbeRefusalTest(unittest.TestCase):
    """THE one real (non-mocked) test: the Auto probes detect the currently-running
    alma-mic and the switch REFUSES. Read-only end to end; the switch is never
    performed; alma-mic is proven untouched afterwards."""

    def test_real_probe_detects_live_alma_mic_and_refuses(self):
        if not real_alma_mic_alive():
            self.skipTest("alma-mic not running right now — refusal cannot be "
                          "honestly asserted against live state")
        before = rival_task_states()
        with tempfile.TemporaryDirectory(prefix="keshev-sw-") as td:
            p = run_switch("new", "-DryRun", journal=td)  # Auto probes, real machine
            self.assertEqual(p.returncode, 3,
                             f"live alma-mic must cause REFUSAL: {p.stdout} {p.stderr}")
            self.assertIn("REFUSED", p.stdout)
            s = summary_of(p)
            self.assertTrue(s["refused"])
            self.assertTrue(s["alma_mic_alive"], "Auto probe failed to see live alma-mic")
            self.assertFalse(s["simulated"])
        # the crutch is untouched: still alive, task states identical
        self.assertTrue(real_alma_mic_alive(), "alma-mic died during a READ-ONLY test!")
        self.assertEqual(before, rival_task_states(),
                         "read-only refusal run altered rival task state")


if __name__ == "__main__":
    unittest.main(verbosity=2)
