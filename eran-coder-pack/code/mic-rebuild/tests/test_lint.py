"""K0 acceptance tests for tools/lint.py — every gate must FIRE and exit nonzero.

Banned tokens in fixture content are assembled by concatenation so this test
file itself never trips the gates when the repo is scanned.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LINT = REPO / "tools" / "lint.py"
sys.path.insert(0, str(REPO / "tools"))
import lint  # noqa: E402


def make_fixture(td: Path, kind: str) -> None:
    (td / "client").mkdir(exist_ok=True)
    ip = "initial" + "_prompt"
    if kind == "except_pass":
        (td / "bad.py").write_text("try:\n    f()\nexcept Exception:\n    pass\n", encoding="utf-8")
    elif kind == "ctx_prompt":
        (td / "bad.py").write_text(f"kw = {{'{ip}': prev_text}}\n", encoding="utf-8")
    elif kind == "json_dump":
        (td / "bad.py").write_text("import json\njson." + "dump(cfg, fh)\n", encoding="utf-8")
    elif kind == "bak_file":
        (td / ("client.json" + ".bak-1")).write_text("{}", encoding="utf-8")
    elif kind == "torch_client":
        (td / "client" / "bad.py").write_text("from " + "torch import cuda\n", encoding="utf-8")
    elif kind == "audio_output":
        (td / "bad.py").write_text("s = sounddevice." + "play(pcm)\n", encoding="utf-8")
    else:
        raise ValueError(kind)


class GateFires(unittest.TestCase):
    """Each gate detects its violation via the library API."""

    def check(self, kind: str, gate, code: str):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            make_fixture(root, kind)
            findings = gate(root)
            self.assertTrue(findings, f"{code} did not fire on {kind}")
            self.assertTrue(all(f.startswith(code) for f in findings), findings)

    def test_g1_except_pass(self):
        self.check("except_pass", lint.gate_except_pass, "G1")

    def test_g2_initial_prompt(self):
        self.check("ctx_prompt", lint.gate_initial_prompt, "G2")

    def test_g3_json_dump(self):
        self.check("json_dump", lint.gate_json_dump, "G3")

    def test_g3_configstore_is_allowed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "client").mkdir()
            (root / "client" / "configstore.py").write_text(
                "import json\n\ndef set_key(cfg, fh):\n    json." + "dump(cfg, fh)\n", encoding="utf-8")
            self.assertEqual(lint.gate_json_dump(root), [])

    def test_g4_bak_file(self):
        self.check("bak_file", lint.gate_bak_files, "G4")

    def test_g5_torch_under_client(self):
        self.check("torch_client", lint.gate_torch_client, "G5")

    def test_g5_ignores_torch_outside_client_and_common(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "server").mkdir()
            (root / "server" / "x.py").write_text("import " + "torch\n", encoding="utf-8")
            self.assertEqual(lint.gate_torch_client(root), [])

    def test_g6_audio_output(self):
        self.check("audio_output", lint.gate_audio_output, "G6")


class ExitCodes(unittest.TestCase):
    """The runnable script exits nonzero on violation, zero when clean."""

    def run_lint(self, root: Path):
        return subprocess.run([sys.executable, str(LINT), "--root", str(root)],
                              capture_output=True, text=True)

    def test_nonzero_on_each_violation(self):
        for kind in ("except_pass", "ctx_prompt", "json_dump", "bak_file",
                     "torch_client", "audio_output"):
            with tempfile.TemporaryDirectory() as td:
                make_fixture(Path(td), kind)
                r = self.run_lint(Path(td))
                self.assertEqual(r.returncode, 1, f"{kind}: rc={r.returncode}\n{r.stdout}{r.stderr}")
                self.assertIn("LINT FAIL", r.stdout)

    def test_zero_on_clean_tree(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "ok.py").write_text("x = 1\n", encoding="utf-8")
            r = self.run_lint(Path(td))
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("LINT PASS", r.stdout)

    def test_self_test_passes(self):
        r = subprocess.run([sys.executable, str(LINT), "--self-test"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("SELF-TEST PASS", r.stdout)

    def test_repo_itself_is_clean(self):
        r = self.run_lint(REPO)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
