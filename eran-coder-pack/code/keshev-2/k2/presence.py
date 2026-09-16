"""KESHEV 2 presence + arm — the two gates that answer the 09:46 scar.

Scar 58 (2026-08-15 09:46): Iddo out of the room, a video playing, eight
TYPED events in nine seconds sent into his chat AS HIM, each with Enter.
Every guard passed because every guard answered a different question;
nobody asked whether the person whose name goes on the message was there.

Two gates, two questions, layered (ruling D-003):

  PresenceGate  "has a human touched this machine recently?" — reads the
                OS last-input clock. idle >= enter_limit: type but NEVER
                Enter (junk in a box is recoverable; SUBMITTING as him is
                not). idle >= type_limit: type nothing. Fail-OPEN on type,
                fail-CLOSED on Enter when the clock is unreadable. 32-bit
                tick wrap handled (49.7-day mute otherwise). DEFAULT-ON.

  ArmSwitch     "did he DELIBERATELY turn typing on?" — KESHEV B's one
                surviving verdict, FIRST-CLASS in K2: a schema'd config
                key (armed_mode), its own journal events (ARM_ON/OFF/REJ),
                and a tested combination path. Ships OFF (D-003: armed-
                default would tax 100% of hands-free dictation to defend
                a window the presence gate already fails closed on).
                When ON, BOTH gates must agree. Arms expire (an arm that
                never expires re-creates 09:46); expiry is observed lazily
                inside is_armed() — no timer thread to die quietly.

  combined_decision() is THE function the typer consults — the combination
  logic exists ONCE, here, and has its own tests. may_type = both agree;
  may_enter = both agree. Disarmed speech is parked, never dropped.

Ported from A's client/presence.py (knowledge and code, per Iddo's order
"with all the insights from A"); K2 changes: config-driven limits, the
single combined_decision seam, and PRESENCE_REJ/ARM_REJ kept as distinct
events (the TelemetryFieldError lesson — three gates, three questions,
three names).

stdlib ctypes only, lazily — importing this module never touches user32.
"""
from __future__ import annotations

import time
from typing import Callable, NamedTuple, Optional

# D-003 ruled defaults — config overrides via configstore, restart-only.
ENTER_IDLE_LIMIT_S: float = 120.0
TYPE_IDLE_LIMIT_S: float = 600.0
ARM_TIMEOUT_S: float = 900.0
ARM_HOTKEY: str = "ctrl+alt+a"

# Non-fatal reasons the Win32 clock could not be read — recorded, never
# swallowed (lint gate G1's spirit).
IDLE_API_SKIPPED: list[str] = []

_TICK_WRAP = 1 << 32                  # GetLastInputInfo.dwTime is 32-bit


class Decision(NamedTuple):
    """What the gates permit for ONE utterance."""
    may_type: bool
    may_enter: bool
    idle_s: Optional[float]           # None = clock unreadable / not read
    reason: str                       # "" when fully permitted


class Win32IdleApi:
    """GetLastInputInfo boundary — replaceable by deterministic fakes."""

    def __init__(self) -> None:
        import ctypes
        from ctypes import wintypes

        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = (("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD))

        u = ctypes.WinDLL("user32", use_last_error=True)
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        u.GetLastInputInfo.argtypes = (ctypes.POINTER(LASTINPUTINFO),)
        u.GetLastInputInfo.restype = wintypes.BOOL
        k.GetTickCount64.restype = ctypes.c_ulonglong
        self._ctypes = ctypes
        self._u, self._k = u, k
        self._LASTINPUTINFO = LASTINPUTINFO

    def idle_seconds(self) -> Optional[float]:
        """Seconds since last keyboard/mouse input, None if the OS won't
        say. The subtraction is done in 32-bit space: dwTime wraps every
        ~49.7 days while GetTickCount64 does not — mixing them makes the
        machine look idle for seven weeks and the mic permanently mute."""
        try:
            info = self._LASTINPUTINFO()
            info.cbSize = self._ctypes.sizeof(info)
            if not self._u.GetLastInputInfo(self._ctypes.byref(info)):
                err = self._ctypes.get_last_error()
                IDLE_API_SKIPPED.append(f"GetLastInputInfo failed err={err}")
                return None
            now32 = int(self._k.GetTickCount64()) % _TICK_WRAP
            delta = (now32 - int(info.dwTime)) % _TICK_WRAP
            return delta / 1000.0
        except Exception as exc:              # recorded, never silent
            IDLE_API_SKIPPED.append(f"{type(exc).__name__}: {exc}")
            return None


class PresenceGate:
    """The authority on 'is a human at this machine'. Smaller claim than
    voice identity, and it is the claim that would have stopped 09:46."""

    def __init__(self, api=None, emit: Optional[Callable[..., None]] = None,
                 enter_idle_limit_s: float = ENTER_IDLE_LIMIT_S,
                 type_idle_limit_s: float = TYPE_IDLE_LIMIT_S) -> None:
        self._api = api if api is not None else Win32IdleApi()
        self._emit = emit
        self.enter_idle_limit_s = float(enter_idle_limit_s)
        self.type_idle_limit_s = float(type_idle_limit_s)
        self._last_idle: Optional[float] = None

    def idle_seconds(self) -> Optional[float]:
        idle = self._api.idle_seconds()
        if idle is not None:
            idle = max(0.0, float(idle))
        self._last_idle = idle
        return idle

    def last_idle(self) -> Optional[float]:
        """Most recent reading for the GUI — never recomputed, so the
        picture cannot hold a different opinion than the gate."""
        return self._last_idle

    def decide(self) -> Decision:
        idle = self.idle_seconds()

        if idle is None:
            # fail-open on type, fail-closed on Enter: an unreadable clock
            # must not throw his words away, and must not speak AS him.
            if self._emit is not None:
                self._emit("GATE_UNAVAILABLE", gate="presence",
                           reason="idle_clock_unreadable")
            return Decision(True, False, None, "presence_unknown")

        if idle >= self.type_idle_limit_s:
            if self._emit is not None:
                self._emit("PRESENCE_REJ", reason="owner_absent",
                           idle_s=int(idle))
            return Decision(False, False, idle, "owner_absent")

        if idle >= self.enter_idle_limit_s:
            if self._emit is not None:
                self._emit("PRESENCE_REJ", reason="owner_idle_no_enter",
                           idle_s=int(idle))
            return Decision(True, False, idle, "owner_idle_no_enter")

        return Decision(True, True, idle, "")


class ArmSwitch:
    """Deliberate consent. ARMING is a human act only — arm()/toggle() are
    wired exclusively to the hotkey; no pipeline code arms the switch.
    DISARM: same hotkey, or lazy timeout inside is_armed(). Fail-closed by
    construction: when enabled, the start state is DISARMED."""

    def __init__(self, enabled: bool = False,
                 timeout_s: float = ARM_TIMEOUT_S,
                 emit: Optional[Callable[..., None]] = None,
                 monotonic: Callable[[], float] = time.monotonic) -> None:
        self.enabled = bool(enabled)
        self.timeout_s = float(timeout_s)
        self._emit = emit
        self._mono = monotonic
        self._armed_at: Optional[float] = None

    def is_armed(self) -> bool:
        if self._armed_at is None:
            return False
        if self.timeout_s > 0 and self._mono() - self._armed_at >= self.timeout_s:
            self._armed_at = None
            if self._emit is not None:
                self._emit("ARM_OFF", reason="timeout")
            return False
        return True

    def arm(self) -> None:
        self._armed_at = self._mono()
        if self._emit is not None:
            self._emit("ARM_ON", timeout_s=int(self.timeout_s))

    def disarm(self, reason: str = "hotkey") -> None:
        if self._armed_at is not None:
            self._armed_at = None
            if self._emit is not None:
                self._emit("ARM_OFF", reason=reason)

    def toggle(self) -> bool:
        if self.is_armed():
            self.disarm()
            return False
        self.arm()
        return True

    def decide(self) -> Decision:
        """Transparent when disabled; hard type-refusal when disarmed."""
        if not self.enabled or self.is_armed():
            return Decision(True, True, None, "")
        if self._emit is not None:
            self._emit("ARM_REJ", reason="disarmed")
        return Decision(False, False, None, "disarmed")


def combined_decision(presence: PresenceGate, arm: ArmSwitch) -> Decision:
    """THE seam the typer consults (D-006). Arm first (cheap, no ctypes);
    a disarmed refusal short-circuits — no reason to read the clock for
    text that will not type. Otherwise both must agree per permission.

    Reasons concatenate so the journal/park record names EVERY refusing
    gate, not just the loudest one."""
    a = arm.decide()
    if not a.may_type:
        return a
    p = presence.decide()
    may_type = a.may_type and p.may_type
    may_enter = a.may_enter and p.may_enter
    reason = ";".join(r for r in (a.reason, p.reason) if r)
    return Decision(may_type, may_enter, p.idle_s, reason)
