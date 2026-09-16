#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""almido_phone.py -- ALMIDO's hands on Iddo's PHONE, behind the same gate as its hands
on this PC.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

Iddo, 2026-09-11 08:29 ("\u05ea\u05e2\u05e9\u05d4 \u05db\u05d5\u05dc\u05dd \u05d1\u05e1\u05d3\u05e8 \u05e9\u05dc\u05da"): give ALMIDO hands on the S26 Ultra.

THE SHAPE IS DELIBERATELY THE SAME AS almido_computer.py, because the lesson is the same:

    almido_phone  -->  almido_gate.gate(kind, detail)   <- THE gate (policy + STOP + audit)
                  -->  adb                              <- THE hands (one subprocess, argv, never a shell)

There is no second path. Nothing here taps, types or presses without gate() answering
ALLOW first, and if the gate cannot be imported at all every action is REFUSED -- fail
closed, the same rule as the PC door.

WHAT THIS ADDS ON TOP, all of it further REFUSALS, never permissions:

  * expect_app IS REQUIRED on every hand. It is a package name, and the FOREGROUND
    package is measured before the action and RE-MEASURED after it. The PC door learned
    this at 06:03 on 2026-09-11, when a click aimed at one window landed in Iddo's own
    application because the aim was never verified. A phone is worse: one stray tap in
    the wrong app sends a message, answers a call, or pays for something.
  * A DENY LIST OF PACKAGES that no aim can reach, whatever the caller says:
      - the dialer / in-call UI  -> a tap during a call is a tap in Iddo's conversation
      - Samsung Wallet, banking, anything that spends money
      - Settings (and any security screen inside it)
      - EVERY audio, microphone, recorder and music package -- AUDIO PROTECTION LAW /
        \u05d7\u05d5\u05e7 \u05d4\u05d2\u05e0\u05ea \u05d4\u05e9\u05de\u05e2. Default DENY on the substrings, not default allow.
    The list is here, in code, and can only be EXTENDED by policy -- never shortened.
  * An ACTIVE CALL blocks everything, whatever app is in front.
  * A rate limit, shared in spirit with the PC door (default 40 actions / 60 s).
  * Nothing ever hangs: every adb invocation carries a timeout (<= 15 s) and a dead or
    unplugged phone returns a clear, immediate error instead of a stuck tool call.
  * Every action lands in the gate's audit trail, and a screenshot lands there WITH THE
    SHA256 OF THE IMAGE, so what the agent saw is provable afterwards.

WHAT IT CANNOT DO. The phone's shell is reachable two ways and only one of them has hands:

    adb (uid 2000 'shell')  -> input, screencap, uiautomator, am, dumpsys    <- the hands
    Termux ssh (uid 10415)  -> an ordinary app: MEASURED 2026-09-11 08:40, `input keyevent`
                               raises SecurityException (no INJECT_EVENTS), `screencap`
                               answers "Capturing failed", and dumpsys window prints
                               nothing. Termux is NOT a fallback for the hands. It is used
                               for exactly one thing -- setting the clipboard, see TYPING.

TYPING HEBREW. `input text` is ASCII-only in practice: the argument is passed through to
KeyCharacterMap, which has no key for \u05e9. The path that works without installing an IME:

    1. termux-clipboard-set over ssh   (an app CAN write the clipboard; measured working)
    2. adb shell input keyevent 279    (KEYCODE_PASTE) into the focused field

Both halves are implemented. Half 1 is measured. Half 2 needs adb, and on 2026-09-11 the
phone was on mobile data with adb TCP off, so it is reported UNVERIFIED rather than
claimed -- see status()['typing'].

Run:  python almido_phone.py status
Test: python -m pytest tests/test_almido_phone.py
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections import deque
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
_HOME = Path(os.path.expanduser("~"))
_TOTZAREI_CLAUDE = "\u05ea\u05d5\u05e6\u05e8\u05d9 \u05e7\u05dc\u05d5\u05d3"     # "totzarei claude"
_HARNESS_NAME = "Perplexity-Computer-Use-Harness"

# The same search order almido_computer.py and almido_backup.py use. The Desktop tidy task
# has moved this folder before, so every place it has actually lived is tried.
HARNESS_CANDIDATES = [Path(p) for p in (
    os.environ.get("ALMIDO_PH_HARNESS", ""),
    os.environ.get("ALMIDO_CU_HARNESS", ""),
    _HOME / "Desktop" / _TOTZAREI_CLAUDE / _HARNESS_NAME,
    _HOME / "Desktop" / "_Organized" / _TOTZAREI_CLAUDE / _HARNESS_NAME,
    _HOME / "Desktop" / "_Organized" / "Docs" / _HARNESS_NAME,
    _HOME / "Desktop" / _HARNESS_NAME,
    Path(r"D:\CLAUDE") / _HARNESS_NAME,
) if str(p)]

# --- the transport -------------------------------------------------------------------
# The phone appears in `adb devices -l` sometimes twice: once under its mDNS name and once
# as ip:port. PHONE_HOST is the string that picks the right one out.
PHONE_HOST = os.environ.get("ALMIDO_PHONE_HOST", "<lan-ip>")
PHONE_SERIAL = os.environ.get("ANDROID_SERIAL", "") or os.environ.get("ALMIDO_PHONE_SERIAL", "")
PHONE_MODEL = os.environ.get("ALMIDO_PHONE_MODEL", "SM-S948B")
ADB = os.environ.get("ALMIDO_ADB", "") or shutil.which("adb") or "adb"

# Nothing may hang. 15 s is the hard ceiling the caller was promised.
ADB_TIMEOUT = min(15.0, float(os.environ.get("ALMIDO_PHONE_TIMEOUT", "15") or 15))
ADB_SHORT = min(ADB_TIMEOUT, 8.0)

# Termux over ssh -- used ONLY for the clipboard, never for the hands.
TERMUX_SSH = os.environ.get("ALMIDO_PHONE_SSH", "u0_a415@<tailnet-ip>")
TERMUX_PORT = os.environ.get("ALMIDO_PHONE_SSH_PORT", "8022")

SHOTS = Path(os.environ.get("ALMIDO_PHONE_SHOTS", str(HERE / "workspace" / "phone-shots")))
SHOTS_KEEP = max(1, int(os.environ.get("ALMIDO_PHONE_SHOTS_KEEP", "40") or 40))

RATE_MAX = max(1, int(os.environ.get("ALMIDO_PHONE_RATE_MAX", "40") or 40))
RATE_WINDOW = float(os.environ.get("ALMIDO_PHONE_RATE_WINDOW", "60") or 60)
_BUCKET: deque = deque()

ACT_KINDS = ("click", "type", "key", "scroll")

_LOADED: dict = {"gate": None, "harness": None, "tried": [], "errors": []}


# ------------------------------------------------------------------ the gate, by path
def _load_module(name: str, path: Path):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError("no loader for %s" % path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _load() -> dict:
    if _LOADED["gate"] is not None or _LOADED["errors"]:
        return _LOADED
    for cand in HARNESS_CANDIDATES:
        _LOADED["tried"].append(str(cand))
        if not (cand / "almido_gate.py").is_file():
            continue
        try:
            _LOADED["gate"] = _load_module("almido_ph_gate", cand / "almido_gate.py")
            _LOADED["harness"] = cand
        except Exception as exc:
            _LOADED["errors"].append("%s: %s: %s" % (cand, type(exc).__name__, exc))
            continue
        return _LOADED
    if not _LOADED["errors"]:
        _LOADED["errors"].append("almido_gate.py found in none of: " + "; ".join(_LOADED["tried"]))
    return _LOADED


def gate_module():
    return _load()["gate"]


# ------------------------------------------------------------------ audit and refusals
def _audit_direct(kind: str, detail: str, verdict: str, reason: str) -> None:
    """One row in the gate's OWN audit trail, for a refusal the gate never saw. Same file,
    same schema as every decision the gate itself makes."""
    gate = _load()["gate"]
    writer = getattr(gate, "_audit", None) if gate is not None else None
    if writer is None:
        return
    try:
        writer(kind, detail, verdict, reason)
    except Exception:
        pass


def _refuse(kind: str, detail: str, reason: str, verdict: str = "BLOCK") -> dict:
    _audit_direct(kind, "phone:" + str(detail), verdict, reason)
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


# ------------------------------------------------------------------ the package fence
# AUDIO PROTECTION LAW plus the phone-specific dangers. Hebrew written with \u escapes so a
# cp1255 re-save cannot quietly empty half of it. DEFAULT DENY: a package that matches any
# of these substrings is refused, whatever the caller passes as expect_app.
_DENY_SUBSTRINGS = (
    # --- audio / microphone / recording / music: never, by default ---------------------
    "audio", "record", "music", "sound", "voicenote", "voicerecorder", "soundpicker",
    "\u05e9\u05de\u05e2", "\u05de\u05d9\u05e7\u05e8\u05d5\u05e4\u05d5\u05df",
    "keshev", "\u05e7\u05e9\u05d1",
    "spotify", "deezer", "soundcloud", "podcast", "radio",
    # --- a live conversation is never touched -----------------------------------------
    "dialer", "incallui", "telecom", "telephony", "phone.call", "com.android.phone",
    # --- money -------------------------------------------------------------------------
    "wallet", "spay", "samsungpay", "bank", "paypal", "\u05d1\u05e0\u05e7",
    "creditcard", "isracard", "leumi", "hapoalim", "mizrahi",
    # --- settings and anything that can change how the phone is secured ----------------
    "com.android.settings", "com.samsung.android.settings", "settings.security",
    "certinstaller", "gms.security",
    # --- credentials / device admin ----------------------------------------------------
    "authenticator", "keychain", "keystore", "passwordmanager", "bitwarden", "lastpass",
)

# Exact packages refused even though their name matches nothing above.
_DENY_EXACT = (
    "com.samsung.android.app.soundpicker",
    "com.sec.android.app.voicenote",
    "com.samsung.android.dialer",
    "com.samsung.android.incallui",
    "com.android.dialer",
    "com.google.android.dialer",
    "com.samsung.android.spay",
    "com.samsung.android.spayfw",
    "com.android.settings",
)


def _policy_extra_denies() -> list:
    r"""Optional EXTRA denies from Iddo's policy files. Deny-only by construction: this
    function reads `phone.block.packages` and nothing else, so a policy edit can never
    open a package that the code above closed.

    Both policy copies are read (they are different files and have drifted):
      ~/.iddo-harness/policy.yaml         -- what almido_gate.py itself reads
      D:\CLAUDE\iddo-harness\policy.yaml  -- what the Claude-CLI hook reads
    """
    out: list = []
    gate = _load()["gate"]
    paths = []
    p = getattr(gate, "POLICY_FILE", None) if gate is not None else None
    if p:
        paths.append(Path(p))
    paths.append(Path(r"D:\CLAUDE\iddo-harness\policy.yaml"))
    for path in paths:
        try:
            import yaml
            with open(path, encoding="utf-8") as f:
                doc = yaml.safe_load(f) or {}
            for pat in ((doc.get("phone") or {}).get("block") or {}).get("packages") or []:
                out.append(str(pat).lower())
        except Exception:
            continue
    return out


def denied_package(package: str) -> str:
    """Return the pattern this package is refused for, or '' if it may be touched."""
    pkg = (package or "").strip().lower()
    if not pkg:
        return ""
    if pkg in _DENY_EXACT:
        return pkg
    for pat in tuple(_DENY_SUBSTRINGS) + tuple(_policy_extra_denies()):
        if pat and pat in pkg:
            return pat
    return ""


# ------------------------------------------------------------------ adb, one subprocess
def _run(cmd: list, timeout: float, binary: bool = False):
    r"""ONE subprocess call. shell=False always -- an argv list, never a shell string, so
    nothing a caller passes can be re-parsed into a second command.

    Returns (rc, out, err). rc = -9 on timeout, -1 when adb is not installed at all. It
    NEVER raises and it NEVER blocks past `timeout`: the promise to the caller is that an
    offline phone ANSWERS, it does not hang."""
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=timeout,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired:
        return -9, (b"" if binary else ""), "timed out after %.0fs: %s" % (timeout, " ".join(cmd[:3]))
    except FileNotFoundError:
        return -1, (b"" if binary else ""), "adb not found at %r -- install Google platform-tools" % ADB
    except Exception as exc:
        return -2, (b"" if binary else ""), "%s: %s" % (type(exc).__name__, exc)
    err = p.stderr.decode("utf-8", "replace").strip()
    if binary:
        return p.returncode, p.stdout, err
    return p.returncode, p.stdout.decode("utf-8", "replace"), err


def _adb_args(args: list, serial: str = "") -> list:
    cmd = [ADB]
    ser = serial or PHONE_SERIAL
    if ser:
        cmd += ["-s", ser]
    return cmd + [str(a) for a in args]


def adb(args: list, timeout: float = None, serial: str = "", binary: bool = False):
    return _run(_adb_args(args, serial), timeout or ADB_TIMEOUT, binary=binary)


_SAFE_SH = re.compile(r"^[A-Za-z0-9_@%+=:,./-]+$")


def _sh_quote(s: str) -> str:
    if _SAFE_SH.match(s):
        return s
    return "'" + s.replace("'", "'\\''") + "'"


def adb_shell(line: list, timeout: float = None, serial: str = "", binary: bool = False):
    """`adb shell` with the command as SEPARATE ARGV ELEMENTS.

    adb still joins them with spaces on the far side, so anything containing a space or a
    shell metacharacter is single-quoted here. That is why every caller in this module
    builds a list and never a string."""
    return adb(["shell"] + [_sh_quote(str(a)) for a in line], timeout, serial, binary)


# ------------------------------------------------------------------ what the phone says
def devices() -> dict:
    """`adb devices -l`, parsed. Never raises, never hangs. Takes no -s: the whole point
    is to see everything that is attached."""
    rc, out, err = _run([ADB, "devices", "-l"], ADB_SHORT)
    rows = []
    for line in (out or "").splitlines():
        line = line.strip()
        if not line or line.startswith("List of devices"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        rows.append({"serial": parts[0], "state": parts[1], "info": " ".join(parts[2:])[:200]})
    return {"ok": rc == 0, "rc": rc, "devices": rows, "error": err or None, "adb": ADB}


def resolve_serial() -> tuple:
    r"""Which device are we talking to? Returns (serial, reason).

    The S26 shows up twice when it is on Wi-Fi -- once as an mDNS name
    (`adb-R5C...._adb-tls-connect`) and once as `<lan-ip>:5555`. Pinning to the one
    containing PHONE_HOST is what the morning survey did by hand; taking whichever is
    first is how a command lands on the Quest instead."""
    if PHONE_SERIAL:
        return PHONE_SERIAL, "pinned by ANDROID_SERIAL/ALMIDO_PHONE_SERIAL"
    d = devices()
    live = [r for r in d["devices"] if r["state"] == "device"]
    if not live:
        offline = [r for r in d["devices"] if r["state"] != "device"]
        return "", ("no device in state 'device'" +
                    (" (%s)" % "; ".join("%s=%s" % (r["serial"], r["state"]) for r in offline)
                     if offline else "; adb sees nothing attached"))
    hit = [r for r in live if PHONE_HOST and PHONE_HOST in r["serial"]]
    if hit:
        return hit[0]["serial"], "matched ALMIDO_PHONE_HOST=%s" % PHONE_HOST
    hit = [r for r in live if PHONE_MODEL and PHONE_MODEL.lower() in r["info"].lower()]
    if hit:
        return hit[0]["serial"], "matched model %s" % PHONE_MODEL
    if len(live) == 1:
        return live[0]["serial"], "the only device attached"
    return "", ("%d devices attached and none matches %s or %s -- ambiguous, refusing to "
                "guess: %s" % (len(live), PHONE_HOST, PHONE_MODEL,
                               ", ".join(r["serial"] for r in live)))


_FOCUS_RE = re.compile(r"([A-Za-z0-9_][A-Za-z0-9_.]*)/([A-Za-z0-9_.$]+)")


def foreground(serial: str = "") -> dict:
    """The package that is in front RIGHT NOW, measured. Several strategies, because
    `mCurrentFocus` moved between Android releases and this phone is on Android 16."""
    tries = (
        (["dumpsys", "window"], ("mCurrentFocus", "mFocusedApp")),
        (["dumpsys", "activity", "activities"], ("topResumedActivity", "mResumedActivity",
                                                 "ResumedActivity")),
    )
    last_err = None
    for args, keys in tries:
        rc, out, err = adb_shell(args, ADB_SHORT, serial)
        if rc != 0:
            last_err = err or ("rc=%d" % rc)
            continue
        for line in out.splitlines():
            if not any(k in line for k in keys):
                continue
            m = _FOCUS_RE.search(line)
            if m:
                return {"ok": True, "package": m.group(1), "activity": m.group(2),
                        "line": line.strip()[:200], "via": " ".join(args)}
            if "NotificationShade" in line or "StatusBar" in line:
                return {"ok": True, "package": "com.android.systemui", "activity": "",
                        "line": line.strip()[:200], "via": " ".join(args)}
    return {"ok": False, "package": "", "activity": "",
            "reason": "could not read the foreground package: %s" % (last_err or "no match")}


def call_active(serial: str = "") -> dict:
    """Is Iddo on the phone? A tap during a call is a tap in his conversation."""
    rc, out, err = adb_shell(["dumpsys", "telephony.registry"], ADB_SHORT, serial)
    if rc != 0:
        return {"known": False, "active": None, "reason": err or ("rc=%d" % rc)}
    states = [int(m) for m in re.findall(r"mCallState=(\d+)", out)]
    return {"known": bool(states), "active": any(s != 0 for s in states),
            "call_states": states[:4]}


def _screen(serial: str = "") -> dict:
    out = {}
    rc, txt, _ = adb_shell(["dumpsys", "power"], ADB_SHORT, serial)
    if rc == 0:
        m = re.search(r"mWakefulness=(\w+)", txt)
        if m:
            out["wakefulness"] = m.group(1)
            out["screen_on"] = m.group(1).lower() == "awake"
    rc, txt, _ = adb_shell(["dumpsys", "window"], ADB_SHORT, serial)
    if rc == 0:
        m = re.search(r"mDreamingLockscreen=(\w+)", txt)
        if m:
            out["locked"] = m.group(1).lower() == "true"
        m = re.search(r"mShowingLockscreen=(\w+)", txt)
        if m and "locked" not in out:
            out["locked"] = m.group(1).lower() == "true"
    return out


def _battery(serial: str = "") -> dict:
    rc, txt, _ = adb_shell(["dumpsys", "battery"], ADB_SHORT, serial)
    if rc != 0:
        return {}
    out = {}
    for key_, pat in (("level", r"level:\s*(\d+)"), ("temperature", r"temperature:\s*(\d+)"),
                      ("status", r"status:\s*(\d+)")):
        m = re.search(pat, txt)
        if m:
            out[key_] = int(m.group(1))
    if "temperature" in out:
        out["temperature_c"] = out.pop("temperature") / 10.0
    m = re.search(r"AC powered:\s*(\w+)", txt)
    if m:
        out["ac_powered"] = m.group(1).lower() == "true"
    return out


def status() -> dict:
    """MEASURED self-report. Taps nothing, types nothing. Answers even when the phone is
    gone -- that is the whole point of it."""
    loaded = _load()
    gate = loaded["gate"]
    out = {
        "i_am": "almido_phone",
        "adb": ADB,
        "adb_found": bool(shutil.which(ADB) or Path(ADB).is_file()),
        "gate_loaded": gate is not None,
        "gate_file": getattr(gate, "__file__", None),
        "audit_log": str(getattr(gate, "AUDIT_LOG", "")) if gate else None,
        "errors": loaded["errors"] or None,
        "phone_host": PHONE_HOST,
        "phone_model": PHONE_MODEL,
        "timeout_s": ADB_TIMEOUT,
        "rate_limit": "%d actions per %.0f s" % (RATE_MAX, RATE_WINDOW),
        "shots_dir": str(SHOTS),
        "termux_ssh": "%s -p %s" % (TERMUX_SSH, TERMUX_PORT),
        "typing": {
            "ascii": "adb shell input text, spaces sent as %s -- the ordinary path, it works.",
            "unicode": ("NOT PROVEN. termux-clipboard-set + KEYCODE_PASTE is implemented and "
                        "is the best ADBKeyboard-free candidate, but see 'unicode_measured'."),
            "unicode_measured": (
                "2026-09-11 08:5x, over Termux ssh with the phone on mobile data: "
                "`termux-clipboard-set` accepted Hebrew and returned rc=0, but reading it "
                "straight back with `termux-clipboard-get` returned EMPTY. That is exactly "
                "what Android 10+ does to a BACKGROUND app's clipboard access -- it does not "
                "error, it silently does nothing. So rc=0 here is not evidence that the text "
                "landed. Run phone_hebrew_probe() once the phone is on adb: it tries every "
                "route and reads the result back out of the live UI, which is the only "
                "honest answer."),
            "why": ("`input text` goes through KeyCharacterMap, which has no key for a "
                    "Hebrew letter, so non-ASCII is dropped rather than typed."),
        },
        "termux_is_not_a_fallback": (
            "MEASURED 2026-09-11 08:40 over ssh as uid 10415: `input keyevent` -> "
            "SecurityException (no INJECT_EVENTS), `screencap` -> 'Capturing failed', "
            "`dumpsys window` -> empty. Only adb (uid 2000) has hands."),
    }
    if gate is not None:
        try:
            out["stopped"] = bool(gate.is_stopped())
            out["stop_file"] = str(gate.STOP_FILE)
        except Exception as exc:
            out["stopped"] = "unreadable: %s" % exc
    else:
        out["stopped"] = "GATE UNAVAILABLE"

    d = devices()
    out["devices"] = d["devices"]
    if d.get("error"):
        out["adb_error"] = d["error"]
    serial, why = resolve_serial()
    out["serial"] = serial or None
    out["serial_reason"] = why
    if not serial:
        out["online"] = False
        out["verdict"] = "OFFLINE: %s. Nothing can be tapped." % why
        return out

    out["online"] = True
    out["foreground"] = foreground(serial)
    out["screen"] = _screen(serial)
    out["battery"] = _battery(serial)
    out["call"] = call_active(serial)
    rc, txt, _ = adb_shell(["getprop", "ro.product.model"], ADB_SHORT, serial)
    out["model"] = txt.strip() if rc == 0 else None
    rc, txt, _ = adb_shell(["getprop", "ro.build.version.release"], ADB_SHORT, serial)
    out["android"] = txt.strip() if rc == 0 else None
    if not out["gate_loaded"]:
        out["verdict"] = "NO HANDS: the gate could not be loaded, so every action is refused."
    elif out.get("stopped") is True:
        out["verdict"] = "STOPPED (STOP file present)"
    elif out.get("call", {}).get("active"):
        out["verdict"] = "CALL IN PROGRESS -- every hand is refused until it ends"
    else:
        out["verdict"] = "ready"
    return out


# ------------------------------------------------------------------ the guard
def _guard(kind: str, detail: str):
    """Everything refused BEFORE the gate is consulted. Returns (refusal|None, serial)."""
    loaded = _load()
    gate = loaded["gate"]
    if gate is None:
        return {"ok": False, "action": kind, "detail": detail, "verdict": "BLOCK",
                "performed": False,
                "reason": "GATE UNAVAILABLE, so nothing is allowed: "
                          + "; ".join(loaded["errors"])[:400]}, ""
    try:
        if gate.is_stopped():
            return _refuse(kind, detail, "STOP file present (%s)" % gate.STOP_FILE), ""
    except Exception as exc:
        return _refuse(kind, detail, "could not read the STOP file: %s" % exc), ""
    if kind in ACT_KINDS and not _rate_ok():
        return _refuse(kind, detail, "rate limit: more than %d actions in %.0f s"
                       % (RATE_MAX, RATE_WINDOW)), ""
    serial, why = resolve_serial()
    if not serial:
        return _refuse(kind, detail,
                       "the phone is not reachable over adb (%s). Nothing was tapped. "
                       "Check that it is on Wi-Fi and that wireless debugging is on." % why), ""
    return None, serial


def _require_app(kind: str, detail: str, expect_app, serial: str):
    """The aim check. Returns (refusal|None, foreground_dict|None).

    Order: named at all -> not a denied package -> the phone is not in a call -> the LIVE
    foreground is not a denied package -> the live foreground IS the named package."""
    expect = "" if expect_app is None else str(expect_app).strip()
    if not expect:
        return _refuse(
            kind, detail,
            "expect_app is REQUIRED: name the package you believe you are acting on "
            "(phone_status reports the foreground one). A hand that aims at 'whatever is "
            "in front' is how the wrong window got clicked on the PC on 2026-09-11."), None

    bad = denied_package(expect)
    if bad:
        return _refuse(
            kind, detail,
            "REFUSED: %r matches the protected pattern %r. Audio, microphone, recorder, "
            "music, the dialer, anything that spends money and Settings are never touched "
            "by any agent hand (AUDIO PROTECTION LAW)." % (expect, bad)), None

    call = call_active(serial)
    if call.get("active"):
        return _refuse(kind, detail,
                       "REFUSED: a call is in progress (mCallState=%s). Nothing is pressed "
                       "on Iddo's phone while he is talking." % call.get("call_states")), None

    fg = foreground(serial)
    if not fg.get("ok"):
        return _refuse(kind, detail,
                       "could not read the foreground package, so the aim cannot be "
                       "verified -- refusing rather than guessing (%s)"
                       % fg.get("reason", "")), None

    bad = denied_package(fg.get("package", ""))
    if bad:
        return _refuse(
            kind, detail,
            "REFUSED: the app in FRONT is %r, which matches the protected pattern %r. "
            "Nothing is pressed while that is on screen, whatever was aimed at."
            % (fg.get("package"), bad)), None

    if fg.get("package", "") != expect:
        return _refuse(
            kind, detail,
            "the app in front is %r, not %r. Open it first (phone_open) or aim at what is "
            "really there -- a tap into the wrong app on a phone sends messages and spends "
            "money." % (fg.get("package"), expect)), None
    return None, fg


def _after(kind: str, expect_app: str, serial: str, out: dict, enforce: bool = True) -> dict:
    """RE-READ the foreground after the action. The 'and after' half of the discipline."""
    fg = foreground(serial)
    out["app_after"] = fg.get("package") or None
    held = bool(fg.get("ok")) and fg.get("package") == expect_app
    out["expect_app_held"] = held
    if enforce and not held:
        out["ok"] = False
        out["reason"] = (
            "the action was performed, but the app in front afterwards is %r, not %r. "
            "Something moved under the hand -- STOP and look before acting again."
            % (fg.get("package"), expect_app))
        _audit_direct(kind, "phone:%s" % out.get("detail", ""), "BLOCK", out["reason"][:180])
    return out


def _do(kind: str, detail: str, run, serial: str = "") -> dict:
    r"""THE one path from a request to the phone: pre-checks, the gate, then the hands.

    `serial` is passed in by every caller that has ALREADY run _guard (which is all of
    them -- they have to, because the aim check needs a serial to read the foreground with).
    Re-running the guard here would charge the rate-limit bucket TWICE for one tap and
    would cost a second `adb devices` round trip. Caught by
    test_the_rate_limit_stops_a_looping_agent, which measured 3 allowed actions turning
    into 1."""
    if not serial:
        refused, serial = _guard(kind, detail)
        if refused is not None:
            return refused
    gate = _load()["gate"]
    try:
        verdict, reason = gate.gate(kind, "phone:" + str(detail))
    except Exception as exc:
        return _refuse(kind, detail, "gate raised %s: %s -- refusing" % (type(exc).__name__, exc))
    if verdict != "ALLOW":
        return {"ok": False, "action": kind, "detail": detail, "verdict": verdict,
                "reason": reason, "performed": False,
                "note": "CONFIRM and BLOCK both stop the hand. Ask Iddo."}
    try:
        rc, out, err = run(serial)
    except Exception as exc:
        return {"ok": False, "action": kind, "detail": detail, "verdict": verdict,
                "reason": "%s: %s" % (type(exc).__name__, exc), "performed": False}
    ok = rc == 0
    res = {"ok": ok, "action": kind, "detail": detail, "verdict": verdict,
           "reason": reason if ok else (err or "adb rc=%d" % rc),
           "performed": ok, "serial": serial, "rc": rc}
    if out and not isinstance(out, bytes):
        res["output"] = str(out).strip()[:2000]
    return res


# ------------------------------------------------------------------ the hands
def tap(x, y, expect_app=None) -> dict:
    try:
        x, y = int(x), int(y)
    except (TypeError, ValueError):
        return _refuse("click", "%r,%r" % (x, y), "x and y must be integers")
    if x < 0 or y < 0:
        return _refuse("click", "(%d,%d)" % (x, y),
                       "negative coordinates are not a point on a screen")
    detail = "tap (%d,%d) in %s" % (x, y, expect_app)
    refused, serial = _guard("click", detail)
    if refused is not None:
        return refused
    refused, _fg = _require_app("click", detail, expect_app, serial)
    if refused is not None:
        return refused
    out = _do("click", detail, lambda s: adb_shell(["input", "tap", str(x), str(y)],
                                                   ADB_TIMEOUT, s), serial)
    if out.get("ok"):
        out = _after("click", str(expect_app), serial, out)
    return out


# --- AUDIO PROTECTION LAW, enforced a SECOND time, here, on the raw keycode -----------
# almido_gate.gate() has its own audio-key check for kind='key' -- but it works by taking
# `detail`, splitting it on '+'/','/'-' and matching whole tokens like "volumedown" against
# _AUDIO_KEYS. key() below builds detail as "key %s in %s" % (k, expect_app), which has none
# of those separators: the whole string collapses into ONE token
# ("keykeycode_volume_downincom.spotify.music") that can never equal "volumedown". So for
# every call that comes through THIS door the shared check silently never fires, and an
# Android hardware keycode would reach the phone. This fence does not depend on the gate's
# string matching at all: it decides straight from the validated keyevent `k`, by number and
# by name, BEFORE the gate (or _do()) is ever consulted -- so a denied key never spends a
# rate-limit slot and never reaches adb.
_AUDIO_KEY_DENY_NUMBERS = frozenset((
    5, 6,                            # KEYCODE_CALL, KEYCODE_ENDCALL
    24, 25, 164,                     # VOLUME_UP, VOLUME_DOWN, VOLUME_MUTE
    79,                               # KEYCODE_HEADSETHOOK
    85, 86, 87, 88, 89, 90, 91,      # MEDIA_PLAY_PAUSE/STOP/NEXT/PREVIOUS/REWIND/FAST_FORWARD, MUTE
    126, 127, 130,                   # MEDIA_PLAY, MEDIA_PAUSE, MEDIA_RECORD
    209,                              # KEYCODE_MUSIC
    219,                              # KEYCODE_ASSIST
    222,                              # KEYCODE_MEDIA_AUDIO_TRACK
    231,                              # KEYCODE_VOICE_ASSIST
))
# Any keyevent NAME containing one of these substrings (case-insensitive) is denied too --
# this also catches keycodes not enumerated above by number, and "ctrl+volumedown"-style
# names should they ever reach key() instead of a hotkey door.
_AUDIO_KEY_DENY_SUBSTRINGS = ("VOLUME", "MEDIA", "MUTE", "HEADSET", "CALL", "VOICE", "MUSIC", "RECORD")
# KEYCODE_ASSIST / ASSIST contains none of the substrings above, so it needs an exact match.
_AUDIO_KEY_DENY_NAMES_EXACT = frozenset(("ASSIST", "KEYCODE_ASSIST"))


def _audio_law_key_block(k: str) -> str:
    """Return a non-empty reason if the already-validated keyevent `k` is a volume / media /
    mute / call / voice-assist / music / recording key the Audio Protection Law forbids --
    else "" ."""
    if k.isdigit():
        if int(k) in _AUDIO_KEY_DENY_NUMBERS:
            return "keycode %s is a volume/media/mute/call/voice/music/record key" % k
        return ""
    up = k.upper()
    if up in _AUDIO_KEY_DENY_NAMES_EXACT:
        return "%s is a volume/media/mute/call/voice/music/record key" % k
    for word in _AUDIO_KEY_DENY_SUBSTRINGS:
        if word in up:
            return "%s matches '%s' -- a volume/media/mute/call/voice/music/record key" % (k, word)
    return ""


def key(keyevent, expect_app=None) -> dict:
    """Press ONE Android key. `keyevent` is a name (KEYCODE_ENTER / ENTER) or a number."""
    k = "" if keyevent is None else str(keyevent).strip()
    if not k:
        return _refuse("key", "", "no keyevent given")
    if not re.match(r"^[A-Za-z0-9_]+$", k):
        return _refuse("key", k, "a keyevent is a name or a number, nothing else")
    audio_block = _audio_law_key_block(k)
    if audio_block:
        return _refuse("key", k, "audio law: %s -- Iddo's audio is never touched" % audio_block)
    detail = "key %s in %s" % (k, expect_app)
    refused, serial = _guard("key", detail)
    if refused is not None:
        return refused
    refused, _fg = _require_app("key", detail, expect_app, serial)
    if refused is not None:
        return refused
    out = _do("key", detail, lambda s: adb_shell(["input", "keyevent", k], ADB_TIMEOUT, s), serial)
    if out.get("ok"):
        out = _after("key", str(expect_app), serial, out)
    return out


def _swipe_unguarded(serial: str, x1, y1, x2, y2, ms, expect_app=None) -> dict:
    r"""The swipe hand itself, for a `serial` the CALLER has already run through `_guard`.

    swipe() and scroll() both land here after guarding exactly once. Neither may call
    `_guard` again inside this function -- that was the WAVE A1 review bug: scroll() used
    to guard itself and then call swipe(), which guarded a second time, so one scroll from
    an agent charged TWO rate-limit slots. Caught by
    test_scroll_consumes_exactly_one_rate_slot."""
    pts = [x1, y1, x2, y2]
    detail = "swipe %s %dms in %s" % (pts, ms, expect_app)
    refused, _fg = _require_app("scroll", detail, expect_app, serial)
    if refused is not None:
        return refused
    out = _do("scroll", detail,
              lambda s: adb_shell(["input", "swipe"] + [str(v) for v in pts] + [str(ms)],
                                  ADB_TIMEOUT, s), serial)
    if out.get("ok"):
        out = _after("scroll", str(expect_app), serial, out)
    return out


def swipe(x1, y1, x2, y2, ms: int = 300, expect_app=None) -> dict:
    try:
        pts = [int(v) for v in (x1, y1, x2, y2)]
        ms = max(1, int(ms))
    except (TypeError, ValueError):
        return _refuse("scroll", "%r" % ([x1, y1, x2, y2],), "coordinates must be integers")
    detail = "swipe %s %dms in %s" % (pts, ms, expect_app)
    refused, serial = _guard("scroll", detail)
    if refused is not None:
        return refused
    return _swipe_unguarded(serial, pts[0], pts[1], pts[2], pts[3], ms, expect_app=expect_app)


def screen_size(serial: str = "") -> dict:
    rc, out, err = adb_shell(["wm", "size"], ADB_SHORT, serial)
    if rc != 0:
        return {"ok": False, "reason": err or "rc=%d" % rc}
    m = re.search(r"(\d+)x(\d+)", out)
    if not m:
        return {"ok": False, "reason": "unparsable: %s" % out.strip()[:120]}
    return {"ok": True, "width": int(m.group(1)), "height": int(m.group(2)),
            "raw": out.strip()[:120]}


def scroll(direction: str = "down", expect_app=None) -> dict:
    """A swipe in screen-relative terms, so a caller does not have to know the resolution."""
    d = str(direction or "down").lower()
    if d not in ("up", "down"):
        return _refuse("scroll", d, "direction is 'up' or 'down'")
    refused, serial = _guard("scroll", "scroll " + d)
    if refused is not None:
        return refused
    size = screen_size(serial)
    if not size.get("ok"):
        return _refuse("scroll", d, "could not read the screen size: %s" % size.get("reason"))
    w, h = size["width"], size["height"]
    x = w // 2
    y1, y2 = (int(h * 0.70), int(h * 0.30)) if d == "down" else (int(h * 0.30), int(h * 0.70))
    # NOT swipe() -- that would guard a second time for the same scroll. _guard already ran
    # above, so the unguarded swipe hand is called directly.
    return _swipe_unguarded(serial, x, y1, x, y2, 300, expect_app=expect_app)


# --- typing ---------------------------------------------------------------------------
def _input_text_arg(text: str) -> str:
    r"""`adb shell input text` passes the string through the shell AND through
    KeyCharacterMap. A space must arrive as %s (a literal space would end the argument)."""
    return text.replace("%", "%%").replace(" ", "%s")


def clipboard_set_via_termux(text: str, timeout: float = 12.0) -> dict:
    r"""Put `text` on the PHONE's clipboard, from the PC, over Termux ssh.

    This is the ONE thing Termux is used for. An ordinary app cannot inject key events or
    grab the screen (measured), but it CAN write the clipboard -- and the clipboard is the
    only route that carries Hebrew onto this phone without installing an IME."""
    if not text:
        return {"ok": False, "reason": "nothing to put on the clipboard"}
    cmd = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8",
           "-p", str(TERMUX_PORT), TERMUX_SSH, "termux-clipboard-set"]
    try:
        p = subprocess.run(cmd, input=text.encode("utf-8"), capture_output=True,
                           timeout=timeout,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired:
        return {"ok": False, "reason": "termux ssh timed out after %.0fs" % timeout}
    except FileNotFoundError:
        return {"ok": False, "reason": "ssh not found on PATH"}
    except Exception as exc:
        return {"ok": False, "reason": "%s: %s" % (type(exc).__name__, exc)}
    err = p.stderr.decode("utf-8", "replace").strip()
    return {"ok": p.returncode == 0, "rc": p.returncode, "reason": err or None,
            "via": "ssh -p %s %s termux-clipboard-set" % (TERMUX_PORT, TERMUX_SSH),
            "chars": len(text)}


def type_text(text: str, expect_app=None) -> dict:
    r"""Type into the focused field of the app you NAME.

    ASCII              -> `input text` (fast, no clipboard, no side effects)
    non-ASCII (Hebrew) -> termux-clipboard-set + KEYCODE_PASTE, because `input text` has no
                          key for a Hebrew letter and silently drops it.

    The gate sees the text FIRST either way, so a credential is refused before it goes
    anywhere near the phone -- including onto its clipboard."""
    text = "" if text is None else str(text)
    if not text:
        return _refuse("type", "", "nothing to type")
    detail = text
    refused, serial = _guard("type", detail)
    if refused is not None:
        return refused
    refused, _fg = _require_app("type", detail, expect_app, serial)
    if refused is not None:
        return refused

    ascii_only = all(ord(c) < 128 for c in text)
    if ascii_only:
        out = _do("type", detail,
                  lambda s: adb_shell(["input", "text", _input_text_arg(text)], ADB_TIMEOUT, s),
                  serial)
        out["method"] = "adb input text"
    else:
        # The gate must ALLOW before the text touches the phone's clipboard, so the
        # clipboard write happens INSIDE the runner, after gate() has answered.
        def _paste(s):
            clip = clipboard_set_via_termux(text)
            if not clip.get("ok"):
                return 1, "", ("could not set the phone clipboard over Termux ssh: %s. "
                               "Hebrew cannot be typed without it." % clip.get("reason"))
            return adb_shell(["input", "keyevent", "279"], ADB_TIMEOUT, s)
        out = _do("type", detail, _paste, serial)
        out["method"] = "termux-clipboard-set + KEYCODE_PASTE (279)"
        out["note"] = ("The field must already have focus and accept a paste. If nothing "
                       "appears, tap the field first and try again.")
    if out.get("ok"):
        out = _after("type", str(expect_app), serial, out)
    return out


# --- apps -----------------------------------------------------------------------------
def open_app(package: str) -> dict:
    """Launch an app by package, via `monkey ... LAUNCHER 1`. The app CHANGES by design,
    so the after-check is not enforced here -- it is REPORTED, and it is what proves the
    launch actually worked rather than merely returning 0."""
    pkg = (package or "").strip()
    if not re.match(r"^[A-Za-z0-9_][A-Za-z0-9_.]*$", pkg):
        return _refuse("click", pkg, "that is not a package name")
    bad = denied_package(pkg)
    if bad:
        return _refuse("click", pkg,
                       "REFUSED: %r matches the protected pattern %r -- audio, microphone, "
                       "recorder, music, dialer, money and Settings are never opened by any "
                       "agent (AUDIO PROTECTION LAW)." % (pkg, bad))
    detail = "open " + pkg
    refused, serial = _guard("click", detail)
    if refused is not None:
        return refused
    call = call_active(serial)
    if call.get("active"):
        return _refuse("click", detail, "REFUSED: a call is in progress.")
    rc, out, _err = adb_shell(["pm", "list", "packages", pkg], ADB_SHORT, serial)
    installed = rc == 0 and any(ln.strip() == "package:" + pkg for ln in out.splitlines())
    if not installed:
        return _refuse("click", detail,
                       "%r is not installed on this phone (pm list packages found no exact "
                       "match). Nothing was opened." % pkg)
    res = _do("click", detail,
              lambda s: adb_shell(["monkey", "-p", pkg, "-c",
                                   "android.intent.category.LAUNCHER", "1"], ADB_TIMEOUT, s),
              serial)
    if res.get("ok"):
        deadline = time.time() + 6.0
        fg = {}
        while time.time() < deadline:
            time.sleep(0.4)
            fg = foreground(serial)
            if fg.get("package") == pkg:
                break
        res["app_after"] = fg.get("package") or None
        res["opened"] = fg.get("package") == pkg
        if not res["opened"]:
            res["ok"] = False
            res["reason"] = ("monkey returned 0 but the app in front is %r, not %r after 6s. "
                             "The launch did not take." % (fg.get("package"), pkg))
    return res


def home() -> dict:
    """HOME is the way OUT of anything. It is still refused while a protected app is in
    front (that would be a keypress inside a call) and while STOP is on."""
    detail = "home"
    refused, serial = _guard("key", detail)
    if refused is not None:
        return refused
    call = call_active(serial)
    if call.get("active"):
        return _refuse("key", detail, "REFUSED: a call is in progress.")
    fg = foreground(serial)
    bad = denied_package(fg.get("package", ""))
    if bad:
        return _refuse("key", detail,
                       "REFUSED: %r is in front (protected pattern %r) -- no key is pressed "
                       "while it is." % (fg.get("package"), bad))
    res = _do("key", detail, lambda s: adb_shell(["input", "keyevent", "KEYCODE_HOME"],
                                                 ADB_TIMEOUT, s), serial)
    if res.get("ok"):
        res["app_after"] = foreground(serial).get("package")
    return res


def back(expect_app=None) -> dict:
    """BACK inside an app you name. The app may legitimately change (that is what back
    does), so the after-check is reported, not enforced."""
    detail = "back in %s" % expect_app
    refused, serial = _guard("key", detail)
    if refused is not None:
        return refused
    refused, _fg = _require_app("key", detail, expect_app, serial)
    if refused is not None:
        return refused
    res = _do("key", detail, lambda s: adb_shell(["input", "keyevent", "KEYCODE_BACK"],
                                                 ADB_TIMEOUT, s), serial)
    if res.get("ok"):
        res = _after("key", str(expect_app), serial, res, enforce=False)
    return res


# --- the eyes -------------------------------------------------------------------------
def _prune_shots() -> None:
    try:
        shots = sorted(SHOTS.glob("phone-*.png"), key=lambda p: p.stat().st_mtime)
        for old in shots[:-SHOTS_KEEP]:
            old.unlink(missing_ok=True)
    except Exception:
        pass


_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def screenshot(max_width: int = 0) -> dict:
    r"""Capture the phone's screen to a PNG on disk and return its PATH and its SHA256.

    `exec-out screencap -p` streams the PNG over the adb protocol. On Windows an older adb
    used to translate 0x0A into 0x0D 0x0A in that stream and corrupt every image, so the
    PNG magic is CHECKED here and the screencap-to-/sdcard-then-pull route is the fallback.
    An image nobody verified is not evidence.

    STOP closes the eyes as well as the hands: reading the phone's screen is surveillance
    of whatever Iddo has open."""
    detail = "screenshot"
    refused, serial = _guard("screenshot", detail)
    if refused is not None:
        return refused

    raw, how = b"", None
    rc, out, err = adb(["exec-out", "screencap", "-p"], ADB_TIMEOUT, serial, binary=True)
    if rc == 0 and isinstance(out, bytes) and out[:8] == _PNG_MAGIC:
        raw, how = out, "adb exec-out screencap -p"
    else:
        remote = "/sdcard/almido_shot.png"
        rc2, _o, err2 = adb_shell(["screencap", "-p", remote], ADB_TIMEOUT, serial)
        if rc2 != 0:
            return _refuse("screenshot", detail,
                           "screencap failed both ways: exec-out(%s) / on-device(%s)"
                           % (err or "rc=%d" % rc, err2 or "rc=%d" % rc2))
        SHOTS.mkdir(parents=True, exist_ok=True)
        tmp = SHOTS / "_pull.png"
        rc3, _o, err3 = adb(["pull", remote, str(tmp)], ADB_TIMEOUT, serial)
        adb_shell(["rm", "-f", remote], ADB_SHORT, serial)
        if rc3 != 0 or not tmp.is_file():
            return _refuse("screenshot", detail, "adb pull failed: %s" % (err3 or "rc=%d" % rc3))
        raw = tmp.read_bytes()
        tmp.unlink(missing_ok=True)
        how = ("adb shell screencap + pull (exec-out returned %d bytes with the wrong magic)"
               % (len(out) if isinstance(out, bytes) else 0))

    if raw[:8] != _PNG_MAGIC:
        return _refuse("screenshot", detail,
                       "what came back is not a PNG (%d bytes, magic %r) -- refusing to "
                       "call it a screenshot" % (len(raw), raw[:8]))

    SHOTS.mkdir(parents=True, exist_ok=True)
    path = SHOTS / ("phone-%s.png" % datetime.now().strftime("%Y%m%d-%H%M%S-%f")[:-3])
    if max_width and int(max_width) > 0:
        try:
            import io
            from PIL import Image
            with Image.open(io.BytesIO(raw)) as im:
                w, h = im.size
                if w > int(max_width):
                    im = im.resize((int(max_width), int(h * int(max_width) / w)))
                im.save(path, format="PNG")
            raw = path.read_bytes()
            how += " + downscaled to %dpx" % int(max_width)
        except Exception as exc:
            path.write_bytes(raw)
            how += " (downscale failed: %s)" % exc
    else:
        path.write_bytes(raw)
    dims = None
    try:
        from PIL import Image
        with Image.open(path) as im:
            dims = list(im.size)
    except Exception:
        pass
    digest = hashlib.sha256(raw).hexdigest()
    _prune_shots()
    _audit_direct("screenshot", "phone:%s sha256=%s" % (path, digest), "ALLOW",
                  "phone screen captured to disk")
    return {"ok": True, "verdict": "ALLOW", "path": str(path), "bytes": len(raw),
            "sha256": digest, "dimensions": dims, "captured_by": how, "serial": serial,
            "note": ("A PATH and a HASH, not an image. You are a coder model; to read what "
                     "is on the screen use phone_ui_text, which returns the real text out "
                     "of uiautomator -- not OCR, not a guess.")}


_UI_TEXT_RE = re.compile(r'text="([^"]*)"')
_UI_DESC_RE = re.compile(r'content-desc="([^"]*)"')
_UI_NODE_RE = re.compile(r'<node[^>]*?text="([^"]*)"[^>]*?bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"')


def ui_text(include_bounds: bool = True) -> dict:
    r"""What the screen SAYS, as text, from `uiautomator dump`.

    This -- not OCR on a JPEG -- is how an assertion about the screen is made honestly.
    uiautomator writes an XML of the whole view hierarchy; every node's `text` and
    `content-desc` is real, and each one carries the rectangle you would tap."""
    detail = "ui_text"
    refused, serial = _guard("screenshot", detail)
    if refused is not None:
        return refused
    remote = "/sdcard/almido_ui.xml"
    rc, out, err = adb_shell(["uiautomator", "dump", remote], ADB_TIMEOUT, serial)
    if rc != 0:
        return _refuse("screenshot", detail, "uiautomator dump failed: %s" % (err or out or rc))
    rc, xml, err = adb_shell(["cat", remote], ADB_TIMEOUT, serial)
    adb_shell(["rm", "-f", remote], ADB_SHORT, serial)
    if rc != 0 or "<hierarchy" not in xml:
        return _refuse("screenshot", detail,
                       "could not read the dump back: %s" % (err or xml[:160]))
    texts = [t for t in _UI_TEXT_RE.findall(xml) if t.strip()]
    descs = [t for t in _UI_DESC_RE.findall(xml) if t.strip()]
    res = {"ok": True, "serial": serial, "texts": texts, "content_desc": descs,
           "all_text": " | ".join(texts), "xml_bytes": len(xml),
           "foreground": foreground(serial).get("package")}
    if include_bounds:
        res["nodes"] = [{"text": m[0],
                         "center": [(int(m[1]) + int(m[3])) // 2, (int(m[2]) + int(m[4])) // 2],
                         "bounds": [int(m[1]), int(m[2]), int(m[3]), int(m[4])]}
                        for m in _UI_NODE_RE.findall(xml) if m[0].strip()]
    _audit_direct("screenshot", "phone:ui_text %d texts" % len(texts), "ALLOW",
                  "read the view hierarchy as text")
    return res


# --- the read-only shell ---------------------------------------------------------------
# An allowlist matched on the leading words. Anything else is put to the gate as a command,
# which means CONFIRM at best -- and CONFIRM stops the hand here.
#
# AUDIO PROTECTION LAW AUDIT (2026-09-11, WAVE A1 review finding #1): `input` -- and so
# `input keyevent <code>` -- is deliberately ABSENT from this allowlist. shell()'s "not
# allowed" branch below never calls _do() (see shell()), so a verb that is not here can
# never reach adb no matter what the gate would have said -- meaning a volume/media/mute/
# call/voice/music/record keycode can never be pressed through this door today. If `input`
# is ever added to _SHELL_ALLOW, key() below (`_audio_law_key_block`) must be applied to
# whatever argument follows `input keyevent` here too, before that branch is allowed to run.
_SHELL_ALLOW = (
    ("dumpsys",),
    ("getprop",),
    ("ls",),
    ("pm", "list"),
    ("pm", "path"),
    ("wm", "size"),
    ("wm", "density"),
    ("settings", "get"),
    ("df",),
    ("uptime",),
)

_SHELL_FORBIDDEN = re.compile(
    r"[;&|><`$]|\brm\b|\bsu\b|\breboot\b|\bpm\s+(uninstall|install|clear|disable|grant|revoke)\b")


def shell(cmd: str) -> dict:
    r"""Run ONE READ-ONLY command on the phone.

    Two fences, both of which must pass:
      1. no shell metacharacter may appear at all -- one command, never a pipeline
      2. the verb must be on the allowlist

    Anything else is handed to the gate as kind='command', where Iddo's own policy decides;
    and because CONFIRM stops the hand in this codebase, in practice that is a refusal with
    a reason rather than a silent execution."""
    line = (cmd or "").strip()
    if not line:
        return _refuse("command", "", "no command given")
    if _SHELL_FORBIDDEN.search(line):
        return _refuse("command", line,
                       "refused: a shell metacharacter or a destructive verb. This door runs "
                       "ONE read-only command, never a pipeline.")
    words = line.split()
    allowed = any(len(words) >= len(pat) and [w.lower() for w in words[:len(pat)]] == list(pat)
                  for pat in _SHELL_ALLOW)
    refused, serial = _guard("command", line)
    if refused is not None:
        return refused
    if not allowed:
        gate = _load()["gate"]
        verdict, reason = gate.gate("command", "phone shell: " + line)
        return {"ok": False, "action": "command", "detail": line, "verdict": verdict,
                "performed": False,
                "reason": ("%r is not on the read-only allowlist (%s). Iddo's policy answered "
                           "%s: %s. Nothing was run."
                           % (words[0], ", ".join(" ".join(p) for p in _SHELL_ALLOW),
                              verdict, reason))}
    return _do("command", line, lambda s: adb_shell(words, ADB_TIMEOUT, s), serial)


# --- the Hebrew question, answered by measurement rather than by hope -------------------
# Every route that could carry a Hebrew letter onto this phone WITHOUT installing an IME.
# None of them is declared to work: the probe runs each one into a field you name and then
# READS THE SCREEN BACK with uiautomator. What the screen says is the answer.
HEBREW_ROUTES = ("input_text", "termux_clipboard", "cmd_clipboard")


def hebrew_probe(expect_app: str, sample: str = "שלום") -> dict:
    r"""Which Hebrew-typing route ACTUALLY lands text in `expect_app`?

    Run this once with a text field focused (Notes, the search box in any app). It tries
    each route in turn and, after each, reads the view hierarchy and asks whether `sample`
    is really on the screen. A route that returns rc=0 and puts nothing on screen is
    reported as a FAILURE, which is the whole point -- `termux-clipboard-set` returns 0
    from the background on Android 10+ and does nothing at all.

    Types nothing until the gate has allowed it, like every other hand here."""
    results = []
    refused, serial = _guard("type", "hebrew_probe " + sample)
    if refused is not None:
        return refused
    refused, _fg = _require_app("type", "hebrew_probe", expect_app, serial)
    if refused is not None:
        return refused

    def _on_screen() -> bool:
        ui = ui_text(include_bounds=False)
        return bool(ui.get("ok")) and sample in (ui.get("all_text") or "")

    for route in HEBREW_ROUTES:
        row = {"route": route}
        if route == "input_text":
            rc, _o, err = adb_shell(["input", "text", _input_text_arg(sample)], ADB_TIMEOUT, serial)
            row.update(rc=rc, error=err or None)
        elif route == "termux_clipboard":
            clip = clipboard_set_via_termux(sample)
            row.update(clipboard=clip)
            if clip.get("ok"):
                rc, _o, err = adb_shell(["input", "keyevent", "279"], ADB_TIMEOUT, serial)
                row.update(rc=rc, error=err or None)
            else:
                row.update(rc=1)
        elif route == "cmd_clipboard":
            # `cmd clipboard` exists on some builds and not others; it is tried, not assumed.
            rc, out, err = adb_shell(["cmd", "clipboard", "set-primary-clip", "--text", sample],
                                     ADB_SHORT, serial)
            row.update(rc=rc, error=(err or out or "").strip()[:160] or None)
            if rc == 0:
                adb_shell(["input", "keyevent", "279"], ADB_TIMEOUT, serial)
        time.sleep(0.8)
        row["landed_on_screen"] = _on_screen()
        results.append(row)
        if row["landed_on_screen"]:
            break

    winner = next((r["route"] for r in results if r.get("landed_on_screen")), None)
    _audit_direct("type", "phone:hebrew_probe winner=%s" % winner, "ALLOW",
                  "measured which Hebrew route lands text")
    return {"ok": winner is not None, "sample": sample, "expect_app": expect_app,
            "winner": winner, "routes": results,
            "note": ("A route is only 'working' if the sample came back out of uiautomator. "
                     "If every route failed, the honest answer is that this phone needs "
                     "ADBKeyboard installed (com.android.adbkeyboard + `ime enable`), and "
                     "that is Iddo's hands, not an agent's.")}


def _cli(argv: list) -> int:
    cmd = (argv[1] if len(argv) > 1 else "status").lower()
    if cmd == "status":
        print(json.dumps(status(), ensure_ascii=False, indent=1, default=str))
    elif cmd == "shot":
        print(json.dumps(screenshot(), ensure_ascii=False, indent=1, default=str))
    elif cmd == "ui":
        print(json.dumps(ui_text(), ensure_ascii=False, indent=1, default=str))
    elif cmd == "open" and len(argv) > 2:
        print(json.dumps(open_app(argv[2]), ensure_ascii=False, indent=1, default=str))
    elif cmd == "home":
        print(json.dumps(home(), ensure_ascii=False, indent=1, default=str))
    else:
        print("usage: almido_phone.py [status|shot|ui|open <pkg>|home]", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli(sys.argv))
