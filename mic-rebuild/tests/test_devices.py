"""K6 acceptance tests for client/devices.py — written FIRST (TDD).

PHASE2-DESIGN.md K6 row + section 2 devices.py spec; PHASE1-INQUIRY.md
section 2.D (scars 21-25, SACRED AUDIO — non-negotiable):

  scar 21  source-level _NEVER_MIC tuple is the SOLE authority, checked
           unconditionally BEFORE any probe/open, with NO config input to
           that check; config extra_avoid is additive-cosmetic only; the
           tuple contents are PINNED BY THE DESIGN (may not be
           under-populated); no allowed mic -> IDLE_NO_MIC honestly
           announced, never fallback.
  scar 22  device layer is capture-only; device-open audit asserts zero
           audio-OUTPUT endpoints held.
  scar 23  WASAPI > DirectSound > WDM-KS, never MME; RMS liveness probe for
           AUTO-PICK only; an explicit pinned mic wins unconditionally and
           is never probe-gated; extra_avoid is a soft demotion, never a
           pre-probe veto; same-physical-mic fallback chain across host
           APIs with 3 open retries + 0.4s sleep on transient errors.

ALL tests run against a FAKE device list — no PortAudio import, no real
device is enumerated, probed, or opened (wave-guardrail: golden/synthetic
only; real-device tests are K5-gated with Iddo).
"""
from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from client import devices  # noqa: E402
from client.devices import (  # noqa: E402
    _NEVER_MIC,
    DeviceInfo,
    DeviceOpenError,
    SacredAudioViolation,
    Selection,
    TransientDeviceError,
    device_open_audit,
    forbidden_match,
    open_with_retry,
    select_device,
)

RMS_FLOOR = devices.RMS_LIVENESS_FLOOR


# ---------------------------------------------------------------- fixtures

def dev(index, name, hostapi="Windows WASAPI", inputs=2, outputs=0):
    return DeviceInfo(index=index, name=name, hostapi=hostapi,
                      max_input_channels=inputs, max_output_channels=outputs)


def brio(index=0, hostapi="Windows WASAPI"):
    return dev(index, "Microphone (Logitech BRIO)", hostapi)


def scarlett(index=1, hostapi="Windows WASAPI"):
    return dev(index, "Analogue 1 + 2 (Focusrite Scarlett 2i2)", hostapi)


class RecordingProbe:
    """RMS probe stub that records which devices it was asked about."""

    def __init__(self, rms_by_index=None, default=0.02):
        self.rms_by_index = rms_by_index or {}
        self.default = default
        self.probed = []

    def __call__(self, device: DeviceInfo) -> float:
        self.probed.append(device)
        return self.rms_by_index.get(device.index, self.default)


# ---------------------------------------------------------------- scar 21: the tuple

class TestNeverMicTuple(unittest.TestCase):
    """The tuple is pinned by the design — under-population is a violation."""

    REQUIRED = (
        # BT / headset family (Sacred Audio law of 2026-08-09)
        "bluetooth", "hands-free", "headset", "wh-1000xm4", "a2dp", "hfp",
        "airpods",
        # loopback / virtual / mapper family
        "stereo mix", "loopback", "virtual", "audiorelay", "sound mapper",
        "primary sound capture",
    )

    def test_tuple_is_a_tuple_of_lowercase_tokens(self):
        self.assertIsInstance(_NEVER_MIC, tuple)
        for token in _NEVER_MIC:
            self.assertEqual(token, token.lower(), f"token {token!r} not lowercase")

    def test_every_pinned_entry_present(self):
        for token in self.REQUIRED:
            self.assertIn(token, _NEVER_MIC,
                          f"design-pinned entry {token!r} missing from _NEVER_MIC "
                          f"(scar 21: an implementation may not under-populate it)")

    def test_forbidden_match_takes_no_config_input(self):
        """Structural: the check has exactly ONE parameter — the name.
        No config object can ever reach it (scar 21 enforcement point)."""
        params = inspect.signature(forbidden_match).parameters
        self.assertEqual(len(params), 1, "forbidden_match must take ONLY the device name")

    def test_match_is_case_insensitive_substring(self):
        self.assertEqual(forbidden_match("WH-1000XM4 Hands-Free AG Audio"), "hands-free")
        # first tuple-order match wins; any forbidden token is a refusal
        self.assertIn(forbidden_match("Headset Microphone (Bluetooth)"), _NEVER_MIC)
        self.assertEqual(forbidden_match("Stereo Mix (Realtek)"), "stereo mix")
        self.assertIsNone(forbidden_match("Microphone (Logitech BRIO)"))
        self.assertIsNone(forbidden_match("Analogue 1 + 2 (Focusrite Scarlett 2i2)"))


class TestTableDrivenRefusal(unittest.TestCase):
    """K6 row: table-driven over the FULL tuple, not one sample —
    each forbidden name refused even as the ONLY device, even pinned,
    even with the config avoid list emptied."""

    def fake_name(self, token: str) -> str:
        return f"Fancy {token.title()} Device"

    def test_every_tuple_entry_blocks_even_as_only_device(self):
        for token in _NEVER_MIC:
            with self.subTest(token=token):
                only = [dev(0, self.fake_name(token))]
                probe = RecordingProbe()
                sel = select_device(only, pinned=None, extra_avoid=(), rms_probe=probe)
                self.assertEqual(sel.state, Selection.IDLE_NO_MIC,
                                 f"{token}: forbidden device must never be selected")
                self.assertIsNone(sel.device)
                self.assertEqual(probe.probed, [],
                                 f"{token}: forbidden device must never even be probed")
                # the refusal is honest: device name + matched token recorded
                self.assertTrue(any(token == t for _, t in sel.refused),
                                f"{token}: refusal must record the matched token")

    def test_every_tuple_entry_blocks_even_when_pinned(self):
        """BT device present + pinned in config -> STILL refused.
        The tuple sits ABOVE the config layer; a pin cannot reach past it."""
        for token in _NEVER_MIC:
            with self.subTest(token=token):
                name = self.fake_name(token)
                probe = RecordingProbe()
                sel = select_device([dev(0, name)], pinned=name,
                                    extra_avoid=(), rms_probe=probe)
                self.assertEqual(sel.state, Selection.IDLE_NO_MIC)
                self.assertIsNone(sel.device)
                self.assertEqual(probe.probed, [])

    def test_emptied_extra_avoid_cannot_reopen_the_hole(self):
        """The 2026-08-06 scar: config `avoid` emptied -> BT exposed.
        Here an emptied (and even an adversarial) extra_avoid changes nothing."""
        bt = dev(0, "WH-1000XM4 Hands-Free AG Audio")
        for avoid in ((), [], ["totally-unrelated"],):
            with self.subTest(extra_avoid=avoid):
                sel = select_device([bt], pinned=None, extra_avoid=avoid)
                self.assertEqual(sel.state, Selection.IDLE_NO_MIC)

    def test_pinned_bt_with_brio_present_bt_never_touched(self):
        """Pin says headset, but the tuple wins: BT refused, the allowed
        BRIO is auto-picked instead — and the BT device is never probed."""
        bt = dev(0, "Headset (WH-1000XM4 Hands-Free)")
        b = brio(1)
        probe = RecordingProbe()
        sel = select_device([bt, b], pinned="WH-1000XM4", rms_probe=probe)
        self.assertEqual(sel.state, Selection.SELECTED)
        self.assertEqual(sel.device.index, 1)
        self.assertNotIn(bt, probe.probed, "forbidden device must never be probed")
        self.assertFalse(sel.pin_honored)


# ---------------------------------------------------------------- IDLE_NO_MIC

class TestIdleNoMic(unittest.TestCase):
    def test_no_devices_at_all(self):
        sel = select_device([])
        self.assertEqual(sel.state, Selection.IDLE_NO_MIC)
        self.assertIsNone(sel.device)

    def test_only_output_devices(self):
        speakers = dev(0, "Speakers (Realtek)", inputs=0, outputs=2)
        sel = select_device([speakers])
        self.assertEqual(sel.state, Selection.IDLE_NO_MIC)

    def test_announcement_is_honest_and_bilingual(self):
        bt = dev(0, "Bluetooth Hands-Free Audio")
        sel = select_device([bt])
        self.assertEqual(sel.state, Selection.IDLE_NO_MIC)
        # honest: says there is no allowed mic and that it will NOT fall back
        self.assertIn("IDLE", sel.announcement)
        self.assertIn("no fallback", sel.announcement.lower())
        # bilingual response law: Hebrew present too
        self.assertTrue(any("֐" <= ch <= "ת" for ch in sel.announcement),
                        "announcement must include Hebrew")

    def test_never_falls_back_to_forbidden_when_probe_says_dead(self):
        """Dead BRIO + live BT: the answer is the (possibly endpoint-muted)
        BRIO — probe is evidence, never a veto (scar 23; scar 25 re-resolves
        silent-open later) — and NEVER the headset, which is never probed."""
        dead_brio = brio(0)
        bt = dev(1, "Bluetooth AV Audio (A2DP)")
        probe = RecordingProbe(rms_by_index={0: 0.00001})
        sel = select_device([dead_brio, bt], rms_probe=probe)
        self.assertEqual(sel.state, Selection.SELECTED)
        self.assertEqual(sel.device.index, 0)
        self.assertNotIn(bt, probe.probed)


# ---------------------------------------------------------------- scar 23: ranking + pin + probe

class TestHostApiRanking(unittest.TestCase):
    def test_wasapi_beats_directsound_beats_wdmks(self):
        devs = [
            brio(0, hostapi="Windows WDM-KS"),
            brio(1, hostapi="Windows DirectSound"),
            brio(2, hostapi="Windows WASAPI"),
        ]
        sel = select_device(devs)
        self.assertEqual(sel.state, Selection.SELECTED)
        self.assertEqual(sel.device.index, 2)
        # same-physical chain is ordered WASAPI > DS > WDM-KS
        self.assertEqual([d.index for d in sel.chain], [2, 1, 0])

    def test_mme_is_never_probed_never_in_chain(self):
        devs = [brio(0, hostapi="MME"), brio(1, hostapi="Windows WASAPI")]
        probe = RecordingProbe()
        sel = select_device(devs, rms_probe=probe)
        self.assertEqual(sel.device.index, 1)
        self.assertNotIn(0, [d.index for d in sel.chain])
        self.assertNotIn(0, [d.index for d in probe.probed])

    def test_mme_only_device_means_idle(self):
        """MME is never opened — even when it is the only path to the mic."""
        sel = select_device([brio(0, hostapi="MME")])
        self.assertEqual(sel.state, Selection.IDLE_NO_MIC)


class TestPinnedMic(unittest.TestCase):
    def test_pinned_brio_present_chosen_unprobed(self):
        probe = RecordingProbe(rms_by_index={0: 0.0})  # probe would call it dead
        sel = select_device([brio(0), scarlett(1)], pinned="Logitech BRIO",
                            rms_probe=probe)
        self.assertEqual(sel.state, Selection.SELECTED)
        self.assertEqual(sel.device.index, 0)
        self.assertTrue(sel.pin_honored)
        self.assertEqual(probe.probed, [],
                         "a pinned mic wins unconditionally — never probe-gated (scar 23)")

    def test_pin_match_is_case_insensitive_substring(self):
        sel = select_device([brio(0)], pinned="logitech brio")
        self.assertEqual(sel.device.index, 0)

    def test_pinned_absent_falls_through_to_auto_pick(self):
        sel = select_device([scarlett(1)], pinned="Logitech BRIO")
        self.assertEqual(sel.state, Selection.SELECTED)
        self.assertEqual(sel.device.index, 1)
        self.assertFalse(sel.pin_honored)

    def test_pinned_chain_spans_host_apis_ranked(self):
        devs = [brio(0, "Windows DirectSound"), brio(1, "Windows WASAPI"), scarlett(2)]
        sel = select_device(devs, pinned="Logitech BRIO")
        self.assertEqual(sel.device.index, 1)
        self.assertEqual([d.index for d in sel.chain], [1, 0])


class TestAutoPickProbe(unittest.TestCase):
    def test_probe_used_for_auto_pick_dead_mic_skipped(self):
        probe = RecordingProbe(rms_by_index={0: 0.0001, 1: 0.02})
        sel = select_device([brio(0), scarlett(1)], rms_probe=probe)
        self.assertEqual(sel.device.index, 1)

    def test_floor_constant_matches_scar_23(self):
        self.assertAlmostEqual(RMS_FLOOR, 0.0008)

    def test_no_probe_given_picks_by_rank(self):
        sel = select_device([scarlett(1, "Windows DirectSound"), brio(0)])
        self.assertEqual(sel.device.index, 0)

    def test_all_dead_but_allowed_still_selected_not_idle(self):
        """Probe is liveness EVIDENCE for ranking, not a veto: if every
        allowed mic looks dead we still pick the best-ranked one (it may be
        muted at the endpoint — scar 25 handles that later), never IDLE
        while an allowed mic exists, and never a forbidden device."""
        probe = RecordingProbe(default=0.0)
        sel = select_device([brio(0), scarlett(1)], rms_probe=probe)
        self.assertEqual(sel.state, Selection.SELECTED)
        self.assertEqual(sel.device.index, 0)

    def test_extra_avoid_is_soft_demotion_never_veto(self):
        # avoided device loses to a non-avoided one...
        sel = select_device([brio(0), scarlett(1)], extra_avoid=["brio"])
        self.assertEqual(sel.device.index, 1)
        # ...but is still selectable when it is the only allowed mic
        sel = select_device([brio(0)], extra_avoid=["brio"])
        self.assertEqual(sel.state, Selection.SELECTED)
        self.assertEqual(sel.device.index, 0)


# ---------------------------------------------------------------- scar 23: open retry chain

class FlakyOpen:
    """open_fn stub: per-device scripted outcomes."""

    def __init__(self, script):
        # script: {index: [exc_or_"ok", ...]} consumed left to right
        self.script = {k: list(v) for k, v in script.items()}
        self.calls = []

    def __call__(self, device: DeviceInfo):
        self.calls.append(device.index)
        outcomes = self.script.get(device.index, ["ok"])
        outcome = outcomes.pop(0) if outcomes else "ok"
        if outcome == "ok":
            return f"handle-{device.index}"
        raise outcome


class TestOpenWithRetry(unittest.TestCase):
    def setUp(self):
        self.sleeps = []
        self.sleep = self.sleeps.append

    def test_transient_error_retried_3x_with_04s_sleep(self):
        transient = TransientDeviceError("Unanticipated host error")
        opener = FlakyOpen({0: [transient, transient, "ok"]})
        handle, device = open_with_retry(opener, [brio(0)], sleep_fn=self.sleep)
        self.assertEqual(handle, "handle-0")
        self.assertEqual(device.index, 0)
        self.assertEqual(opener.calls, [0, 0, 0])
        self.assertEqual(self.sleeps, [0.4, 0.4])

    def test_three_transient_failures_move_down_the_chain(self):
        transient = TransientDeviceError("Unanticipated host error")
        opener = FlakyOpen({0: [transient] * 3, 1: ["ok"]})
        handle, device = open_with_retry(
            opener, [brio(0, "Windows WASAPI"), brio(1, "Windows DirectSound")],
            sleep_fn=self.sleep)
        self.assertEqual(device.index, 1)
        self.assertEqual(opener.calls, [0, 0, 0, 1])

    def test_non_transient_error_moves_on_immediately(self):
        opener = FlakyOpen({0: [RuntimeError("device unplugged")], 1: ["ok"]})
        handle, device = open_with_retry(
            opener, [brio(0), brio(1, "Windows DirectSound")], sleep_fn=self.sleep)
        self.assertEqual(device.index, 1)
        self.assertEqual(opener.calls, [0, 1])
        self.assertEqual(self.sleeps, [])

    def test_whole_chain_failed_raises_loudly(self):
        opener = FlakyOpen({0: [RuntimeError("nope")]})
        with self.assertRaises(DeviceOpenError):
            open_with_retry(opener, [brio(0)], sleep_fn=self.sleep)

    def test_forbidden_device_in_chain_is_a_hard_refusal(self):
        """Defense in depth: even if a forbidden device somehow reaches the
        open layer, the unconditional check refuses to open it."""
        opener = FlakyOpen({})
        with self.assertRaises(SacredAudioViolation):
            open_with_retry(opener, [dev(0, "Bluetooth Hands-Free Audio")],
                            sleep_fn=self.sleep)
        self.assertEqual(opener.calls, [], "forbidden device must never reach open_fn")


# ---------------------------------------------------------------- scar 22: output audit

class Handle:
    def __init__(self, name, kind):
        self.name = name
        self.kind = kind  # "capture" | "output"


class TestDeviceOpenAudit(unittest.TestCase):
    def test_capture_only_passes(self):
        device_open_audit([Handle("BRIO", "capture")])  # no raise

    def test_any_output_endpoint_is_a_violation(self):
        with self.assertRaises(SacredAudioViolation):
            device_open_audit([Handle("BRIO", "capture"),
                               Handle("Speakers (Realtek)", "output")])

    def test_empty_is_fine(self):
        device_open_audit([])


# ---------------------------------------------------------------- structural: capture-only module

class TestModuleIsCaptureOnly(unittest.TestCase):
    def test_no_output_call_site_and_no_sounddevice_import_at_module_level(self):
        """scar 22 + wave guardrail: devices.py must not import PortAudio at
        module import time (tests must never touch real devices) and must
        contain no output-stream call site (lint G6 backs this repo-wide)."""
        src = (REPO / "client" / "devices.py").read_text(encoding="utf-8")
        # tokens assembled at runtime so this test file itself stays G6-clean
        self.assertNotIn("Output" + "Stream", src)
        self.assertNotIn("sd" + ".play", src)
        for line in src.splitlines():
            stripped = line.strip()
            self.assertFalse(
                stripped.startswith(("import sounddevice", "from sounddevice")),
                "sounddevice must be imported lazily, never at module level")


if __name__ == "__main__":
    unittest.main()
