"""K14 intrusive tests — criterion 8 (UIPI round-trip) + criterion 9 (focus
torture, BOUNDED) against REAL windows.

FOCUS-COURTESY GUARDRAIL (wave 4): every test here steals global foreground
focus and flashes windows, so:

  * all tests are marked @pytest.mark.focus_intrusive AND skipped unless
    KESHEV_FOCUS_INTRUSIVE=1 — the normal full suite never grabs focus;
  * each test is run AT MOST ONCE per change, briefly;
  * criterion 9 runs with ITERATIONS = 3 here; the full multi-minute
    torture loop is DEFERRED to the K17 overnight window (guardrail order,
    recorded in the K14 RAMCHAT post) — it is implemented, only its long
    run is deferred;
  * text is typed ONLY into windows these tests themselves create
    (child processes spawned here), never into anything of Iddo's.

Criterion 8 (scar 19): type through the REAL typer into a same-integrity
child window and read back VERBATIM what the child received — including
100+ chars with spaces, mixed Hebrew+English, and a real console window
(paste path; terminals discard KEYEVENTF_UNICODE).

Criterion 9 (scars 34/35/38), bounded: Alt-Tab storm mid-utterance, a
spinner-title window rewriting its caption every 100ms, and KESHEV's own
window focused — zero text into the wrong window, zero text into the own
window, blocked text parked and recoverable, every refusal logged.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

INTRUSIVE = os.environ.get("KESHEV_FOCUS_INTRUSIVE") == "1"
ITERATIONS = 3   # bounded per the focus-courtesy guardrail; full run = K17

pytestmark = pytest.mark.focus_intrusive

if INTRUSIVE:
    from client.focus import FocusGuard, Win32FocusApi
    from client.selftest import (
        PROBE_HE_EN,
        _focus_window,
        _python_exe,
        uipi_roundtrip,
    )
    from client.typer import INTER_CHUNK_SLEEP_S, Typer, Win32Clipboard, Win32InputApi

HERE = Path(__file__).resolve().parent
TARGET_SCRIPT = REPO / "client" / "_selftest_target.py"

_skip = unittest.skipUnless(
    INTRUSIVE,
    "focus-intrusive (steals foreground): set KESHEV_FOCUS_INTRUSIVE=1 to run",
)


class EmitRecorder:
    def __init__(self):
        self.events = []

    def __call__(self, evt, **fields):
        self.events.append((evt, fields))

    def count(self, evt):
        return sum(1 for e, _ in self.events if e == evt)


def spawn_tk(tmp: Path, name: str, title: str, spin: bool = False):
    """Spawn one receiving tk child; returns (popen, hwnd, got, done)."""
    got = tmp / f"{name}-got.txt"
    ready = tmp / f"{name}-ready.json"
    done = tmp / f"{name}-done.flag"
    argv = [_python_exe(), str(TARGET_SCRIPT), str(got), str(ready), str(done), title]
    if spin:
        argv.append("spin")
    child = subprocess.Popen(argv, creationflags=0x08000000)
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if ready.exists() and ready.stat().st_size > 0:
            hwnd = int(json.loads(ready.read_text(encoding="utf-8"))["hwnd"])
            return child, hwnd, got, done
        time.sleep(0.1)
    child.terminate()
    raise AssertionError(f"child window {name} never became ready")


def read_back(child, got: Path, done: Path, timeout_s: float = 20.0,
              settle_s: float = 1.0) -> str:
    # SendInput queues events; the receiving thread drains them at its own
    # pace. Let the LAST burst land before asking the child to flush, or the
    # readback truncates the tail (observed live: 20 of 43 chars).
    time.sleep(settle_s)
    done.write_text("done", encoding="utf-8")
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if got.exists():
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.terminate()
            return got.read_text(encoding="utf-8")
        time.sleep(0.1)
    child.terminate()
    raise AssertionError(f"child never wrote {got}")


def parked_records(state_dir: Path) -> list[dict]:
    p = state_dir / "parked.txt"
    if not p.exists():
        return []
    return [json.loads(line) for line in
            p.read_text(encoding="utf-8").splitlines() if line.strip()]


# ------------------------------------------------------------- criterion 8


class ClipboardCourtesyMixin:
    """Snapshot the user's clipboard before an intrusive test and put it
    back afterwards — Iddo is working on this machine."""

    def setUp(self):
        super().setUp()
        self._courtesy_clip = Win32Clipboard()
        self._courtesy_prev = self._courtesy_clip.get()

    def tearDown(self):
        if self._courtesy_prev is not None:
            self._courtesy_clip.set(self._courtesy_prev)
        super().tearDown()


@_skip
class Criterion8RoundTripTests(ClipboardCourtesyMixin, unittest.TestCase):
    """Round-trip or it did not happen (scar 19)."""

    def test_probe_is_the_hallmark(self):
        self.assertGreaterEqual(len(PROBE_HE_EN), 100)
        self.assertIn(" ", PROBE_HE_EN)
        self.assertTrue(any("֐" <= c <= "׿" for c in PROBE_HE_EN))  # Hebrew
        self.assertTrue(any("a" <= c.lower() <= "z" for c in PROBE_HE_EN))    # English

    def test_tk_paste_roundtrip_verbatim(self):
        emit = EmitRecorder()
        r = uipi_roundtrip(kind="tk", method="paste", emit=emit)
        self.assertTrue(r.ok, f"detail={r.detail!r} got={r.got!r}")
        self.assertEqual(r.got, PROBE_HE_EN)
        self.assertEqual(emit.count("UIPI_SELFTEST"), 1)

    def test_tk_sendinput_fallback_roundtrip_verbatim(self):
        """The 79-char scar regression: chunked per-char Unicode fallback
        must deliver every character AND every space of a 100+ char burst."""
        r = uipi_roundtrip(kind="tk", method="sendinput")
        self.assertTrue(r.ok, f"detail={r.detail!r} got={r.got!r}")
        self.assertEqual(r.got, PROBE_HE_EN)
        self.assertEqual(r.got.count(" "), PROBE_HE_EN.count(" "))  # spaces survived

    def test_terminal_paste_roundtrip_verbatim(self):
        """A REAL console window (spawned by the selftest itself): paste
        path + separate Enter burst, read back through the console input."""
        r = uipi_roundtrip(kind="terminal", method="paste")
        self.assertTrue(r.ok, f"detail={r.detail!r} got={r.got!r}")
        self.assertEqual(r.got, PROBE_HE_EN)


# ------------------------------------------------- criterion 9 (bounded)


class FlippingInput:
    """Wraps the real input layer; flips focus to another hwnd after N bursts
    (a deterministic Alt-Tab-mid-utterance)."""

    def __init__(self, real, flip_after: int, flip_fn):
        self.real = real
        self.bursts = 0
        self.flip_after = flip_after
        self.flip_fn = flip_fn
        self.flipped = False

    def send_input(self, events):
        n = self.real.send_input(events)
        self.bursts += 1
        if not self.flipped and self.bursts >= self.flip_after:
            self.flipped = True
            self.flip_fn()
        return n


@_skip
class Criterion9FocusTortureTests(ClipboardCourtesyMixin, unittest.TestCase):
    """BOUNDED torture (ITERATIONS=3). Full multi-minute run: K17 overnight."""

    def setUp(self):
        super().setUp()
        self.tmp = Path(tempfile.mkdtemp(prefix="keshev-torture-"))
        self.focus_api = Win32FocusApi()
        self.input_api = Win32InputApi()
        self.children = []

    def tearDown(self):
        for ch in self.children:
            if ch.poll() is None:
                ch.terminate()

    def _typer(self, emit=None, input_api=None, anywhere=True, targets=(),
               sleep=None):
        guard = FocusGuard(api=self.focus_api, emit=emit)
        guard.set_policy(anywhere=anywhere, targets=targets)
        t = Typer(guard=guard, input_api=input_api or self.input_api,
                  state_dir=self.tmp, emit=emit,
                  sleep=sleep or time.sleep)
        return t, guard

    def _focus(self, hwnd):
        self.assertTrue(_focus_window(hwnd, self.focus_api, self.input_api),
                        "could not focus the test's own child window")

    def test_alt_tab_storm_zero_text_into_wrong_window(self):
        """Focus flips to window B mid-utterance: B must receive ZERO
        characters; the un-typed remainder is parked, recoverable; every
        refusal is logged (scar 35)."""
        emit = EmitRecorder()
        a_child, a_hwnd, a_got, a_done = spawn_tk(self.tmp, "A", f"STORM-A-{os.getpid()}")
        self.children.append(a_child)
        b_child, b_hwnd, b_got, b_done = spawn_tk(self.tmp, "B", f"STORM-B-{os.getpid()}")
        self.children.append(b_child)

        texts = [f"iteration {i} of the alt tab storm keeps every space intact "
                 f"וגם עברית באמצע {i}" for i in range(ITERATIONS)]

        def flip_to_b():
            # Let A's thread DISPATCH the already-queued chunks first: events
            # accepted by SendInput but not yet dispatched when focus flips
            # are dropped by the OS — that margin is documented in typer.py;
            # here we make delivery deterministic so the ledger math is exact.
            time.sleep(0.25)
            _focus_window(b_hwnd, self.focus_api, self.input_api)

        expected_prefixes = []
        for i, text in enumerate(texts):
            self._focus(a_hwnd)
            time.sleep(0.15)
            flip = FlippingInput(self.input_api, flip_after=2, flip_fn=flip_to_b)
            typer, _ = self._typer(emit=emit, input_api=flip)
            out = typer.type(text, force_sendinput=True)
            if out.ok:
                expected_prefixes.append(text)       # flip landed after the last chunk
            else:
                self.assertEqual(out.reason, "focus_changed_mid_burst")
                self.assertTrue(out.parked)
                recs = parked_records(self.tmp)
                remainder = recs[-1]["text"]
                self.assertTrue(text.endswith(remainder))
                expected_prefixes.append(text[: len(text) - len(remainder)])

        a_text = read_back(a_child, a_got, a_done)
        b_text = read_back(b_child, b_got, b_done)
        self.assertEqual(b_text, "", "text leaked into the WRONG window")
        self.assertEqual(a_text, "".join(expected_prefixes),
                         "typed prefixes must land in A, in order, verbatim")
        refusals = emit.count("FOCUS_BLOCK")
        parked_n = len(parked_records(self.tmp))
        self.assertEqual(refusals, parked_n, "every parked refusal must be logged")

    def test_spinner_title_window_types_verbatim(self):
        """A window rewriting its caption every 100ms (terminal spinner
        class, scar 34): identity is HWND+PID+exe, so typing proceeds —
        wrongful refusal on a title tick was the original bug."""
        child, hwnd, got, done = spawn_tk(
            self.tmp, "SPIN", f"SPIN-{os.getpid()}", spin=True)
        self.children.append(child)
        self._focus(hwnd)
        time.sleep(0.15)

        # Slow the inter-chunk breather so title ticks HAPPEN between chunks.
        def slow_sleep(s):
            time.sleep(0.12 if s == INTER_CHUNK_SLEEP_S else s)

        texts = [f"spinner iteration {i} keeps spaces ורווחים {i} " for i in range(ITERATIONS)]
        typer, _ = self._typer(sleep=slow_sleep)
        for text in texts:
            out = typer.type(text, force_sendinput=True)
            self.assertTrue(out.ok, f"refused on a title tick: {out.reason}")
        received = read_back(child, got, done)
        self.assertEqual(received, "".join(texts))

    def test_own_window_receives_nothing(self):
        """A window carrying KESHEV's own-title marker is focused: the guard
        must NEVER type into it — restore to the allowed external window or
        park. Zero characters may land in the own window (scars 34/38)."""
        emit = EmitRecorder()
        nonce = f"EXT-{os.getpid()}"
        a_child, a_hwnd, a_got, a_done = spawn_tk(self.tmp, "EXT", nonce)
        self.children.append(a_child)
        own_child, own_hwnd, own_got, own_done = spawn_tk(
            self.tmp, "OWN", f"KESHEV tray {os.getpid()}")
        self.children.append(own_child)

        # Allowlist mode locked to OUR external window: even if the restore
        # walk lands somewhere unexpected, typing outside A is impossible.
        typer, guard = self._typer(emit=emit, anywhere=False,
                                   targets=(nonce.casefold(),))
        self._focus(a_hwnd)
        time.sleep(0.15)
        guard.note_foreground()                      # watcher memory = A

        texts = [f"own window test {i} " for i in range(ITERATIONS)]
        landed, parked_before = [], len(parked_records(self.tmp))
        for text in texts:
            self._focus(own_hwnd)                    # OUR own-marker window forward
            time.sleep(0.15)
            out = typer.type(text)
            if out.ok:
                landed.append(text)
            else:
                self.assertTrue(out.parked, "refusal without parking is a silent drop")
            time.sleep(0.4)   # let A dispatch the paste before the next flip

        own_text = read_back(own_child, own_got, own_done)
        a_text = read_back(a_child, a_got, a_done)
        self.assertEqual(own_text, "", "the own window MUST receive nothing")
        self.assertEqual(a_text, "".join(landed))
        parked_n = len(parked_records(self.tmp)) - parked_before
        self.assertEqual(len(landed) + parked_n, ITERATIONS,
                         "every utterance must land in A or be parked — zero lost")
        if parked_n:
            self.assertGreaterEqual(emit.count("FOCUS_BLOCK"), parked_n)


if __name__ == "__main__":
    unittest.main()
