# -*- coding: utf-8 -*-
r"""THE SACRED AUDIO LAW, AS A GATE RATHER THAN A SENTENCE IN A FILE.

🎧 AUDIO PROTECTION LAW (Iddo, 2026-08-09): his music is his flow state. A
Bluetooth headset is NEVER a microphone -- opening one flips it to HFP telephone
quality and wrecks his sound. It happened on 2026-08-09 on the PC and again on
2026-09-09 on the phone. Mic input is USB only.

Until now that law lived in a comment and in memory. Here it is a test, run
against the ACTUAL predicate the engine calls before it opens a device
(main.device_allowed), including the case that matters most: a device Iddo
himself picked by name in the window's chooser. A chooser is a preference, not a
licence to open a headset.

No audio device is opened by this file. PortAudio is never initialised: the
"devices" below are plain dicts of exactly the shape sd.query_devices() returns.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
import main  # noqa: E402


def dev(name, ch=2):
    return {"name": name, "max_input_channels": ch}


FORBIDDEN = [
    "Headset (WH-1000XM4 Hands-Free AG Audio)",   # the 2026-08-09 disaster itself
    "Microphone (WH-1000XM4)",
    "Headphones (Bluetooth SCO)",
    "Hands-Free AG Audio",
    "Microphone (USBAudio1.0)",                   # the silent Jieli dongle, 09-09 18:13
    "Microphone Array (AudioRelay Virtual Microphone)",
    "Microsoft Sound Mapper - Input",
    "Microphone (Vive)",                          # the 08-28 deaf night
    "Microphone (Oculus Virtual Audio Device)",
    "Stereo Mix (Realtek)",
]

ALLOWED = [
    "Microphone (Logitech BRIO)",                 # his actual microphone
    "Microphone (Scarlett Solo USB)",
]


def test_forbidden_devices_are_refused():
    for name in FORBIDDEN:
        assert not main.device_allowed(dev(name), "Windows WASAPI"), \
            "THE AUDIO LAW LEAKED: %r was allowed" % name


def test_his_own_pick_cannot_unlock_a_headset():
    """explicit=True is the window's chooser. It lifts the WDM-KS rule and
    NOTHING else -- a picked headset is still refused."""
    for name in FORBIDDEN:
        assert not main.device_allowed(dev(name), "Windows WASAPI", explicit=True), \
            "a chooser pick opened %r -- that is his music" % name


def test_config_never_use_devices_is_actually_in_force():
    """voice-input/config.json is the list he can edit. It must REACH the fence
    -- on 2026-09-09 the engine and the dropdown had drifted apart and the
    dropdown offered a device the engine had already learned to refuse."""
    never = main._config_never_use()
    assert never, "never_use_devices came back empty -- the config is not being read"
    assert any("wh-1000" in n for n in never)
    assert any("bluetooth" in n for n in never)
    for n in never:
        assert not main.device_allowed(dev("Microphone (%s something)" % n), "Windows WASAPI"), \
            "config listed %r as never-use and the fence allowed it" % n


def test_a_real_usb_microphone_is_still_allowed():
    """A fence that refuses everything is not a fence, it is a deaf microphone."""
    for name in ALLOWED:
        assert main.device_allowed(dev(name), "Windows WASAPI"), \
            "the fence refused %r -- his mic would be DEAF" % name


def test_output_only_devices_are_refused():
    assert not main.device_allowed(dev("Speakers (Realtek)", ch=0), "Windows WASAPI")


def test_wdm_ks_needs_an_explicit_pick():
    """2026-09-09 22:45: 'Microphone (Scarlett Solo USB)' existed ONLY as a
    WDM-KS ghost pin and opening it answered -9996; the prefer list would have
    chosen it and killed the engine every 20 s."""
    d = dev("Microphone (Scarlett Solo USB)")
    assert not main.device_allowed(d, "Windows WDM-KS")
    assert main.device_allowed(d, "Windows WDM-KS", explicit=True)
