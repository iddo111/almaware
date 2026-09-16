#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""almido_computer.py -- ALMIDO's eyes and hands on this PC, behind Iddo's gate.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

Iddo, 2026-09-11 ~04:49: wire the Perplexity Computer-Use Harness into ALMIDO so the
local coder gains computer use, and secure whatever it exposes over Tailscale.

WHAT THIS IS. One small module that turns the harness's existing pieces into something
ALMIDO can call. It invents no new policy and no new gate:

    almido_computer  -->  almido_gate.gate(kind, detail)   <- THE gate (policy + STOP + audit)
                     -->  actions.execute_*                <- THE hands (pyautogui)
                     -->  vision.get_screenshot_base64     <- THE eyes (mss + Pillow)

all three imported BY PATH out of the harness Iddo already has:
  C:\Users\<user>\Desktop\תוצרי קלוד\Perplexity-Computer-Use-Harness

THE ONE RULE. Nothing here moves the mouse, presses a key or types a character without
`almido_gate.gate()` returning ALLOW first. There is no second path, no "raw" helper, no
flag that skips it. If the gate cannot be imported at all, every action is REFUSED --
fail closed, the same lesson as almido_gate_hook.py (Phase-1 defect #2: a gate that
swallowed a missing PyYAML and answered ALLOW to `rm -rf /`).

WHAT THE GATE GIVES US, unchanged:
  * ~/.iddo-harness/STOP exists  -> every action BLOCKs. Emergency stop, one file.
  * typing secret-like text      -> BLOCK ("password", "token", "secret", api_key, ...)
  * AUDIO PROTECTION LAW         -> media/volume keys BLOCK (added to the gate 2026-09-11)
  * every decision, allow or not -> one line in ~/.iddo-harness/audit.log

WHAT THIS MODULE ADDS ON TOP, all of it further REFUSALS, never permissions:
  * clicks outside the real desktop bounds are refused before the gate is even asked
  * a rate limit (default 40 actions / 60 s) so a looping agent cannot machine-gun the UI
  * the STOP switch can be ENGAGED from here and can NEVER be cleared from here.
    Clearing it is Iddo deleting the file with his own hands. An agent that can lift its
    own emergency stop does not have one.

EYES FOR A TEXT MODEL. ALMIDO's brain is qwen3-coder-next on eran4 -- a coder, not a
vision model. A base64 screenshot is useless to it and would cost ~100k tokens of
context. So `screenshot()` writes a JPEG to disk and returns the PATH, and the real
eyes for a text model are `screen_info()`: monitors, cursor, foreground window, and
every visible top-level window with its title and rectangle, as text. base64 is opt-in
and capped.

NO LISTENING SOCKET. This module is called in-process by almido_mcp.py over stdio.
It opens no port. The optional tailnet-only bridge is a separate file
(almido_computer_bridge.py) and is not started by anything here.

Run:  python almido_computer.py status     (measured self-report, no action taken)
Test: python -m pytest tests/test_almido_computer.py
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent

# The harness lives on the Desktop under a Hebrew folder name. It is written with \u
# escapes so this source file cannot be broken by a tool that re-saves it in cp1255,
# and the Desktop tidy-task has moved things before -- so it is SEARCHED for, not
# assumed, and `status()` reports which copy actually answered.
_TOTZAREI_CLAUDE = "\u05ea\u05d5\u05e6\u05e8\u05d9 \u05e7\u05dc\u05d5\u05d3"   # "תוצרי קלוד"
_HARNESS_NAME = "Perplexity-Computer-Use-Harness"
_HOME = Path(os.path.expanduser("~"))

HARNESS_CANDIDATES = [Path(p) for p in (
    os.environ.get("ALMIDO_CU_HARNESS", ""),
    _HOME / "Desktop" / _TOTZAREI_CLAUDE / _HARNESS_NAME,
    _HOME / "Desktop" / "_Organized" / _TOTZAREI_CLAUDE / _HARNESS_NAME,
    _HOME / "Desktop" / "_Organized" / "Docs" / _HARNESS_NAME,
    _HOME / "Desktop" / _HARNESS_NAME,
    Path(r"D:\CLAUDE") / _HARNESS_NAME,
) if str(p)]

SHOTS = Path(os.environ.get("ALMIDO_CU_SHOTS", str(HERE / "workspace" / "screenshots")))
SHOTS_KEEP = max(1, int(os.environ.get("ALMIDO_CU_SHOTS_KEEP", "40") or 40))

# Rate limit. A coder model in a retry loop can emit hundreds of tool calls a minute;
# pyautogui.PAUSE alone (0.5 s) is a throttle, not a ceiling.
RATE_MAX = max(1, int(os.environ.get("ALMIDO_CU_RATE_MAX", "40") or 40))
RATE_WINDOW = float(os.environ.get("ALMIDO_CU_RATE_WINDOW", "60") or 60)

# base64 is opt-in and capped: 1 MB of base64 is roughly 350k tokens of nothing useful
# to a text-only coder model.
B64_MAX_BYTES = max(1024, int(os.environ.get("ALMIDO_CU_B64_MAX", "350000") or 350000))

_LOADED: dict = {"harness": None, "gate": None, "actions": None, "vision": None,
                 "errors": [], "tried": []}


def _mss():
    """mss 10 renamed mss.mss -> mss.MSS and deprecated the old name with a warning on
    stderr. The harness's vision.py still calls the old one; ours does not need to."""
    import mss as _m
    return getattr(_m, "MSS", None) or _m.mss
_BUCKET: deque = deque()

ACT_KINDS = ("click", "type", "key", "scroll")


# ------------------------------------------------------------------ loading the harness
def _load_module(name: str, path: Path):
    """Import ONE file under a private name. Same reason as almido_mcp._load_module:
    several copies of this code exist on this machine and `import actions` would pick
    whichever one sys.path happens to reach first."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError("no loader for %s" % path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _block_cv2() -> str:
    r"""Keep OpenCV out of the import path.

    MEASURED 2026-09-11: the FIRST computer-use call through the MCP server took over
    45 s and qwen-code would have timed it out. faulthandler caught it mid-import --

        pyautogui/__init__.py:180 -> pyscreeze -> import cv2 -> numpy -> multiarray (C ext)

    pyscreeze pulls in the whole of OpenCV (~90 MB of DLLs, cold off the disk, scanned on
    the way past) purely so that locateOnScreen() can do image matching. This door never
    calls locateOnScreen. `sys.modules["cv2"] = None` makes `import cv2` raise ImportError,
    which is the branch pyscreeze already handles (`useOpenCV = False`).

    Only ever set when cv2 has not already been imported by someone else, and turned off
    with ALMIDO_CU_ALLOW_CV2=1."""
    if os.environ.get("ALMIDO_CU_ALLOW_CV2") == "1":
        return "allowed by ALMIDO_CU_ALLOW_CV2"
    if "cv2" in sys.modules:
        return "already imported by someone else; left alone"
    sys.modules["cv2"] = None
    return "blocked (pyscreeze falls back to useOpenCV=False)"


def _load() -> dict:
    """Find the harness and import gate/actions/vision out of it. Cached, failures too."""
    if _LOADED["harness"] is not None or _LOADED["errors"]:
        return _LOADED
    _LOADED["cv2"] = _block_cv2()
    for cand in HARNESS_CANDIDATES:
        _LOADED["tried"].append(str(cand))
        if not (cand / "almido_gate.py").is_file():
            continue
        try:
            gate = _load_module("almido_cu_gate", cand / "almido_gate.py")
        except Exception as exc:
            _LOADED["errors"].append("%s: gate: %s: %s" % (cand, type(exc).__name__, exc))
            continue
        _LOADED["harness"] = cand
        _LOADED["gate"] = gate
        # The hands and the eyes are allowed to be missing (a machine with no pyautogui
        # can still answer status() and screen_info()); the GATE is not.
        for attr, fname in (("actions", "actions.py"), ("vision", "vision.py")):
            try:
                _LOADED[attr] = _load_module("almido_cu_" + attr, cand / fname)
            except Exception as exc:
                _LOADED["errors"].append("%s: %s: %s: %s" % (cand, fname, type(exc).__name__, exc))
        return _LOADED
    if not _LOADED["errors"]:
        _LOADED["errors"].append("almido_gate.py found in none of: " + "; ".join(_LOADED["tried"]))
    return _LOADED


def gate_module():
    return _load()["gate"]


def warm(background: bool = True):
    r"""Pay the import cost off the critical path.

    Even with OpenCV out of the way, the first touch of the hands imports pyautogui,
    pyscreeze, mouseinfo (which imports tkinter) and mss -- cold, on a busy machine, that
    is seconds, and it lands on whichever tool call happens to be first. almido_mcp calls
    this once at startup, in a daemon thread; it is a no-op afterwards."""
    def _go():
        try:
            t0 = time.time()
            _load()
            for mod in ("mss", "PIL.Image"):
                try:
                    __import__(mod)
                except Exception:
                    pass
            _LOADED["warm_seconds"] = round(time.time() - t0, 2)
        except Exception as exc:
            _LOADED["warm_error"] = "%s: %s" % (type(exc).__name__, exc)

    if not background:
        _go()
        return _LOADED.get("warm_seconds")
    t = threading.Thread(target=_go, daemon=True, name="almido-cu-warm")
    t.start()
    return t


# ------------------------------------------------------------------ refusals and audit
def _audit_direct(kind: str, detail: str, verdict: str, reason: str) -> None:
    """Write ONE row to the gate's own audit trail for a refusal the gate never saw
    (bounds, rate limit, missing hands). Deliberately the gate's `_audit`, so these rows
    land in the same file, in the same schema, as every decision the gate itself makes."""
    gate = _load()["gate"]
    writer = getattr(gate, "_audit", None) if gate is not None else None
    if writer is None:
        return
    try:
        writer(kind, detail, verdict, reason)
    except Exception:
        pass


def _refuse(kind: str, detail: str, reason: str, verdict: str = "BLOCK") -> dict:
    _audit_direct(kind, detail, verdict, reason)
    return {"ok": False, "action": kind, "detail": detail, "verdict": verdict,
            "reason": reason, "performed": False}


def _rate_ok() -> bool:
    now = time.time()
    while _BUCKET and now - _BUCKET[0] > RATE_WINDOW:
        _BUCKET.popleft()
    if len(_BUCKET) >= RATE_MAX:
        return False
    _BUCKET.append(now)
    return True


def _bounds() -> tuple:
    """The virtual desktop rectangle (left, top, right, bottom), measured. mss first
    (it knows multi-monitor), pyautogui.size() as the fallback, (0,0,0,0) if neither."""
    try:
        with _mss()() as sct:
            m = sct.monitors[0]
            return (int(m["left"]), int(m["top"]),
                    int(m["left"]) + int(m["width"]), int(m["top"]) + int(m["height"]))
    except Exception:
        pass
    try:
        import pyautogui
        w, h = pyautogui.size()
        return (0, 0, int(w), int(h))
    except Exception:
        return (0, 0, 0, 0)


# ------------------------------------------------------------------ the target-window guard
# THE SCAR, 2026-09-11 06:03. In the decoy test the model announced "I'll click on the Free
# Download Manager window" and clicked the centre of FDM's rectangle. FDM was COVERED by
# Iddo's Claude app, so the click landed in Iddo's foreground application instead. The eyes
# had told the truth -- screen_info listed both windows, with `foreground` on the right one --
# and the hand had no way to refuse. A hand that cannot check what it is about to hit is not
# gated, it is merely slow.
#
# So: every hand (click/type/key/scroll) now REQUIRES the caller to name the window it
# believes it is acting on, and this module verifies that belief against the live desktop
# before anything moves. Not a hint, not a default -- a required argument. There is no way
# to say "whatever is in front", because "whatever is in front" is exactly how Iddo's own
# application got clicked.
#
# The check is, in order:
#   1. a target was named at all                     -> else refuse
#   2. the named target is not a protected window    -> else refuse (AUDIO PROTECTION LAW)
#   3. the FOREGROUND window is not protected        -> else refuse, whatever was aimed at
#   4. the foreground title contains the substring   -> pass
#      ...otherwise exactly ONE visible window matches -> focus it, WAIT, RE-READ the
#      foreground, and require the match again       -> else refuse
#   5. for a click: the point is inside that window's rectangle -> else refuse
#
# Step 4's re-read is the part that matters: SetForegroundWindow can silently fail for a
# background process on Windows, and a focus we did not verify is a guess.
_PROTECTED_TITLE_SUBSTRINGS = (
    # AUDIO PROTECTION LAW / חוק הגנת השמע -- Iddo's music is his flow state and the mic is
    # sacred. No agent hand lands on any of these, for any reason, ever. Written with \u
    # escapes so a cp1255 re-save cannot quietly empty the Hebrew half of this fence.
    "keshev", "\u05e7\u05e9\u05d1",                                 # KESHEV / קשב
    "mic", "\u05de\u05d9\u05e7\u05e8\u05d5\u05e4\u05d5\u05df",      # mic / מיקרופון
    "microphone", "audio", "\u05e9\u05de\u05e2",                    # audio / שמע
    "volume", "\u05e2\u05d5\u05e6\u05de\u05ea \u05e7\u05d5\u05dc",  # volume / עוצמת קול
    "sound", "\u05e6\u05dc\u05d9\u05dc",                            # sound / צליל
    "wh-1000xm4", "wh1000xm4", "bluetooth",
    "voicemeeter", "realtek audio", "sound settings", "recording devices",
    "spotify", "foobar2000", "vlc media",
)

# How long to wait for Windows to actually honour a focus request before re-reading the
# foreground. A focus that is going to work lands well inside 300 ms; one Windows means to
# refuse never lands at all. Polled, not slept blindly.
FOCUS_WAIT_S = float(os.environ.get("ALMIDO_CU_FOCUS_WAIT", "1.5") or 1.5)
FOCUS_POLL_S = 0.1


def _protected_title(title: str) -> str:
    """Return the protected pattern this title matches, or '' if it is safe to touch."""
    low = (title or "").lower()
    for pat in _PROTECTED_TITLE_SUBSTRINGS:
        if pat in low:
            return pat
    return ""


def _foreground_window() -> dict | None:
    """The window that is actually in front RIGHT NOW, measured, or None."""
    try:
        import ctypes
        import ctypes.wintypes as wt
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None
        n = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(max(1, n) + 1)
        user32.GetWindowTextW(hwnd, buf, len(buf))
        r = wt.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(r))
        return {"title": buf.value.strip()[:160], "hwnd": int(hwnd),
                "rect": [r.left, r.top, r.right, r.bottom], "foreground": True}
    except Exception:
        return None


def _focus_window(hwnd: int) -> bool:
    """Ask Windows to bring one window to the front. Returns whether the CALL succeeded --
    never whether it WORKED. Only a re-read of the foreground can answer that, which is
    exactly what the caller does next."""
    try:
        import ctypes
        user32 = ctypes.windll.user32
        SW_RESTORE = 9
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)
        return bool(user32.SetForegroundWindow(hwnd))
    except Exception:
        return False


def _match_windows(substr: str) -> list:
    low = (substr or "").lower()
    return [w for w in _windows()
            if isinstance(w, dict) and low in str(w.get("title", "")).lower()]


def _require_window(kind: str, detail: str, expect_window, point=None):
    """The guard. Returns (refusal_dict_or_None, target_window_or_None).

    A refusal here is audited exactly like every other pre-gate refusal, so a blocked
    mis-aim leaves the same kind of row as a blocked command."""
    expect = "" if expect_window is None else str(expect_window).strip()
    if not expect:
        return _refuse(
            kind, detail,
            "expect_window is REQUIRED: name a substring of the title of the window you "
            "believe you are acting on (call computer_screen_info first and copy it from "
            "there). A hand that aims at 'whatever is in front' is how Iddo's own "
            "application got clicked on 2026-09-11."), None

    bad = _protected_title(expect)
    if bad:
        return _refuse(
            kind, detail,
            "REFUSED by the AUDIO PROTECTION LAW: the window you named matches the "
            "protected pattern %r. KESHEV, the microphone, and anything that touches "
            "Iddo's audio are never touched by any agent hand." % bad), None

    fg = _foreground_window()
    if fg is None:
        return _refuse(kind, detail,
                       "could not read the foreground window, so the target cannot be "
                       "verified -- refusing rather than guessing"), None

    bad = _protected_title(fg.get("title", ""))
    if bad:
        return _refuse(
            kind, detail,
            "REFUSED: the FOREGROUND window is %r, which matches the protected pattern "
            "%r (AUDIO PROTECTION LAW). Nothing is pressed while that window is in front, "
            "whatever was aimed at." % (fg.get("title", ""), bad)), None

    target = fg
    if expect.lower() not in str(fg.get("title", "")).lower():
        candidates = _match_windows(expect)
        if not candidates:
            return _refuse(
                kind, detail,
                "no visible window has %r in its title. The window in front is %r. "
                "Call computer_screen_info and aim at something that exists."
                % (expect, fg.get("title", ""))), None
        if len(candidates) > 1:
            return _refuse(
                kind, detail,
                "%d visible windows match %r (%s) -- ambiguous, so nothing is pressed. "
                "Give a longer, unique substring."
                % (len(candidates), expect,
                   "; ".join(repr(c.get("title", "")) for c in candidates[:4]))), None
        cand = candidates[0]
        bad = _protected_title(cand.get("title", ""))
        if bad:
            return _refuse(
                kind, detail,
                "REFUSED by the AUDIO PROTECTION LAW: %r matches the protected pattern %r."
                % (cand.get("title", ""), bad)), None

        _audit_direct("focus", "%s -> %r" % (kind, cand.get("title", "")), "ALLOW",
                      "bringing the named target to the front before acting on it")
        _focus_window(int(cand.get("hwnd", 0)))
        deadline = time.time() + FOCUS_WAIT_S
        ok = False
        while time.time() < deadline:
            time.sleep(FOCUS_POLL_S)
            fg2 = _foreground_window()
            if fg2 and int(fg2.get("hwnd", 0)) == int(cand.get("hwnd", 0)):
                target, ok = fg2, True
                break
        if not ok:
            now_fg = _foreground_window() or {}
            return _refuse(
                kind, detail,
                "focus was requested for %r but after %.1fs the window in front is still "
                "%r. Windows refused the focus change (that is normal for a background "
                "process). NOT pressing -- ask Iddo to click that window himself."
                % (cand.get("title", ""), FOCUS_WAIT_S, now_fg.get("title", ""))), None

    # Re-check the protected list against whatever we ended up in front of.
    bad = _protected_title(target.get("title", ""))
    if bad:
        return _refuse(kind, detail,
                       "REFUSED: ended up in front of %r (protected pattern %r)."
                       % (target.get("title", ""), bad)), None

    if point is not None:
        rect = target.get("rect") or []
        if len(rect) == 4:
            x, y = int(point[0]), int(point[1])
            l, t, r, b = (int(v) for v in rect)
            if not (l <= x < r and t <= y < b):
                return _refuse(
                    kind, detail,
                    "the point (%d,%d) is OUTSIDE %r, whose rectangle is (%d,%d)-(%d,%d). "
                    "A click aimed at one window that lands on another is the 06:03 bug -- "
                    "refusing." % (x, y, target.get("title", ""), l, t, r, b)), None

    return None, target


def _guard(kind: str, detail: str) -> dict | None:
    """Every refusal that happens BEFORE the gate is consulted. Returns a refusal dict,
    or None when the action may go on to the gate.

    Order matters: STOP wins over everything, including a valid, in-bounds, unthrottled
    click. That is what an emergency stop means."""
    loaded = _load()
    gate = loaded["gate"]
    if gate is None:
        # No audit row is possible here -- the audit belongs to the gate we could not
        # load -- so the refusal has to carry its own reason.
        return {"ok": False, "action": kind, "detail": detail, "verdict": "BLOCK",
                "reason": "GATE UNAVAILABLE, so nothing is allowed: " + "; ".join(loaded["errors"])[:400],
                "performed": False}
    try:
        if gate.is_stopped():
            return _refuse(kind, detail, "STOP file present (%s)" % gate.STOP_FILE)
    except Exception as exc:
        return _refuse(kind, detail, "could not read the STOP file: %s" % exc)
    if kind in ACT_KINDS and not _rate_ok():
        return _refuse(kind, detail, "rate limit: more than %d actions in %.0f s" % (RATE_MAX, RATE_WINDOW))
    return None


def _do(kind: str, detail: str, run) -> dict:
    """THE one path from a request to the machine. Pre-checks, then the gate, then --
    only on ALLOW -- the hands. There is no other way through this module."""
    refused = _guard(kind, detail)
    if refused is not None:
        return refused
    gate = _load()["gate"]
    try:
        verdict, reason = gate.gate(kind, detail)
    except Exception as exc:
        return _refuse(kind, detail, "gate raised %s: %s -- refusing" % (type(exc).__name__, exc))
    if verdict != "ALLOW":
        return {"ok": False, "action": kind, "detail": detail, "verdict": verdict,
                "reason": reason, "performed": False,
                "note": "CONFIRM and BLOCK both stop the hand. Ask Iddo." if verdict == "CONFIRM" else None}
    acts = _load()["actions"]
    if acts is None:
        return _refuse(kind, detail, "the hands are missing: " + "; ".join(_LOADED["errors"])[:300])
    try:
        ok = bool(run(acts))
    except Exception as exc:
        name = type(exc).__name__
        if "FailSafe" in name:
            return {"ok": False, "action": kind, "detail": detail, "verdict": verdict,
                    "reason": "pyautogui FAIL-SAFE fired: the pointer is in a screen corner. "
                              "That is Iddo (or the last action) aborting you on purpose.",
                    "performed": False}
        return {"ok": False, "action": kind, "detail": detail, "verdict": verdict,
                "reason": "%s: %s" % (name, exc), "performed": False}
    return {"ok": ok, "action": kind, "detail": detail, "verdict": verdict,
            "reason": reason, "performed": ok}


# ------------------------------------------------------------------ typing, the layout problem
# MEASURED 2026-09-11 05:10 on this PC, with the live target window in tests/:
#
#   Iddo's active keyboard layout is HEBREW (HKL 0xF03D040D, langid 0x040D). pyautogui
#   0.9.54 builds its character table with VkKeyScanW(c) at import time, which asks the
#   ACTIVE layout "which key makes this character?". Under a Hebrew layout there is no
#   key that makes 'a', so VkKeyScanW returns -1 -- and pyautogui's _keyDown then does
#   `mods, vk = divmod(-1, 0x100)` -> mods = -1 -> it presses ALT and CTRL and SHIFT and
#   then virtual-key 255.
#
#   So `type_text("almido")` delivered NOT ONE CHARACTER to the window. What it actually
#   sent was six rounds of Alt+Ctrl+Shift+garbage -- which is not merely useless, it is a
#   good way to trip an application shortcut by accident. Hebrew text fared no better.
#
# THE FIX, and the only correct one: SendInput with KEYEVENTF_UNICODE. That injects a
# Unicode code point directly into the input queue and never consults the layout at all,
# so 'a' is 'a' and 'ש' is 'ש' whatever keyboard is selected. Plain ctypes, no new
# dependency. The harness's own actions.execute_type is kept only as the fallback for a
# platform where SendInput does not exist.
#
# (actions.py in the harness still has the bug. It is not fixed there because nothing
# runs it any more -- the harness's HTTP server main.py is gone -- and this module is
# where the live path is. Flagged for the harness's owner.)
_KEYEVENTF_KEYUP = 0x0002
_KEYEVENTF_UNICODE = 0x0004
_INPUT_KEYBOARD = 1
_VK = {"\n": 0x0D, "\r": 0x0D, "\t": 0x09}


def _sendinput_types():
    import ctypes
    import ctypes.wintypes as wt
    ulong_ptr = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", wt.LONG), ("dy", wt.LONG), ("mouseData", wt.DWORD),
                    ("dwFlags", wt.DWORD), ("time", wt.DWORD), ("dwExtraInfo", ulong_ptr)]

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", wt.DWORD),
                    ("time", wt.DWORD), ("dwExtraInfo", ulong_ptr)]

    class HARDWAREINPUT(ctypes.Structure):
        _fields_ = [("uMsg", wt.DWORD), ("wParamL", wt.WORD), ("wParamH", wt.WORD)]

    class _U(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]

    class INPUT(ctypes.Structure):
        _anonymous_ = ("u",)
        _fields_ = [("type", wt.DWORD), ("u", _U)]

    return ctypes, INPUT, KEYBDINPUT, MOUSEINPUT


def _send_text(text: str):
    """THE typing implementation: one SendInput per UTF-16 code unit, KEYEVENTF_UNICODE.

    Returns True/False, or None when SendInput is not available (then the caller falls
    back to the harness's pyautogui path). Tests monkeypatch THIS function -- it is the
    single boundary between this module and the real keyboard."""
    try:
        ctypes, INPUT, KEYBDINPUT, _ = _sendinput_types()
        user32 = ctypes.windll.user32
    except Exception:
        return None
    events = []
    for ch in str(text):
        vk = _VK.get(ch)
        if vk is not None:                      # Enter and Tab are keys, not characters
            for up in (0, _KEYEVENTF_KEYUP):
                events.append(INPUT(type=_INPUT_KEYBOARD,
                                    ki=KEYBDINPUT(wVk=vk, wScan=0, dwFlags=up, time=0, dwExtraInfo=0)))
            continue
        blob = ch.encode("utf-16-le")          # two units for anything above the BMP
        for i in range(0, len(blob), 2):
            scan = int.from_bytes(blob[i:i + 2], "little")
            for up in (0, _KEYEVENTF_KEYUP):
                events.append(INPUT(type=_INPUT_KEYBOARD,
                                    ki=KEYBDINPUT(wVk=0, wScan=scan,
                                                  dwFlags=_KEYEVENTF_UNICODE | up,
                                                  time=0, dwExtraInfo=0)))
    if not events:
        return False
    array = (INPUT * len(events))(*events)
    sent = user32.SendInput(len(events), array, ctypes.sizeof(INPUT))
    return int(sent) == len(events)


_MOUSEEVENTF_WHEEL = 0x0800
_INPUT_MOUSE = 0
_WHEEL_DELTA = 120


def _send_wheel(clicks: int):
    r"""Scroll by `clicks` notches, via SendInput.

    MEASURED 2026-09-11: pyautogui 0.9.54 scrolls by almost nothing on Windows. Its
    _pyautogui_win._scroll ends in

        _sendMouseEvent(MOUSEEVENTF_WHEEL, x, y, dwData=clicks)

    passing the notch count straight through as the wheel delta. Windows measures that
    delta in units of WHEEL_DELTA = 120, so `scroll(-2)` asks for 2/120 of one notch --
    the live target window's view did not move at all. Multiplying here is the fix.

    Returns True/False, or None when SendInput is unavailable. Tests patch this."""
    try:
        ctypes, INPUT, _, MOUSEINPUT = _sendinput_types()
        user32 = ctypes.windll.user32
    except Exception:
        return None
    data = (int(clicks) * _WHEEL_DELTA) & 0xFFFFFFFF     # dwData is unsigned
    ev = INPUT(type=_INPUT_MOUSE,
               mi=MOUSEINPUT(dx=0, dy=0, mouseData=data, dwFlags=_MOUSEEVENTF_WHEEL,
                             time=0, dwExtraInfo=0))
    array = (INPUT * 1)(ev)
    return int(user32.SendInput(1, array, ctypes.sizeof(INPUT))) == 1


def _unmappable_key(key: str):
    r"""Would pyautogui fire Alt+Ctrl+Shift+garbage for this key under the ACTIVE layout?

    Reads pyautogui's own table, which is exactly what _keyDown reads. A negative or
    missing entry is the -1 from VkKeyScanW described above. Returns a reason or None."""
    try:
        import pyautogui
        table = getattr(getattr(pyautogui, "platformModule", None), "keyboardMapping", None)
        if not isinstance(table, dict):
            return None
        if key not in table:
            return "pyautogui has no key called %r" % key
        code = table.get(key)
        if code is None or (isinstance(code, int) and code < 0):
            return ("the active keyboard layout has no key for %r (pyautogui mapped it to %r). "
                    "Pressing it would send Alt+Ctrl+Shift+garbage, not that key." % (key, code))
    except Exception:
        return None
    return None


# ------------------------------------------------------------------ the hands
def click(x, y, right: bool = False, expect_window=None) -> dict:
    try:
        x, y = int(x), int(y)
    except (TypeError, ValueError):
        return _refuse("click", "%r,%r" % (x, y), "x and y must be integers")
    detail = "(%d,%d) right=%s" % (x, y, bool(right))
    left, top, rightb, bottom = _bounds()
    if rightb > left and bottom > top and not (left <= x < rightb and top <= y < bottom):
        return _refuse("click", detail,
                       "outside the desktop (%d,%d)-(%d,%d) -- a click nobody can see is a bug, not an action"
                       % (left, top, rightb, bottom))
    refused, target = _require_window("click", detail, expect_window, point=(x, y))
    if refused is not None:
        return refused
    out = _do("click", detail, lambda a: a.execute_click(x, y, bool(right)))
    out["window"] = target.get("title")
    return out


def _run_type(acts, text: str):
    out = _send_text(text)
    if out is None:                  # no SendInput here: fall back to the harness's hands
        return acts.execute_type(text)
    return out


def _run_key(acts, key: str):
    # A single printable character is TEXT, not a named key: sending it as a virtual key
    # is what produces mojibake (or Alt+Ctrl+Shift+garbage) under a non-US layout.
    if len(key) == 1 and key.isprintable():
        out = _send_text(key)
        if out is not None:
            return out
    # Checked AFTER the gate on purpose, so a media key is refused for the reason that
    # matters (the audio law) rather than for being unmappable.
    bad = _unmappable_key(key)
    if bad:
        raise ValueError(bad + " This door presses ONE key; it has no chord/hotkey verb.")
    return acts.execute_key(key)


def type_text(text: str, expect_window=None) -> dict:
    text = "" if text is None else str(text)
    if not text:
        return _refuse("type", "", "nothing to type")
    refused, target = _require_window("type", text, expect_window)
    if refused is not None:
        return refused
    out = _do("type", text, lambda a: _run_type(a, text))
    out["window"] = target.get("title")
    return out


def press_key(key: str, expect_window=None) -> dict:
    key = "" if key is None else str(key).strip()
    if not key:
        return _refuse("key", "", "no key given")
    refused, target = _require_window("key", key, expect_window)
    if refused is not None:
        return refused
    out = _do("key", key, lambda a: _run_key(a, key))
    out["window"] = target.get("title")
    return out


def scroll(amount, x=None, y=None, expect_window=None) -> dict:
    try:
        amount = int(amount)
    except (TypeError, ValueError):
        return _refuse("scroll", "%r" % (amount,), "amount must be an integer")
    if amount == 0:
        return _refuse("scroll", "0", "a scroll of 0 does nothing")

    def run(acts):
        out = _send_wheel(amount)
        return acts.execute_scroll(amount) if out is None else out

    refused, target = _require_window("scroll", str(amount), expect_window)
    if refused is not None:
        return refused
    out = _do("scroll", str(amount), run)
    out["window"] = target.get("title")
    return out


# ------------------------------------------------------------------ the eyes
def _windows() -> list:
    r"""Visible top-level windows with titles and rectangles, via plain ctypes.

    This -- not a JPEG -- is what a TEXT model can actually see with. No new dependency:
    user32 is already there, and pywin32/uiautomation are not installed on this PC."""
    out: list = []
    try:
        import ctypes
        import ctypes.wintypes as wt
        user32 = ctypes.windll.user32
        fg = user32.GetForegroundWindow()
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)

        def cb(hwnd, _lparam):
            try:
                if not user32.IsWindowVisible(hwnd):
                    return True
                n = user32.GetWindowTextLengthW(hwnd)
                if n <= 0:
                    return True
                buf = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(hwnd, buf, n + 1)
                title = buf.value.strip()
                if not title:
                    return True
                r = wt.RECT()
                user32.GetWindowRect(hwnd, ctypes.byref(r))
                if r.right - r.left <= 0 or r.bottom - r.top <= 0:
                    return True
                out.append({"title": title[:160], "hwnd": int(hwnd),
                            "rect": [r.left, r.top, r.right, r.bottom],
                            "size": [r.right - r.left, r.bottom - r.top],
                            "foreground": int(hwnd) == int(fg)})
            except Exception:
                pass
            return True

        user32.EnumWindows(WNDENUMPROC(cb), 0)
    except Exception as exc:
        return [{"error": "%s: %s" % (type(exc).__name__, exc)}]
    out.sort(key=lambda w: (not w.get("foreground", False), w.get("title", "")))
    return out


def screen_info(windows: bool = True) -> dict:
    """What is on the screen, as TEXT. Reads nothing but geometry and window titles --
    it presses nothing, so it does not pass through the gate as an action. It is still
    the honest place to notice that the STOP file is on."""
    info: dict = {"ts": datetime.now().astimezone().isoformat(timespec="seconds")}
    left, top, right, bottom = _bounds()
    info["desktop_rect"] = [left, top, right, bottom]
    info["desktop_size"] = [right - left, bottom - top]
    try:
        with _mss()() as sct:
            info["monitors"] = [dict(m) for m in sct.monitors]
    except Exception as exc:
        info["monitors"] = "unavailable: %s: %s" % (type(exc).__name__, exc)
    try:
        import pyautogui
        info["cursor"] = list(pyautogui.position())
        info["pyautogui_size"] = list(pyautogui.size())
    except Exception as exc:
        info["cursor"] = "unavailable: %s" % exc
    if windows:
        info["windows"] = _windows()
        info["window_count"] = len(info["windows"])
    gate = _load()["gate"]
    info["stopped"] = bool(gate.is_stopped()) if gate is not None else "GATE UNAVAILABLE"
    return info


def _prune_shots() -> None:
    try:
        shots = sorted(SHOTS.glob("shot-*.jpg"), key=lambda p: p.stat().st_mtime)
        for old in shots[:-SHOTS_KEEP]:
            old.unlink(missing_ok=True)
    except Exception:
        pass


def screenshot(monitor: int = 1, max_width: int = 1600, include_base64: bool = False) -> dict:
    """Capture the screen to a JPEG on disk and return its PATH.

    Reading the screen is not a keystroke, but it IS surveillance of whatever Iddo has
    open, and the picture leaves this PC (it goes to eran4 over the tailnet if the model
    is ever shown it). So the STOP file silences it too: STOP means ALMIDO's eyes close,
    not just its hands."""
    gate = _load()["gate"]
    if gate is None:
        return {"ok": False, "reason": "GATE UNAVAILABLE: " + "; ".join(_LOADED["errors"])[:400]}
    try:
        if gate.is_stopped():
            _audit_direct("screenshot", "monitor=%s" % monitor, "BLOCK", "STOP file present")
            return {"ok": False, "verdict": "BLOCK",
                    "reason": "STOP file present (%s): the eyes are closed too" % gate.STOP_FILE}
    except Exception as exc:
        return {"ok": False, "reason": "could not read the STOP file: %s" % exc}

    vision = _load()["vision"]
    b64 = None
    how = None
    if vision is not None:
        try:
            import warnings
            with warnings.catch_warnings():      # vision.py still calls the deprecated mss.mss
                warnings.simplefilter("ignore", DeprecationWarning)
                b64 = vision.get_screenshot_base64(max_width=int(max_width), monitor_index=int(monitor))
            how = "harness vision.py (mss)"
        except Exception as exc:
            b64 = None
            how = "harness vision.py failed: %s: %s" % (type(exc).__name__, exc)
    if not b64:
        # Fallback with no mss at all: Pillow's own grabber. Whole virtual desktop only.
        try:
            import base64
            import io
            from PIL import ImageGrab
            img = ImageGrab.grab(all_screens=True).convert("RGB")
            w, h = img.size
            if w > int(max_width):
                img = img.resize((int(max_width), int(h * int(max_width) / w)))
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            b64 = base64.b64encode(buf.getvalue()).decode("ascii")
            how = "PIL.ImageGrab fallback (%s)" % (how or "no vision module")
        except Exception as exc:
            return {"ok": False, "reason": "screen capture failed: %s: %s (%s)"
                                           % (type(exc).__name__, exc, how)}

    import base64 as _b64
    raw = _b64.b64decode(b64)
    SHOTS.mkdir(parents=True, exist_ok=True)
    path = SHOTS / ("shot-%s.jpg" % datetime.now().strftime("%Y%m%d-%H%M%S-%f")[:-3])
    path.write_bytes(raw)
    _prune_shots()
    dims = None
    try:
        from PIL import Image
        with Image.open(path) as im:
            dims = list(im.size)
    except Exception:
        pass
    _audit_direct("screenshot", str(path), "ALLOW", "screen captured to disk")
    out = {"ok": True, "verdict": "ALLOW", "path": str(path), "bytes": len(raw),
           "dimensions": dims, "monitor": int(monitor), "captured_by": how,
           "note": "A PATH, not an image. ALMIDO's brain (qwen3-coder-next) is a CODER, not a "
                   "vision model -- it cannot see a JPEG, and the base64 would cost ~100k tokens. "
                   "Use computer_screen_info for what is on screen as TEXT, or open this file yourself."}
    if include_base64:
        if len(b64) > B64_MAX_BYTES:
            out["base64_omitted"] = ("%d base64 chars is over the %d cap -- read the file at 'path' instead"
                                     % (len(b64), B64_MAX_BYTES))
        else:
            out["base64_jpeg"] = b64
    return out


# ------------------------------------------------------------------ the emergency stop
def stop_status() -> dict:
    gate = _load()["gate"]
    if gate is None:
        return {"stopped": "GATE UNAVAILABLE", "errors": _LOADED["errors"]}
    p = gate.STOP_FILE
    out = {"stop_file": str(p), "stopped": bool(p.exists())}
    if out["stopped"]:
        try:
            out["content"] = p.read_text(encoding="utf-8", errors="replace")[:500]
            out["since"] = datetime.fromtimestamp(p.stat().st_mtime).astimezone().isoformat(timespec="seconds")
        except Exception:
            pass
    out["how_to_clear"] = ("Iddo deletes %s himself. Nothing in ALMIDO can clear it -- an agent "
                           "that can lift its own emergency stop does not have one." % p)
    return out


def stop_engage(reason: str = "") -> dict:
    """Create the STOP file. Deliberately one-way: there is no stop_release()."""
    gate = _load()["gate"]
    if gate is None:
        return {"ok": False, "reason": "GATE UNAVAILABLE: " + "; ".join(_LOADED["errors"])[:400]}
    p = gate.STOP_FILE
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        if not p.exists():
            p.write_text("STOP engaged %s\nby: almido_computer\nreason: %s\n"
                         % (datetime.now().astimezone().isoformat(timespec="seconds"),
                            str(reason or "(none given)")[:400]), encoding="utf-8")
    except Exception as exc:
        return {"ok": False, "reason": "%s: %s" % (type(exc).__name__, exc)}
    _audit_direct("command", "stop_engage", "BLOCK", "STOP engaged: " + str(reason or "")[:120])
    return {"ok": True, "stopped": True, "stop_file": str(p),
            "note": "Every computer-use action now BLOCKs, including screenshots. "
                    "Only Iddo, deleting that file, can undo this."}


# ------------------------------------------------------------------ the self-report
def status() -> dict:
    """Measured, never declared: which harness copy answered, whether the gate loaded,
    whether the hands and eyes are importable, whether STOP is on."""
    loaded = _load()
    gate = loaded["gate"]
    out = {
        "i_am": "almido_computer",
        "harness_dir": str(loaded["harness"]) if loaded["harness"] else None,
        "harness_searched": loaded["tried"],
        "gate_loaded": gate is not None,
        "gate_file": getattr(gate, "__file__", None),
        "hands_loaded": loaded["actions"] is not None,
        "eyes_loaded": loaded["vision"] is not None,
        "errors": loaded["errors"] or None,
        "audit_log": str(getattr(gate, "AUDIT_LOG", "")) if gate else None,
        "policy_file": str(getattr(gate, "POLICY_FILE", "")) if gate else None,
        "screenshot_dir": str(SHOTS),
        "rate_limit": "%d actions per %.0f s" % (RATE_MAX, RATE_WINDOW),
        "opencv": loaded.get("cv2"),
        "warm_seconds": loaded.get("warm_seconds"),
        "listening_socket": "none -- this module is called in-process over stdio and opens no port",
        "stop": stop_status(),
    }
    # The keyboard layout is not trivia here: it is what broke typing entirely until
    # 2026-09-11 (see the TYPING note above). Reported so the next person measures it.
    try:
        import ctypes
        u = ctypes.windll.user32
        hkl = u.GetKeyboardLayout(u.GetWindowThreadProcessId(u.GetForegroundWindow(), None))
        out["keyboard_layout"] = {"hkl": "0x%08X" % (hkl & 0xFFFFFFFF),
                                  "langid": "0x%04X" % (hkl & 0xFFFF)}
    except Exception as exc:
        out["keyboard_layout"] = "unknown: %s" % exc
    out["typing"] = ("SendInput + KEYEVENTF_UNICODE -- independent of the keyboard layout. "
                     "pyautogui.write() is NOT, and under Iddo's Hebrew layout it delivered "
                     "zero characters and fired Alt+Ctrl+Shift+garbage instead.")
    for mod in ("pyautogui", "mss", "PIL"):
        try:
            m = __import__(mod)
            out.setdefault("deps", {})[mod] = getattr(m, "__version__", "present")
        except Exception as exc:
            out.setdefault("deps", {})[mod] = "MISSING (%s)" % type(exc).__name__
    if not out["gate_loaded"]:
        out["verdict"] = "NO HANDS: the gate could not be loaded, so every action is refused."
    elif not out["hands_loaded"]:
        out["verdict"] = "EYES ONLY: the gate is up but actions.py did not import."
    else:
        out["verdict"] = "ready" if not out["stop"].get("stopped") else "STOPPED (STOP file present)"
    return out


def _cli(argv: list) -> int:
    cmd = (argv[1] if len(argv) > 1 else "status").lower()
    if cmd == "status":
        print(json.dumps(status(), ensure_ascii=False, indent=1, default=str))
    elif cmd == "screen":
        print(json.dumps(screen_info(), ensure_ascii=False, indent=1, default=str))
    elif cmd == "shot":
        print(json.dumps(screenshot(), ensure_ascii=False, indent=1, default=str))
    elif cmd == "stop":
        print(json.dumps(stop_engage(" ".join(argv[2:])), ensure_ascii=False, indent=1, default=str))
    else:
        print("usage: almido_computer.py [status|screen|shot|stop <reason>]", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli(sys.argv))
