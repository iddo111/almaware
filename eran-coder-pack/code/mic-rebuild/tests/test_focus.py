"""K14 TDD tests — client/focus.py (PHASE2-DESIGN.md section 2 focus.py row,
K14 milestone row; PHASE1-INQUIRY.md scars 34/35/37/38, criterion 9 logic).

The guard's laws, each mapped to a real mis-type from the scar register:

  scar 34  compare windows by HWND+PID+image-path, NEVER title (terminal
           spinners rewrite titles every tick); strip Unicode Cf controls
           before ANY match (spoofed exe names / RTL-wrapped titles); deny
           browser top-levels in allowlist mode (top-level HWND cannot
           distinguish chat content from the address bar); hard-block
           title-less windows EVEN in "anywhere" mode (typing into the
           desktop renames files); own-window hard block (feedback loop);
           restore focus to the last-external target — Z-order-behind
           first, watcher memory second — and VERIFY the change.
  scar 35  refusal is a real, honest error — never a silent drop; every
           refusal emits FOCUS_BLOCK (exe names only, never titles).
  scar 38  the guard itself never launches apps; restoring focus to the
           window the user was just in is the ONE sanctioned focus move.

Everything here runs against a deterministic FakeApi — no real windows, no
focus theft (focus-courtesy guardrail): the real-window proof lives in
tests/test_selftest_uipi.py behind the focus_intrusive marker.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from client.focus import (  # noqa: E402
    BROWSER_EXES,
    TERMINAL_EXES,
    FocusChangedError,
    FocusGuard,
    FocusGuardError,
    Target,
    clean_image_path,
    exe_name,
    is_browser,
    is_terminal,
    same_target,
    strip_cf,
)

OWN_PID = 4242


class FakeApi:
    """Deterministic stand-in for the Win32 window layer."""

    def __init__(self):
        self.windows: dict[int, dict] = {}   # hwnd -> {title, pid, image_path, visible}
        self.foreground: int = 0
        self.behind: dict[int, list[int]] = {}
        self.restore_calls: list[int] = []
        self.restore_ok: set[int] = set()    # hwnds restore_focus succeeds for

    def add(self, hwnd, title, pid, image_path, visible=True):
        self.windows[hwnd] = {"title": title, "pid": pid,
                              "image_path": image_path, "visible": visible}

    # --- the interface focus.py consumes ---
    def foreground_hwnd(self) -> int:
        return self.foreground

    def window_title(self, hwnd) -> str:
        w = self.windows.get(hwnd)
        return w["title"] if w else ""

    def process_identity(self, hwnd):
        w = self.windows.get(hwnd)
        return (w["pid"], w["image_path"]) if w else (0, "")

    def restore_focus(self, hwnd) -> bool:
        self.restore_calls.append(hwnd)
        if hwnd in self.restore_ok:
            self.foreground = hwnd
            return True
        return False

    def windows_behind(self, hwnd, limit=8):
        return list(self.behind.get(hwnd, ()))[:limit]


def guard_with(api, emit=None, anywhere=True, targets=()):
    g = FocusGuard(api=api, own_pid=OWN_PID, emit=emit)
    g.set_policy(anywhere=anywhere, targets=targets)
    return g


class EmitRecorder:
    def __init__(self):
        self.events: list[tuple[str, dict]] = []

    def __call__(self, evt, **fields):
        self.events.append((evt, fields))

    def blocks(self):
        return [f for e, f in self.events if e == "FOCUS_BLOCK"]


# ------------------------------------------------------------- pure helpers


class CfStrippingTests(unittest.TestCase):
    """Scar 34: Unicode Cf controls stripped before ANY match."""

    def test_strip_cf_removes_format_controls(self):
        # RLM, LRM, ZWSP, ZWJ are all category Cf
        self.assertEqual(strip_cf("a\u200fb\u200ec\u200bd\u200de"), "abcde")

    def test_strip_cf_keeps_hebrew_and_spaces(self):
        self.assertEqual(strip_cf("שלום עולם 12"), "שלום עולם 12")

    def test_exe_name_strips_cf_from_spoofed_path(self):
        # an exe name spoofed with an invisible RLM must still match
        spoofed = "C:\\Program Files\\Goo\u200egle\\Chrome\\chr\u200fome.exe"
        self.assertEqual(exe_name(spoofed), "chrome.exe")

    def test_clean_image_path_normalizes_prefix_and_slashes(self):
        self.assertEqual(
            clean_image_path("\\\\?\\C:/Windows/notepad.exe"),
            "C:\\Windows\\notepad.exe",
        )

    def test_is_browser_matches_cf_spoofed_exe(self):
        self.assertTrue(is_browser("C:\\x\\chro\u200bme.exe"))

    def test_is_terminal_covers_windows_terminal(self):
        self.assertTrue(is_terminal("C:\\wt\\WindowsTerminal.exe"))
        self.assertFalse(is_terminal("C:\\x\\notepad.exe"))

    def test_browser_and_terminal_sets_are_disjoint_and_nonempty(self):
        self.assertTrue(BROWSER_EXES and TERMINAL_EXES)
        self.assertFalse(set(BROWSER_EXES) & set(TERMINAL_EXES))


class SameTargetTests(unittest.TestCase):
    """Scar 34: identity is HWND+PID+image-path, NEVER the caption."""

    def test_spinner_title_change_is_same_target(self):
        a = Target(527370, "\u2802 security-fix-fleet-plan", 3532, "C:\\wt\\WindowsTerminal.exe")
        b = Target(527370, "\u2810 security-fix-fleet-plan", 3532, "C:\\wt\\WindowsTerminal.exe")
        self.assertTrue(same_target(a, b))

    def test_different_hwnd_is_not_same(self):
        a = Target(1, "x", 10, "C:\\a.exe")
        b = Target(2, "x", 10, "C:\\a.exe")
        self.assertFalse(same_target(a, b))

    def test_different_pid_is_not_same(self):
        a = Target(1, "x", 10, "C:\\a.exe")
        b = Target(1, "x", 11, "C:\\a.exe")
        self.assertFalse(same_target(a, b))

    def test_image_path_compare_is_normalized_case_insensitive(self):
        a = Target(1, "x", 10, "\\\\?\\C:/Apps/App.EXE")
        b = Target(1, "y", 10, "c:\\apps\\app.exe")
        self.assertTrue(same_target(a, b))


# --------------------------------------------------------------- guard core


class GuardBasicTests(unittest.TestCase):
    def test_no_foreground_window_refused(self):
        api, emit = FakeApi(), EmitRecorder()
        g = guard_with(api, emit)
        with self.assertRaises(FocusGuardError) as cm:
            g.require_allowed_target()
        self.assertEqual(cm.exception.reason, "no_window")
        self.assertEqual(emit.blocks()[0]["reason"], "no_window")

    def test_titled_external_window_allowed_in_anywhere_mode(self):
        api = FakeApi()
        api.add(100, "Notepad - notes.txt", 555, "C:\\Windows\\notepad.exe")
        api.foreground = 100
        g = guard_with(api, anywhere=True)
        t = g.require_allowed_target()
        self.assertEqual((t.hwnd, t.pid), (100, 555))

    def test_titleless_window_hard_blocked_even_in_anywhere_mode(self):
        """Scar 34: typing into the desktop renames files."""
        api, emit = FakeApi(), EmitRecorder()
        api.add(100, "", 555, "C:\\Windows\\explorer.exe")
        api.foreground = 100
        g = guard_with(api, emit, anywhere=True)
        with self.assertRaises(FocusGuardError) as cm:
            g.require_allowed_target()
        self.assertEqual(cm.exception.reason, "no_title")
        # the error is HONEST: it names the image path so Iddo can see who held focus
        self.assertIn("explorer.exe", str(cm.exception))

    def test_cf_only_title_is_titleless(self):
        api = FakeApi()
        api.add(100, "\u200f\u200e", 555, "C:\\Windows\\explorer.exe")
        api.foreground = 100
        g = guard_with(api, anywhere=True)
        with self.assertRaises(FocusGuardError) as cm:
            g.require_allowed_target()
        self.assertEqual(cm.exception.reason, "no_title")

    def test_every_refusal_emits_focus_block_with_exe_never_title(self):
        api, emit = FakeApi(), EmitRecorder()
        api.add(100, "", 555, "C:\\Windows\\explorer.exe")
        api.foreground = 100
        g = guard_with(api, emit, anywhere=True)
        with self.assertRaises(FocusGuardError):
            g.require_allowed_target()
        blocks = emit.blocks()
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0]["exe"], "explorer.exe")
        self.assertNotIn("title", blocks[0])  # privacy: EXE names only


class AllowlistModeTests(unittest.TestCase):
    def test_browser_top_level_denied_in_allowlist_mode(self):
        """Scar 34 / K14 row: top-level HWND cannot distinguish page from address bar."""
        api, emit = FakeApi(), EmitRecorder()
        api.add(100, "Claude - Google Chrome", 555,
                "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe")
        api.foreground = 100
        g = guard_with(api, emit, anywhere=False, targets=("claude",))
        with self.assertRaises(FocusGuardError) as cm:
            g.require_allowed_target()
        self.assertEqual(cm.exception.reason, "browser_allowlist")

    def test_browser_denied_even_when_exe_is_cf_spoofed(self):
        api = FakeApi()
        api.add(100, "Claude - Google Chrome", 555, "C:\\x\\chro\u200fme.exe")
        api.foreground = 100
        g = guard_with(api, anywhere=False, targets=("claude",))
        with self.assertRaises(FocusGuardError) as cm:
            g.require_allowed_target()
        self.assertEqual(cm.exception.reason, "browser_allowlist")

    def test_browser_allowed_in_anywhere_mode(self):
        api = FakeApi()
        api.add(100, "Claude - Google Chrome", 555,
                "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe")
        api.foreground = 100
        g = guard_with(api, anywhere=True)
        self.assertEqual(g.require_allowed_target().hwnd, 100)

    def test_allowlist_match_is_cf_stripped_casefolded_substring(self):
        api = FakeApi()
        api.add(100, "Draft \u200f| CLAUDE", 555, "C:\\Apps\\Claude\\claude.exe")
        api.foreground = 100
        g = guard_with(api, anywhere=False, targets=("claude",))
        self.assertEqual(g.require_allowed_target().hwnd, 100)

    def test_non_matching_window_refused_in_allowlist_mode(self):
        api, emit = FakeApi(), EmitRecorder()
        api.add(100, "Notepad", 555, "C:\\Windows\\notepad.exe")
        api.foreground = 100
        g = guard_with(api, emit, anywhere=False, targets=("claude",))
        with self.assertRaises(FocusGuardError) as cm:
            g.require_allowed_target()
        self.assertEqual(cm.exception.reason, "not_in_allowlist")

    def test_default_policy_fails_closed(self):
        """No policy set at all -> allowlist mode with zero targets -> refuse."""
        api = FakeApi()
        api.add(100, "Notepad", 555, "C:\\Windows\\notepad.exe")
        api.foreground = 100
        g = FocusGuard(api=api, own_pid=OWN_PID)
        with self.assertRaises(FocusGuardError):
            g.require_allowed_target()


class OwnWindowTests(unittest.TestCase):
    """Scar 34/38: the app's own window is a feedback loop — hard block,
    then put focus BACK where the user was (Z-order first, memory second)."""

    def _own_foreground(self, api):
        api.add(1, "KESHEV settings", OWN_PID, "C:\\Python312\\pythonw.exe")
        api.foreground = 1

    def test_own_pid_window_never_typed_into_no_candidates(self):
        api, emit = FakeApi(), EmitRecorder()
        self._own_foreground(api)
        g = guard_with(api, emit, anywhere=True)
        with self.assertRaises(FocusGuardError) as cm:
            g.require_allowed_target()
        self.assertEqual(cm.exception.reason, "own_window_unrecovered")

    def test_own_window_restores_zorder_candidate_first(self):
        api = FakeApi()
        self._own_foreground(api)
        api.add(200, "Notepad", 555, "C:\\Windows\\notepad.exe")
        api.add(300, "Word", 666, "C:\\Office\\winword.exe")
        api.behind[1] = [200, 300]
        api.restore_ok = {200, 300}
        g = guard_with(api, anywhere=True)
        # watcher remembered 300 earlier — Z-order (200) must still win
        api.foreground = 300
        g.note_foreground()
        api.foreground = 1
        t = g.require_allowed_target()
        self.assertEqual(t.hwnd, 200)
        self.assertEqual(api.restore_calls[0], 200)

    def test_own_window_falls_back_to_watcher_memory(self):
        api = FakeApi()
        self._own_foreground(api)
        api.add(300, "Word", 666, "C:\\Office\\winword.exe")
        api.behind[1] = []                      # nothing usable behind us
        api.restore_ok = {300}
        g = guard_with(api, anywhere=True)
        api.foreground = 300
        g.note_foreground()                     # watcher saw Word
        api.foreground = 1
        t = g.require_allowed_target()
        self.assertEqual(t.hwnd, 300)

    def test_restore_is_verified_failed_restore_refused(self):
        api, emit = FakeApi(), EmitRecorder()
        self._own_foreground(api)
        api.add(200, "Notepad", 555, "C:\\Windows\\notepad.exe")
        api.behind[1] = [200]
        api.restore_ok = set()                  # restore_focus lies? -> no foreground change
        g = guard_with(api, emit, anywhere=True)
        with self.assertRaises(FocusGuardError):
            g.require_allowed_target()

    def test_restored_target_must_itself_be_allowed(self):
        """Restoring into a browser in allowlist mode is still a refusal."""
        api = FakeApi()
        self._own_foreground(api)
        api.add(200, "Claude - Google Chrome", 555, "C:\\x\\chrome.exe")
        api.behind[1] = [200]
        api.restore_ok = {200}
        g = guard_with(api, anywhere=False, targets=("claude",))
        with self.assertRaises(FocusGuardError):
            g.require_allowed_target()

    def test_own_title_marker_blocked_even_with_foreign_pid(self):
        api = FakeApi()
        api.add(1, "KESHEV tray", 9999, "C:\\other\\host.exe")
        api.foreground = 1
        g = guard_with(api, anywhere=True)
        with self.assertRaises(FocusGuardError):
            g.require_allowed_target()


class WatcherTests(unittest.TestCase):
    def test_watcher_records_external_windows_only(self):
        api = FakeApi()
        api.add(1, "KESHEV", OWN_PID, "C:\\py\\pythonw.exe")
        api.add(200, "Notepad", 555, "C:\\Windows\\notepad.exe")
        g = guard_with(api, anywhere=True)
        api.foreground = 200
        g.note_foreground()
        self.assertEqual(g.last_external().hwnd, 200)
        api.foreground = 1
        g.note_foreground()                     # own window must NOT overwrite memory
        self.assertEqual(g.last_external().hwnd, 200)

    def test_watcher_ignores_titleless(self):
        api = FakeApi()
        api.add(100, "", 555, "C:\\Windows\\explorer.exe")
        g = guard_with(api, anywhere=True)
        api.foreground = 100
        g.note_foreground()
        self.assertIsNone(g.last_external())

    def test_watch_interval_is_quarter_second(self):
        self.assertEqual(FocusGuard.WATCH_INTERVAL_S, 0.25)


class FocusChangedTests(unittest.TestCase):
    def test_focus_changed_error_is_a_guard_error(self):
        self.assertTrue(issubclass(FocusChangedError, FocusGuardError))


if __name__ == "__main__":
    unittest.main()
