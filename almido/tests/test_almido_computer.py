# -*- coding: utf-8 -*-
r"""almido_computer: ALMIDO's eyes and hands, and the proof that Iddo's gate is in front
of every single one of them.

> BROKEN WINDOWS LAW: test the REAL output, not a proxy.

These tests are hermetic in the one way that matters: the gate object they exercise is
the REAL `almido_gate` loaded out of Iddo's harness -- the policy, the STOP logic and the
secret markers are his, not a mock -- but its STOP_FILE and AUDIT_LOG are redirected into
tmp_path, and the hands are a recorder. So:

  * a test can never create Iddo's real ~/.iddo-harness/STOP and silently disarm every
    computer-use door on this machine   [[feedback_never_test_safety_on_a_living_system]]
  * a test can never move his real mouse or type into whatever he has open
  * and yet a change to the real gate's policy WILL break these tests, which is the point.

The end-to-end proof that the hands really reach the Windows input queue is
`ALMIDO_CU_LIVE=1 pytest -k live` -- it builds its own Tk window to be clicked and typed
into, so even the live test never touches one of Iddo's applications.
"""
import json
import os
import subprocess
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import almido_computer as C  # noqa: E402
import almido_mcp as M  # noqa: E402

LIVE = os.environ.get("ALMIDO_CU_LIVE") == "1"
live_only = pytest.mark.skipif(not LIVE, reason="set ALMIDO_CU_LIVE=1 to drive the real mouse")

# Every hand now has to NAME the window it believes it is acting on (the 2026-09-11 scar:
# the model aimed at Notepad and clicked Iddo's foreground Claude app). The hermetic tests
# get a fake desktop holding exactly one window with this title, so they exercise the gate
# without depending on whatever Iddo happens to have open.
TESTWIN = "ALMIDO TEST WINDOW"
FAKE_RECT = [0, 0, 4000, 4000]


def _fake_window(title=TESTWIN, hwnd=4242, rect=None):
    return {"title": title, "hwnd": hwnd, "rect": list(rect or FAKE_RECT),
            "size": [4000, 4000], "foreground": True}


class Hands:
    """A recorder with actions.py's exact signatures. If a test ever sees something in
    `calls` that the gate refused, the gate was bypassed."""

    def __init__(self):
        self.calls = []

    def execute_click(self, x, y, right_click=False):
        self.calls.append(("click", x, y, right_click))
        return True

    def execute_type(self, text):
        self.calls.append(("type", text))
        return True

    def execute_key(self, key):
        self.calls.append(("key", key))
        return True

    def execute_scroll(self, amount):
        self.calls.append(("scroll", amount))
        return True


@pytest.fixture()
def cu(tmp_path, monkeypatch):
    """The real gate, pointed at a temp STOP file and a temp audit log; fake hands."""
    loaded = C._load()
    gate = loaded["gate"]
    assert gate is not None, "the REAL almido_gate must load, or these tests prove nothing: %s" % loaded["errors"]
    monkeypatch.setattr(gate, "HARNESS", tmp_path)
    monkeypatch.setattr(gate, "STOP_FILE", tmp_path / "STOP")
    monkeypatch.setattr(gate, "AUDIT_LOG", tmp_path / "audit.log")
    hands = Hands()
    monkeypatch.setitem(C._LOADED, "actions", hands)
    # _send_text is THE boundary to the real keyboard (SendInput + KEYEVENTF_UNICODE).
    # Patching it here is what keeps these tests from typing into whatever Iddo has open.
    monkeypatch.setattr(C, "_send_text", lambda text: (hands.calls.append(("type", text)) or True))
    monkeypatch.setattr(C, "_send_wheel", lambda n: (hands.calls.append(("scroll", n)) or True))
    monkeypatch.setattr(C, "SHOTS", tmp_path / "shots")
    # The fake desktop for the target-window guard. Patched here and not inside each test
    # so that a test which forgets to name a window FAILS -- the guard is not optional.
    monkeypatch.setattr(C, "_foreground_window", lambda: _fake_window())
    monkeypatch.setattr(C, "_windows", lambda: [_fake_window()])
    monkeypatch.setattr(C, "_focus_window", lambda hwnd: True)
    C._BUCKET.clear()

    class Fixture:
        pass

    f = Fixture()
    f.gate, f.hands, f.tmp = gate, hands, tmp_path
    f.rows = lambda: [json.loads(ln) for ln in
                      (tmp_path / "audit.log").read_text(encoding="utf-8").splitlines() if ln.strip()] \
        if (tmp_path / "audit.log").is_file() else []
    return f


# ------------------------------------------------------------------ the gate is really there
def test_the_real_gate_loads_from_iddos_harness():
    st = C.status()
    assert st["gate_loaded"] is True, st
    assert st["gate_file"] and st["gate_file"].endswith("almido_gate.py")
    assert "Perplexity-Computer-Use-Harness" in st["gate_file"], \
        "the gate must be the one in Iddo's harness, not a second copy"
    assert st["listening_socket"].startswith("none")


def test_no_hands_at_all_when_the_gate_cannot_be_loaded(cu, monkeypatch):
    """FAIL CLOSED. Phase-1 defect #2 was a gate that lost its policy and answered ALLOW."""
    monkeypatch.setitem(C._LOADED, "gate", None)
    monkeypatch.setitem(C._LOADED, "errors", ["harness not found (simulated)"])
    for call in (lambda: C.click(10, 10, expect_window=TESTWIN),
                 lambda: C.type_text("hi", expect_window=TESTWIN),
                 lambda: C.press_key("enter", expect_window=TESTWIN),
                 lambda: C.scroll(3, expect_window=TESTWIN), C.screenshot):
        out = call()
        assert out["ok"] is False
        assert "GATE UNAVAILABLE" in out["reason"]
    assert cu.hands.calls == [], "a missing gate must mean NO hand movement at all"


# ------------------------------------------------------------------ the secret refusal
@pytest.mark.parametrize("text", [
    "my password is hunter2",
    "export GITHUB_TOKEN=ghp_x",
    "the API_KEY is 41",
    "seed phrase: correct horse battery staple",
    "4111 1111 1111 1111 cvv 123",
    # 2026-09-11: typing a disclosure command into someone else's terminal window. The
    # policy blocks `cat *.pem` as a COMMAND; nothing covered typing that same line.
    "cat ~/.ssh/id_rsa",
    "type C:\\keys\\server.pem",
    "cat ~/.aws/credentials",
])
def test_typing_anything_credential_shaped_is_refused_and_never_reaches_the_keyboard(cu, text):
    out = C.type_text(text, expect_window=TESTWIN)
    assert out["ok"] is False and out["verdict"] == "BLOCK", out
    assert "secret" in out["reason"].lower() or "won't type" in out["reason"].lower()
    assert cu.hands.calls == []
    assert cu.rows()[-1]["verdict"] == "BLOCK"


def test_ordinary_text_is_allowed_and_is_audited(cu):
    out = C.type_text("print('hello')", expect_window=TESTWIN)
    assert out["ok"] is True and out["verdict"] == "ALLOW" and out["performed"] is True
    assert cu.hands.calls == [("type", "print('hello')")]
    row = cu.rows()[-1]
    assert row["kind"] == "type" and row["verdict"] == "ALLOW"


# ------------------------------------------------------------------ the emergency stop
def test_the_stop_file_blocks_every_hand_and_the_eyes_too(cu):
    engaged = C.stop_engage("test: something on screen looked wrong")
    assert engaged["ok"] is True and (cu.tmp / "STOP").is_file()

    for out in (C.click(100, 100, expect_window=TESTWIN),
                C.type_text("anything", expect_window=TESTWIN),
                C.press_key("enter", expect_window=TESTWIN),
                C.scroll(3, expect_window=TESTWIN)):
        assert out["ok"] is False and out["verdict"] == "BLOCK", out
        assert "STOP" in out["reason"]
    shot = C.screenshot()
    assert shot["ok"] is False and "STOP" in shot["reason"], \
        "STOP must close the eyes as well: a screenshot is surveillance of whatever he has open"
    assert cu.hands.calls == []
    assert not list((cu.tmp / "shots").glob("*.jpg")) if (cu.tmp / "shots").is_dir() else True


def test_nothing_here_can_lift_the_stop(cu):
    """An agent that can clear its own emergency stop does not have one."""
    C.stop_engage("test")
    verbs = [n for n in dir(C) if not n.startswith("_")]
    assert not [v for v in verbs if any(w in v.lower() for w in
                                        ("release", "clear", "unstop", "resume", "disengage", "lift"))], verbs
    assert "how_to_clear" in C.stop_status()
    assert (cu.tmp / "STOP").is_file(), "still stopped after asking the module for everything it has"


def test_stop_status_reports_the_reason_iddo_will_read(cu):
    C.stop_engage("the screen showed a bank page")
    st = C.stop_status()
    assert st["stopped"] is True
    assert "bank page" in st["content"]
    assert st["stop_file"] == str(cu.tmp / "STOP")


# ------------------------------------------------------------------ the audio protection law
@pytest.mark.parametrize("key", ["volumedown", "VolumeUp", "volumemute", "playpause",
                                 "nexttrack", "prevtrack", "ctrl+volumedown"])
def test_media_and_volume_keys_are_refused(cu, key):
    """AUDIO PROTECTION LAW / חוק הגנת השמע: no agent mutes, ducks or skips his music."""
    out = C.press_key(key, expect_window=TESTWIN)
    assert out["ok"] is False and out["verdict"] == "BLOCK", out
    assert "audio" in out["reason"].lower()
    assert cu.hands.calls == []


@pytest.mark.parametrize("key", ["enter", "tab", "esc", "f5", "backspace"])
def test_ordinary_keys_still_work(cu, key):
    out = C.press_key(key, expect_window=TESTWIN)
    assert out["ok"] is True and out["performed"] is True, out
    assert cu.hands.calls[-1] == ("key", key)


def test_a_single_letter_is_typed_as_TEXT_not_pressed_as_a_virtual_key(cu):
    """Under Iddo's Hebrew layout, pressing the virtual key for 'a' does not produce 'a'.
    A printable character therefore goes down the Unicode path, like any other text."""
    out = C.press_key("a", expect_window=TESTWIN)
    assert out["ok"] is True and out["performed"] is True, out
    assert cu.hands.calls == [("type", "a")], cu.hands.calls


def test_a_chord_is_refused_with_a_reason_instead_of_silently_doing_nothing(cu):
    """pyautogui.press('ctrl+s') is a no-op: the key is not in its table, so _keyDown
    returns without pressing anything and the caller is told it succeeded."""
    out = C.press_key("ctrl+s", expect_window=TESTWIN)
    assert out["ok"] is False and out["performed"] is False, out
    assert "no chord" in out["reason"] or "no key called" in out["reason"]
    assert ("key", "ctrl+s") not in cu.hands.calls


# ------------------------------------------------------------------ the extra refusals
def test_a_click_off_the_desktop_is_refused_before_the_gate_is_even_asked(cu):
    left, top, right, bottom = C._bounds()
    assert right > left, "this test needs a real desktop"
    for x, y in ((right + 50, top + 10), (left - 50, top + 10), (left + 10, bottom + 50)):
        out = C.click(x, y, expect_window=TESTWIN)
        assert out["ok"] is False and "outside the desktop" in out["reason"], (x, y, out)
    assert cu.hands.calls == []


def test_the_rate_limit_stops_a_looping_agent(cu, monkeypatch):
    monkeypatch.setattr(C, "RATE_MAX", 5)
    C._BUCKET.clear()
    allowed = [C.press_key("tab", expect_window=TESTWIN) for _ in range(5)]
    assert all(r["ok"] for r in allowed)
    blocked = C.press_key("tab", expect_window=TESTWIN)
    assert blocked["ok"] is False and "rate limit" in blocked["reason"]
    assert len(cu.hands.calls) == 5, "the sixth key must never have been pressed"


def test_bad_arguments_are_refused_not_crashed(cu):
    assert C.click("left", "top", expect_window=TESTWIN)["ok"] is False
    assert C.scroll("lots", expect_window=TESTWIN)["ok"] is False
    assert C.scroll(0, expect_window=TESTWIN)["ok"] is False
    assert C.type_text("", expect_window=TESTWIN)["ok"] is False
    assert C.press_key("  ", expect_window=TESTWIN)["ok"] is False
    assert cu.hands.calls == []


# ------------------------------------------------------------------ the eyes
def test_screen_info_is_text_a_coder_model_can_actually_read(cu):
    info = C.screen_info()
    assert info["desktop_size"][0] > 0 and info["desktop_size"][1] > 0
    assert isinstance(info["windows"], list) and info["window_count"] >= 1
    assert any(w.get("foreground") for w in info["windows"]), "something must have focus"
    for w in info["windows"]:
        assert set(("title", "rect", "size")) <= set(w), w
    assert json.dumps(info, default=str)          # must survive going down the JSON-RPC wire


def test_screenshot_returns_a_path_and_a_real_jpeg_not_a_wall_of_base64(cu):
    out = C.screenshot(max_width=640)
    assert out["ok"] is True, out
    assert "base64_jpeg" not in out, "base64 must be opt-in: it is ~100k tokens a coder cannot read"
    path = out["path"]
    assert os.path.isfile(path) and out["bytes"] > 2000
    from PIL import Image
    with Image.open(path) as im:
        assert im.format == "JPEG" and im.size[0] <= 640
        lo, hi = im.convert("L").getextrema()
    assert hi > lo, "a single-colour image means the capture failed silently"


# ------------------------------------------------------------------ the target-window guard
# THE SCAR, 2026-09-11 06:03: the model said "I'll click on the Free Download Manager
# window" and clicked the centre of FDM's rectangle -- which was covered by Iddo's Claude
# app, so the click landed in Iddo's application. screen_info had told the truth; the hand
# had no way to refuse. These tests are that refusal.
@pytest.mark.parametrize("hand", ["click", "type", "key", "scroll"])
def test_a_hand_that_names_no_window_is_refused(cu, hand):
    call = {"click": lambda: C.click(10, 10),
            "type": lambda: C.type_text("hello"),
            "key": lambda: C.press_key("enter"),
            "scroll": lambda: C.scroll(3)}[hand]
    out = call()
    assert out["ok"] is False and out["performed"] is False, out
    assert "expect_window is REQUIRED" in out["reason"], out
    assert cu.hands.calls == [], "nothing may move before the target is named"


def test_naming_a_window_that_is_not_there_is_refused(cu):
    out = C.click(10, 10, expect_window="Free Download Manager")
    assert out["ok"] is False and "no visible window has" in out["reason"], out
    assert cu.hands.calls == []


def test_a_click_outside_the_named_windows_rectangle_is_refused(cu, monkeypatch):
    """THE 06:03 BUG ITSELF: the coordinates belonged to another window."""
    monkeypatch.setattr(C, "_foreground_window", lambda: _fake_window(rect=[100, 100, 300, 300]))
    monkeypatch.setattr(C, "_windows", lambda: [_fake_window(rect=[100, 100, 300, 300])])
    out = C.click(900, 900, expect_window=TESTWIN)
    assert out["ok"] is False and "OUTSIDE" in out["reason"], out
    assert cu.hands.calls == []
    inside = C.click(200, 200, expect_window=TESTWIN)
    assert inside["ok"] is True and inside["performed"] is True, inside


def test_the_named_window_is_brought_to_the_front_and_the_foreground_is_RE_READ(cu, monkeypatch):
    """A SetForegroundWindow that Windows refuses must not be mistaken for a focus."""
    other = _fake_window(title="Iddo's own application", hwnd=1)
    target = _fake_window(title="Decoy Notepad", hwnd=2)
    monkeypatch.setattr(C, "_windows", lambda: [other, target])

    state = {"fg": other, "focus_calls": []}
    monkeypatch.setattr(C, "_foreground_window", lambda: state["fg"])
    monkeypatch.setattr(C, "_focus_window",
                        lambda hwnd: state["focus_calls"].append(hwnd) or True)
    monkeypatch.setattr(C, "FOCUS_WAIT_S", 0.3)
    monkeypatch.setattr(C, "FOCUS_POLL_S", 0.05)

    # Windows refuses the focus change: the foreground never becomes the target.
    out = C.click(10, 10, expect_window="Decoy Notepad")
    assert out["ok"] is False and "still" in out["reason"], out
    assert state["focus_calls"] == [2], "the focus must have been attempted"
    assert cu.hands.calls == [], "nothing may be pressed into the wrong window"

    # Now the focus really lands -- and only then is the hand allowed through.
    def focus(hwnd):
        state["fg"] = target
        state["focus_calls"].append(hwnd)
        return True

    monkeypatch.setattr(C, "_focus_window", focus)
    ok = C.click(10, 10, expect_window="Decoy Notepad")
    assert ok["ok"] is True and ok["performed"] is True, ok
    assert ok["window"] == "Decoy Notepad"


def test_an_ambiguous_name_presses_nothing(cu, monkeypatch):
    monkeypatch.setattr(C, "_windows", lambda: [_fake_window(title="notes - one", hwnd=1),
                                                _fake_window(title="notes - two", hwnd=2)])
    monkeypatch.setattr(C, "_foreground_window", lambda: _fake_window(title="something else", hwnd=9))
    out = C.type_text("hello", expect_window="notes")
    assert out["ok"] is False and "ambiguous" in out["reason"], out
    assert cu.hands.calls == []


@pytest.mark.parametrize("title", [
    "KESHEV 5000 - live mic",
    "\u05e7\u05e9\u05d1 - \u05de\u05d9\u05e7\u05e8\u05d5\u05e4\u05d5\u05df",
    "Sound Settings",
    "Volume Mixer",
    "WH-1000XM4 Bluetooth",
    "Spotify Premium",
])
def test_no_hand_ever_lands_on_an_audio_or_mic_window(cu, monkeypatch, title):
    """AUDIO PROTECTION LAW / \u05d7\u05d5\u05e7 \u05d4\u05d2\u05e0\u05ea \u05d4\u05e9\u05de\u05e2. Refused whether it is named as the target
    or merely happens to be the window in front."""
    monkeypatch.setattr(C, "_windows", lambda: [_fake_window(title=title)])
    monkeypatch.setattr(C, "_foreground_window", lambda: _fake_window(title=title))
    named = C.type_text("anything", expect_window=title)
    assert named["ok"] is False and "AUDIO PROTECTION LAW" in named["reason"], named

    # Aimed elsewhere, but that window is the one in front: still refused.
    monkeypatch.setattr(C, "_windows", lambda: [_fake_window(title=title),
                                                _fake_window(title="Notepad", hwnd=7)])
    other = C.click(10, 10, expect_window="Notepad")
    assert other["ok"] is False and "protected pattern" in other["reason"], other
    assert cu.hands.calls == []


def test_a_refused_aim_is_audited_like_every_other_refusal(cu):
    C.click(10, 10, expect_window="Free Download Manager")
    rows = cu.rows()
    assert rows and rows[-1]["verdict"] == "BLOCK", rows
    assert rows[-1]["kind"] == "click"


def test_the_mcp_door_requires_the_window_on_every_hand():
    """The schema is the contract the model reads. If expect_window is not REQUIRED there,
    a model will simply not send it."""
    by_name = {t["name"]: t for t in M.TOOLS}
    for name in ("computer_click", "computer_type", "computer_key", "computer_scroll"):
        schema = by_name[name]["inputSchema"]
        assert "expect_window" in schema["properties"], name
        assert "expect_window" in schema["required"], name
    for name in ("computer_status", "computer_screen_info", "computer_screenshot"):
        assert "expect_window" not in by_name[name]["inputSchema"].get("properties", {}), \
            "%s only reads; it must not demand a target" % name


# ------------------------------------------------------------------ the audit
def test_every_decision_lands_in_the_gates_own_audit_log(cu):
    C.type_text("ok", expect_window=TESTWIN)
    C.type_text("my password", expect_window=TESTWIN)
    C.press_key("volumedown", expect_window=TESTWIN)
    C.click(10, 10, expect_window=TESTWIN)
    rows = cu.rows()
    assert [r["verdict"] for r in rows] == ["ALLOW", "BLOCK", "BLOCK", "ALLOW"], rows
    assert {r["src"] for r in rows} == {"almido/perplexity"}
    assert all(r["ts"] and r["kind"] for r in rows)


# ------------------------------------------------------------------ the MCP door
def test_the_mcp_door_declares_and_answers_every_computer_tool(cu):
    names = [t["name"] for t in M.TOOLS if t["name"].startswith("computer_")]
    assert names == ["computer_status", "computer_screen_info", "computer_screenshot",
                     "computer_click", "computer_type", "computer_key", "computer_scroll",
                     "computer_stop"]
    assert set(names) <= set(M.HANDLERS)
    for name in names:
        if name == "computer_stop":
            continue                          # exercised above, against the redirected STOP file
        out = M.HANDLERS[name]({})
        assert out["content"][0]["text"], name
        assert "unknown tool" not in out["content"][0]["text"], name


def test_a_refused_action_reaches_the_model_as_an_ERROR_not_as_a_success(cu):
    """A coder model handed {"ok": false} inside a success envelope carries on as if it
    clicked. It did not."""
    out = M.HANDLERS["computer_type"]({"text": "my password is x", "expect_window": TESTWIN})
    assert out.get("isError") is True
    assert "secret" in out["content"][0]["text"].lower() or "won't type" in out["content"][0]["text"].lower()
    assert cu.hands.calls == []


def test_the_tool_schemas_have_no_maxLength():
    """llama.cpp grammar limit -- the same rule as the rest of this server."""
    tools = [t for t in M.TOOLS if t["name"].startswith("computer_")]
    assert "maxLength" not in json.dumps(tools)


# ------------------------------------------------------------------ the tailnet bridge
def test_the_bridge_refuses_to_bind_to_anything_but_the_tailnet():
    """The bridge is the ONLY networked piece. It must be unable to listen on 0.0.0.0 or
    on the LAN, and it must say so instead of starting."""
    import almido_computer_bridge as B
    assert B.is_tailnet("<tailnet-ip>") and B.is_tailnet("<tailnet-ip>") and B.is_tailnet("<tailnet-ip>")
    for bad in ("0.0.0.0", "127.0.0.1", "<lan-ip>", "<fabric-ip>", "<tailnet-ip>", "<tailnet-ip>", "::"):
        assert not B.is_tailnet(bad), bad


@pytest.mark.parametrize("bad", ["0.0.0.0", "<lan-ip>", "127.0.0.1"])
def test_the_bridge_exits_rather_than_listen_on_a_non_tailnet_address(bad, tmp_path):
    p = subprocess.run([sys.executable, "-X", "utf8",
                        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                                     "almido_computer_bridge.py"), "--bind", bad, "--check"],
                       capture_output=True, text=True, timeout=60,
                       env=dict(os.environ, PYTHONIOENCODING="utf-8",
                                ALMIDO_CU_TOKEN_FILE=str(tmp_path / "tok")))
    assert p.returncode != 0, "it must refuse, not listen"
    assert "tailnet" in (p.stdout + p.stderr).lower()


# ------------------------------------------------------------------ qwen-code's own gate
HOOK = r"D:\CLAUDE\iddo-harness\almido_gate_hook.py"


def _hook(tool_name, tool_input=None, stop_file=None):
    """Ask the REAL PreToolUse hook what qwen-code would be told, with the emergency stop
    redirected so no test ever creates the live one."""
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    env["ALMIDO_GATE_STOP"] = str(stop_file or (os.path.join(os.environ["TEMP"], "no-such-STOP")))
    p = subprocess.run([sys.executable, "-X", "utf8", HOOK], input=json.dumps(
        {"tool_name": tool_name, "tool_input": tool_input or {}, "session_id": "pytest"}),
        capture_output=True, text=True, timeout=120, env=env)
    return json.loads(p.stdout)["hookSpecificOutput"]


@pytest.mark.skipif(not os.path.isfile(HOOK), reason="the qwen-code gate hook is not installed")
@pytest.mark.parametrize("tool", ["computer_status", "computer_screen_info", "computer_screenshot",
                                  "computer_click", "computer_type", "computer_key",
                                  "computer_scroll", "computer_stop"])
def test_qwen_codes_gate_has_a_deliberate_rule_for_every_computer_tool(tool):
    """Before 2026-09-11 every one of these fell through to 'no matching rule (defaulting
    to confirmation)' -- which under approvalMode 'yolo' is a decision nobody made."""
    d = _hook("mcp__almido__" + tool, {"x": 1, "y": 2, "text": "hello", "key": "tab"})
    assert d["permissionDecision"] == "allow", d
    assert "no matching rule" not in d["permissionDecisionReason"], d


@pytest.mark.skipif(not os.path.isfile(HOOK), reason="the qwen-code gate hook is not installed")
@pytest.mark.parametrize("tool_name", ["computer_use__click",          # qwen-code's own cua-driver
                                       "mcp__almido__computer_click",  # ours
                                       "mcp__almido__computer_screenshot"])
def test_the_stop_file_reaches_qwen_codes_native_computer_use_too(tool_name, tmp_path):
    """ONE file must stop BOTH pairs of hands. qwen-code 0.21.4 ships its own computer use
    (computer_use__*, the cua-driver) which never touches almido_gate -- this hook is the
    only thing in front of it."""
    stop = tmp_path / "STOP"
    assert _hook(tool_name, {"x": 1, "y": 2}, stop)["permissionDecision"] == "allow"
    stop.write_text("engaged by a test", encoding="utf-8")
    d = _hook(tool_name, {"x": 1, "y": 2}, stop)
    assert d["permissionDecision"] == "deny", d
    assert "STOP" in d["permissionDecisionReason"]


@pytest.mark.skipif(not os.path.isfile(HOOK), reason="the qwen-code gate hook is not installed")
def test_the_stop_file_does_not_silently_become_a_global_agent_kill_switch(tmp_path):
    """STOP is the COMPUTER-USE emergency stop. Turning it into 'the agent may do nothing
    at all' would be a surprise nobody asked for."""
    stop = tmp_path / "STOP"
    stop.write_text("engaged", encoding="utf-8")
    d = _hook("run_shell_command", {"command": "git status"}, stop)
    assert d["permissionDecision"] == "allow", d


@pytest.mark.skipif(not os.path.isfile(HOOK), reason="the qwen-code gate hook is not installed")
@pytest.mark.parametrize("text,pattern", [("ssh eran3 and look", "eran3"),
                                          ("systemctl stop eranb-life", "eranb-"),
                                          ("<lan-ip>", "<lan-ip>")])
def test_the_global_block_list_still_wins_over_the_new_auto_allow(text, pattern):
    """The ERAN fence is evaluated BEFORE the almido-qwen profile. Auto-allowing
    computer_type* must not have opened a way to type ERAN's address into a terminal."""
    d = _hook("mcp__almido__computer_type", {"text": text})
    assert d["permissionDecision"] == "deny", d
    assert pattern in d["permissionDecisionReason"]


# ------------------------------------------------------------------ the live proof
@live_only
def test_live_the_hands_really_reach_the_windows_input_queue(tmp_path):
    """THE REAL ONE. Spawns a Tk window of its own, asks the eyes where it is, clicks into
    it, types, presses keys and scrolls -- then reads back what the window actually
    received. Nothing of Iddo's is touched: the target is our own window."""
    target = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cu_live_target.py")
    log = tmp_path / "target.json"
    proc = subprocess.Popen([sys.executable, "-X", "utf8", target, str(log)],
                            env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    try:
        deadline = time.time() + 20
        rect = None
        while time.time() < deadline and rect is None:
            for w in C.screen_info()["windows"]:
                if w["title"].startswith("ALMIDO-LIVE-TARGET") and w["foreground"]:
                    rect = w["rect"]
            time.sleep(0.4)
        assert rect, "the target window never came to the foreground"
        cx, cy = (rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2

        assert C.click(cx, cy, expect_window="ALMIDO-LIVE-TARGET")["performed"] is True
        assert C.type_text("almido", expect_window="ALMIDO-LIVE-TARGET")["performed"] is True
        # Hebrew matters: Iddo's keyboard layout IS Hebrew, and this is the case
        # pyautogui.write() could not do at all.
        assert C.type_text("שלום", expect_window="ALMIDO-LIVE-TARGET")["performed"] is True
        assert C.press_key("enter", expect_window="ALMIDO-LIVE-TARGET")["performed"] is True
        assert C.scroll(-3, expect_window="ALMIDO-LIVE-TARGET")["performed"] is True
        time.sleep(0.6)
        assert C.press_key("escape", expect_window="ALMIDO-LIVE-TARGET")["performed"] is True

        deadline = time.time() + 15
        got = {}
        while time.time() < deadline:
            if log.is_file():
                try:
                    got = json.loads(log.read_text(encoding="utf-8"))
                except Exception:
                    got = {}
                if got.get("closed"):
                    break
            time.sleep(0.3)
        assert got.get("clicks"), "no click reached the window: %s" % got
        typed = "".join(got.get("typed", []))
        assert "almido" in typed, got
        assert "שלום" in typed, "Hebrew must arrive as Hebrew, not as mojibake: %s" % got
        assert "Return" in got.get("keys", []), got
        assert got.get("wheel"), "no wheel event reached the window: %s" % got
        views = got.get("yview") or []
        assert max(views) > min(views), "the wheel event arrived but nothing scrolled: %s" % got
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=10)
        except Exception:
            pass
