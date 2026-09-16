"""KESHEV presence gate — the guard that asks IS THE OWNER HERE?

Scar 58 (2026-08-15 09:46): with Iddo out of the room, KESHEV typed the
ROOM into his live chat as him — "Welcome to Art Racer.", "Hola, saludos.",
"Let's go." — eight TYPED events in nine seconds, each one a user turn with
Enter. Nothing was broken. Every guard did its job:

  * devices.py  proved the audio came from an authorized USB mic,
  * the energy gate + blip guard + webrtcvad proved it was speech,
  * langpolicy + textguard proved it was not a hallucination,
  * focus.py proved the destination window was allowed.

Not one of them asks whether the person whose name goes on the message was
in the room. focus.py is the authority on WHERE typing may land; this module
is the authority on WHETHER IT MAY HAPPEN AT ALL. They are different
questions and the 09:46 scar is what it costs to have only the first.

`owner_gate_typing` in config is the OTHER half — a voice-identity gate
(criterion 18) that is honestly unbuilt: the switch exists, the machine
behind it does not, and configstore refuses to flip it without a PASS
gate18 report. This module is deliberately NOT that. It needs no model, no
embedding and no network: it reads the OS's own last-input clock. It cannot
tell Iddo's voice from a stranger's — it can only tell whether a human has
touched this machine recently. That is a smaller claim, and it is the claim
that would have stopped 09:46.

TWO LIMITS, NOT ONE — because the two harms are not the same size:

  ENTER_IDLE_LIMIT_S (120 s)  Beyond this, text may still be typed but
                              ENTER NEVER FIRES. Speaking into a chat box
                              is recoverable — he sees it and deletes it.
                              SUBMITTING as him is not. This is the cheap
                              half and it alone downgrades 09:46 from
                              "eight messages sent as Iddo" to "some junk
                              in a text box".

  TYPE_IDLE_LIMIT_S (600 s)   Beyond this nothing is typed at all. Ten
                              minutes of no keyboard and no mouse is not a
                              man dictating; it is an empty room.

Hands-free dictation while he is AT the machine is unaffected: any keypress
or mouse move resets the clock, and normal dictation is punctuated by both.
Dictating from across the room with untouched peripherals degrades to
type-without-Enter after two minutes, which is the correct answer to "I
cannot prove he is here".

FAIL-OPEN ON TYPE, FAIL-CLOSED ON ENTER. If the OS clock cannot be read we
do not know whether he is here. Refusing to type would throw away his words
over a ctypes glitch; pressing Enter would speak as him on an unproven
claim. So an unreadable clock types without Enter and journals
GATE_UNAVAILABLE. Unprovable presence is never permission to act AS him —
but it is also never a reason to lose what he said.

Refusals park the text through the typer (scar 35: divert, never drop) and
emit PRESENCE_REJ / GATE_UNAVAILABLE.

PRESENCE_REJ, not OWNER_REJ. The first cut of this module reused OWNER_REJ
because it was already in the vocabulary — and OWNER_REJ carries
REQUIRED_FIELDS ("score", "theta", "mode", "len_ms"), because it belongs to
the voice-identity gate: a SCORED decision about whose voice this is. This
gate has no score. Emitting it raised TelemetryFieldError the first time it
actually fired, and the unit tests here never saw it because they inject a
fake emitter — only the end-to-end app tests, running the real Telemetry,
caught it. Presence and identity are different questions and now have
different event names.
"""
from __future__ import annotations

import time
from typing import Callable, NamedTuple, Optional

# ------------------------------------------------------------------ limits

ENTER_IDLE_LIMIT_S: float = 120.0    # no Enter beyond two minutes idle
TYPE_IDLE_LIMIT_S: float = 600.0     # no typing at all beyond ten minutes

# Non-fatal reasons the Win32 clock could not be read, recorded rather than
# swallowed (lint gate G1: no silent except — the CUDA_DLL_SKIPPED pattern).
IDLE_API_SKIPPED: list[str] = []

_TICK_WRAP = 1 << 32                 # GetLastInputInfo.dwTime is 32-bit


class Decision(NamedTuple):
    """What the gate permits for ONE utterance."""
    may_type: bool
    may_enter: bool
    idle_s: Optional[float]          # None = clock unreadable
    reason: str                      # "" when fully permitted


# ------------------------------------------------------- real Win32 layer


class Win32IdleApi:
    """GetLastInputInfo boundary — replaceable by deterministic fakes.

    Instantiated lazily so importing this module never touches user32 (the
    server side, lint and the test suite import it freely)."""

    def __init__(self):
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
        """Seconds since the last keyboard or mouse input, or None if the
        OS would not say.

        dwTime is a 32-bit tick that wraps every ~49.7 days while
        GetTickCount64 does not, so the subtraction is done in 32-bit space
        — otherwise one wrap makes the machine look idle for seven weeks and
        the mic goes permanently mute."""
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
        except Exception as exc:                     # never silent (gate G1)
            IDLE_API_SKIPPED.append(f"{type(exc).__name__}: {exc}")
            return None


# ------------------------------------------------------------------- gate


class PresenceGate:
    """The single authority on whether the owner is present enough to act."""

    def __init__(
        self,
        api=None,
        emit: Optional[Callable[..., None]] = None,
        enter_idle_limit_s: float = ENTER_IDLE_LIMIT_S,
        type_idle_limit_s: float = TYPE_IDLE_LIMIT_S,
    ):
        self._api = api if api is not None else Win32IdleApi()
        self._emit = emit
        self.enter_idle_limit_s = float(enter_idle_limit_s)
        self.type_idle_limit_s = float(type_idle_limit_s)
        self._last_idle: Optional[float] = None
        self._last_decision: Optional[Decision] = None

    # ------------------------------------------------------------ reading

    def idle_seconds(self) -> Optional[float]:
        idle = self._api.idle_seconds()
        if idle is not None:
            idle = max(0.0, float(idle))
        self._last_idle = idle
        return idle

    def last_idle(self) -> Optional[float]:
        """Most recent reading, for the tray/window — never recomputed here
        so the picture can never hold a different opinion than the gate."""
        return self._last_idle

    def last_decision(self) -> Optional[Decision]:
        return self._last_decision

    # ----------------------------------------------------------- deciding

    def decide(self) -> Decision:
        """Permit, downgrade, or refuse ONE utterance."""
        idle = self.idle_seconds()

        if idle is None:
            d = Decision(may_type=True, may_enter=False, idle_s=None,
                         reason="presence_unknown")
            if self._emit is not None:
                self._emit("GATE_UNAVAILABLE", gate="presence",
                           reason="idle_clock_unreadable")
            self._last_decision = d
            return d

        if idle >= self.type_idle_limit_s:
            d = Decision(may_type=False, may_enter=False, idle_s=idle,
                         reason="owner_absent")
            if self._emit is not None:
                self._emit("PRESENCE_REJ", reason="owner_absent",
                           idle_s=int(idle))
            self._last_decision = d
            return d

        if idle >= self.enter_idle_limit_s:
            d = Decision(may_type=True, may_enter=False, idle_s=idle,
                         reason="owner_idle_no_enter")
            if self._emit is not None:
                self._emit("PRESENCE_REJ", reason="owner_idle_no_enter",
                           idle_s=int(idle))
            self._last_decision = d
            return d

        d = Decision(may_type=True, may_enter=True, idle_s=idle, reason="")
        self._last_decision = d
        return d


# ------------------------------------------------------------ the arm switch
#
# KESHEV B's one surviving verdict (VERDICT-CLOSED-20260817.md): Qwen's
# physical arming key — "no body, no key press, no typing" — is a STRONGER
# claim than the idle clock above, and it was ruled to live here, INSIDE A,
# as an option layered over the presence gate, defaulting OFF.
#
# The layering, stated once: the ArmSwitch answers "did he DELIBERATELY turn
# typing on?", the PresenceGate answers "is he still around?". When armed
# mode is off (the default, and the shipped state) the switch is transparent
# and KESHEV behaves exactly as before. When on, BOTH must agree: an armed
# mic with an absent owner still refuses Enter after 2 minutes, and a
# present owner with a disarmed mic types nothing at all.
#
# Knobs are CODE under git (design section 5, and configstore's own refusal
# message: "new knobs are code under git, not config") — flipping ARMED_MODE
# is a commit, not a config write.

ARMED_MODE: bool = False                 # the option, default OFF (B verdict)
ARM_HOTKEY: str = "ctrl+alt+a"           # bound only when ARMED_MODE is True
# An arm that never expires re-creates 09:46 exactly — armed in the morning,
# the room typed into his chat in the evening. 0 disables expiry.
ARM_TIMEOUT_S: float = 900.0


class ArmSwitch:
    """The deliberate-consent gate. ARMING is a human act only — toggle()
    and arm() are wired exclusively to the hotkey; no code path in the
    pipeline arms the switch. DISARMING happens two ways: the same hotkey,
    or the timeout expiring (observed lazily inside is_armed(), so there is
    no timer thread to die quietly — the scar-5 family).

    Fail-closed by construction: when enabled, the start state is DISARMED.
    """

    def __init__(self, enabled: bool = ARMED_MODE,
                 timeout_s: float = ARM_TIMEOUT_S,
                 emit: Optional[Callable[..., None]] = None,
                 monotonic: Callable[[], float] = time.monotonic):
        self.enabled = bool(enabled)
        self.timeout_s = float(timeout_s)
        self._emit = emit
        self._mono = monotonic
        self._armed_at: Optional[float] = None   # None = disarmed

    # ----------------------------------------------------------- switching

    def is_armed(self) -> bool:
        """True while armed and unexpired. Expiry is observed lazily, HERE,
        so there is no timer thread to die quietly (the scar-5 family)."""
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
        """The hotkey action. Returns the state it produced."""
        if self.is_armed():
            self.disarm()
            return False
        self.arm()
        return True

    # ------------------------------------------------------------ deciding

    def decide(self) -> Decision:
        """Transparent when disabled; a hard type-refusal when disarmed."""
        if not self.enabled or self.is_armed():
            return Decision(may_type=True, may_enter=True, idle_s=None,
                            reason="")
        if self._emit is not None:
            self._emit("ARM_REJ", reason="disarmed")
        return Decision(may_type=False, may_enter=False, idle_s=None,
                        reason="disarmed")
