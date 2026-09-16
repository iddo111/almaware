# -*- coding: utf-8 -*-
r"""What the phone door must REFUSE, and what it must do.

The rule these tests exist for: a hand on a phone is worse than a hand on a PC. A stray tap
sends a message, answers a call, or pays for something. So almost every test here is about a
REFUSAL, and the two that are about success check that the aim was verified before AND after.

Nothing here touches a real phone: `adb` is replaced by a fake whose transcript the test
reads back. A test that needed a live phone would be skipped on the day it mattered.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import almido_phone as P  # noqa: E402

CALC = "com.sec.android.app.popupcalculator"


class FakeAdb:
    """A scriptable adb. `calls` is the transcript: what the door really tried to run."""

    def __init__(self, foreground=CALC, call_state=0, rc=0):
        self.calls = []
        self.foreground = foreground
        self.call_state = call_state
        self.rc = rc
        self.text = {}

    def __call__(self, cmd, timeout, binary=False):
        self.calls.append(list(cmd))
        line = " ".join(str(c) for c in cmd)
        if "devices" in cmd:
            return 0, "List of devices attached\n192.168.1.230:5555\tdevice model:SM_S948B\n", ""
        if "telephony.registry" in line:
            return 0, "mCallState=%d\n" % self.call_state, ""
        if "dumpsys window" in line:
            return 0, "  mCurrentFocus=Window{ab12 u0 %s/%s.Calculator}\n" % (
                self.foreground, self.foreground), ""
        if "dumpsys power" in line:
            return 0, "mWakefulness=Awake\n", ""
        if "dumpsys battery" in line:
            return 0, "level: 77\ntemperature: 312\nAC powered: false\n", ""
        if "wm size" in line:
            return 0, "Physical size: 1440x3120\n", ""
        if "getprop" in line:
            return 0, "SM-S948B\n", ""
        if "pm list packages" in line:
            return 0, "package:%s\n" % cmd[-1], ""
        for key, val in self.text.items():
            if key in line:
                return val
        if binary:
            return self.rc, b"", ""
        return self.rc, "", ""


@pytest.fixture()
def phone(monkeypatch, tmp_path):
    """A fake phone, a temp screenshot dir, and the rate-limit bucket emptied.

    Hermetic exactly like test_almido_computer.py's `cu` fixture: the REAL almido_gate is
    loaded (policy, STOP logic and secret markers are Iddo's, not a mock), but its
    STOP_FILE and AUDIT_LOG are redirected into tmp_path FIRST -- before that, this fixture
    was writing every one of these tests' rows into Iddo's real ~/.iddo-harness/audit.log
    (WAVE A1 review finding #3). Only test_stop_file_blocks_every_hand overrode STOP_FILE
    itself, and nothing anywhere in this file ever redirected AUDIT_LOG."""
    fake = FakeAdb()
    monkeypatch.setattr(P, "_run", fake)
    monkeypatch.setattr(P, "SHOTS", tmp_path / "shots")
    monkeypatch.setattr(P, "PHONE_SERIAL", "")
    gate = P._load()["gate"]
    if gate is not None:
        monkeypatch.setattr(gate, "HARNESS", tmp_path)
        monkeypatch.setattr(gate, "STOP_FILE", tmp_path / "STOP")
        monkeypatch.setattr(gate, "AUDIT_LOG", tmp_path / "audit.log")
    P._BUCKET.clear()
    return fake


# ------------------------------------------------------------------ the fence
@pytest.mark.parametrize("pkg", [
    "com.samsung.android.app.soundpicker",     # the sound picker, named in Iddo's order
    "com.sec.android.app.voicenote",           # voice recorder
    "com.samsung.android.dialer",              # a live conversation
    "com.android.settings",                    # security screens
    "com.samsung.android.spay",                # money
    "com.spotify.music",                       # his music, his flow state
    "com.example.audiothing",                  # the generic substring, default deny
    "com.bank.leumi",
])
def test_protected_packages_are_denied(pkg):
    assert P.denied_package(pkg), "%s must be refused" % pkg


@pytest.mark.parametrize("pkg", [CALC, "com.whatsapp", "com.termux", "com.android.chrome"])
def test_ordinary_packages_are_not_denied(pkg):
    assert P.denied_package(pkg) == ""


def test_a_denied_app_cannot_be_opened_even_if_installed(phone):
    out = P.open_app("com.samsung.android.app.soundpicker")
    assert out["ok"] is False
    assert "AUDIO PROTECTION LAW" in out["reason"]
    # and nothing was even asked of the phone
    assert not any("monkey" in " ".join(c) for c in phone.calls)


def test_a_denied_app_cannot_be_aimed_at(phone):
    out = P.tap(10, 10, expect_app="com.samsung.android.dialer")
    assert out["ok"] is False and "protected pattern" in out["reason"]
    assert not any("input tap" in " ".join(c) for c in phone.calls)


def test_the_foreground_being_protected_blocks_a_tap_aimed_elsewhere(phone):
    phone.foreground = "com.samsung.android.incallui"
    out = P.tap(10, 10, expect_app=CALC)
    assert out["ok"] is False
    assert "in FRONT" in out["reason"]
    assert not any("input tap" in " ".join(c) for c in phone.calls)


def test_an_active_call_blocks_everything(phone):
    phone.call_state = 2
    out = P.tap(10, 10, expect_app=CALC)
    assert out["ok"] is False and "call is in progress" in out["reason"]
    assert not any("input tap" in " ".join(c) for c in phone.calls)


# ------------------------------------------------------------------ the aim
def test_expect_app_is_required(phone):
    for call in (lambda: P.tap(1, 1), lambda: P.type_text("hi"), lambda: P.key("KEYCODE_ENTER")):
        out = call()
        assert out["ok"] is False
        assert "expect_app is REQUIRED" in out["reason"]


def test_aiming_at_an_app_that_is_not_in_front_is_refused(phone):
    phone.foreground = "com.android.chrome"
    out = P.tap(100, 100, expect_app=CALC)
    assert out["ok"] is False
    assert "com.android.chrome" in out["reason"] and CALC in out["reason"]
    assert not any("input tap" in " ".join(c) for c in phone.calls)


def test_the_app_changing_under_the_hand_is_reported_as_a_failure(phone):
    """The 'and after' half. The tap really happened -- and the caller is told the aim broke,
    instead of being allowed to believe it is still in the app it named."""
    real = phone.__call__
    state = {"n": 0}

    def moving(cmd, timeout, binary=False):
        line = " ".join(str(c) for c in cmd)
        if "input tap" in line:
            phone.foreground = "com.android.chrome"     # something stole focus
            state["n"] += 1
        return real(cmd, timeout, binary)

    phone_calls_before = len(phone.calls)
    import types
    P._run = moving
    out = P.tap(100, 100, expect_app=CALC)
    assert state["n"] == 1, "the tap must really have been sent"
    assert out["ok"] is False
    assert out["expect_app_held"] is False
    assert out["app_after"] == "com.android.chrome"
    assert len(phone.calls) > phone_calls_before


def test_a_tap_that_holds_its_app_succeeds(phone):
    out = P.tap(100, 200, expect_app=CALC)
    assert out["ok"] is True and out["performed"] is True
    assert out["expect_app_held"] is True
    assert ["shell", "input", "tap", "100", "200"] == [str(c) for c in
                                                       next(c for c in phone.calls
                                                            if "tap" in " ".join(map(str, c)))[-5:]]


# ------------------------------------------------------------------ typing
def test_ascii_is_typed_with_input_text_and_spaces_become_percent_s(phone):
    out = P.type_text("hello world", expect_app=CALC)
    assert out["ok"] is True and out["method"] == "adb input text"
    sent = next(c for c in phone.calls if "text" in " ".join(map(str, c)))
    assert "hello%sworld" in " ".join(map(str, sent))


def test_hebrew_goes_through_the_clipboard_not_input_text(phone, monkeypatch):
    seen = {}

    def fake_clip(text, timeout=12.0):
        seen["text"] = text
        return {"ok": True, "rc": 0}

    monkeypatch.setattr(P, "clipboard_set_via_termux", fake_clip)
    out = P.type_text("שלום", expect_app=CALC)
    assert out["ok"] is True
    assert "KEYCODE_PASTE" in out["method"] or "279" in out["method"]
    assert seen["text"] == "שלום"
    assert any("keyevent 279" in " ".join(map(str, c)) for c in phone.calls)
    assert not any("input text" in " ".join(map(str, c)) for c in phone.calls)


def test_hebrew_fails_loudly_when_the_clipboard_route_fails(phone, monkeypatch):
    monkeypatch.setattr(P, "clipboard_set_via_termux",
                        lambda t, timeout=12.0: {"ok": False, "reason": "ssh refused"})
    out = P.type_text("שלום", expect_app=CALC)
    assert out["ok"] is False
    assert "clipboard" in out["reason"] and "ssh refused" in out["reason"]


def test_the_gate_refuses_to_type_a_credential(phone):
    out = P.type_text("my password is hunter2", expect_app=CALC)
    assert out["ok"] is False
    assert out["verdict"] == "BLOCK"
    assert not any("input text" in " ".join(map(str, c)) for c in phone.calls)


def test_a_credential_never_reaches_the_clipboard_either(phone, monkeypatch):
    """The Hebrew path writes to the PHONE's clipboard. The gate must have said ALLOW before
    that happens, or a refused secret would still have been copied onto Iddo's phone."""
    touched = {"n": 0}
    monkeypatch.setattr(P, "clipboard_set_via_termux",
                        lambda t, timeout=12.0: touched.update(n=touched["n"] + 1) or {"ok": True})
    out = P.type_text("סיסמה api_key שלי", expect_app=CALC)
    assert out["ok"] is False
    assert touched["n"] == 0, "the clipboard must not be written when the gate says BLOCK"


# ------------------------------------------------------------------ the emergency stop
def test_stop_file_blocks_every_hand(phone, monkeypatch, tmp_path):
    gate = P._load()["gate"]
    monkeypatch.setattr(gate, "STOP_FILE", tmp_path / "STOP")
    (tmp_path / "STOP").write_text("stopped by the test")
    for call in (lambda: P.tap(1, 1, CALC), lambda: P.type_text("x", CALC),
                 lambda: P.key("KEYCODE_ENTER", CALC), lambda: P.home(),
                 lambda: P.screenshot(), lambda: P.ui_text(),
                 lambda: P.open_app(CALC), lambda: P.shell("getprop ro.product.model")):
        out = call()
        assert out["ok"] is False, out
        assert "STOP" in out["reason"]


def test_no_gate_means_no_hands(monkeypatch, phone):
    monkeypatch.setitem(P._LOADED, "gate", None)
    monkeypatch.setitem(P._LOADED, "errors", ["gate deliberately unloaded by the test"])
    out = P.tap(1, 1, CALC)
    assert out["ok"] is False and "GATE UNAVAILABLE" in out["reason"]


# ------------------------------------------------------------------ offline behaviour
def test_an_offline_phone_answers_instead_of_hanging(monkeypatch, tmp_path):
    """Does not use the `phone` fixture (it needs its own `_run` for the whole test, not
    just FakeAdb's), so it must redirect gate.AUDIT_LOG itself -- P.tap() below reaches the
    REAL gate otherwise. Found while verifying WAVE A1 review finding #3: this was the one
    test in the file the `phone` fixture's fix did not cover."""
    gate = P._load()["gate"]
    if gate is not None:
        monkeypatch.setattr(gate, "STOP_FILE", tmp_path / "STOP")
        monkeypatch.setattr(gate, "AUDIT_LOG", tmp_path / "audit.log")
    monkeypatch.setattr(P, "_run", lambda cmd, timeout, binary=False:
                        (0, "List of devices attached\n", "") if "devices" in cmd
                        else (1, "", "device offline"))
    monkeypatch.setattr(P, "PHONE_SERIAL", "")
    P._BUCKET.clear()
    st = P.status()
    assert st["online"] is False
    assert "OFFLINE" in st["verdict"]
    out = P.tap(1, 1, CALC)
    assert out["ok"] is False and "not reachable over adb" in out["reason"]


def test_every_adb_call_carries_a_timeout(monkeypatch):
    """A tool that can hang blocks the agent that called it. No call may go out untimed,
    and none may exceed the 15 s ceiling the caller was promised."""
    seen = []
    monkeypatch.setattr(P, "_run", lambda cmd, timeout, binary=False:
                        seen.append(timeout) or (0, "List of devices attached\n", ""))
    P.devices()
    P.adb(["shell", "true"])
    assert seen and all(t is not None and 0 < t <= 15.0 for t in seen), seen


# ------------------------------------------------------------------ the read-only shell
@pytest.mark.parametrize("cmd", [
    "rm -rf /sdcard", "pm uninstall com.whatsapp", "reboot",
    "getprop; rm -rf /", "dumpsys | grep x", "settings put global x 1",
    "am start -n com.x/.Y", "input tap 1 1",
    "input keyevent 25", "input keyevent KEYCODE_VOLUME_DOWN",   # WAVE A1 finding #1 audit
])
def test_the_shell_refuses_anything_that_is_not_read_only(phone, cmd):
    out = P.shell(cmd)
    assert out["ok"] is False, cmd


@pytest.mark.parametrize("cmd", ["getprop ro.product.model", "pm list packages calc",
                                 "dumpsys battery", "wm size"])
def test_the_shell_allows_the_read_only_verbs(phone, cmd):
    out = P.shell(cmd)
    assert out["ok"] is True, out


def test_shell_input_keyevent_never_reaches_adb(phone):
    """`input` is not on _SHELL_ALLOW (see the comment there), so shell()'s 'not allowed'
    branch must refuse BEFORE _do() runs -- no keyevent call, volume or otherwise, may ever
    reach adb through this door."""
    out = P.shell("input keyevent 25")
    assert out["ok"] is False and out["performed"] is False
    assert not any("keyevent" in " ".join(map(str, c)) for c in phone.calls)


# ------------------------------------------------------------------ audio protection law (key())
# WAVE A1 review finding #1, CRITICAL: key() built its gate detail as "key %s in %s", which
# the shared almido_gate audio-key check (it matches whole tokens like "volumedown" after
# splitting on '+'/','/'-') could never match -- so an Android hardware keycode for volume,
# media, mute, a call, voice assist, music or recording would have reached the phone. Fixed
# with an explicit deny-list checked in key() itself, before _guard()/_do(). These tests
# prove the block fires BEFORE any adb call (phone.calls stays empty), by both name and
# number, and that it does not over-block ordinary navigation keys.
_AUDIO_DENY_BY_NAME = [
    "KEYCODE_VOLUME_UP", "KEYCODE_VOLUME_DOWN", "KEYCODE_VOLUME_MUTE",
    "KEYCODE_MEDIA_PLAY_PAUSE", "KEYCODE_MEDIA_STOP", "KEYCODE_MEDIA_NEXT",
    "KEYCODE_MEDIA_PREVIOUS", "KEYCODE_MEDIA_REWIND", "KEYCODE_MEDIA_FAST_FORWARD",
    "KEYCODE_MEDIA_PLAY", "KEYCODE_MEDIA_PAUSE", "KEYCODE_MEDIA_RECORD",
    "KEYCODE_MEDIA_AUDIO_TRACK", "KEYCODE_MUTE", "KEYCODE_HEADSETHOOK",
    "KEYCODE_CALL", "KEYCODE_ENDCALL", "KEYCODE_VOICE_ASSIST", "KEYCODE_ASSIST",
    "KEYCODE_MUSIC",
    # bare names too (key() accepts a name with or without the KEYCODE_ prefix)
    "VOLUME_UP", "MUTE", "ASSIST", "volume_down",
]
_AUDIO_DENY_BY_NUMBER = [5, 6, 24, 25, 79, 85, 86, 87, 88, 89, 90, 91,
                        126, 127, 130, 164, 209, 219, 222, 231]


@pytest.mark.parametrize("keyevent", _AUDIO_DENY_BY_NAME)
def test_audio_law_denies_media_keys_by_name(phone, keyevent):
    out = P.key(keyevent, expect_app=CALC)
    assert out["ok"] is False, keyevent
    assert out["verdict"] == "BLOCK", keyevent
    assert "audio law" in out["reason"].lower(), out["reason"]
    assert phone.calls == [], "no adb call may be made for a denied key: %r" % (phone.calls,)


@pytest.mark.parametrize("keyevent", _AUDIO_DENY_BY_NUMBER)
def test_audio_law_denies_media_keys_by_number(phone, keyevent):
    out = P.key(keyevent, expect_app=CALC)
    assert out["ok"] is False, keyevent
    assert out["verdict"] == "BLOCK", keyevent
    assert "audio law" in out["reason"].lower(), out["reason"]
    assert phone.calls == [], "no adb call may be made for a denied key: %r" % (phone.calls,)


@pytest.mark.parametrize("keyevent", ["KEYCODE_BACK", 4, "KEYCODE_HOME", 3, "KEYCODE_ENTER", 66])
def test_ordinary_keys_still_reach_the_gate(phone, keyevent):
    out = P.key(keyevent, expect_app=CALC)
    assert out["ok"] is True, out
    assert out["performed"] is True
    assert any("keyevent" in " ".join(map(str, c)) for c in phone.calls), phone.calls


# ------------------------------------------------------------------ the eyes
def test_a_screenshot_that_is_not_a_png_is_refused(phone, monkeypatch):
    """A capture nobody verified is not evidence. adb on Windows has corrupted this stream
    before, and a corrupt file saved as 'the screenshot' is worse than no screenshot."""
    def bad(cmd, timeout, binary=False):
        line = " ".join(str(c) for c in cmd)
        if "exec-out" in line:
            return 0, b"not a png at all", ""
        if "screencap" in line:
            return 1, "", "Capturing failed"
        return phone(cmd, timeout, binary)
    monkeypatch.setattr(P, "_run", bad)
    out = P.screenshot()
    assert out["ok"] is False
    assert "screencap failed both ways" in out["reason"] or "not a PNG" in out["reason"]


def test_a_good_screenshot_is_hashed_and_written(phone, monkeypatch, tmp_path):
    png = (b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)

    def good(cmd, timeout, binary=False):
        if "exec-out" in " ".join(str(c) for c in cmd):
            return 0, png, ""
        return phone(cmd, timeout, binary)
    monkeypatch.setattr(P, "_run", good)
    out = P.screenshot()
    assert out["ok"] is True
    import hashlib
    assert out["sha256"] == hashlib.sha256(png).hexdigest()
    from pathlib import Path
    assert Path(out["path"]).read_bytes() == png


def test_ui_text_returns_the_real_strings_and_their_tap_targets(phone, monkeypatch):
    xml = ('<?xml version="1.0"?><hierarchy>'
           '<node text="4" bounds="[10,20][30,40]" content-desc="result"/>'
           '<node text="" bounds="[0,0][1,1]"/></hierarchy>')

    def with_dump(cmd, timeout, binary=False):
        line = " ".join(str(c) for c in cmd)
        if line.startswith(("adb", P.ADB)) and " cat " in line:
            return 0, xml, ""
        if "cat" in cmd:
            return 0, xml, ""
        return phone(cmd, timeout, binary)
    monkeypatch.setattr(P, "_run", with_dump)
    out = P.ui_text()
    assert out["ok"] is True
    assert "4" in out["texts"]
    assert out["nodes"][0]["center"] == [20, 30]


# ------------------------------------------------------------------ launching
def test_open_reports_a_failure_when_the_app_did_not_really_come_up(phone, monkeypatch):
    """monkey returns 0 whether or not the app appeared. Believing its exit code is how a
    tool reports success for something that did not happen."""
    phone.foreground = "com.android.chrome"
    monkeypatch.setattr(P.time, "sleep", lambda s: None)
    out = P.open_app(CALC)
    assert out["ok"] is False
    assert "did not take" in out["reason"]


def test_open_refuses_a_package_that_is_not_installed(phone, monkeypatch):
    def not_installed(cmd, timeout, binary=False):
        if "pm list packages" in " ".join(str(c) for c in cmd):
            return 0, "", ""
        return phone(cmd, timeout, binary)
    monkeypatch.setattr(P, "_run", not_installed)
    out = P.open_app("com.does.not.exist")
    assert out["ok"] is False and "not installed" in out["reason"]


# ------------------------------------------------------------------ the rate limit
def test_the_rate_limit_stops_a_looping_agent(phone, monkeypatch):
    monkeypatch.setattr(P, "RATE_MAX", 3)
    P._BUCKET.clear()
    oks = [P.tap(1, 1, CALC)["ok"] for _ in range(5)]
    assert oks[:3] == [True, True, True]
    assert oks[3] is False and oks[4] is False


def test_scroll_consumes_exactly_one_rate_slot(phone, monkeypatch):
    """WAVE A1 review finding #2, MEDIUM: scroll() used to call _guard itself and then call
    swipe(), which guarded AGAIN for the same action -- one scroll from an agent charged TWO
    rate-limit slots, not one. Fixed by scroll() guarding once and calling the internal,
    unguarded _swipe_unguarded() hand directly (swipe()'s own public behaviour -- guard once,
    then that same hand -- is unchanged)."""
    monkeypatch.setattr(P, "RATE_MAX", 3)
    P._BUCKET.clear()
    oks = [P.scroll("down", expect_app=CALC)["ok"] for _ in range(3)]
    assert oks == [True, True, True], oks
    assert len(P._BUCKET) == 3, (
        "3 scrolls must consume exactly 3 rate slots, not 6 -- scroll() is double-charging")
    out4 = P.scroll("down", expect_app=CALC)
    assert out4["ok"] is False and "rate limit" in out4["reason"]


def test_swipe_still_guards_exactly_once(phone, monkeypatch):
    """swipe()'s own public behaviour must be unchanged by the scroll() fix: one swipe still
    costs exactly one rate slot."""
    monkeypatch.setattr(P, "RATE_MAX", 3)
    P._BUCKET.clear()
    out = P.swipe(10, 20, 10, 200, 300, expect_app=CALC)
    assert out["ok"] is True, out
    assert len(P._BUCKET) == 1


# ------------------------------------------------------------------ status honesty
def test_status_says_hebrew_is_not_proven(phone):
    """The clipboard write returned 0 and the read-back was EMPTY. Reporting that as a
    working route would be exactly the kind of claim this workspace keeps getting burned by."""
    st = P.status()
    assert "NOT PROVEN" in st["typing"]["unicode"]
    assert "termux-clipboard-get" in st["typing"]["unicode_measured"]
