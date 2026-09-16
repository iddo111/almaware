# -*- coding: utf-8 -*-
"""Decoy tests for FOREMAN's gates.

Iddo's law: an untested safety rule is not a real rule -- and you NEVER
demonstrate a gate against a living system, only against a decoy.

So every test here writes into a throwaway temp dir. Nothing touches
foreman/out, keshev-4d, or any real project. Each test names the real
failure it would have caught.

Run:  python test_gates.py
"""
import json
import pathlib
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import foreman as F  # noqa: E402


class GateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="foreman-decoy-"))
        # The decoy becomes an allowed root so the containment gate lets
        # legitimate writes through; the real roots stay untouched.
        self._roots = list(F.ALLOWED_ROOTS)
        F.ALLOWED_ROOTS = [self.tmp]

    def tearDown(self):
        F.ALLOWED_ROOTS = self._roots
        shutil.rmtree(self.tmp, ignore_errors=True)

    def order(self, **kw):
        o = {"id": "DECOY", "lane": "decoy", "status": "open", "kind": "doc",
             "title": "decoy", "project": str(self.tmp),
             "target": str(self.tmp / "out.md"),
             "min_chars": 50, "must_contain": [], "prompt": "x"}
        o.update(kw)
        return o

    # ---- gate 1: truncation the model admits to -------------------------
    def test_rejects_finish_reason_length(self):
        """Would have caught all 69 pages cut off at max_tokens."""
        text = "## one\n" + ("word " * 200) + "end."
        ok, why = F.validate_doc(self.order(), text, finish_reason="length")
        self.assertFalse(ok)
        self.assertIn("truncated", why)
        self.assertFalse((self.tmp / "out.md").exists(), "must not write a cut page")

    # ---- gate 2: truncation the model hides -----------------------------
    def test_rejects_mid_word_ending(self):
        """The real accepted file ended '...ותזכור לשחקן לקפ' and passed."""
        text = "## one\n" + ("word " * 200) + "ותזכור לשחקן לקפ"
        ok, why = F.validate_doc(self.order(), text, finish_reason="stop")
        self.assertFalse(ok)
        self.assertIn("mid-sentence", why)

    # ---- gate 3: silently dropped items ---------------------------------
    def test_rejects_missing_sections(self):
        """59 of 100 pages covered fewer ideas than ordered. 24 had none."""
        text = "## one\n" + ("word " * 200) + "done."
        o = self.order(idea_range=[1, 10])          # ordered 10 ideas
        ok, why = F.validate_doc(o, text, finish_reason="stop")
        self.assertFalse(ok)
        self.assertIn("covered 1 of 10", why)

    def test_rejects_zero_headings(self):
        text = ("word " * 200) + "done."
        o = self.order(idea_range=[1, 3])
        ok, why = F.validate_doc(o, text, finish_reason="stop")
        self.assertFalse(ok)
        self.assertIn("covered 0 of 3", why)

    # ---- gate 4: write containment --------------------------------------
    def test_blocks_write_outside_allowed_roots(self):
        """The docstring promised this for a month; nothing enforced it."""
        escape = pathlib.Path(tempfile.gettempdir()) / "foreman-ESCAPED.md"
        if escape.exists():
            escape.unlink()
        text = "## one\n" + ("word " * 200) + "done."
        o = self.order(target=str(escape))
        ok, why = F.validate_doc(o, text, finish_reason="stop")
        self.assertFalse(ok)
        self.assertIn("BLOCKED", why)
        self.assertFalse(escape.exists(), "the gate must prevent the write itself")

    def test_blocks_traversal_out_of_root(self):
        sneaky = self.tmp / "sub" / ".." / ".." / "foreman-TRAVERSED.md"
        text = "## one\n" + ("word " * 200) + "done."
        ok, why = F.validate_doc(self.order(target=str(sneaky)), text, "stop")
        self.assertFalse(ok)
        self.assertIn("BLOCKED", why)

    # ---- the happy path still works -------------------------------------
    def test_accepts_a_genuinely_complete_page(self):
        text = "\n".join("## idea %d\n%s done." % (i, "word " * 40)
                         for i in range(1, 4))
        o = self.order(idea_range=[1, 3], must_contain=["idea 2"])
        ok, why = F.validate_doc(o, text, finish_reason="stop")
        self.assertTrue(ok, why)
        self.assertIn("3 sections", why)
        self.assertTrue((self.tmp / "out.md").exists())
        self.assertEqual((self.tmp / "out.md").read_text(encoding="utf-8"), text)

    def test_write_is_atomic_no_tmp_left_behind(self):
        text = "\n".join("## idea %d\n%s done." % (i, "word " * 40)
                         for i in range(1, 3))
        F.validate_doc(self.order(idea_range=[1, 2]), text, "stop")
        leftovers = list(self.tmp.glob("*.tmp"))
        self.assertEqual(leftovers, [], "atomic write must leave no .tmp")

    # ---- gate 5: the stop button ----------------------------------------
    def test_halt_switch(self):
        real = F.STATE
        F.STATE = self.tmp / "whip_state.json"
        try:
            self.assertIsNone(F.halted(), "no file means running")
            F.STATE.write_text(json.dumps({"halt": True, "by": "decoy"}),
                               encoding="utf-8")
            self.assertIsNotNone(F.halted())
            self.assertEqual(F.halted()["by"], "decoy")
            F.STATE.write_text(json.dumps({"halt": False}), encoding="utf-8")
            self.assertIsNone(F.halted(), "halt:false means running")
        finally:
            F.STATE = real

    # ---- gate 6: lanes come from the router, not from memory ------------
    def test_lanes_fall_back_loudly_when_router_is_down(self):
        real = F.MODELS_URL
        F.MODELS_URL = "http://127.0.0.1:9/nope"      # discard port, refuses fast
        try:
            lanes, src = F.live_lanes()
            self.assertTrue(src.startswith("fallback:"), src)
            self.assertEqual(lanes, F.LANES_FALLBACK)
        finally:
            F.MODELS_URL = real


if __name__ == "__main__":
    unittest.main(verbosity=2)
