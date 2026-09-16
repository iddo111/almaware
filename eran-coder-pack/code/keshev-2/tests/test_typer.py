"""Typer: the single door — dedup, gates inside, Enter re-verified AND
re-gated, paste-first, terminal fallback refusal, park-never-drop."""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from k2 import typer as typer_mod
from k2.presence import Decision
from k2.typer import Target, Typer, same_target, utf16_units, chunks


class FakeOs:
    """A scriptable OsLayer that records every call."""

    def __init__(self):
        self.fg = Target(100, 42, "chrome.exe")
        self.fg_sequence = None          # optional iterator of Targets
        self.clipboard_ok = True
        self.paste_ok = True
        self.enter_ok = True
        self.unicode_ok = True
        self.calls = []

    def _next_fg(self):
        if self.fg_sequence:
            try:
                self.fg = next(self.fg_sequence)
            except StopIteration:
                pass
        return self.fg

    def foreground(self):
        self.calls.append("foreground")
        return self._next_fg()

    def clipboard_set(self, text):
        self.calls.append(("clipboard_set", text))
        return self.clipboard_ok

    def send_paste(self):
        self.calls.append("send_paste")
        return self.paste_ok

    def send_enter(self):
        self.calls.append("send_enter")
        return self.enter_ok

    def send_unicode_chunk(self, units):
        self.calls.append(("unicode", tuple(units)))
        return self.unicode_ok

    def own_pid(self):
        return 999


class Harness:
    def __init__(self, td, decision=None, decisions=None):
        self.os = FakeOs()
        self.events = []
        self._decisions = list(decisions) if decisions else None
        self._decision = decision or Decision(True, True, 5.0, "")
        self.parked = Path(td) / "parked.txt"
        self.typer = Typer(
            os_layer=self.os,
            decide=self._decide,
            emit=lambda e, **f: self.events.append((e, f)),
            parked_path=self.parked,
            sleep=lambda s: None)

    def _decide(self):
        if self._decisions:
            return self._decisions.pop(0)
        return self._decision

    def parked_records(self):
        if not self.parked.exists():
            return []
        return [json.loads(x) for x in
                self.parked.read_text(encoding="utf-8").splitlines()]


class Dedup(unittest.TestCase):

    def test_same_rid_types_once(self):
        with TemporaryDirectory() as td:
            h = Harness(td)
            r1 = h.typer.type("שלום", "abcd1234-000001")
            r2 = h.typer.type("שלום", "abcd1234-000001")
            self.assertTrue(r1.typed)
            self.assertFalse(r2.typed)
            self.assertEqual(r2.reason, "duplicate")
            self.assertIn("DUP_DISCARD", [e for e, _ in h.events])
            pastes = [c for c in h.os.calls if c == "send_paste"]
            self.assertEqual(len(pastes), 1)

    def test_lru_bounded(self):
        with TemporaryDirectory() as td:
            h = Harness(td)
            for i in range(typer_mod.DEDUP_LRU_SIZE + 10):
                h.typer.type("x", f"abcd1234-{i:06d}")
            self.assertLessEqual(len(h.typer._seen),
                                 typer_mod.DEDUP_LRU_SIZE)


class GatesInsideTheDoor(unittest.TestCase):

    def test_gate_refusal_parks_and_never_touches_os(self):
        with TemporaryDirectory() as td:
            h = Harness(td, decision=Decision(False, False, 700.0,
                                              "owner_absent"))
            r = h.typer.type("סודי לגמרי", "abcd1234-000001")
            self.assertFalse(r.typed)
            self.assertEqual(h.os.calls, [])          # OS never touched
            recs = h.parked_records()
            self.assertEqual(recs[0]["text"], "סודי לגמרי")
            self.assertEqual(recs[0]["reason"], "gate:owner_absent")
            evts = dict(h.events)
            self.assertIn("TYPE_FAIL_PARKED", evts)
            self.assertNotIn("text", evts["TYPE_FAIL_PARKED"])  # len only

    def test_idle_types_but_never_enters(self):
        """The cheap half of 09:46 at the door."""
        with TemporaryDirectory() as td:
            h = Harness(td, decision=Decision(True, False, 200.0,
                                              "owner_idle_no_enter"))
            r = h.typer.type("טקסט", "abcd1234-000001", want_enter=True)
            self.assertTrue(r.typed)
            self.assertFalse(r.entered)
            self.assertNotIn("send_enter", h.os.calls)


class EnterDiscipline(unittest.TestCase):

    def test_enter_rechecks_gates_at_enter_time(self):
        """K2's improvement (D-003/D-006): permission at type time is not
        permission at Enter time. PROOF THE GUARD CAN FIRE."""
        with TemporaryDirectory() as td:
            h = Harness(td, decisions=[
                Decision(True, True, 5.0, ""),          # at type time
                Decision(True, False, 130.0,            # at Enter time
                         "owner_idle_no_enter"),
            ])
            r = h.typer.type("טקסט", "abcd1234-000001", want_enter=True)
            self.assertTrue(r.typed)
            self.assertFalse(r.entered)
            self.assertIn("enter_recheck", r.reason)
            self.assertNotIn("send_enter", h.os.calls)
            rej = [f for e, f in h.events if e == "PRESENCE_REJ"]
            self.assertTrue(any("enter_recheck" in f["reason"] for f in rej))

    def test_enter_refused_when_target_changed(self):
        """scar 36: re-verify the SAME window before Enter."""
        with TemporaryDirectory() as td:
            h = Harness(td)
            fgs = iter([
                Target(100, 42, "chrome.exe"),   # snapshot at type
                Target(100, 42, "chrome.exe"),   # post-paste verify
                Target(200, 77, "notepad.exe"),  # before Enter — MOVED
            ])
            h.os.fg_sequence = fgs
            r = h.typer.type("טקסט", "abcd1234-000001", want_enter=True)
            self.assertTrue(r.typed)
            self.assertFalse(r.entered)
            self.assertEqual(r.reason, "target_changed")
            self.assertNotIn("send_enter", h.os.calls)

    def test_full_success_path(self):
        with TemporaryDirectory() as td:
            h = Harness(td)
            r = h.typer.type("שלום עולם", "abcd1234-000001",
                             want_enter=True)
            self.assertEqual(r, (True, True, ""))
            typed = [f for e, f in h.events if e == "TYPED"]
            self.assertEqual(typed[0]["len"], 9)
            self.assertEqual(typed[0]["exe"], "chrome.exe")
            self.assertNotIn("text", typed[0])


class FocusRules(unittest.TestCase):

    def test_own_window_hard_block(self):
        with TemporaryDirectory() as td:
            h = Harness(td)
            h.os.fg = Target(5, 999, "python.exe")    # own pid
            r = h.typer.type("x", "abcd1234-000001")
            self.assertFalse(r.typed)
            self.assertEqual(r.reason, "own_window")
            self.assertEqual(h.parked_records()[0]["reason"],
                             "focus:own_window")

    def test_unverifiable_focus_parks(self):
        with TemporaryDirectory() as td:
            h = Harness(td)
            h.os.fg = None
            r = h.typer.type("x", "abcd1234-000001")
            self.assertFalse(r.typed)
            self.assertEqual(h.parked_records()[0]["reason"],
                             "focus:unverifiable")

    def test_same_target_never_compares_titles(self):
        """Target has no title field AT ALL — comparison by identity
        fields only (scar 34 made structural)."""
        self.assertNotIn("title", Target._fields)
        a = Target(1, 2, "x.exe")
        self.assertTrue(same_target(a, Target(1, 2, "x.exe")))
        self.assertFalse(same_target(a, Target(1, 3, "x.exe")))
        self.assertFalse(same_target(a, None))


class Delivery(unittest.TestCase):

    def test_paste_failure_in_terminal_parks_never_unicode(self):
        """Terminals discard KEYEVENTF_UNICODE while reporting success —
        the fallback is an honest refusal."""
        with TemporaryDirectory() as td:
            h = Harness(td)
            h.os.fg = Target(1, 42, "windowsterminal.exe")
            h.os.paste_ok = False
            r = h.typer.type("ls -la", "abcd1234-000001")
            self.assertFalse(r.typed)
            unicode_calls = [c for c in h.os.calls
                             if isinstance(c, tuple) and c[0] == "unicode"]
            self.assertEqual(unicode_calls, [])
            self.assertEqual(h.parked_records()[0]["reason"],
                             "terminal_paste_failed")

    def test_paste_failure_elsewhere_falls_back_chunked(self):
        with TemporaryDirectory() as td:
            h = Harness(td)
            h.os.clipboard_ok = False
            text = "א" * 80                            # 3 chunks of 32
            r = h.typer.type(text, "abcd1234-000001")
            self.assertTrue(r.typed)
            unicode_calls = [c for c in h.os.calls
                             if isinstance(c, tuple) and c[0] == "unicode"]
            self.assertEqual(len(unicode_calls), 3)
            self.assertEqual(sum(len(c[1]) for c in unicode_calls), 80)

    def test_fallback_aborts_on_focus_loss_mid_chunk(self):
        with TemporaryDirectory() as td:
            h = Harness(td)
            h.os.clipboard_ok = False
            fgs = iter([
                Target(1, 42, "chrome.exe"),     # type-time snapshot
                Target(1, 42, "chrome.exe"),     # chunk 1 check
                Target(9, 43, "other.exe"),      # chunk 2 check — moved
            ])
            h.os.fg_sequence = fgs
            r = h.typer.type("x" * 60, "abcd1234-000001")
            self.assertFalse(r.typed)
            self.assertEqual(h.parked_records()[0]["reason"],
                             "focus_lost_mid_fallback")

    def test_post_paste_focus_move_fails_delivery(self):
        with TemporaryDirectory() as td:
            h = Harness(td)
            fgs = iter([
                Target(1, 42, "chrome.exe"),
                Target(2, 50, "explorer.exe"),   # moved during paste
            ])
            h.os.fg_sequence = fgs
            h.os.clipboard_ok = True
            # paste "succeeds" but verification sees the wrong window;
            # fallback then also fails its focus check -> parked
            r = h.typer.type("y", "abcd1234-000001")
            self.assertFalse(r.typed)


class Utf16(unittest.TestCase):

    def test_bmp_chars_single_unit(self):
        self.assertEqual(utf16_units("אb"), [0x05D0, 0x62])

    def test_astral_chars_surrogate_pairs(self):
        units = utf16_units("👍")
        self.assertEqual(units, [0xD83D, 0xDC4D])

    def test_chunking(self):
        self.assertEqual([len(c) for c in chunks(list(range(70)), 32)],
                         [32, 32, 6])


class NoClipboardRestore(unittest.TestCase):

    def test_restore_capability_absent_from_module(self):
        """D-006: absent code cannot race. The word does not appear."""
        import inspect
        src = inspect.getsource(typer_mod)
        self.assertNotIn("restore_clipboard", src)
        self.assertNotIn("GetClipboardData", src)     # we never read it


if __name__ == "__main__":
    unittest.main()
