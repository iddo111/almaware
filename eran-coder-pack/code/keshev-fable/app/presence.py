"""presence.py — is the person whose name goes on the message THERE.

Laws inherited (INSIGHTS §3 — the 09:46 scar; keshev-2 D-003):
- Two limits because the harms differ:
    idle ≥ IDLE_NO_ENTER_S (120)  → type, but NEVER Enter. Junk in a box is
                                     recoverable; SUBMITTING as him is not.
    idle ≥ IDLE_NO_TYPE_S  (600)  → type nothing; park the speech.
- Fail-open on type, fail-closed on Enter when the idle clock is unreadable.
- 32-bit tick wrap handled (GetTickCount wraps at 49.7 days — the wrap once
  meant a permanent mute).
- The ARM switch (B's one surviving idea) layers OVER this gate, never
  replaces it; ARMED_MODE default False (keshev-2 D-001). An arm expires:
  an arm that never expires re-creates 09:46 with extra steps.
- Three verdicts, three journal names: PRESENCE_REJ / ARM_REJ are distinct.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

IDLE_NO_ENTER_S: int = 120
IDLE_NO_TYPE_S: int = 600
ARM_TTL_S: int = 900            # keshev-2 D-003: presence 120/600/900

ARMED_MODE: bool = False        # D-001: opt-in, never default


def _idle_seconds_windows() -> float | None:
    """OS last-input clock via GetLastInputInfo. None = unreadable."""
    try:
        import ctypes

        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_uint),
                        ("dwTime", ctypes.c_uint)]

        info = LASTINPUTINFO()
        info.cbSize = ctypes.sizeof(info)
        if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
            return None
        now = ctypes.windll.kernel32.GetTickCount()  # 32-bit, wraps 49.7d
        delta = (now - info.dwTime) & 0xFFFFFFFF     # wrap-safe subtraction
        return delta / 1000.0
    except Exception:  # noqa: BLE001 — unreadable clock is a defined state
        return None


@dataclass
class Presence:
    """The gate. idle_fn is injectable so tests never need a real desktop."""
    idle_fn: object = _idle_seconds_windows
    armed_mode: bool = ARMED_MODE
    _armed_at: float | None = field(default=None, init=False)

    # ---------------------------------------------------------------- arm --
    def arm(self, now: float | None = None) -> None:
        self._armed_at = time.monotonic() if now is None else now

    def disarm(self) -> None:
        self._armed_at = None

    def is_armed(self, now: float | None = None) -> bool:
        if self._armed_at is None:
            return False
        t = time.monotonic() if now is None else now
        if t - self._armed_at > ARM_TTL_S:
            self._armed_at = None       # expiry IS the safety property
            return False
        return True

    # ------------------------------------------------------------ verdict --
    def verdict(self, now: float | None = None) -> tuple[bool, bool, str]:
        """(may_type, may_enter, reason).

        reason ∈ ok | idle_no_enter | idle_no_type | clock_unreadable |
                 arm_required | armed
        """
        if self.armed_mode:
            # B's stronger claim: no body, no key press, no typing.
            if self.is_armed(now):
                return True, True, "armed"
            return False, False, "arm_required"

        idle = self.idle_fn() if callable(self.idle_fn) else None
        if idle is None:
            # fail-open on type, fail-closed on Enter
            return True, False, "clock_unreadable"
        if idle >= IDLE_NO_TYPE_S:
            return False, False, "idle_no_type"
        if idle >= IDLE_NO_ENTER_S:
            return True, False, "idle_no_enter"
        return True, True, "ok"
