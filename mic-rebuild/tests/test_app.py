"""K14/K15 TDD tests — client/app.py, THE ENTRY POINT (the assembly).

Every module in this repo was tested in isolation and wired to nothing. This
file tests the thing that makes KESHEV a PROGRAM: one process that assembles

    config -> telemetry -> mutex -> devices -> capture -> resample ->
    segmenter -> spool -> worker_mgr -> router(guard_fn, type_fn) -> typer

and runs it. The laws asserted here:

  assembly      build_app() constructs every component and wires the REAL
                seams — the router's guard_fn is the K13 textguard adapter
                (never router.default_guard, the K12 pass-through placeholder
                that would type "תודה רבה" straight into Iddo's window), and
                its type_fn is the K14 typer.
  purity        build_app() opens NO audio device and starts NO thread. It is
                pure assembly; every side effect lives behind .start().
                Proven with spies, not with hope.
  startup order the mutex acquire is the FIRST statement of main(), before any
                heavy import (design 7, scar 1, criterion 7's <1s refusal);
                the alma-mic coexistence refusal (exit 3, criterion 23) runs
                on INJECTED process/task probes and never touches an audio
                device (Sacred Audio).
  ids           session id is exactly 8 lowercase hex, so every segmenter id
                satisfies common.protocol.valid_request_id — a wrong session
                id silently breaks EVERY DGX decode with err=bad_request.
  survival      the Segmenter survives a device re-resolve (its _seq must not
                restart — colliding ids make the router DUP_DISCARD real
                speech); the CapturePipeline does not, and its drop counter
                accumulates ACROSS pipelines (criterion 22).
  end to end    synthetic PCM in -> segmenter -> spool -> router -> stub
                decoder -> REAL textguard -> real Typer over a fake Win32
                layer -> text out, IN ORDER.

Zero real hardware: no device is enumerated or opened, no real SendInput, no
real clipboard, no real window, no subprocess. alma-mic is never touched.
"""
from __future__ import annotations

import ast
import json
import re
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import numpy as np  # noqa: E402

from client import router as router_mod  # noqa: E402
from client import textguard  # noqa: E402
from client.devices import DeviceInfo, Selection  # noqa: E402
from common import protocol  # noqa: E402
from tests.test_focus import OWN_PID, FakeApi  # noqa: E402
from tests.test_typer import FakeClip, FakeInput  # noqa: E402

import client.app as app  # noqa: E402

APP_SRC = (REPO / "client" / "app.py").read_text(encoding="utf-8")

# Modules whose import is expensive or device-bearing: none of them may be a
# MODULE-LEVEL import of client/app.py, or the mutex would no longer be the
# first thing a duplicate launch reaches (design 7 startup order).
HEAVY_MODULES = (
    "numpy", "sounddevice", "client.capture", "client.segmenter",
    "client.devices", "client.router", "client.spool", "client.worker_mgr",
    "client.keshev_worker", "client.typer", "client.focus",
)


# ------------------------------------------------------------------ fixtures


def make_cfg(**over) -> dict:
    """The 12-key schema shape, as configstore.load() returns it."""
    cfg = {
        "revision": 0,
        "mic_name": "Logitech BRIO",
        "server_url": "http://<lan-ip>:8737/",
        "auth_token_file": "state\\stt-token",
        "gate_rms": {
            "value": 0.004,
            "calibrated_at": "2026-08-12T09:00:00+03:00",
            "method": "test fixture",
            "measured_floor": 0.0009,
            "measured_speech": 0.0182,
            "author": "tests",
        },
        "stale_sec": 25,
        "hotkey_pause": "ctrl+alt+m",
        "auto_enter": False,
        "clipboard_restore": False,
        "extra_avoid": [],
        "corpus_capture": False,
        "owner_gate_typing": False,
    }
    cfg.update(over)
    return cfg


BRIO = DeviceInfo(index=3, name="Logitech BRIO", hostapi="Windows WASAPI",
                  max_input_channels=2)
BRIO_DS = DeviceInfo(index=9, name="Logitech BRIO", hostapi="Windows DirectSound",
                     max_input_channels=2)
XM4 = DeviceInfo(index=1, name="Headset (WH-1000XM4 Hands-Free)",
                 hostapi="Windows WASAPI", max_input_channels=1)


# THE REAL K13 seam (client/textguard.py::guard) — dict in, final text or None
# out, exactly the shape client/router.py:428 calls. Not a test-local copy: the
# end-to-end tests below drive the same adapter production will run. app.py may
# not import textguard itself (tests/test_textguard.py::
# test_import_discipline_client_only_router), so it is injected here and
# resolved from the router in production.
textguard_adapter = textguard.guard


class StubWorker:
    """A decoder that answers from a script — no subprocess, no model, no LAN."""

    def __init__(self, replies=None, healthy=True):
        self.replies = list(replies or [])
        self.calls: list[tuple[str, str]] = []
        self.state = "READY"
        self.local_state = "READY"
        self.worker_rss_mb = 120
        self.worker_vram_mb = 0
        self.started = 0
        self.stopped = 0
        self._healthy = healthy

    def start(self):
        self.started += 1

    def stop(self):
        self.stopped += 1

    def decode(self, rec_id, pcm, *, engine, lang_hint="auto"):
        self.calls.append((rec_id, engine))
        reply = self.replies.pop(0) if self.replies else {"ok": False, "err": "no_script"}
        out = dict(reply)
        out["id"] = rec_id
        out.setdefault("engine", engine)
        out.setdefault("decode_ms", 120)
        return out

    def ping(self):
        return True

    def probe(self):
        return {"healthy": self._healthy, "decode_p95_ms": 400, "uptime_s": 9999}


class FakeStream:
    """Stands in for sounddevice.InputStream — counts start/stop/close only."""

    def __init__(self, device, rate, channels, pipeline):
        self.device = device
        self.rate = rate
        self.channels = channels
        self.pipeline = pipeline
        self.started = 0
        self.stopped = 0
        self.closed = 0
        self.kind = "capture"
        self.name = device.name

    def start(self):
        self.started += 1

    def stop(self):
        self.stopped += 1

    def close(self):
        self.closed += 1


class DeviceSpies:
    """Records every device-layer call so a test can prove NONE happened."""

    def __init__(self, devices=(BRIO, BRIO_DS, XM4), native=(48000, 2)):
        self.devices = list(devices)
        self.native = native
        self.enumerated = 0
        self.native_calls: list[DeviceInfo] = []
        self.checks: list[tuple] = []
        self.opens: list[tuple] = []
        self.streams: list[FakeStream] = []

    def enumerate_fn(self):
        self.enumerated += 1
        return list(self.devices)

    def native_format_fn(self, device):
        self.native_calls.append(device)
        return self.native

    def check_format_fn(self, device, rate, channels):
        self.checks.append((device.index, rate, channels))
        if rate != 16000 or channels != 1:
            raise ValueError(f"refused {rate}/{channels}")

    def open_stream_fn(self, device, rate, channels, pipeline):
        self.opens.append((device.index, rate, channels))
        st = FakeStream(device, rate, channels, pipeline)
        self.streams.append(st)
        return st

    @property
    def touched(self) -> bool:
        return bool(self.enumerated or self.native_calls or self.checks or self.opens)


def frames(amp: float, n: int, samples: int = 480) -> list[np.ndarray]:
    """n frames of 30ms @16k — a saw at `amp` (0.0 = digital silence)."""
    if amp == 0.0:
        return [np.zeros(samples, dtype=np.float32) for _ in range(n)]
    base = (np.linspace(-1.0, 1.0, samples, dtype=np.float32) * amp)
    return [base.copy() for _ in range(n)]


class FakePresence:
    """Deterministic stand-in for client.presence.PresenceGate.

    The real gate reads the OS last-input clock (GetLastInputInfo), which makes
    it a hidden dependency on whether a human touched the keyboard recently.
    Tests state the idle seconds they mean."""

    def __init__(self, idle_s=0.0):
        self.idle_s = idle_s
        self.calls = 0

    def decide(self):
        from client.presence import PresenceGate, Win32IdleApi  # noqa: F401
        from client.presence import Decision, ENTER_IDLE_LIMIT_S, TYPE_IDLE_LIMIT_S
        self.calls += 1
        idle = self.idle_s
        if idle is None:
            return Decision(True, False, None, "presence_unknown")
        if idle >= TYPE_IDLE_LIMIT_S:
            return Decision(False, False, idle, "owner_absent")
        if idle >= ENTER_IDLE_LIMIT_S:
            return Decision(True, False, idle, "owner_idle_no_enter")
        return Decision(True, True, idle, "")

    def last_idle(self):
        return self.idle_s

    def last_decision(self):
        return self.decide()


class QuietIdleApi:
    """Idle-clock fake for the typer's hold-while-typing gate. The real
    gate reads GetLastInputInfo — without this fake the suite would depend
    on whether a human (or the LIVE mic's own SendInput) touched the input
    clock while tests ran. Default says "keyboard quiet for a minute"."""

    def __init__(self, idle_s=60.0):
        self.idle_s = idle_s

    def idle_seconds(self):
        return self.idle_s


class QuietHotkeyApi:
    """Hotkey API fake for the harness: registers nothing, pumps nothing —
    a suite that grabbed the REAL global ctrl+alt+m while Iddo works would
    be the focus-courtesy violation with a keyboard instead of a window."""

    def thread_id(self):
        return 0

    def register(self, hk_id, mods, vk):
        return False                      # nothing global is ever taken

    def unregister(self, hk_id):
        pass

    def get_message(self):
        from client.hotkeys import WM_QUIT
        return (WM_QUIT, 0)               # a started pump exits immediately

    def post_quit(self, thread_id):
        pass


class AppHarness:
    """A built app plus every fake it was built from."""

    # -- see __init__: presence must be a fake or the suite depends on the
    #    operator's keyboard.

    def __init__(self, tmp: Path, cfg=None, worker=None, guard_fn=textguard_adapter,
                 devices=(BRIO, BRIO_DS, XM4), api=None, **over):
        self.tmp = tmp
        self.cfg = cfg or make_cfg()
        self.spies = DeviceSpies(devices=devices)
        self.worker = worker or StubWorker()
        self.api = api or default_focus_api()
        self.clip = FakeClip()
        self.input = FakeInput()
        # Presence: the real gate reads the OS last-input clock, so without a
        # fake here the suite silently depends on whether a human touched the
        # keyboard in the last two minutes — green on a busy machine, red on a
        # long run or a build server. Default fake says "he is right here";
        # tests that care about absence pass presence=FakePresence(idle).
        self.presence = FakePresence(0.0)
        self.typer_idle = QuietIdleApi()
        kwargs = dict(
            state_dir=tmp / "state",
            session_id="abcdef12",
            worker=self.worker,
            guard_fn=guard_fn,
            focus_api=self.api,
            input_api=self.input,
            clipboard=self.clip,
            typer_idle_api=self.typer_idle,
            presence=self.presence,
            vad=lambda frame_bytes: True,
            enumerate_fn=self.spies.enumerate_fn,
            native_format_fn=self.spies.native_format_fn,
            check_format_fn=self.spies.check_format_fn,
            open_stream_fn=self.spies.open_stream_fn,
            set_priority_fn=lambda: 1,
            rss_fn=lambda: 321,
            hotkey_api_factory=QuietHotkeyApi,
        )
        kwargs.update(over)
        self.app = app.build_app(self.cfg, **kwargs)

    def typed(self) -> list[str]:
        return list(self.clip.set_calls)

    def ledger(self) -> list[dict]:
        path = self.tmp / "state" / "events.jsonl"
        if not path.is_file():
            return []
        return [json.loads(line) for line in
                path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def journal(self) -> list[dict]:
        path = self.tmp / "state" / "spool" / "journal.jsonl"
        if not path.is_file():
            return []
        return [json.loads(line) for line in
                path.read_text(encoding="utf-8").splitlines() if line.strip()]


def default_focus_api() -> FakeApi:
    """A plain, allowed, titled Notepad window in the foreground."""
    api = FakeApi()
    api.add(101, "Untitled - Notepad", 777, r"C:\Windows\notepad.exe")
    api.foreground = 101
    return api


class TmpCase(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory(prefix="keshev-app-")
        self.tmp = Path(self._td.name)
        self.addCleanup(self._td.cleanup)

    def build(self, **kw) -> AppHarness:
        h = AppHarness(self.tmp, **kw)
        self.addCleanup(h.app.shutdown)
        return h


# ------------------------------------------------------------------ assembly


class AssemblyTests(TmpCase):
    """build_app() constructs EVERY component and wires the real seams."""

    def test_every_component_is_constructed_and_wired(self):
        from client.router import Router
        from client.segmenter import Segmenter
        from client.spool import RecoveredTranscript, Spool
        from client.telemetry import Telemetry
        from client.typer import Typer
        from client.focus import FocusGuard

        a = self.build().app
        self.assertIsInstance(a.telemetry, Telemetry)
        self.assertIsInstance(a.spool, Spool)
        self.assertIsInstance(a.recovered, RecoveredTranscript)
        self.assertIsInstance(a.segmenter, Segmenter)
        self.assertIsInstance(a.focus_guard, FocusGuard)
        self.assertIsInstance(a.typer, Typer)
        self.assertIsInstance(a.router, Router)
        # the router holds the SAME objects, not copies
        self.assertIs(a.router.spool, a.spool)
        self.assertIs(a.router.recovered, a.recovered)
        self.assertIs(a.router.telemetry, a.telemetry)
        self.assertIs(a.router.worker, a.worker)
        self.assertIs(a.segmenter.spool, a.spool)
        self.assertIs(a.typer._guard, a.focus_guard)

    def test_guard_fn_is_the_textguard_seam_never_the_k12_placeholder(self):
        a = self.build().app
        self.assertIs(a.router.guard_fn, textguard_adapter)
        self.assertIsNot(a.router.guard_fn, router_mod.default_guard)

    def test_uninjected_assembly_runs_on_the_real_guard(self):
        """With no guard_fn injected the assembly takes the guard the ROUTER
        declares. This asserts the OUTCOME, not "resolved or refused" — the
        earlier resolve-or-raise phrasing passed while client/router.py was
        still on the K12 placeholder, which is how an unwired guard shipped
        green. Refusal-on-a-placeholder is covered against a stub router in
        GuardResolutionTests."""
        a = self.build(guard_fn=None).app
        self.assertIs(a.router.guard_fn, textguard_adapter)
        self.assertIsNot(a.router.guard_fn, router_mod.default_guard)

    def test_type_fn_is_the_typer_entry_point(self):
        h = self.build()
        self.assertIsNot(h.app.router.type_fn, router_mod._default_type_fn)
        self.assertTrue(h.app.router.type_fn("שלום"))
        self.assertEqual(h.typed(), ["שלום"])

    def test_type_fn_carries_auto_enter_from_config(self):
        h = self.build(cfg=make_cfg(auto_enter=True))
        h.app.router.type_fn("line")
        # paste burst (4 events) + the SEPARATE enter burst (scar 36)
        self.assertGreaterEqual(len(h.input.bursts), 2)
        self.assertEqual(h.input.bursts[-1][0][0], "vk")

    def test_arm_switch_ships_transparent(self):
        """presence.ARMED_MODE is False in the tree: the arm switch exists,
        is wired, and does NOTHING — the B-verdict option, defaulting off."""
        h = self.build()
        self.assertFalse(h.app.arm.enabled)
        self.assertTrue(h.app.router.type_fn("שלום"))
        self.assertEqual(h.typed(), ["שלום"])

    def test_armed_mode_disarmed_parks_instead_of_typing(self):
        """Qwen's claim, enforced: no deliberate arming act, no typing —
        and the words are PARKED, never dropped (scar 35)."""
        from client.presence import ArmSwitch
        h = self.build(arm=ArmSwitch(enabled=True))
        self.assertFalse(h.app.router.type_fn("סוד גדול"))
        self.assertEqual(h.typed(), [])
        parked = (self.tmp / "state" / "parked.txt").read_text(encoding="utf-8")
        self.assertIn("סוד גדול", parked)
        self.assertIn("disarmed", parked)

    def test_armed_mode_armed_types_again(self):
        from client.presence import ArmSwitch
        s = ArmSwitch(enabled=True)
        s.arm()
        h = self.build(arm=s)
        self.assertTrue(h.app.router.type_fn("שלום"))
        self.assertEqual(h.typed(), ["שלום"])

    def test_arm_is_layered_over_presence_not_instead_of_it(self):
        """An armed switch with an ABSENT owner still refuses — the idle
        gate keeps its authority (the whole point of the B verdict's
        'layered over presence.py')."""
        from client.presence import ArmSwitch, TYPE_IDLE_LIMIT_S
        s = ArmSwitch(enabled=True)
        s.arm()
        h = self.build(arm=s, presence=FakePresence(TYPE_IDLE_LIMIT_S + 1))
        self.assertFalse(h.app.router.type_fn("מי שם"))
        self.assertEqual(h.typed(), [])
        parked = (self.tmp / "state" / "parked.txt").read_text(encoding="utf-8")
        self.assertIn("owner_absent", parked)

    def test_pause_hotkey_is_finally_bound(self):
        """The fourth guard species, closed: parse_hotkey guarded a binding
        that never existed. The assembled app now carries a listener with
        the pause chord from config wired to a real pause toggle."""
        h = self.build()
        self.assertIsNotNone(h.app.hotkeys)
        chords = [hk.label for hk, _ in h.app.hotkeys._bindings]
        self.assertEqual(chords, ["Ctrl+Alt+M"])   # hotkey_pause, and ONLY it
        # the bound action really toggles pause
        _, action = h.app.hotkeys._bindings[0]
        self.assertFalse(h.app.is_paused())
        action()
        self.assertTrue(h.app.is_paused())
        action()
        self.assertFalse(h.app.is_paused())

    def test_arm_hotkey_bound_only_when_armed_mode_is_on(self):
        from client.presence import ARM_HOTKEY, ArmSwitch
        h = self.build(arm=ArmSwitch(enabled=True))
        chords = [hk.label for hk, _ in h.app.hotkeys._bindings]
        self.assertEqual(chords, ["Ctrl+Alt+M", "Ctrl+Alt+A"])
        self.assertEqual(ARM_HOTKEY, "ctrl+alt+a")
        # the bound action is the switch's own toggle
        _, arm_action = h.app.hotkeys._bindings[1]
        self.assertFalse(h.app.arm.is_armed())
        arm_action()
        self.assertTrue(h.app.arm.is_armed())

    def test_clipboard_restore_reaches_the_typer(self):
        self.assertFalse(self.build().app.typer._clipboard_restore)
        h = self.build(cfg=make_cfg(clipboard_restore=True))
        self.assertTrue(h.app.typer._clipboard_restore)

    def test_router_gets_stale_sec_and_the_client_rss_probe(self):
        a = self.build(cfg=make_cfg(stale_sec=41)).app
        self.assertEqual(a.router.stale_sec, 41.0)
        self.assertEqual(a.router._rss_fn(), 321)

    def test_focus_policy_is_anywhere_not_the_zero_target_allowlist(self):
        """FocusGuard's constructor default is allowlist mode with ZERO
        targets — it parks 100% of dictation. The ship default is code under
        git (there is no 13th config key)."""
        a = self.build().app
        self.assertTrue(app.FOCUS_ANYWHERE_DEFAULT)
        self.assertTrue(a.focus_guard.policy()["anywhere"])

    def test_segmenter_and_telemetry_share_one_session_id(self):
        a = self.build().app
        self.assertEqual(a.session_id, a.segmenter.session_id)
        self.assertEqual(a.session_id, a.telemetry.session_id)


class GuardResolutionTests(unittest.TestCase):
    """app.py may not import textguard (router-only, scar 28), so the guard is
    resolved FROM THE ROUTER. Whatever name the router-side wiring picks, the
    Router's own guard_fn default IS the contract — read it, never guess."""

    @staticmethod
    def _stub_router_module(guard_default, attr=None):
        import types
        mod = types.ModuleType("stub_router")
        mod.default_guard = router_mod.default_guard

        class Router:
            def __init__(self, spool, worker, telemetry, *, recovered,
                         type_fn=None, guard_fn=guard_default):
                pass

        mod.Router = Router
        if attr is not None:
            mod.textguard_guard = attr
        return mod

    def test_resolution_reads_the_routers_own_guard_default(self):
        mod = self._stub_router_module(textguard_adapter)
        self.assertIs(app.resolve_guard_fn(mod), textguard_adapter)

    def test_resolution_refuses_a_router_still_on_the_placeholder(self):
        mod = self._stub_router_module(router_mod.default_guard)
        with self.assertRaises(app.AssemblyError) as ctx:
            app.resolve_guard_fn(mod)
        self.assertIn("textguard", str(ctx.exception).lower())

    def test_an_explicit_module_level_adapter_wins(self):
        mod = self._stub_router_module(router_mod.default_guard,
                                       attr=textguard_adapter)
        self.assertIs(app.resolve_guard_fn(mod), textguard_adapter)

    def test_the_real_router_module_resolves_to_the_real_guard(self):
        """Against the REAL client.router, with nothing stubbed: resolution
        must SUCCEED and hand back client/textguard.py's adapter."""
        self.assertIs(app.resolve_guard_fn(), textguard_adapter)


class SessionIdTests(unittest.TestCase):
    """A non-8-hex session id silently breaks EVERY DGX decode."""

    def test_new_session_id_is_8_lowercase_hex(self):
        for _ in range(50):
            sid = app.new_session_id()
            self.assertRegex(sid, r"^[0-9a-f]{8}$")

    def test_generated_ids_satisfy_the_wire_contract(self):
        sid = app.new_session_id()
        self.assertTrue(protocol.valid_request_id(f"{sid}-000001"))
        self.assertTrue(protocol.valid_request_id(protocol.make_request_id(sid, 7)))


# -------------------------------------------------------------------- purity


class PurityTests(TmpCase):
    """build_app() is assembly ONLY: no device, no thread, no subprocess."""

    def test_build_app_opens_no_audio_device(self):
        h = self.build()
        self.assertFalse(h.spies.touched,
                         f"device layer touched during build: "
                         f"enumerate={h.spies.enumerated} opens={h.spies.opens}")
        self.assertIsNone(h.app.capture)
        self.assertIsNone(h.app.stream)

    def test_build_app_starts_no_thread(self):
        before = threading.active_count()
        self.build()
        self.assertEqual(threading.active_count(), before)

    def test_build_app_does_not_start_the_worker(self):
        h = self.build()
        self.assertEqual(h.worker.started, 0)

    def test_app_module_imports_no_heavy_module_at_module_level(self):
        tree = ast.parse(APP_SRC)
        top: list[str] = []
        for node in tree.body:
            if isinstance(node, ast.Import):
                top += [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                top.append(node.module)
        for heavy in HEAVY_MODULES:
            for name in top:
                self.assertFalse(name == heavy or name.startswith(heavy + "."),
                                 f"{heavy} imported at module level of app.py — "
                                 f"the mutex must be reachable before any heavy "
                                 f"import (design 7 startup order)")

    def test_app_never_imports_textguard(self):
        """tests/test_textguard.py::test_import_discipline_client_only_router —
        the guard is router-only; app.py injects the seam instead."""
        self.assertIsNone(re.search(r"^\s*(?:import|from)\s+\S*textguard",
                                    APP_SRC, re.M))

    def test_app_never_starts_a_second_heartbeat_source(self):
        """The Router already emits HEARTBEAT every 60s from its idle tick.
        A second source would double-write the ledger."""
        for node in ast.walk(ast.parse(APP_SRC)):
            if isinstance(node, ast.Call):
                name = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
                self.assertNotEqual(name, "start_heartbeat",
                                    f"app.py:{node.lineno} starts a second "
                                    f"heartbeat source (the router owns the pulse)")

    def test_sounddevice_is_lazy_everywhere(self):
        """sounddevice is not installed on this PC; the whole assembly must
        still import and build headlessly."""
        tree = ast.parse(APP_SRC)
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            if any(n.split(".")[0] == "sounddevice" for n in names):
                self.assertGreater(node.col_offset, 0,
                                   "sounddevice imported at column 0 — must be "
                                   "inside a function (it is not installed)")


# ----------------------------------------------------------- process prelude


class AlmaMicCoexistenceTests(unittest.TestCase):
    """Criterion 23 / scar 56: KESHEV REFUSES to start while alma-mic lives.
    Both probes are injected and neither may touch an audio device."""

    def test_running_alma_task_is_alive(self):
        alive, why = app.almamic_alive(
            list_procs_fn=lambda: [],
            list_tasks_fn=lambda: [("\\ALMA-MIC-Elevated", "Running")])
        self.assertTrue(alive)
        self.assertIn("ALMA-MIC", why)

    def test_startup_rival_task_is_alive(self):
        alive, _ = app.almamic_alive(
            list_procs_fn=lambda: [],
            list_tasks_fn=lambda: [("START-MIC", "Running")])
        self.assertTrue(alive)

    def test_ready_task_is_not_alive(self):
        alive, why = app.almamic_alive(
            list_procs_fn=lambda: [],
            list_tasks_fn=lambda: [("\\ALMA-MIC-Elevated", "Ready")])
        self.assertFalse(alive)
        self.assertTrue(why)

    def test_process_commandline_patterns(self):
        for cmdline in (r'pythonw "D:\CLAUDE\alma-mic\supervisor.py"',
                        r'python D:\CLAUDE\voice-input\transcribe.py',
                        r'python d:\claude\heb-mic\run.py'):
            with self.subTest(cmdline=cmdline):
                alive, why = app.almamic_alive(
                    list_procs_fn=lambda c=cmdline: [c],
                    list_tasks_fn=lambda: [])
                self.assertTrue(alive)
                self.assertTrue(why)

    def test_keshev_itself_is_not_mistaken_for_alma_mic(self):
        alive, _ = app.almamic_alive(
            list_procs_fn=lambda: [r'python -m client.app  # D:\CLAUDE\mic-rebuild',
                                   r'python -m client.keshev_worker --gen 1'],
            list_tasks_fn=lambda: [("KESHEV-Elevated", "Running")])
        self.assertFalse(alive)

    def test_probe_failure_is_not_silently_alive_or_dead(self):
        """A probe that raises must not be swallowed into 'dead' — that would
        let KESHEV open a mic while alma-mic holds it."""
        def boom():
            raise OSError("schtasks exploded")
        with self.assertRaises(OSError):
            app.almamic_alive(list_procs_fn=lambda: [], list_tasks_fn=boom)

    def test_the_probe_touches_no_audio_device(self):
        import inspect
        for fn in (app.almamic_alive, app.default_list_tasks, app.default_list_procs):
            src = inspect.getsource(fn)
            with self.subTest(fn=fn.__name__):
                self.assertNotIn("sounddevice", src)
                self.assertNotIn("query_devices", src)
                self.assertNotIn("InputStream", src)


class StartupOrderTests(unittest.TestCase):
    """Design 7: the mutex is the FIRST meaningful statement of main()."""

    @staticmethod
    def _main_body():
        tree = ast.parse(APP_SRC)
        fn = next(n for n in tree.body
                  if isinstance(n, ast.FunctionDef) and n.name == "main")
        body = list(fn.body)
        if (body and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)):
            body = body[1:]
        return body

    def test_mutex_acquire_is_the_first_statement_of_main(self):
        first = self._main_body()[0]
        calls = [n for n in ast.walk(first) if isinstance(n, ast.Call)]
        self.assertTrue(calls, "first statement of main() makes no call")
        target = calls[0].func
        self.assertIsInstance(target, ast.Attribute)
        self.assertEqual(target.attr, "acquire_or_exit")

    def test_exit_codes_are_the_contract(self):
        self.assertEqual(app.EXIT_CONFIG_HALT, 2)
        self.assertEqual(app.EXIT_ALMAMIC_ALIVE, 3)
        from client.mutexguard import EXIT_DUPLICATE
        self.assertEqual(EXIT_DUPLICATE, 11)


class WorkerSpawnTests(unittest.TestCase):
    """worker_mgr.default_spawn_fn passes ONLY --gen; without --server-url and
    --token-file every DGX decode answers dgx_unconfigured, forever."""

    def test_spawn_argv_carries_server_url_and_token_file(self):
        seen = {}

        def fake_popen(argv, **kw):
            seen["argv"] = list(argv)
            seen["kw"] = kw
            return object()

        cfg = make_cfg(server_url="http://<lan-ip>:8737/",
                       auth_token_file="state\\stt-token")
        spawn = app.build_spawn_fn(cfg, popen=fake_popen)
        spawn(7)
        argv = seen["argv"]
        self.assertIn("--gen", argv)
        self.assertEqual(argv[argv.index("--gen") + 1], "7")
        self.assertIn("--server-url", argv)
        self.assertEqual(argv[argv.index("--server-url") + 1],
                         "http://<lan-ip>:8737/")
        self.assertIn("--token-file", argv)
        self.assertEqual(argv[argv.index("--token-file") + 1], "state\\stt-token")
        self.assertIn("client.keshev_worker", argv)

    def test_spawn_is_never_the_broken_default(self):
        from client import worker_mgr
        spawn = app.build_spawn_fn(make_cfg(), popen=lambda argv, **kw: object())
        self.assertIsNot(spawn, worker_mgr.default_spawn_fn)


# ------------------------------------------------------------------- devices


class DeviceResolutionTests(TmpCase):
    def test_pinned_mic_is_selected_and_the_headset_refused(self):
        h = self.build()
        sel = h.app.resolve_device()
        self.assertEqual(sel.state, Selection.SELECTED)
        self.assertEqual(sel.device.name, "Logitech BRIO")
        self.assertTrue(sel.pin_honored)
        self.assertIn("WH-1000XM4", " ".join(n for n, _ in sel.refused))

    def test_no_allowed_mic_is_IDLE_NO_MIC_and_never_a_fallback(self):
        h = self.build(devices=(XM4,))
        opened = h.app.open_capture_now()
        self.assertFalse(opened)
        self.assertEqual(h.app.state, app.STATE_IDLE_NO_MIC)
        self.assertEqual(h.spies.opens, [], "a forbidden device was opened")
        self.assertIsNone(h.app.capture)

    def test_open_negotiates_the_format_and_starts_the_stream(self):
        h = self.build()
        self.assertTrue(h.app.open_capture_now())
        self.assertEqual(h.app.state, app.STATE_CAPTURING)
        self.assertEqual(h.spies.opens, [(BRIO.index, 16000, 1)])
        self.assertEqual(h.spies.streams[-1].started, 1)
        self.assertEqual(h.app.capture.cap_rate, 16000)
        evts = [e["evt"] for e in h.ledger()]
        self.assertIn("DEVICE_OPEN", evts)

    def test_reresolve_rebuilds_capture_but_REUSES_the_segmenter(self):
        """A second Segmenter would reset _seq to 0, regenerate ids already in
        the router's typed_lru, and DUP_DISCARD real speech — the single most
        dangerous mistake available in this assembly."""
        h = self.build()
        h.app.open_capture_now()
        seg, cap1, stream1 = h.app.segmenter, h.app.capture, h.app.stream
        h.app.reresolve_now()
        self.assertIs(h.app.segmenter, seg)
        self.assertIsNot(h.app.capture, cap1)
        self.assertEqual(stream1.stopped, 1)
        self.assertEqual(stream1.closed, 1)

    def test_drop_frames_accumulate_across_pipelines(self):
        h = self.build()
        h.app.open_capture_now()
        for f in frames(0.3, 205):
            h.app.capture.on_audio(f)          # 200-frame queue -> 5 dropped
        dropped = h.app.capture.frames_dropped
        self.assertGreater(dropped, 0)
        h.app.reresolve_now()
        self.assertEqual(h.app.capture.frames_dropped, 0)
        self.assertGreaterEqual(h.app.drop_frames(), dropped)

    def test_silent_open_event_raises_the_reresolve_flag_only(self):
        """scar 25 fires from the PortAudio callback thread: the handler may
        journal and set a flag — re-resolving there would deadlock PortAudio."""
        h = self.build()
        h.app.open_capture_now()
        h.spies.opens.clear()
        h.app.capture_events("DEVICE_SILENT_REOPEN", silent_s=30.0, rate=16000)
        self.assertTrue(h.app.reresolve_pending())
        self.assertEqual(h.spies.opens, [])
        self.assertIn("DEVICE_SILENT_REOPEN", [e["evt"] for e in h.ledger()])


# ------------------------------------------------------------------ end to end


class EndToEndTests(TmpCase):
    """Synthetic PCM in -> text out, through EVERY real stage."""

    def _speak(self, a, n_loud=40):
        for f in frames(0.3, n_loud):
            a.capture.on_audio(f)
        for f in frames(0.0, 40):              # 1.2s silence closes the segment
            a.capture.on_audio(f)
        while True:
            frame = a.capture.read(timeout=0)
            if frame is None:
                break
            a.segmenter.feed(frame)

    def test_fake_audio_in_text_out_in_order(self):
        worker = StubWorker([
            {"ok": True, "text": "שלום עולם", "lang": "he", "avg_logprob": -0.2},
            {"ok": True, "text": "second utterance", "lang": "en",
             "avg_logprob": -0.3},
        ])
        h = self.build(worker=worker)
        a = h.app
        a.open_capture_now()
        self._speak(a)
        self._speak(a)
        self.assertEqual(a.spool.qsize(), 2)
        a.router.step()
        a.router.step()
        self.assertEqual(h.typed(), ["שלום עולם", "second utterance"])
        outcomes = [j["outcome"] for j in h.journal()]
        self.assertEqual(outcomes, ["TYPED", "TYPED"])

    def test_every_segment_id_satisfies_the_wire_contract(self):
        h = self.build()
        h.app.open_capture_now()
        self._speak(h.app)
        self._speak(h.app)
        ids = []
        while (rec := h.app.spool.pop(timeout=0)) is not None:
            ids.append(rec.id)
        self.assertEqual(len(ids), 2)
        for rid in ids:
            with self.subTest(rid=rid):
                self.assertTrue(protocol.valid_request_id(rid), rid)
        self.assertEqual(ids, sorted(ids))

    def test_hallucination_is_dropped_by_the_real_guard_not_typed(self):
        """The K12 placeholder would have typed this into Iddo's window."""
        worker = StubWorker([
            {"ok": True, "text": "תודה רבה", "lang": "he", "avg_logprob": -0.2},
            {"ok": True, "text": "real speech", "lang": "en", "avg_logprob": -0.2},
        ])
        h = self.build(worker=worker)
        h.app.open_capture_now()
        self._speak(h.app)
        self._speak(h.app)
        h.app.router.step()
        h.app.router.step()
        self.assertEqual(h.typed(), ["real speech"])
        self.assertEqual([j["outcome"] for j in h.journal()],
                         ["GUARD_DROP", "TYPED"])

    def test_low_logprob_is_dropped_by_the_real_guard(self):
        worker = StubWorker([
            {"ok": True, "text": "perfectly normal words", "lang": "en",
             "avg_logprob": -3.5},
        ])
        h = self.build(worker=worker)
        h.app.open_capture_now()
        self._speak(h.app)
        h.app.router.step()
        self.assertEqual(h.typed(), [])
        self.assertEqual([j["outcome"] for j in h.journal()], ["GUARD_DROP"])

    def test_missing_avg_logprob_fails_OPEN(self):
        """A worker that stops reporting logprobs must not mute the mic."""
        worker = StubWorker([{"ok": True, "text": "no logprob here", "lang": "en"}])
        h = self.build(worker=worker)
        h.app.open_capture_now()
        self._speak(h.app)
        h.app.router.step()
        self.assertEqual(h.typed(), ["no logprob here"])

    def test_focus_refusal_parks_and_journals_PARKED(self):
        api = FakeApi()
        api.add(202, "", 888, r"C:\Windows\explorer.exe")   # title-less: refused
        api.foreground = 202
        worker = StubWorker([
            {"ok": True, "text": "must not land here", "lang": "en",
             "avg_logprob": -0.2},
        ])
        h = self.build(worker=worker, api=api)
        h.app.open_capture_now()
        self._speak(h.app)
        h.app.router.step()
        self.assertEqual(h.typed(), [])
        self.assertEqual([j["outcome"] for j in h.journal()], ["PARKED"])
        parked = (self.tmp / "state" / "parked.txt").read_text(encoding="utf-8")
        self.assertIn("must not land here", parked)
        evts = [e["evt"] for e in h.ledger()]
        self.assertIn("TYPE_FAIL_PARKED", evts)
        self.assertIn("FOCUS_BLOCK", evts)

    def test_stale_backlog_goes_to_recovered_never_to_live_focus(self):
        worker = StubWorker([
            {"ok": True, "text": "minutes old", "lang": "en", "avg_logprob": -0.2},
        ])
        h = self.build(worker=worker, cfg=make_cfg(stale_sec=5))
        a = h.app
        a.open_capture_now()
        self._speak(a)
        rec = a.spool.pop(timeout=0)
        rec.t_end -= 600.0
        a.spool.enqueue(rec)
        a.router.step()
        self.assertEqual(h.typed(), [])
        recovered = (self.tmp / "state" / "recovered.txt").read_text(encoding="utf-8")
        self.assertIn("minutes old", recovered)


# ------------------------------------------------------------------ lifecycle


class LifecycleTests(TmpCase):
    def test_start_then_shutdown_returns_the_thread_count_to_baseline(self):
        before = threading.active_count()
        h = self.build()
        h.app.start()
        self.assertGreater(threading.active_count(), before)
        self.assertEqual(h.worker.started, 1)
        h.app.shutdown()
        deadline = time.monotonic() + 5.0
        while threading.active_count() > before and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertEqual(threading.active_count(), before,
                         [t.name for t in threading.enumerate()])
        self.assertEqual(h.worker.stopped, 1)
        self.assertEqual(h.spies.streams[-1].closed, 1)

    def test_shutdown_flushes_the_open_segment_instead_of_discarding_it(self):
        h = self.build()
        a = h.app
        a.open_capture_now()
        for f in frames(0.3, 40):              # speech still open, never closed
            a.capture.on_audio(f)
        while (frame := a.capture.read(timeout=0)) is not None:
            a.segmenter.feed(frame)
        self.assertEqual(a.spool.qsize(), 0)
        a.shutdown()
        self.assertEqual(a.spool.qsize(), 1)
        self.assertIn("SESSION_END", [e["evt"] for e in h.ledger()])

    def test_shutdown_is_idempotent(self):
        h = self.build()
        h.app.shutdown()
        h.app.shutdown()

    def test_session_begin_is_journaled_at_build(self):
        h = self.build()
        begins = [e for e in h.ledger() if e["evt"] == "SESSION_BEGIN"]
        self.assertEqual(len(begins), 1)
        self.assertEqual(begins[0]["sid"], "abcdef12")


if __name__ == "__main__":
    unittest.main()


class ThreadDeathIsLoud(unittest.TestCase):
    """THE 2026-08-14 17:22 OUTAGE, as a law.

    The stream went silent, the supervisor called reresolve_now(), something in
    there raised, the exception escaped the bare daemon thread, and the thread
    ceased — one line after _close_stream(). KESHEV held no device for FOUR
    HOURS while every heartbeat reported READY. Nothing journalled a thing: no
    error, no state change, no reopen attempt. A silent thread death is the
    same lie as a green icon over a dead mic (scar 17/18).
    """

    def setUp(self):
        import shutil
        self.td = Path(tempfile.mkdtemp(prefix="keshev-td-"))
        # Registered FIRST, so unittest's LIFO cleanup runs it LAST — after the
        # telemetry handle below is closed. Windows will not delete a directory
        # with an open log file under it.
        self.addCleanup(shutil.rmtree, self.td, True)
        self.app = AppHarness(self.td).app
        self.addCleanup(self.app.telemetry.close)

    def _explode(self, flag, msg):
        def boom():
            flag.set()
            raise RuntimeError(msg)
        return boom

    def test_dying_critical_thread_is_journalled_and_stops_the_app(self):
        a, ran = self.app, threading.Event()
        a._spawn("keshev-device-supervisor", self._explode(ran, "enumeration blew up"))
        self.assertTrue(ran.wait(2.0), "target never ran")
        self.assertTrue(
            a.stop.wait(2.0),
            "a dead device supervisor left the app running — this is the "
            "four-hour deaf outage of 2026-08-14")
        text = "\n".join(p.read_text(encoding="utf-8", errors="replace")
                         for p in (self.td / "state").rglob("*.log"))
        self.assertIn("THREAD_DIED", text,
                      "a thread died and nothing was written down")

    def test_dying_tray_thread_does_NOT_stop_dictation(self):
        """The picture may fail; the audio path may not (scar 12's inversion)."""
        a, ran = self.app, threading.Event()
        a._spawn("keshev-tray", self._explode(ran, "tkinter went away"))
        self.assertTrue(ran.wait(2.0), "target never ran")
        self.assertFalse(
            a.stop.wait(1.0),
            "a dead TRAY stopped dictation — the mic must outlive the window")

    def test_critical_set_names_the_threads_start_actually_spawns(self):
        """CRITICAL_THREADS is matched by NAME, so a rename in start() would
        silently downgrade the supervisor to cosmetic. Bind them together."""
        src = Path(app.__file__).read_text(encoding="utf-8")
        for name in app.CRITICAL_THREADS:
            self.assertIn(f'"{name}"', src,
                          f"CRITICAL_THREADS names {name!r} but nothing spawns it")


class SearcherIsNotAMicrophone(unittest.TestCase):
    """2026-08-15 00:05 — KESHEV refused to start and Iddo had no mic, because
    a stuck code-search sat in the process table:

        grep.exe -ril scar /d/CLAUDE/alma-mic /d/CLAUDE/voice-input

    almamic_alive() scans COMMAND LINES for alma-mic|voice-input|heb-mic, and
    a searcher's arguments contain those paths. It reported a rival dictation
    client that did not exist. His own scar register warns of exactly this
    trap (reference_double_mic_fix: never match a process by a word that is in
    your own command).

    The law: a rival mic must be identified by its EXECUTABLE, never by a path
    that merely appears in someone's arguments.
    """

    SEARCHERS = [
        r'"C:\Program Files\Git\usr\bin\grep.exe" -ril scar /d/CLAUDE/alma-mic',
        r'"C:\Program Files\Git\bin\bash.exe" -c "grep -r voice-input ."',
        r'C:\Windows\System32\findstr.exe /s heb-mic *.py',
        r'powershell.exe -Command "Select-String alma-mic"',
        r'C:\Windows\explorer.exe D:\CLAUDE\alma-mic',
    ]
    REAL_RIVALS = [
        r'C:\Python313\pythonw.exe D:\CLAUDE\alma-mic\gui.py',
        r'C:\Python312\python.exe D:\CLAUDE\voice-input\voice_input.py',
        r'C:\Python312\pythonw.exe -s D:\CLAUDE\voice-input\supervisor.py',
    ]

    def test_a_searcher_never_blocks_startup(self):
        for cmd in self.SEARCHERS:
            with self.subTest(cmd=cmd[:60]):
                alive, why = app.almamic_alive(lambda c=cmd: [c], lambda: [])
                self.assertFalse(
                    alive,
                    f"a SEARCH TOOL blocked KESHEV from starting ({why}) — this "
                    f"is the 2026-08-15 outage: a grep left Iddo with no mic")

    def test_a_real_rival_still_blocks(self):
        """The narrowing must not have made the guard blind — the whole point
        of criterion 23 is that two clients never fight over the BRIO."""
        for cmd in self.REAL_RIVALS:
            with self.subTest(cmd=cmd[:60]):
                alive, why = app.almamic_alive(lambda c=cmd: [c], lambda: [])
                self.assertTrue(
                    alive, f"a REAL rival dictation client was not detected: {cmd}")

    def test_running_alma_task_still_blocks(self):
        alive, why = app.almamic_alive(lambda: [], lambda: [("ALMA-MIC-Elevated", "Running")])
        self.assertTrue(alive)
        self.assertIn("ALMA-MIC-Elevated", why)
