# app/presence.py
"""
Presence detection module for KESHEV-4D.

Provides:
- IDLE_NO_ENTER_S: seconds of idle after which Enter is disabled.
- IDLE_NO_TYPE_S: seconds of idle after which typing is disabled.
- ARM_TTL_S: time‑to‑live for an armed state.
- Presence: class encapsulating idle and armed logic.
"""

from __future__ import annotations

import time
from typing import Callable, Tuple, Optional

# Constants as mandated by the King's canonical tests
IDLE_NO_ENTER_S: int = 120
IDLE_NO_TYPE_S: int = 600
ARM_TTL_S: int = 900


class Presence:
    """
    Determines whether typing and Enter are permitted based on idle time
    and optional armed mode.

    Parameters
    ----------
    idle_fn : Callable[[], Optional[float]]
        Callable returning the current idle time in seconds, or ``None`` if
        the clock is unreadable.
    armed_mode : bool, optional
        When ``True`` the instance requires explicit arming before any
        action is allowed. Defaults to ``False``.
    """

    __slots__ = ("idle_fn", "armed_mode", "_armed_at")

    def __init__(self, idle_fn: Callable[[], Optional[float]], *, armed_mode: bool = False):
        self.idle_fn: Callable[[], Optional[float]] = idle_fn
        self.armed_mode: bool = armed_mode
        self._armed_at: Optional[float] = None

    # --------------------------------------------------------------------- #
    # Armed‑mode management
    # --------------------------------------------------------------------- #
    def arm(self, *, now: Optional[float] = None) -> None:
        """
        Arm the presence detector. ``now`` can be supplied for deterministic
        testing; otherwise the current monotonic time is used.
        """
        self._armed_at = now if now is not None else time.time()

    def disarm(self) -> None:
        """Immediately disarm the detector."""
        self._armed_at = None

    # --------------------------------------------------------------------- #
    # Verdict computation
    # --------------------------------------------------------------------- #
    def verdict(self, *, now: Optional[float] = None) -> Tuple[bool, bool, str]:
        """
        Return a tuple ``(type_allowed, enter_allowed, reason)``.

        * ``type_allowed`` – whether typing is permitted.
        * ``enter_allowed`` – whether the Enter key is permitted.
        * ``reason`` – a short string explaining the decision.

        The logic follows the King's specifications.
        """
        # Armed‑mode overrides idle logic
        if self.armed_mode:
            if self._armed_at is None:
                return False, False, "arm_required"
            current = now if now is not None else time.time()
            if current - self._armed_at < ARM_TTL_S:
                return True, True, "armed"
            # TTL expired – treat as un‑armed
            return False, False, "arm_required"

        # Non‑armed (or after TTL expiry) – evaluate idle time
        idle = self.idle_fn()
        if idle is None:
            # Clock unreadable – typing allowed, Enter blocked
            return True, False, "clock_unreadable"

        if idle >= IDLE_NO_TYPE_S:
            return False, False, "idle_no_type"
        if idle >= IDLE_NO_ENTER_S:
            return True, False, "idle_no_enter"
        return True, True, "ok"
