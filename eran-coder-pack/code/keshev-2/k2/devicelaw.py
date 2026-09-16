"""KESHEV 2 device law — USB wired mics ONLY, structural IDLE_NO_MIC.

SACRED AUDIO LAW (חוק השמע הקדוש, 2026-08-09): a Bluetooth headset mic
flips A2DP->HFP and wrecks Iddo's music. It happened; never again. The law
lives ABOVE the config layer:

  scar 21   `_NEVER_MIC` is a SOURCE-LEVEL tuple checked before any
            probe/open, unconditionally, with NO merge logic. On
            2026-08-06 a config write emptied alma-mic's avoid-list and
            removed all Bluetooth protection for eleven days; a config
            cannot empty a tuple. The config-layer deny-list is purely
            ADDITIVE-cosmetic: `is_forbidden` consults the tuple FIRST and
            an `extra` list can only add denials, structurally never
            subtract.
  scar 21   If no allowed mic is live: IDLE, honestly announced — no
            fallback, ever. `select()` returns state IDLE_NO_MIC; there is
            no code path from "no USB mic" to "open something else".
  scar 22   No audio OUTPUT call site exists in this repo (lint gate G6
            greps for it; G2 blocks capture imports entirely tonight).

THIS MODULE OPENS NOTHING. It is pure name-classification law: no
sounddevice, no pyaudio, no ctypes into any audio API. KESHEV A holds the
BRIO tonight and until KESHEV 2 beats the acceptance baseline; the capture
module that will someday consume `Selection` does not exist yet, and the
interlock (k2/interlock.py) guards the day it does.

stdlib only, pure functions — every rule reachable by tests.
"""
from __future__ import annotations

from typing import Iterable, NamedTuple

# ------------------------------------------------------------- the tuple
# Source-level. A config write CANNOT touch this. Kept superset of A's and
# of voice-input's never_use_devices, plus virtual-device families the
# 4D device-case council surfaced (see WORKERS-LOG.md).

_NEVER_MIC: tuple[str, ...] = (
    # Bluetooth / telephony profiles — the A2DP->HFP scar itself
    "bluetooth", "hands-free", "handsfree", "headset", "wh-1000xm4",
    "a2dp", "hfp", "airpods", "bt audio", "ag audio",
    # loopback / virtual capture — never a human voice
    # ("audio relay" WITH the space: the 4D device-case draft (glm) listed
    #  'Audio Relay' and the one-word marker missed it — a real catch.)
    "stereo mix", "loopback", "virtual", "audiorelay", "audio relay",
    "sound mapper",
    "primary sound capture", "what u hear", "wave out mix",
    "vb-audio", "voicemeeter", "cable output", "obs", "steam streaming",
    "nvidia broadcast", "droidcam",
)

# Devices we affirmatively know are Iddo's wired USB mics. An allowlist
# match is REQUIRED for auto-selection: an unknown name is never opened
# automatically (it may be tomorrow's virtual device wearing a new name).
_ALLOWED_USB: tuple[str, ...] = (
    "brio", "logi 4k", "logitech", "scarlett", "focusrite",
    "usb audio device", "usb microphone",
)

IDLE_NO_MIC = "IDLE_NO_MIC"


class Selection(NamedTuple):
    """The outcome of device selection. `state` is honest: SELECTED with a
    name, or IDLE_NO_MIC with the reasons every candidate was refused."""
    state: str                       # "SELECTED" | IDLE_NO_MIC
    device: str | None               # the chosen name, or None
    refused: tuple[tuple[str, str], ...]   # (name, reason) per rejected


def is_forbidden(name: str, extra: Iterable[str] = ()) -> str | None:
    """Return the matching deny-marker, or None if the name is clean.

    THE ORDER IS THE LAW: the source tuple is consulted first and
    unconditionally; `extra` (config additions) can only extend the
    denials. There is no parameter that skips or filters the tuple."""
    lowered = name.lower()
    for marker in _NEVER_MIC:
        if marker in lowered:
            return marker
    for marker in extra:
        m = str(marker).lower().strip()
        if m and m in lowered:
            return m
    return None


def is_allowed_usb(name: str) -> bool:
    """Affirmative allowlist match. NOT the inverse of is_forbidden:
    a name must be BOTH not-forbidden AND recognized to be auto-opened."""
    lowered = name.lower()
    return any(marker in lowered for marker in _ALLOWED_USB)


def classify(name: str, extra: Iterable[str] = ()) -> str:
    """FORBIDDEN | ALLOWED | UNKNOWN. Forbidden wins over allowed —
    'Headset (WH-1000XM4 Hands-Free AG Audio)' contains no allow marker,
    but even a name matching both lists is FORBIDDEN (the tuple outranks
    everything, including our own allowlist)."""
    if is_forbidden(name, extra) is not None:
        return "FORBIDDEN"
    if is_allowed_usb(name):
        return "ALLOWED"
    return "UNKNOWN"


def select(candidates: Iterable[str], extra: Iterable[str] = (),
           chosen: str | None = None) -> Selection:
    """Pick the mic KESHEV 2 may use, or refuse honestly.

    * `chosen` (an explicit user pick) wins unconditionally over ranking —
      scar 23 — but NEVER over the tuple: an explicit pick that matches
      `_NEVER_MIC` is refused like any other name. The user cannot consent
      to the Bluetooth trap; that is what "law" means here.
    * Otherwise the first ALLOWED candidate in listing order wins.
    * UNKNOWN names are never auto-opened; they are refused with reason
      "unrecognized" and appear in `refused` so the honest journal / GUI
      can show WHY the mic is idle.
    * No allowed candidate -> IDLE_NO_MIC. There is no fallback branch."""
    refused: list[tuple[str, str]] = []

    if chosen is not None:
        marker = is_forbidden(chosen, extra)
        if marker is not None:
            refused.append((chosen, f"never_mic:{marker}"))
            return Selection(IDLE_NO_MIC, None, tuple(refused))
        return Selection("SELECTED", chosen, ())

    for name in candidates:
        marker = is_forbidden(name, extra)
        if marker is not None:
            refused.append((name, f"never_mic:{marker}"))
            continue
        if not is_allowed_usb(name):
            refused.append((name, "unrecognized"))
            continue
        return Selection("SELECTED", name, tuple(refused))

    return Selection(IDLE_NO_MIC, None, tuple(refused))


def never_mic_markers() -> tuple[str, ...]:
    """Read-only view for the GUI/acceptance report. Returns the tuple
    itself — immutable by construction."""
    return _NEVER_MIC
