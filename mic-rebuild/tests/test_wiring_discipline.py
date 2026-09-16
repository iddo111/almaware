"""THE WIRING LAW — a module that only its own test imports is not shipped.

WHY THIS FILE EXISTS. Every single defect found in this repo on 2026-08-12/13 was
the SAME defect wearing different clothes, and none of them was a logic error:

  client/textguard.py   written, correct, well tested — and imported by NOTHING but
                        its own test. The router still ran K12's placeholder guard, so
                        an assembled Router typed 'תודה רבה', the Amara subtitle credit
                        and Arabic subscribe boilerplate straight through. Commit
                        a680f56 said "textguard gets the router guard_fn seam, proven
                        end-to-end" and never opened client/router.py.
  client/router.py      written, 51 tests green — and imported by NOTHING but its own
                        test until client/app.py landed.
  server/sdnotify.py    written, correct, AND wired — but petting every 300 s against a
                        90 s watchdog, so systemd SIGABRT'd the server five times and
                        gave up on the unit.

The modules were never the problem. THE SEAMS WERE. And the tests could not see it,
because every one of them injected the collaborator by hand:

    Router(guard_fn=lambda res: ...)      # passes forever, proves nothing about the app

A test that supplies the dependency it is meant to verify cannot fail when the
dependency is missing. That is how a green suite hid a mic that typed hallucinations.

WHAT THIS FILE ASSERTS, mechanically, so nobody has to remember it:
  1. every module under client/ is imported by PRODUCTION code, not only by tests
  2. the specific seams that have already broken stay wired, by identity
  3. no module is imported EXCLUSIVELY by tests/ (the general form of bug #1)

Deliberately mechanical and dependency-free: stdlib ast + pathlib, no imports of the
modules themselves, so this stays fast and cannot be defeated by an import side effect.
"""
from __future__ import annotations

import ast
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CLIENT = REPO / "client"
PRODUCTION_DIRS = ("client", "server", "common", "tools")

# Modules that are legitimately standalone entry points or fixtures, with the reason.
# Adding a name here is a deliberate act and needs a reason next to it.
ALLOWED_UNWIRED = {
    "app": "the entry point itself — nothing above it to import it",
    "selftest": "manual diagnostic, run by hand (criterion 8)",
    "_selftest_target": "fixture process spawned by selftest, never imported",
    "_selftest_console": "fixture process spawned by selftest, never imported",
    "keshev_worker": "decode subprocess — spawned via python -m, not imported",
    "pulse": "standalone diagnostic CLI (python -m client.pulse): EAR opens "
             "the CAPTURE DEVICE, so the live app must never import or run "
             "it while it holds the mic — a second BRIO capture is the "
             "double-mic scar. Run by hand, or by the watchdog ONLY when "
             "the app is confirmed down. Wiring it into KESHEV 2's "
             "supervisor is on INSIGHTS-FOR-KESHEV2.md.",
}


def _module_names(pkg: Path) -> set[str]:
    return {p.stem for p in pkg.glob("*.py") if p.stem != "__init__"}


def _imported_names(py: Path) -> set[str]:
    """Every module name this file imports, however it spells it."""
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
            # `from client import textguard` — the names ARE modules
            for a in node.names:
                found.add(a.name)
    return found


def _production_files() -> list[Path]:
    out: list[Path] = []
    for d in PRODUCTION_DIRS:
        out.extend((REPO / d).rglob("*.py"))
    return [p for p in out if "__pycache__" not in p.parts and p.name != "__init__.py"]


class WiringDiscipline(unittest.TestCase):

    def test_every_client_module_is_reachable_from_production(self):
        """The general law. This is the test that would have caught textguard."""
        modules = _module_names(CLIENT)
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
            "these client modules are imported by NO production file — they are "
            "tested, they may be perfect, and they do not run:\n  "
            + "\n  ".join(orphans)
            + "\nWire them, or add them to ALLOWED_UNWIRED with a reason.")

    def test_no_module_is_imported_only_by_its_own_tests(self):
        """The exact shape of the textguard bug, stated as a rule."""
        modules = _module_names(CLIENT)
        prod = _production_files()
        tests = [p for p in (REPO / "tests").rglob("*.py")
                 if "__pycache__" not in p.parts]
        guilty = []
        for name in sorted(modules):
            if name in ALLOWED_UNWIRED:
                continue
            in_prod = any(p.stem != name and name in _imported_names(p) for p in prod)
            in_test = any(name in _imported_names(p) for p in tests)
            if in_test and not in_prod:
                guilty.append(name)
        self.assertEqual(
            guilty, [],
            "imported by tests/ and by nothing else. A green suite over a module "
            "the program never loads is a green suite over nothing:\n  "
            + "\n  ".join(guilty))


class SeamsThatHaveAlreadyBroken(unittest.TestCase):
    """Regression by IDENTITY, not by mock. Each of these has failed in real life."""

    def _app(self):
        import client.app as app
        return app

    def test_router_guard_is_textguard_not_the_k12_placeholder(self):
        """a680f56 claimed this was done. It was not. Codex caught it by running it."""
        import client.router as router
        from client import textguard
        guard = self._app().resolve_guard_fn()
        self.assertIsNot(
            guard, router.default_guard,
            "the router is still running K12's placeholder guard: an assembled "
            "Router will type 'תודה רבה' and subtitle credits verbatim")
        self.assertIs(guard, textguard.guard,
                      "guard_fn must BE textguard.guard, not merely something callable")

    def test_watchdog_pet_is_faster_than_the_kill(self):
        """The eran1 bug: petting every 300 s against a 90 s watchdog."""
        import re
        from common import protocol
        unit = (REPO / "server" / "keshev-stt.service").read_text(encoding="utf-8")
        m = re.search(r"^WatchdogSec[=\s]+(\d+)", unit, re.M)
        self.assertIsNotNone(m, "WatchdogSec vanished from the unit file")
        self.assertLessEqual(protocol.PET_INTERVAL_S, int(m.group(1)) / 2)


if __name__ == "__main__":
    unittest.main()
