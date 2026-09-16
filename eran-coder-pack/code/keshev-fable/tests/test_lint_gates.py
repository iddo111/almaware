"""The 6 lint gates run UNDER pytest — so the suite can never be green while
the lint is broken. Born 2026-08-20: G5 had been BROKEN since fe52732
('OWNER_BLOCK' not in VOCAB), 97 tests were green, and the live mic raised
JournalVocabError on its first owner-block and lost its heartbeat for 4 h."""
from __future__ import annotations

import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _load_lint():
    spec = importlib.util.spec_from_file_location("keshev_lint", ROOT / "tools" / "lint.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


class LintGatesTests(unittest.TestCase):
    def test_all_six_gates_clean_over_app(self):
        lint = _load_lint()
        files = lint.py_files()
        self.assertTrue(files, "lint found no app files — wrong ROOT?")
        problems = [p for gate in lint.GATES for p in gate(files)]
        self.assertEqual(problems, [], "\n".join(problems))

    def test_every_journalled_name_in_app_is_in_vocab(self):
        """G5 restated directly, so the message names the offender."""
        import ast
        from app.journal import VOCAB
        bad = []
        for p in sorted((ROOT / "app").glob("*.py")):
            tree = ast.parse(p.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                        and node.func.attr == "event" and node.args
                        and isinstance(node.args[0], ast.Constant)
                        and isinstance(node.args[0].value, str)
                        and node.args[0].value not in VOCAB):
                    bad.append(f"{p.name}:{node.lineno} {node.args[0].value!r}")
        self.assertEqual(bad, [], f"journal names outside VOCAB: {bad}")

    def test_lint_self_test_still_fires_on_poison(self):
        lint = _load_lint()
        self.assertEqual(lint.self_test(), 0)


if __name__ == "__main__":
    unittest.main()
