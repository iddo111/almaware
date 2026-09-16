"""lawbook.py — which capture device MAY open. The Sacred Audio Law as code.

Laws inherited (INSIGHTS §1.5, feedback_usb_mic_only):
- A Bluetooth headset is NEVER a microphone. Opening the WH-1000XM4's mic
  flips it to HFP telephone quality and wrecks Iddo's music. It happened.
  Never again.
- `_NEVER_MIC` is a SOURCE-LEVEL tuple checked before any open, with zero
  merge logic — an emptied config, a malicious allowlist, a clever caller:
  none of them can re-expose Bluetooth. The law outranks every parameter.
- No authorized USB mic present → the app is IDLE, structurally. Idle is a
  correct state, not an error; no fallback exists by design.
- No audio OUTPUT call site exists anywhere in this repo (lint will grep).
"""
from __future__ import annotations

# The law. Not configuration. Test test_lawbook.py asserts these are tuples
# of str at import time and that choose_device consults them regardless of
# arguments.
_NEVER_MIC: tuple[str, ...] = (
    "WH-1000", "Hands-Free", "Headset", "Bluetooth", "AirPods", "BT",
)
ALLOWED_SUBSTRINGS: tuple[str, ...] = ("BRIO", "Scarlett", "USBAudio")


def is_forbidden(name: str) -> bool:
    """True when the law forbids this device, whatever anyone passes in."""
    low = name.casefold()
    return any(bad.casefold() in low for bad in _NEVER_MIC)


def choose_device(device_names: list[str],
                  allowed: tuple[str, ...] = ALLOWED_SUBSTRINGS) -> str | None:
    """First device that is allowed AND not forbidden; None → IDLE_NO_MIC.

    The forbidden check runs FIRST and against the source-level tuple, so a
    caller passing allowed=("WH-1000",) still gets None for a headset — the
    law cannot be argued with from a parameter list.
    """
    for name in device_names:
        if is_forbidden(name):
            continue
        low = name.casefold()
        if any(ok.casefold() in low for ok in allowed):
            return name
    return None
