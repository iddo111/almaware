from __future__ import annotations

import subprocess
import sys
import unittest
from unittest import mock

import task_policy
import worker


class WorkerSecurityTests(unittest.TestCase):
    def test_token_is_mandatory_and_has_no_default(self):
        for value in ("", "alma", "short"):
            with self.assertRaises(ValueError):
                worker.validate_token(value)
        self.assertEqual(worker.validate_token("a" * 24), "a" * 24)

    def test_remote_cleartext_coordinator_is_rejected(self):
        self.assertEqual(
            worker.validate_coordinator_url("http://127.0.0.1:8900"),
            "http://127.0.0.1:8900",
        )
        self.assertEqual(
            worker.validate_coordinator_url("https://grid.example.test"),
            "https://grid.example.test",
        )
        for value in (
            "http://<lan-ip>:8900",
            "http://<tailnet-ip>:8900",
            "https://user:pass@example.test",
            "https://example.test/api",
        ):
            with self.assertRaises(ValueError):
                worker.validate_coordinator_url(value)

    def test_command_strings_and_unknown_tasks_are_rejected(self):
        attacks = (
            "whoami & calc.exe",
            {"kind": "process", "argv": ["cmd.exe", "/c", "calc.exe"]},
            {"kind": "python.version", "argv": ["-c", "import os; os.system('calc')"]},
            {"kind": "system.info", "extra": "$(whoami)"},
        )
        for attack in attacks:
            with self.assertRaises(task_policy.PolicyError):
                task_policy.validate_task(attack)

    def test_dry_run_never_starts_a_process(self):
        with mock.patch.object(worker.subprocess, "run") as run:
            output, return_code = worker.run_task(
                {"kind": "python.version"}, dry_run=True
            )
        self.assertEqual(return_code, 0)
        self.assertIn('"dry_run": true', output)
        run.assert_not_called()

    def test_only_exact_argv_executes_without_a_shell(self):
        completed = subprocess.CompletedProcess(
            [sys.executable, "--version"], 0, "Python test\n", ""
        )
        with mock.patch.object(worker.subprocess, "run", return_value=completed) as run:
            output, return_code = worker.run_task(
                {"kind": "python.version"}, dry_run=False
            )
        self.assertEqual((output, return_code), ("Python test", 0))
        run.assert_called_once_with(
            [sys.executable, "--version"],
            shell=False,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )

    def test_echo_metacharacters_are_data_not_code(self):
        message = "hello & calc.exe | $(whoami); rm -rf /"
        with mock.patch.object(worker.subprocess, "run") as run:
            output, return_code = worker.run_task(
                {"kind": "diagnostic.echo", "message": message}, dry_run=False
            )
        self.assertEqual((output, return_code), (message, 0))
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
