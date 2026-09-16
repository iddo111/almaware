"""K15 TDD — client/tray.py: the part that makes KESHEV HONEST TO LOOK AT.

(PHASE2-DESIGN.md section 4.5 "Client top-level state (tray honesty)", the
K15 row of section 10, the tray.py row of section 2, scars 22/49.)

THE ONE THING THIS PART EXISTS TO PREVENT
-----------------------------------------
A mic that has silently stopped hearing while showing a calm green icon.
That is the single worst failure of the whole old stack: Iddo talks, nothing
arrives, and the tray says everything is fine. So the tests below are not
"does it render" tests. They are:

  1. The tray CANNOT BE TOLD a state.  There is no set_state(); TrayInputs
     carries raw OBSERVATIONS only (capture state, frame recency, FSM state,
     worker state, decode results). The state is DERIVED. A caller cannot
     lie to the tray, therefore the tray cannot lie to Iddo.
  2. DEAF IS UNMISTAKABLE.  Two deaf-family states (no mic, no engine),
     both FLASHING (>= 2 icon frames that alternate on every tick), both in
     the red family, both re-ballooning while they last — a deafness that
     scrolls out of the notification area is a deafness nobody saw.
  3. A CAPTURE CALLBACK THAT WENT QUIET IS DEAFNESS, whatever the state
     variable says. capture_state == "CAPTURING" with a stale frame age
     resolves to the deaf family, not to READY.
  4. THE ENGINE SHOWN IS THE ENGINE USED.  Never the configured one, never
     the routing pointer when the last real decode disagrees with it, and
     an unproven pointer is labelled unproven.
  5. SILENCE IS NEVER A SIGNAL.  Sacred Audio (scar 22): every alert is
     visual. No sound flag, no beep call site, no way to ask for one.
  6. A TRAY THAT CANNOT SEE ITS OWN STATE SAYS SO.  If the snapshot raises,
     the icon goes UNKNOWN + flashing — it does NOT keep showing last-good
     green.

Everything runs headless against the fake backend: no GUI, no window, no
device, no audio, no network. pystray is NOT installed on this PC (Pillow
is), so the real backend is expected to be unavailable and make_backend()
must fall back honestly rather than pretend.
"""
from __future__ import annotations

import dataclasses
import json
import re
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from client import tray  # noqa: E402
from client.telemetry import Telemetry  # noqa: E402


# ------------------------------------------------------------------ helpers

def inputs(**over):
    """A healthy, hearing, DGX-decoding observation set — the baseline that
    every test perturbs by ONE field, so a failure names its own cause."""
    base = dict(
        paused=False,
        capture_state="CAPTURING",
        frame_age_s=0.05,
        fsm_state="PRIMARY_DGX",
        fsm_deaf=False,
        maint=False,
        worker_state="READY",
        local_state="READY",
        decoding=False,
        speech_active=False,
        last_decode_engine="dgx",
        last_decode_age_s=2.0,
        mic_name="Logitech BRIO",
        queue_depth=0,
    )
    base.update(over)
    return tray.TrayInputs(**base)


def make_tray(snap, **kw):
    """A Tray on the headless backend. `snap` is either a TrayInputs or a
    zero-arg callable (so a test can make the snapshot raise)."""
    backend = tray.HeadlessBackend()
    fn = snap if callable(snap) else (lambda: snap)
    t = tray.Tray(backend, snapshot_fn=fn, **kw)
    return t, backend


# ------------------------------------------------- 1. cannot be told a state

class TheTrayCannotBeToldAState(unittest.TestCase):
    """Honesty rule #1: the state is derived from observations, never set."""

    def test_no_setter_exists(self):
        for banned in ("set_state", "show_state", "force_state", "state_setter"):
            self.assertFalse(hasattr(tray.Tray, banned),
                             f"Tray.{banned} would let a caller assert a state "
                             f"the tray is not in")

    def test_inputs_carry_observations_not_conclusions(self):
        fields = {f.name for f in dataclasses.fields(tray.TrayInputs)}
        for banned in ("state", "client_state", "tray_state", "icon", "status"):
            self.assertNotIn(banned, fields,
                             f"TrayInputs.{banned} is a CONCLUSION — the tray "
                             f"must compute its state, not be handed one")
        for needed in ("capture_state", "frame_age_s", "fsm_state", "fsm_deaf",
                       "worker_state", "last_decode_engine", "last_decode_age_s"):
            self.assertIn(needed, fields)

    def test_state_is_a_pure_function_of_the_snapshot(self):
        t, _ = make_tray(inputs())
        self.assertEqual(t.update().state, tray.READY)
        # same tray, new observation -> new truth, no memory of being green
        t2, _ = make_tray(inputs(capture_state="IDLE_NO_MIC"))
        self.assertEqual(t2.update().state, tray.IDLE_NO_MIC)


# --------------------------------------------------- 2. every state renders

class EveryDesignStateRenders(unittest.TestCase):
    """K15 row: 'every section-4.5 state renders (icon set + balloon)'."""

    CASES = {
        tray.READY:       inputs(),
        tray.LISTENING:   inputs(speech_active=True),
        tray.DECODING:    inputs(decoding=True),
        tray.CAPTURING:   inputs(worker_state="WARMING"),
        tray.DEGRADED:    inputs(fsm_state="FALLBACK_LOCAL",
                                 last_decode_engine="local"),
        tray.FLAKY:       inputs(fsm_state="PINNED_LOCAL",
                                 last_decode_engine="local"),
        tray.MAINT:       inputs(maint=True, fsm_state="FALLBACK_LOCAL",
                                 last_decode_engine="local"),
        tray.DEAF:        inputs(fsm_deaf=True),
        tray.IDLE_NO_MIC: inputs(capture_state="IDLE_NO_MIC", mic_name=None),
        tray.PAUSED:      inputs(paused=True),
    }

    def test_the_ladder_covers_section_4_5_and_the_activity_states(self):
        for state in (tray.READY, tray.LISTENING, tray.DECODING,
                      tray.DEGRADED, tray.DEAF, tray.PAUSED, tray.MAINT,
                      tray.FLAKY, tray.CAPTURING, tray.IDLE_NO_MIC):
            self.assertIn(state, tray.LADDER)
        self.assertIn(tray.UNKNOWN, tray.STATES)

    def test_each_state_resolves_from_its_own_observations(self):
        for state, obs in self.CASES.items():
            with self.subTest(state=state):
                self.assertEqual(tray.resolve_state(obs), state)

    def test_each_state_has_an_icon_a_tooltip_and_an_entry_balloon(self):
        for state, obs in self.CASES.items():
            with self.subTest(state=state):
                t, backend = make_tray(obs)
                vis = t.update()
                self.assertEqual(vis.state, state)
                self.assertTrue(vis.icon.key)
                self.assertIn(state, vis.tooltip)
                self.assertIsNotNone(vis.balloon,
                                     "entering a state with no balloon is a "
                                     "state change nobody was told about")
                self.assertTrue(vis.balloon.text.strip())
                self.assertTrue(backend.icons, "backend never got an icon")
                self.assertEqual(backend.icons[-1][0], vis.icon.key)
                self.assertEqual(backend.balloons[-1].title, vis.balloon.title)

    def test_no_two_states_look_the_same(self):
        signatures = {}
        for state in tray.STATES:
            sig = tuple(f.key for f in tray.icon_frames(state))
            self.assertNotIn(sig, signatures,
                             f"{state} and {signatures.get(sig)} render the "
                             f"same icon — one of them is a lie")
            signatures[sig] = state

    def test_a_balloon_is_not_repeated_for_an_unchanged_healthy_state(self):
        t, backend = make_tray(inputs())
        t.update()
        t.update()
        t.update()
        self.assertEqual(len(backend.balloons), 1)


# ---------------------------------------------------- 3. DEAF is unmistakable

class DeafIsUnmistakable(unittest.TestCase):
    """The whole reason this rebuild exists."""

    DEAF_FAMILY = (tray.DEAF, tray.IDLE_NO_MIC)

    def test_deaf_family_flashes(self):
        for state in self.DEAF_FAMILY:
            with self.subTest(state=state):
                frames = tray.icon_frames(state)
                self.assertGreaterEqual(len(frames), 2,
                                        f"{state} must FLASH (design 4.5: "
                                        f"'red flash + balloon')")
        self.assertEqual(len(tray.icon_frames(tray.READY)), 1,
                         "READY must be steady — a flashing green teaches the "
                         "eye to ignore flashing")

    def test_the_flash_actually_alternates_on_tick(self):
        t, backend = make_tray(inputs(fsm_deaf=True))
        keys = [t.tick().icon.key for _ in range(4)]
        self.assertEqual(len(set(keys)), 2, f"icon never alternated: {keys}")
        self.assertNotEqual(keys[0], keys[1])
        self.assertEqual(keys[0], keys[2])
        self.assertEqual([k for k, _ in backend.icons], keys)

    def test_ready_does_not_flash_on_tick(self):
        t, _ = make_tray(inputs())
        self.assertEqual(len({t.tick().icon.key for _ in range(4)}), 1)

    def test_deaf_is_red_and_ready_is_green(self):
        """Both deaf states must read as ALARM at a glance. The first cut of
        this test only asked for r>150 and r>g+60, which a decorative PINK
        passes — and pink is what actually rendered. Blue is pinned down too:
        an alarm has no blue in it."""
        for state in self.DEAF_FAMILY:
            r, g, b = tray.icon_frames(state)[0].rgb
            self.assertGreater(r, 150, f"{state} lead frame is not red")
            self.assertGreater(r, g + 60)
            self.assertLess(b, r // 2, f"{state} lead frame reads pink/violet, "
                                       f"not red: {(r, g, b)}")
            # blue running ahead of green IS the pink signature — the eye sees
            # it instantly, the earlier r/g-only assertions did not.
            self.assertLessEqual(b, g + 25,
                                 f"{state} lead frame {(r, g, b)} reads PINK, "
                                 f"not alarm-red")
        rr, rg, rb = tray.icon_frames(tray.READY)[0].rgb
        self.assertGreater(rg, rr + 40, "READY is not green")

    def test_a_silently_stopped_capture_callback_is_deafness(self):
        """capture_state still says CAPTURING, no frame in a minute. THIS is
        the calm-green-icon failure. It must resolve deaf."""
        obs = inputs(frame_age_s=60.0)
        self.assertIn(tray.resolve_state(obs), self.DEAF_FAMILY)
        t, _ = make_tray(obs)
        vis = t.update()
        self.assertTrue(vis.flash)
        self.assertIn("60", vis.tooltip.replace(".0", ""))

    def test_a_capture_that_never_delivered_a_frame_is_deafness(self):
        self.assertIn(tray.resolve_state(inputs(frame_age_s=None)),
                      self.DEAF_FAMILY)

    def test_deafness_reballoons_so_it_cannot_scroll_away(self):
        clock = [0.0]
        t, backend = make_tray(inputs(fsm_deaf=True),
                               monotonic=lambda: clock[0])
        t.update()
        self.assertEqual(len(backend.balloons), 1)
        clock[0] = tray.DEAF_BALLOON_REPEAT_S - 1
        t.update()
        self.assertEqual(len(backend.balloons), 1, "re-balloon too eager")
        clock[0] = tray.DEAF_BALLOON_REPEAT_S + 1
        t.update()
        self.assertEqual(len(backend.balloons), 2,
                         "a deafness that stops shouting is a deafness nobody "
                         "notices")

    def test_deaf_balloon_says_what_is_wrong_in_words(self):
        t, _ = make_tray(inputs(fsm_deaf=True))
        b = t.update().balloon
        self.assertEqual(b.level, "error")
        self.assertIn("NOT", b.title.upper())
        t2, _ = make_tray(inputs(capture_state="IDLE_NO_MIC", mic_name=None))
        b2 = t2.update().balloon
        self.assertEqual(b2.level, "error")
        self.assertNotEqual(b2.text, b.text, "no-mic and no-engine deafness "
                                             "are different problems")

    # --------------------------------------------------- Sacred Audio (22)

    def test_no_balloon_can_ask_for_a_sound(self):
        fields = {f.name for f in dataclasses.fields(tray.Balloon)}
        for banned in ("sound", "beep", "audio", "silent"):
            self.assertNotIn(banned, fields)

    def test_no_sound_call_site_in_the_module(self):
        # Tokens are ASSEMBLED, never written literally: K0's gate G6 is a
        # token scan over the whole repo, and a test that spells them out is
        # itself a G6 violation (tools/lint.py does the same in its self-test).
        src = (REPO / "client" / "tray.py").read_text(encoding="utf-8")
        for token in ("MessageBeep", "win" + "sound", "play" + "sound",
                      "Beep(", "Play" + "Sound"):
            self.assertNotIn(token, src,
                             f"{token} in tray.py — Sacred Audio (scar 22): "
                             f"every alert is VISUAL")

    def test_the_win32_balloon_flags_carry_the_nosound_bit(self):
        self.assertTrue(tray.BALLOON_FLAGS & tray.NIIF_NOSOUND)


# ------------------------------------------------------- 4. engine honesty

class TheEngineShownIsTheEngineUsed(unittest.TestCase):

    def test_routing_says_dgx_but_the_last_real_decode_was_local(self):
        label = tray.engine_label(inputs(fsm_state="PRIMARY_DGX",
                                        last_decode_engine="local",
                                        last_decode_age_s=1.0))
        self.assertIn("local", label.lower())
        self.assertNotIn("dgx", label.lower())

    def test_dgx_in_use_says_dgx(self):
        self.assertIn("dgx", tray.engine_label(inputs()).lower())

    def test_an_unproven_pointer_is_labelled_unproven(self):
        label = tray.engine_label(inputs(last_decode_engine=None,
                                         last_decode_age_s=None))
        self.assertIn("dgx", label.lower())
        self.assertTrue(re.search(r"unproven|no decode", label, re.I),
                        f"{label!r} claims an engine that has never decoded")

    def test_a_stale_decode_stops_proving_anything(self):
        label = tray.engine_label(
            inputs(last_decode_engine="dgx",
                   last_decode_age_s=tray.ENGINE_PROVEN_S + 10))
        self.assertTrue(re.search(r"unproven|no decode", label, re.I))

    def test_paused_never_says_in_use_because_nothing_is_flowing(self):
        label = tray.engine_label(inputs(paused=True))
        self.assertNotIn("in use", label.lower())
        self.assertIn("paused", label.lower())

    def test_deaf_shows_no_engine_at_all(self):
        self.assertEqual(tray.engine_label(inputs(fsm_deaf=True)).lower(),
                         "none")
        self.assertEqual(
            tray.engine_label(inputs(capture_state="IDLE_NO_MIC")).lower(),
            "none")

    def test_the_engine_is_in_the_tooltip_and_the_menu(self):
        t, _ = make_tray(inputs(fsm_state="FALLBACK_LOCAL",
                                last_decode_engine="local",
                                last_decode_age_s=1.0))
        vis = t.update()
        self.assertIn("local", vis.tooltip.lower())
        labels = {i.key: i.label for i in t.menu()}
        self.assertIn("local", labels["engine"].lower())

    def test_degraded_carries_its_reason(self):
        t, _ = make_tray(inputs(maint=True, fsm_state="FALLBACK_LOCAL",
                                last_decode_engine="local"))
        vis = t.update()
        self.assertEqual(vis.state, tray.MAINT)
        self.assertIn("maintenance", vis.tooltip.lower())


# ------------------------------------------------------ 5. visible counters

class VisibleCounters(unittest.TestCase):
    """Criterion 18 / scar 49: 'Owner-rej: N' is a VISIBLE counter, and a
    rejection is never a silent drop."""

    def test_owner_rej_counter_is_in_the_menu_and_tracks_the_number(self):
        c = tray.Counters(owner_rej=0)
        t, _ = make_tray(inputs(counters=c))
        t.update()
        self.assertIn("Owner-rej: 0", [i.label for i in t.menu()])
        t2, _ = make_tray(inputs(counters=tray.Counters(owner_rej=7)))
        t2.update()
        self.assertIn("Owner-rej: 7", [i.label for i in t2.menu()])

    def test_owner_rej_click_opens_the_rejection_log(self):
        opened = []
        with TemporaryDirectory() as td:
            state = Path(td)
            (state / "owner_rej.log").write_text("x\n", encoding="utf-8")
            t, _ = make_tray(inputs(counters=tray.Counters(owner_rej=3)),
                             state_dir=state, open_fn=opened.append)
            t.update()
            t.invoke("owner_rej")
            self.assertEqual(opened, [state / "owner_rej.log"])

    def test_recovered_counter_click_opens_recovered_txt(self):
        opened = []
        with TemporaryDirectory() as td:
            state = Path(td)
            (state / "recovered.txt").write_text("x\n", encoding="utf-8")
            t, _ = make_tray(inputs(counters=tray.Counters(recovered=2)),
                             state_dir=state, open_fn=opened.append)
            t.update()
            self.assertIn("Recovered: 2", [i.label for i in t.menu()])
            t.invoke("recovered")
            self.assertEqual(opened, [state / "recovered.txt"])

    def test_the_design_menu_exists_in_order(self):
        t, _ = make_tray(inputs())
        t.update()
        self.assertEqual([i.key for i in t.menu()], list(tray.MENU_KEYS))
        for required in ("pause", "engine", "mic", "owner_rej", "recovered",
                         "open_log", "recalibrate", "restart_worker", "quit"):
            self.assertIn(required, tray.MENU_KEYS)

    def test_the_mic_item_shows_the_device_actually_open(self):
        t, _ = make_tray(inputs())
        t.update()
        mic = {i.key: i.label for i in t.menu()}["mic"]
        self.assertIn("BRIO", mic)
        self.assertIn("●", mic)                      # ● = open
        t2, _ = make_tray(inputs(capture_state="IDLE_NO_MIC", mic_name=None))
        t2.update()
        mic2 = {i.key: i.label for i in t2.menu()}["mic"]
        self.assertIn("○", mic2)                     # ○ = not open
        self.assertIn("none", mic2.lower())

    def test_the_tooltip_carries_the_working_counters(self):
        t, _ = make_tray(inputs(queue_depth=4,
                                counters=tray.Counters(typed=11, guard_drop=5,
                                                       parked=1, owner_rej=2)))
        tip = t.update().tooltip
        for needle in ("typed 11", "guard 5", "parked 1", "q 4",
                       "owner-rej 2"):
            self.assertIn(needle, tip.lower())

    def test_an_unwired_menu_action_says_so_instead_of_doing_nothing(self):
        t, backend = make_tray(inputs())
        t.update()
        before = len(backend.balloons)
        t.invoke("recalibrate")                 # no on_recalibrate wired
        self.assertEqual(len(backend.balloons), before + 1)
        self.assertIn("not wired", backend.balloons[-1].text.lower())


# ------------------------------------------------------------ 6. pause hotkey

class PauseHotkey(unittest.TestCase):

    def test_parse_the_configured_hotkey(self):
        hk = tray.parse_hotkey("ctrl+alt+m")
        self.assertEqual(hk.vk, 0x4D)
        self.assertTrue(hk.mods & tray.MOD_CONTROL)
        self.assertTrue(hk.mods & tray.MOD_ALT)
        self.assertFalse(hk.mods & tray.MOD_SHIFT)
        self.assertEqual(hk.label, "Ctrl+Alt+M")

    def test_a_hotkey_with_no_modifier_is_refused(self):
        with self.assertRaises(tray.HotkeyError):
            tray.parse_hotkey("m")

    def test_garbage_hotkeys_are_refused_loudly(self):
        for bad in ("", "ctrl+", "ctrl+alt+nope", "ctrl+alt+mm"):
            with self.subTest(bad=bad), self.assertRaises(tray.HotkeyError):
                tray.parse_hotkey(bad)

    def test_the_hotkey_toggles_pause_and_the_icon_follows(self):
        paused = {"v": False}
        t, _ = make_tray(lambda: inputs(paused=paused["v"]),
                         on_pause=lambda: paused.__setitem__("v", True),
                         on_resume=lambda: paused.__setitem__("v", False))
        self.assertEqual(t.update().state, tray.READY)
        t.toggle_pause()
        self.assertTrue(paused["v"])
        vis = t.update()
        self.assertEqual(vis.state, tray.PAUSED)
        self.assertEqual({i.key: i.label for i in t.menu()}["pause"], "Resume")
        t.toggle_pause()
        self.assertFalse(paused["v"])
        self.assertEqual(t.update().state, tray.READY)

    def test_pause_via_the_menu_item_is_the_same_action(self):
        paused = {"v": False}
        t, _ = make_tray(lambda: inputs(paused=paused["v"]),
                         on_pause=lambda: paused.__setitem__("v", True),
                         on_resume=lambda: paused.__setitem__("v", False))
        t.update()
        t.invoke("pause")
        self.assertTrue(paused["v"])
        self.assertEqual(t.update().state, tray.PAUSED)

    def test_resume_returns_to_the_OBSERVED_state_not_a_remembered_one(self):
        """Paused while healthy, unplugged while paused -> resume must land on
        the truth (no mic), not on the green it remembers."""
        obs = {"v": inputs(paused=True)}
        t, _ = make_tray(lambda: obs["v"],
                         on_resume=lambda: obs.__setitem__(
                             "v", inputs(capture_state="IDLE_NO_MIC",
                                         mic_name=None)))
        self.assertEqual(t.update().state, tray.PAUSED)
        t.toggle_pause()
        self.assertEqual(t.update().state, tray.IDLE_NO_MIC)


# ----------------------------------------------- 7. no window, no focus theft

class NoWindowNoFocusTheft(unittest.TestCase):
    """K15 row: 'no window class exists (grep assert: no SetForegroundWindow
    on self)'. A tray you can type into is a tray that eats dictation."""

    FORBIDDEN = ("SetForegroundWindow", "SetActiveWindow", "BringWindowToTop",
                 "AttachThreadInput", "SwitchToThisWindow", "SetFocus",
                 "CreateWindowEx", "RegisterClassEx", "tkinter", "PySide",
                 "PyQt", "wx.App")

    def test_the_module_creates_no_window_and_steals_no_focus(self):
        src = (REPO / "client" / "tray.py").read_text(encoding="utf-8")
        for token in self.FORBIDDEN:
            self.assertNotIn(token, src, f"{token} in client/tray.py")

    def test_the_module_never_imports_the_typer_or_the_focus_guard(self):
        src = (REPO / "client" / "tray.py").read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"^\s*(?:from|import)\s+\S*\b(typer|focus)\b",
                                    src, re.M))


# ------------------------------------------------------- 8. thin backend seam

class TheBackendIsThinAndFakeable(unittest.TestCase):

    SURFACE = ("set_icon", "notify", "set_menu", "run", "stop")

    def test_the_fake_implements_the_whole_surface(self):
        for name in self.SURFACE:
            self.assertTrue(callable(getattr(tray.HeadlessBackend, name, None)),
                            f"HeadlessBackend.{name} missing")
            self.assertTrue(callable(getattr(tray.TrayBackend, name, None)))

    def test_make_backend_falls_back_honestly_when_pystray_is_absent(self):
        backend, real = tray.make_backend(import_fn=self._no_pystray)
        self.assertFalse(real)
        self.assertIsInstance(backend, tray.HeadlessBackend)

    def test_the_fallback_is_journalled_not_silent(self):
        with TemporaryDirectory() as td:
            tel = Telemetry(Path(td), "abcdef01")
            try:
                tray.make_backend(import_fn=self._no_pystray, emit=tel.event)
            finally:
                tel.close()
            lines = [json.loads(x) for x in
                     (Path(td) / "events.jsonl").read_text(
                         encoding="utf-8").splitlines() if x.strip()]
            self.assertTrue(any("TRAY_BACKEND" in str(e.get("state", ""))
                                for e in lines), lines)

    def test_the_real_backend_refuses_to_pretend(self):
        with self.assertRaises(tray.TrayBackendUnavailable):
            tray.PystrayBackend(import_fn=self._no_pystray)

    def test_it_refuses_EVEN_WITH_the_dependency_present(self):
        """The drawing code is unbuilt. A backend that constructed happily and
        then drew nothing would make make_backend() report a real tray over an
        empty notification area — a tray lying about its own existence."""
        with self.assertRaises(tray.TrayBackendUnavailable) as caught:
            tray.PystrayBackend(import_fn=lambda name: object())
        self.assertIn("unbuilt", str(caught.exception).lower())
        backend, real = tray.make_backend(import_fn=lambda name: object())
        self.assertFalse(real)
        self.assertIsInstance(backend, tray.HeadlessBackend)

    def test_the_backend_really_is_unavailable_on_this_pc(self):
        """Not a hypothetical: pystray is genuinely not installed here."""
        backend, real = tray.make_backend()
        self.assertFalse(real, "pystray appeared — rewire the real backend")
        self.assertIsInstance(backend, tray.HeadlessBackend)

    @staticmethod
    def _no_pystray(name):
        raise ModuleNotFoundError(f"No module named {name!r}")


# --------------------------------------------- 9. a blind tray says it is blind

class ATrayThatCannotSeeSaysSo(unittest.TestCase):

    def test_a_raising_snapshot_becomes_UNKNOWN_never_last_good_green(self):
        boom = {"v": False}

        def snap():
            if boom["v"]:
                raise RuntimeError("router thread is gone")
            return inputs()

        t, backend = make_tray(snap)
        self.assertEqual(t.update().state, tray.READY)
        boom["v"] = True
        vis = t.update()
        self.assertEqual(vis.state, tray.UNKNOWN)
        self.assertTrue(vis.flash, "an unknown state must be visually loud")
        self.assertNotEqual(vis.icon.key, tray.icon_frames(tray.READY)[0].key)
        self.assertEqual(backend.balloons[-1].level, "error")

    def test_recovery_from_UNKNOWN_is_possible(self):
        boom = {"v": True}

        def snap():
            if boom["v"]:
                raise RuntimeError("no")
            return inputs()

        t, _ = make_tray(snap)
        self.assertEqual(t.update().state, tray.UNKNOWN)
        boom["v"] = False
        self.assertEqual(t.update().state, tray.READY)


# -------------------------------------------------------- 10. telemetry wiring

class StateChangesAreJournalled(unittest.TestCase):

    def test_every_state_change_lands_in_the_closed_vocabulary_ledger(self):
        with TemporaryDirectory() as td:
            tel = Telemetry(Path(td), "abcdef02")
            obs = {"v": inputs()}
            t, _ = make_tray(lambda: obs["v"], emit=tel.event)
            try:
                t.update()
                obs["v"] = inputs(fsm_deaf=True)
                t.update()
                t.update()                       # unchanged: no second line
            finally:
                tel.close()
            evts = [json.loads(x) for x in
                    (Path(td) / "events.jsonl").read_text(
                        encoding="utf-8").splitlines() if x.strip()]
            states = [e.get("state") for e in evts if e["evt"] == "STATE"]
            self.assertEqual(states, [f"TRAY_{tray.READY}",
                                      f"TRAY_{tray.DEAF}"])


# ------------------------------------------------------------ 11. real pixels

class IconsRenderToRealPixels(unittest.TestCase):
    """Pillow IS installed on this PC; pystray is not. Rendering is testable
    even though the tray backend is not."""

    def setUp(self):
        try:
            import PIL  # noqa: F401
        except ModuleNotFoundError:
            self.skipTest("Pillow not installed")

    def test_every_frame_renders_and_no_two_frames_are_identical(self):
        seen = {}
        for state in tray.STATES:
            for frame in tray.icon_frames(state):
                png = tray.render_icon_png(frame)
                self.assertTrue(png.startswith(b"\x89PNG"))
                self.assertNotIn(png, seen,
                                 f"{frame.key} renders identically to "
                                 f"{seen.get(png)}")
                seen[png] = frame.key


# ------------------------------------- 12. the recency signal has a REAL source

class FrameRecencyComesFromTheCounterThatActuallyExists(unittest.TestCase):
    """client/capture.py:198 hands this exact job here, by name:

        "A stream that stops delivering callbacks entirely is the wedge case,
         watched elsewhere (design sec 7, capture-callback recency)."

    CapturePipeline keeps no timestamp — it keeps `callbacks`, a monotonic
    counter. Deafness is therefore DERIVED here, with no change to capture.py:
    a counter that stops moving is a stream that stopped delivering.
    """

    def test_no_pipeline_at_all_reads_as_never_heard(self):
        r = tray.FrameRecency(monotonic=lambda: 100.0)
        self.assertIsNone(r.observe(None))

    def test_a_pipeline_that_never_called_back_is_not_fresh(self):
        clock = [0.0]
        r = tray.FrameRecency(monotonic=lambda: clock[0])
        self.assertIsNone(r.observe(0))
        clock[0] = 30.0
        self.assertEqual(r.observe(0), 30.0)

    def test_the_first_callback_is_fresh(self):
        r = tray.FrameRecency(monotonic=lambda: 5.0)
        self.assertEqual(r.observe(1), 0.0)

    def test_a_frozen_counter_ages(self):
        clock = [0.0]
        r = tray.FrameRecency(monotonic=lambda: clock[0])
        r.observe(100)
        clock[0] = 7.5
        self.assertEqual(r.observe(100), 7.5)

    def test_a_moving_counter_stays_fresh(self):
        clock = [0.0]
        r = tray.FrameRecency(monotonic=lambda: clock[0])
        r.observe(100)
        for n in range(101, 105):
            clock[0] += 1.0
            self.assertEqual(r.observe(n), 0.0)

    def test_a_rebuilt_pipeline_is_not_mistaken_for_deafness(self):
        """app.reresolve_now() builds a NEW CapturePipeline whose counter
        restarts at 0. That is a device re-open, not a dead mic."""
        clock = [0.0]
        r = tray.FrameRecency(monotonic=lambda: clock[0])
        r.observe(5000)
        clock[0] = 10.0
        self.assertEqual(r.observe(0), 0.0)      # reset = a fresh start
        clock[0] = 12.0
        self.assertEqual(r.observe(0), 2.0)      # ...and it ages from there

    def test_it_drives_the_deaf_rule_end_to_end(self):
        clock = [0.0]
        r = tray.FrameRecency(monotonic=lambda: clock[0])
        r.observe(10)
        clock[0] = tray.FRAME_STALE_S + 1
        obs = inputs(frame_age_s=r.observe(10))
        self.assertEqual(tray.resolve_state(obs), tray.IDLE_NO_MIC)


# ------------------------------------------- 13. unknown is not the same as zero

class ACounterWithNoSourceSaysUnknownNotZero(unittest.TestCase):
    """'Owner-rej: 0' means I COUNTED ZERO. If nobody is counting, saying 0 is
    the same lie as a green icon over a dead mic — it reports a healthy number
    for a measurement that never happened (criterion 18 / scar 49)."""

    def test_no_counter_source_renders_unknown(self):
        t, _ = make_tray(inputs())                # counters default: no source
        t.update()
        labels = {i.key: i.label for i in t.menu()}
        self.assertNotEqual(labels["owner_rej"], "Owner-rej: 0")
        self.assertRegex(labels["owner_rej"], r"not counted")
        self.assertRegex(labels["recovered"], r"not counted")

    def test_a_real_zero_is_still_a_zero(self):
        t, _ = make_tray(inputs(counters=tray.Counters(owner_rej=0)))
        t.update()
        self.assertIn("Owner-rej: 0", [i.label for i in t.menu()])

    def test_the_tooltip_says_uncounted_too(self):
        t, _ = make_tray(inputs())
        self.assertIn("not counted", t.update().tooltip.lower())


# ------------------------------- 14. the snapshot reads a REAL app, not a mock

class TheSnapshotReadsTheRealApp(unittest.TestCase):
    """tests/test_wiring_discipline.py's law, applied to my own seam: a test
    that hand-injects the collaborator cannot fail when the collaborator's
    attribute names are wrong. So this drives a REAL KeshevApp — real Router,
    real FailoverFSM, real Spool, real Segmenter — and reads the fields the
    production snapshot will read."""

    def setUp(self):
        from tests.test_app import AppHarness      # real assembly + its fakes
        self._td = TemporaryDirectory(prefix="keshev-tray-")
        self.addCleanup(self._td.cleanup)
        self.h = AppHarness(Path(self._td.name))
        self.addCleanup(self.h.app.shutdown)
        self.recency = tray.FrameRecency()

    def snap(self, **kw):
        return tray.snapshot_from_app(self.h.app, recency=self.recency, **kw)

    def test_every_field_reads_off_the_real_objects(self):
        obs = self.snap()
        self.assertIsInstance(obs, tray.TrayInputs)
        self.assertEqual(obs.capture_state, self.h.app.state)
        self.assertEqual(obs.fsm_state, self.h.app.router.fsm.state)
        self.assertEqual(obs.fsm_deaf, self.h.app.router.fsm.deaf)
        self.assertEqual(obs.maint, self.h.app.router.fsm.maint)
        self.assertEqual(obs.worker_state, self.h.app.worker.state)
        self.assertEqual(obs.local_state, self.h.app.worker.local_state)
        self.assertEqual(obs.queue_depth, self.h.app.spool.qsize())

    def test_an_assembled_but_unstarted_app_is_honestly_deaf(self):
        """build_app() opens no device. Nothing is being heard, and the tray
        must say so rather than show the green of a healthy FSM."""
        self.assertEqual(tray.resolve_state(self.snap()), tray.IDLE_NO_MIC)

    def test_the_engine_stays_unproven_while_the_router_records_nothing(self):
        """client/router.py does not record which engine served the last
        decode (its heartbeat reports fsm.engine(), the POINTER). Until it
        does, the tray must refuse to claim an engine."""
        label = tray.engine_label(
            dataclasses.replace(self.snap(), capture_state="CAPTURING",
                                frame_age_s=0.0))
        self.assertRegex(label, r"unproven|no decode")

    def test_when_the_router_DOES_record_a_decode_the_tray_reports_it(self):
        """The forward-compatible seam: the moment router.py sets
        last_decode_engine/at, the tray lights up with the real engine and
        nobody has to touch tray.py."""
        r = self.h.app.router
        r.last_decode_engine = "local"
        r.last_decode_at = tray.time.monotonic()
        obs = dataclasses.replace(self.snap(), capture_state="CAPTURING",
                                  frame_age_s=0.0)
        self.assertEqual(obs.last_decode_engine, "local")
        self.assertLess(obs.last_decode_age_s, 5.0)
        self.assertIn("local", tray.engine_label(obs).lower())

    def test_counters_are_unknown_until_something_counts_them(self):
        self.assertIsNone(self.snap().counters)

    def test_a_counters_source_is_honoured_when_one_is_given(self):
        obs = self.snap(counters=tray.Counters(owner_rej=4))
        self.assertEqual(obs.counters.owner_rej, 4)


if __name__ == "__main__":
    unittest.main()
