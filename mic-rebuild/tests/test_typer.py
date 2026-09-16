"""K14 TDD tests — client/typer.py (PHASE2-DESIGN.md section 2 typer.py row,
K14 milestone row; PHASE1-INQUIRY.md scars 31/32/33/36, criterion 8 logic).

The typing laws, each mapped to a real production failure:

  scar 31  PASTE-FIRST for EVERY window (clipboard + Ctrl+V = 4 events,
           atomic — nothing to drop); per-char Unicode SendInput only as
           the fallback, WITH surrogate pairs, and CHUNKED so long bursts
           survive (the 79-char utterance whose spaces were stripped);
           terminals discard KEYEVENTF_UNICODE entirely — a failed paste
           into a terminal is an honest refusal, never a silent loss.
  scar 32  NO automatic clipboard restore (opt-in only; wait >= 1.0s;
           restore only if the clipboard still holds exactly what was
           pasted) — the 120-230ms restore race lost a night of Hebrew.
  scar 33  clipboard ctypes discipline lives in the real layer; the
           12x OpenClipboard retry contract is asserted as a constant.
  scar 36  auto-Enter is a SEPARATE burst after ~0.35s that re-verifies
           the SAME target — single-burst Enter submitted half lines.
  design   ONE serialization point: Typer.type is the only door and it
           holds a lock; refused text is PARKED (state\\parked.txt),
           recoverable, never dropped (scar 35).

All fakes — zero real SendInput, zero real clipboard, zero real windows
(focus-courtesy guardrail). The real-window proof is the UIPI selftest.
"""
from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from client.focus import FocusGuard, Target  # noqa: E402
from client.typer import (  # noqa: E402
    CLIPBOARD_OPEN_RETRIES,
    CLIPBOARD_RESTORE_WAIT_S,
    ENTER_DELAY_S,
    Outcome,
    Typer,
    utf16_units,
)
from tests.test_focus import OWN_PID, EmitRecorder, FakeApi  # noqa: E402


class FakeClip:
    def __init__(self, fail_set=False, initial="OLD-CLIPBOARD"):
        self.content = initial
        self.fail_set = fail_set
        self.set_calls: list[str] = []

    def get(self):
        return self.content

    def set(self, text):
        self.set_calls.append(text)
        if self.fail_set:
            return False
        self.content = text
        return True


class FakeInput:
    """Records every send_input burst as a list of event tuples."""

    def __init__(self):
        self.bursts: list[list[tuple]] = []

    def send_input(self, events):
        events = list(events)
        self.bursts.append(events)
        return len(events)


class SleepRecorder:
    def __init__(self):
        self.calls: list[float] = []

    def __call__(self, s):
        self.calls.append(s)


def make_typer(api=None, clip=None, inp=None, emit=None, anywhere=True,
               targets=(), clipboard_restore=False, state_dir=None, sleep=None):
    api = api or FakeApi()
    guard = FocusGuard(api=api, own_pid=OWN_PID, emit=emit)
    guard.set_policy(anywhere=anywhere, targets=targets)
    state_dir = state_dir or Path(tempfile.mkdtemp(prefix="keshev-typer-test-"))
    t = Typer(
        guard=guard,
        input_api=inp or FakeInput(),
        clip=clip if clip is not None else FakeClip(),
        state_dir=Path(state_dir),
        emit=emit,
        clipboard_restore=clipboard_restore,
        sleep=sleep or SleepRecorder(),
    )
    return t, api


def focus_notepad(api, hwnd=100, pid=555):
    api.add(hwnd, "Notepad - notes.txt", pid, "C:\\Windows\\notepad.exe")
    api.foreground = hwnd


def focus_terminal(api, hwnd=100, pid=555):
    api.add(hwnd, "pwsh in mic-rebuild", pid, "C:\\wt\\WindowsTerminal.exe")
    api.foreground = hwnd


HE_EN = "מה עם אפליקציית המיקרופון? Can you fix it please? גם בעברית עם רווחים 12345"


class PasteFirstTests(unittest.TestCase):
    def test_paste_first_for_every_window_four_atomic_events(self):
        clip, inp = FakeClip(), FakeInput()
        t, api = make_typer(clip=clip, inp=inp)
        focus_notepad(api)
        out = t.type("hello world")
        self.assertTrue(out.ok)
        self.assertEqual(out.method, "paste")
        self.assertEqual(clip.content, "hello world")
        self.assertEqual(len(inp.bursts), 1)
        burst = inp.bursts[0]
        self.assertEqual(len(burst), 4)  # ctrl down, v down, v up, ctrl up
        kinds = [(e[0], e[2]) for e in burst]
        self.assertEqual(kinds, [("vk", False), ("vk", False), ("vk", True), ("vk", True)])

    def test_paste_used_even_for_terminals(self):
        clip, inp = FakeClip(), FakeInput()
        t, api = make_typer(clip=clip, inp=inp)
        focus_terminal(api)
        out = t.type(HE_EN)
        self.assertTrue(out.ok)
        self.assertEqual(out.method, "paste")

    def test_hebrew_reaches_clipboard_verbatim(self):
        clip = FakeClip()
        t, api = make_typer(clip=clip)
        focus_notepad(api)
        t.type(HE_EN)
        self.assertEqual(clip.content, HE_EN)

    def test_empty_text_no_events_no_clipboard(self):
        clip, inp = FakeClip(), FakeInput()
        t, api = make_typer(clip=clip, inp=inp)
        focus_notepad(api)
        out = t.type("")
        self.assertTrue(out.ok)
        self.assertEqual(out.events, 0)
        self.assertEqual(clip.set_calls, [])
        self.assertEqual(inp.bursts, [])


class ClipboardRestoreTests(unittest.TestCase):
    """Scar 32 — the race that lost a whole night of Hebrew dictation."""

    def test_no_restore_by_default(self):
        clip = FakeClip(initial="PRECIOUS")
        t, api = make_typer(clip=clip)
        focus_notepad(api)
        t.type("dictated text")
        self.assertEqual(clip.content, "dictated text")  # old clipboard NOT put back
        self.assertEqual(clip.set_calls, ["dictated text"])

    def test_opt_in_restore_waits_full_second_and_verifies(self):
        clip, sleep = FakeClip(initial="PRECIOUS"), SleepRecorder()
        t, api = make_typer(clip=clip, clipboard_restore=True, sleep=sleep)
        focus_notepad(api)
        t.type("dictated text")
        self.assertIn(CLIPBOARD_RESTORE_WAIT_S, sleep.calls)
        self.assertGreaterEqual(CLIPBOARD_RESTORE_WAIT_S, 1.0)
        self.assertEqual(clip.content, "PRECIOUS")       # restored: clipboard was still ours

    def test_opt_in_restore_skipped_if_clipboard_changed_meanwhile(self):
        class TouchedClip(FakeClip):
            def get(self):
                # someone else wrote the clipboard after our paste
                return "USER-COPIED-SOMETHING" if self.set_calls else self.content

        clip = TouchedClip(initial="PRECIOUS")
        t, api = make_typer(clip=clip, clipboard_restore=True)
        focus_notepad(api)
        t.type("dictated text")
        # never clobber a clipboard the user touched since
        self.assertEqual(clip.set_calls, ["dictated text"])

    def test_open_retry_contract_is_twelve(self):
        self.assertGreaterEqual(CLIPBOARD_OPEN_RETRIES, 12)


class SendInputFallbackTests(unittest.TestCase):
    """Scar 31 — the fallback must survive the 79-char burst that lost spaces."""

    def test_fallback_on_paste_failure_two_events_per_char(self):
        clip, inp = FakeClip(fail_set=True), FakeInput()
        t, api = make_typer(clip=clip, inp=inp)
        focus_notepad(api)
        out = t.type("ab c")
        self.assertTrue(out.ok)
        self.assertEqual(out.method, "sendinput")
        events = [e for b in inp.bursts for e in b]
        self.assertEqual(len(events), 8)                 # 2 per char, spaces included
        codes = [e[1] for e in events[::2]]
        self.assertEqual(codes, [ord("a"), ord("b"), ord(" "), ord("c")])

    def test_surrogate_pairs_for_astral_chars(self):
        clip, inp = FakeClip(fail_set=True), FakeInput()
        t, api = make_typer(clip=clip, inp=inp)
        focus_notepad(api)
        t.type("\U0001F600")                             # emoji outside the BMP
        events = [e for b in inp.bursts for e in b]
        self.assertEqual(len(events), 4)                 # 2 code units x down+up
        downs = [e[1] for e in events if not e[2]]
        self.assertEqual(downs, [0xD83D, 0xDE00])

    def test_utf16_units_helper(self):
        self.assertEqual(utf16_units("a"), [ord("a")])
        self.assertEqual(utf16_units("\U0001F600"), [0xD83D, 0xDE00])

    def test_long_burst_is_chunked(self):
        """The 79-char scar: one giant burst loses events. Chunk it."""
        clip, inp = FakeClip(fail_set=True), FakeInput()
        t, api = make_typer(clip=clip, inp=inp)
        focus_notepad(api)
        text = "What about the mic app? Can you fix it please? So it types in any window. Over."
        self.assertGreaterEqual(len(text), 79)   # the scar utterance was exactly 79 chars
        out = t.type(text)
        self.assertTrue(out.ok)
        self.assertGreater(len(inp.bursts), 1)           # NOT one giant burst
        for burst in inp.bursts:
            self.assertLessEqual(len(burst), t.CHUNK_EVENTS)
        events = [e for b in inp.bursts for e in b]
        self.assertEqual(len(events), 2 * len(text))     # every char, every space, sent
        typed = "".join(chr(e[1]) for e in events[::2])
        self.assertEqual(typed, text)                    # order preserved across chunks

    def test_terminal_paste_failure_is_honest_refusal_not_unicode_fallback(self):
        """Terminals discard KEYEVENTF_UNICODE — falling back would be the
        'TYPED ok lied for weeks' hole. Park instead."""
        clip, inp, emit = FakeClip(fail_set=True), FakeInput(), EmitRecorder()
        t, api = make_typer(clip=clip, inp=inp, emit=emit)
        focus_terminal(api)
        out = t.type("some text")
        self.assertFalse(out.ok)
        self.assertTrue(out.parked)
        self.assertEqual(out.reason, "terminal_paste_failed")
        self.assertEqual(inp.bursts, [])                 # zero unicode events at a terminal
        parked = t.parked_path.read_text(encoding="utf-8")
        self.assertIn("some text", parked)

    def test_focus_change_mid_burst_stops_and_parks_remainder(self):
        clip, inp = FakeClip(fail_set=True), FakeInput()
        t, api = make_typer(clip=clip, inp=inp)
        focus_notepad(api, hwnd=100)
        api.add(200, "Other window", 777, "C:\\other\\other.exe")

        flipped = {"done": False}
        orig_send = inp.send_input

        def flipping_send(events):
            n = orig_send(events)
            if not flipped["done"]:
                flipped["done"] = True
                api.foreground = 200                     # user Alt-Tabs mid-utterance
            return n

        inp.send_input = flipping_send
        text = "x" * 100
        out = t.type(text)
        self.assertFalse(out.ok)
        self.assertEqual(out.reason, "focus_changed_mid_burst")
        self.assertTrue(out.parked)
        # nothing was sent after the flip: exactly one burst went out
        self.assertEqual(len(inp.bursts), 1)
        # the un-typed remainder is recoverable from the park file
        parked = t.parked_path.read_text(encoding="utf-8")
        rec = json.loads(parked.splitlines()[-1])
        sent_chars = len(inp.bursts[0]) // 2
        self.assertEqual(rec["text"], text[sent_chars:])


class FocusRefusalTests(unittest.TestCase):
    def test_refused_focus_parks_text_and_reports(self):
        emit = EmitRecorder()
        t, api = make_typer(emit=emit)                   # nothing focused at all
        out = t.type(HE_EN)
        self.assertFalse(out.ok)
        self.assertTrue(out.parked)
        rec = json.loads(t.parked_path.read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual(rec["text"], HE_EN)             # verbatim, recoverable
        self.assertTrue(rec["ts"])
        self.assertTrue(any(e == "FOCUS_BLOCK" for e, _ in emit.events))

    def test_double_snapshot_change_before_send_is_refused(self):
        """User Alt-Tabs between recognition and typing (scar 34 double-snapshot)."""
        clip = FakeClip()

        t, api = make_typer(clip=clip)
        focus_notepad(api, hwnd=100)
        api.add(200, "Other", 777, "C:\\other\\other.exe")

        orig_set = clip.set

        def flipping_set(text):
            api.foreground = 200                         # focus flips during preparation
            return orig_set(text)

        clip.set = flipping_set
        out = t.type("hello")
        self.assertFalse(out.ok)
        self.assertEqual(out.reason, "focus_changed")
        self.assertTrue(out.parked)

    def test_park_file_lives_under_state(self):
        t, _ = make_typer()
        self.assertEqual(t.parked_path.name, "parked.txt")


class EnterTests(unittest.TestCase):
    """Scar 36 — Enter is a separate burst that re-verifies the target."""

    def test_enter_is_separate_burst_after_delay(self):
        inp, sleep = FakeInput(), SleepRecorder()
        t, api = make_typer(inp=inp, sleep=sleep)
        focus_notepad(api)
        out = t.type("hello", enter=True)
        self.assertTrue(out.ok)
        self.assertTrue(out.enter_ok)
        self.assertEqual(len(inp.bursts), 2)             # paste burst, THEN enter burst
        enter_burst = inp.bursts[1]
        self.assertEqual(len(enter_burst), 2)
        self.assertEqual(enter_burst[0][1], 0x0D)        # VK_RETURN
        self.assertIn(ENTER_DELAY_S, sleep.calls)
        self.assertAlmostEqual(ENTER_DELAY_S, 0.35)

    def test_enter_refused_if_target_changed_text_still_ok(self):
        inp, emit = FakeInput(), EmitRecorder()
        sleep = SleepRecorder()

        t, api = make_typer(inp=inp, emit=emit, sleep=sleep)
        focus_notepad(api, hwnd=100)
        api.add(200, "Other", 777, "C:\\other\\other.exe")

        real_sleep_calls = []

        def flipping_sleep(s):
            real_sleep_calls.append(s)
            if s == ENTER_DELAY_S:
                api.foreground = 200                     # target changed during the delay
        t._sleep = flipping_sleep
        out = t.type("hello", enter=True)
        self.assertTrue(out.ok)                          # the text DID land
        self.assertFalse(out.enter_ok)                   # the Enter was refused
        self.assertEqual(len(inp.bursts), 1)             # no Enter events sent
        self.assertTrue(any(e == "FOCUS_BLOCK" for e, _ in emit.events))

    def test_no_enter_by_default(self):
        inp = FakeInput()
        t, api = make_typer(inp=inp)
        focus_notepad(api)
        t.type("hello")
        self.assertEqual(len(inp.bursts), 1)


class SerializationTests(unittest.TestCase):
    def test_type_is_serialized_by_a_lock(self):
        """ONE serialization point: two threads may never interleave bursts."""
        clip = FakeClip(fail_set=True)                   # force multi-burst sendinput path
        inp = FakeInput()
        t, api = make_typer(clip=clip, inp=inp)
        focus_notepad(api)
        inside = {"n": 0, "max": 0}
        lock = threading.Lock()
        orig = inp.send_input

        def tracking_send(events):
            with lock:
                inside["n"] += 1
                inside["max"] = max(inside["max"], inside["n"])
            try:
                return orig(events)
            finally:
                with lock:
                    inside["n"] -= 1

        inp.send_input = tracking_send
        threads = [threading.Thread(target=t.type, args=("abcdef" * 20,)) for _ in range(4)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()
        self.assertEqual(inside["max"], 1)               # never two bursts in flight

    def test_outcome_shape_for_router(self):
        """PHASE2-DESIGN 4.1: router does `outcome = typer.type(text)` and
        journals TYPED / TYPE_FAIL_PARKED off outcome.ok."""
        self.assertTrue(hasattr(Outcome, "_fields"))
        for field in ("ok", "method", "reason", "events", "parked", "enter_ok", "exe"):
            self.assertIn(field, Outcome._fields)


if __name__ == "__main__":
    unittest.main()
