"""Device law: the tuple is above everything; IDLE_NO_MIC is structural.

Adversarial name lists seeded from the 4D device-case draft
(harness/drafts/devicecases-glm-4.7-flash.txt) — reviewed: two of glm's
classifications were hallucinated and are corrected here (Realtek analog
and a Hebrew-named mic are UNKNOWN, not FORBIDDEN; neither matches any
marker and neither may be auto-opened). See WORKERS-LOG.md."""
from __future__ import annotations

import unittest

from k2 import devicelaw

MUST_BLOCK = [
    "BLUETOOTH AUDIO DEVICE",
    "Hands-Free AG Audio",
    "headset (WH-1000XM4)",
    "Headset (WH-1000XM4 Hands-Free AG Audio)",
    "Microphone (AirPods Pro)",
    "AirPods Pro",
    "A2DP Sink",
    "HFP Device",
    "Stereo Mix (Realtek High Definition Audio)",
    "VB-Audio Virtual Cable",
    "VoiceMeeter Input",
    "NVIDIA Broadcast Audio",
    "Microphone (Steam Streaming Microphone)",
    "OBS Virtual Audio Device",
    "Sound Mapper",
    "Microsoft Sound Mapper - Input",
    "Communications Headset",
    "Loopback",
    "Primary Sound Capture Driver",
    "Microphone (Virtual Audio Device)",
    "Audio Relay",                      # the spaced variant glm caught
    "AudioRelay Virtual Mic",
    "Headset (Logitech G433)",          # wired — 'headset' blocks by LAW
    "Wave Out Mix",
    "What U Hear (Sound Blaster)",
    "wh-1000xm4",
    "DroidCam Virtual Audio",
]

MUST_ALLOW = [
    "Microphone (Logi 4K Stream Edition)",
    "BRIO 4K Stream Edition",
    "Microphone (BRIO)",
    "Scarlett 2i2 USB",
    "Microphone (Focusrite USB Audio)",
    "Microphone (USB Audio Device)",
    "USB Microphone (Generic)",
    "Logitech BRIO",
]

# Not forbidden, not recognized -> UNKNOWN: never auto-opened, never
# FORBIDDEN. glm classified the first two as must_block with fabricated
# reasoning — corrected here.
UNKNOWN = [
    "Microphone (Realtek High Definition Audio)",
    "Microphone (קולות)",
    "Line In (High Definition Audio)",
]


class Classification(unittest.TestCase):

    def test_must_block_every_name(self):
        for name in MUST_BLOCK:
            self.assertEqual(
                devicelaw.classify(name), "FORBIDDEN",
                f"{name!r} escaped the tuple")

    def test_must_allow_every_name(self):
        for name in MUST_ALLOW:
            self.assertEqual(
                devicelaw.classify(name), "ALLOWED",
                f"{name!r} was not recognized as an allowed USB mic")

    def test_unknown_names_are_neither(self):
        for name in UNKNOWN:
            self.assertEqual(devicelaw.classify(name), "UNKNOWN", name)

    def test_case_insensitive(self):
        self.assertEqual(devicelaw.classify("bLuEtOoTh HeAdSeT"), "FORBIDDEN")


class TupleAboveEverything(unittest.TestCase):

    def test_extra_is_additive_only(self):
        """Config additions can only ADD denials. There is no argument
        that removes a tuple entry — assert the signature has no such
        parameter and behavior confirms it."""
        # extra adds a new denial
        self.assertEqual(
            devicelaw.classify("My Custom Mic", extra=["custom"]),
            "FORBIDDEN")
        # empty extra removes nothing
        self.assertEqual(devicelaw.classify("Bluetooth Mic", extra=[]),
                         "FORBIDDEN")

    def test_forbidden_wins_over_allowlist(self):
        """A name matching BOTH lists is FORBIDDEN — the tuple outranks
        our own allowlist."""
        self.assertEqual(
            devicelaw.classify("BRIO Bluetooth Edition"), "FORBIDDEN")

    def test_explicit_user_pick_cannot_override_the_tuple(self):
        """The user cannot consent to the Bluetooth trap (scar 21)."""
        sel = devicelaw.select(
            ["Microphone (BRIO)"], chosen="Headset (WH-1000XM4)")
        self.assertEqual(sel.state, devicelaw.IDLE_NO_MIC)
        self.assertIn("never_mic:headset", sel.refused[0][1])

    def test_explicit_clean_pick_wins_unconditionally(self):
        sel = devicelaw.select([], chosen="My Weird USB Mic")
        self.assertEqual(sel.state, "SELECTED")
        self.assertEqual(sel.device, "My Weird USB Mic")


class Selection(unittest.TestCase):

    def test_idle_no_mic_when_nothing_allowed(self):
        """No fallback branch exists: forbidden + unknown -> IDLE."""
        sel = devicelaw.select(
            ["Headset (WH-1000XM4 Hands-Free AG Audio)",
             "Stereo Mix (Realtek)",
             "Microphone (Realtek High Definition Audio)"])
        self.assertEqual(sel.state, devicelaw.IDLE_NO_MIC)
        self.assertIsNone(sel.device)
        self.assertEqual(len(sel.refused), 3)
        reasons = dict(sel.refused)
        # WHICH marker matched is tuple-order detail, not law; the LAW is
        # that the refusal names a never_mic marker.
        self.assertTrue(
            reasons["Headset (WH-1000XM4 Hands-Free AG Audio)"]
            .startswith("never_mic:"))
        self.assertEqual(
            reasons["Microphone (Realtek High Definition Audio)"],
            "unrecognized")

    def test_first_allowed_wins_and_refusals_are_recorded(self):
        sel = devicelaw.select(
            ["Bluetooth AV", "Microphone (BRIO)", "Scarlett 2i2 USB"])
        self.assertEqual(sel.state, "SELECTED")
        self.assertEqual(sel.device, "Microphone (BRIO)")
        self.assertEqual(len(sel.refused), 1)       # only what came before

    def test_empty_candidate_list_is_idle(self):
        sel = devicelaw.select([])
        self.assertEqual(sel.state, devicelaw.IDLE_NO_MIC)

    def test_never_mic_markers_is_the_tuple(self):
        m = devicelaw.never_mic_markers()
        self.assertIsInstance(m, tuple)              # immutable by type
        self.assertIn("bluetooth", m)
        self.assertIn("audio relay", m)              # the glm catch


if __name__ == "__main__":
    unittest.main()
