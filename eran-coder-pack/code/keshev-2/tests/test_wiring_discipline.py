"""THE WIRING LAW — a module only its own test imports is not shipped.

Inherited from KESHEV A (tests/test_wiring_discipline.py there), where five
separate guards were written, wired, tested — and structurally unable to
fire. The countermeasure is mechanical: production reachability asserted by
ast, plus seam tests BY BEHAVIOR for the guards that matter most."""
from __future__ import annotations

import ast
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO = Path(__file__).resolve().parent.parent
K2 = REPO / "k2"
PRODUCTION_DIRS = ("k2",)

# Legitimately standalone, with the reason. Adding a name here is a
# deliberate act and needs a reason next to it.
ALLOWED_UNWIRED = {
    "app": "the entry point itself — nothing above it to import it",
}


def _module_names(pkg: Path) -> set[str]:
    return {p.stem for p in pkg.glob("*.py") if p.stem != "__init__"}


def _imported_names(py: Path) -> set[str]:
    try:
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
    except SyntaxError:
        return set()
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                found.update(a.name.split("."))
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                found.update(node.module.split("."))
            for a in node.names:
                found.add(a.name)
    return found


def _production_files() -> list[Path]:
    out: list[Path] = []
    for d in PRODUCTION_DIRS:
        out.extend((REPO / d).rglob("*.py"))
    return [p for p in out
            if "__pycache__" not in p.parts and p.name != "__init__.py"]


class WiringDiscipline(unittest.TestCase):

    def test_every_k2_module_is_reachable_from_production(self):
        modules = _module_names(K2)
        prod = _production_files()
        orphans = []
        for name in sorted(modules):
            if name in ALLOWED_UNWIRED:
                continue
            importers = [p for p in prod
                         if p.stem != name and name in _imported_names(p)]
            if not importers:
                orphans.append(name)
        self.assertEqual(
            orphans, [],
            "these k2 modules are imported by NO production file — tested, "
            "maybe perfect, and they do not run:\n  " + "\n  ".join(orphans))

    def test_no_module_is_imported_only_by_its_own_tests(self):
        modules = _module_names(K2)
        prod = _production_files()
        tests = [p for p in (REPO / "tests").rglob("*.py")
                 if "__pycache__" not in p.parts]
        guilty = []
        for name in sorted(modules):
            if name in ALLOWED_UNWIRED:
                continue
            in_prod = any(p.stem != name and name in _imported_names(p)
                          for p in prod)
            in_test = any(name in _imported_names(p) for p in tests)
            if in_test and not in_prod:
                guilty.append(name)
        self.assertEqual(
            guilty, [],
            "imported by tests/ and nothing else — a green suite over a "
            "module the program never loads:\n  " + "\n  ".join(guilty))


class SeamsByBehavior(unittest.TestCase):
    """Not 'is the collaborator injected' — DOES the assembled thing act."""

    def _cfg(self, td, **over):
        from k2 import configstore
        token = Path(td) / "tok"
        token.write_text("test-token\n", encoding="utf-8")
        data = {
            "server_url": "http://<lan-ip>:8737",
            "server_token_path": str(token),
            "lang_hint_default": "he",
            "armed_mode": False,
            "enter_idle_limit_s": 120,
            "type_idle_limit_s": 600,
            "arm_timeout_s": 900,
            "never_use_devices_extra": [],
            "revision": 1,
        }
        data.update(over)
        p = Path(td) / "k2.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        return configstore.ConfigStore(p).load()

    class _ActiveOwner:
        """Deterministic idle clock: the owner touched the machine 5s ago.
        Injected because the REAL clock flips these tests when Iddo walks
        away — which it did, 22:20 on night one: the presence gate fired
        on the real machine in the middle of the suite. The gate was
        right; the test was environmental."""

        def idle_seconds(self):
            return 5.0

    def test_armed_mode_config_reaches_the_typing_decision(self):
        """THE seam that must never die: config armed_mode=true means the
        assembled decide() REFUSES typing until armed. If this breaks, the
        arm switch is a K15-tray — built, honest, invisible."""
        from k2 import app, journal
        with TemporaryDirectory() as td:
            jr = journal.Journal(Path(td) / "state", "abcd1234")
            try:
                decide, typer, stt = app.build(self._cfg(td, armed_mode=True),
                                               jr,
                                               idle_api=self._ActiveOwner())
                d = decide()
                self.assertFalse(
                    d.may_type,
                    "armed_mode=true in config did NOT reach the assembled "
                    "typing decision — the arm layer is disconnected")
                self.assertEqual(d.reason, "disarmed")
            finally:
                jr.close()

    def test_unarmed_default_config_permits(self):
        from k2 import app, journal
        with TemporaryDirectory() as td:
            jr = journal.Journal(Path(td) / "state", "abcd1234")
            try:
                decide, typer, stt = app.build(
                    self._cfg(td), jr, idle_api=self._ActiveOwner())
                self.assertTrue(decide().may_type)
            finally:
                jr.close()

    def test_typer_gate_seam_is_the_combined_decision(self):
        """The typer's injected decide must be app.build's closure over
        combined_decision — not a default, not a lambda True."""
        from k2 import app, journal
        with TemporaryDirectory() as td:
            jr = journal.Journal(Path(td) / "state", "abcd1234")
            try:
                decide, typer, stt = app.build(self._cfg(td), jr)
                self.assertIs(typer._decide, decide)
            finally:
                jr.close()

    def test_interlock_probe_is_openmutex_not_createmutex(self):
        """The read-only probe must never be 'upgraded' to CreateMutexW —
        that would squat A's name and block A's next start (D-002)."""
        src = (K2 / "interlock.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        probe = next(n for n in ast.walk(tree)
                     if isinstance(n, ast.FunctionDef)
                     and n.name == "probe_rival_mutex")
        probe_src = ast.get_source_segment(src, probe)
        self.assertIn("OpenMutexW", probe_src)
        self.assertNotIn("CreateMutexW", probe_src)

    def test_config_auto_refusal_is_reachable(self):
        """The 'auto' refusal must fire on a real config load, not only
        exist as a validator."""
        from k2 import configstore
        with TemporaryDirectory() as td:
            with self.assertRaises(configstore.ConfigHaltError):
                self._cfg(td, lang_hint_default="auto")


if __name__ == "__main__":
    unittest.main()
