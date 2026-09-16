"""KESHEV device law — K6 (PHASE2-DESIGN.md section 2; PHASE1-INQUIRY.md
section 2.D, scars 21-25 — SACRED AUDIO, non-negotiable).

The laws enforced here, each mapped to its scar:

  scar 21  `_NEVER_MIC` below is the SOLE authority. It is a source-level
           tuple pinned by the design (an implementation may not
           under-populate it) and is checked unconditionally, BEFORE any
           probe or open, by `forbidden_match()` — a function that takes
           ONLY the device name. No config object can reach that check:
           there is no merge logic, no parameter to pass one, nothing to
           empty. The config `extra_avoid` list is consulted in a separate,
           later, ADDITIVE-only step and can only demote allowed devices —
           it can never re-expose a forbidden one (the 2026-08-06 hole,
           closed structurally). If no allowed mic exists the answer is
           IDLE_NO_MIC, honestly announced — never a fallback.
  scar 22  This module is capture-only. There is no output-endpoint code
           path (lint gate G6 enforces repo-wide); `device_open_audit()`
           asserts zero audio-OUTPUT endpoints are ever held.
  scar 23  Host APIs ranked WASAPI > DirectSound > WDM-KS; MME is never
           opened (silent for USB mics). Liveness is proven by an RMS probe
           (floor 0.0008) for AUTO-PICK ranking only — an explicitly pinned
           mic wins unconditionally and is never probe-gated, and the probe
           is evidence, never a veto. Same-PHYSICAL-mic fallback chain
           across host APIs; transient open errors ("Unanticipated host
           error") retried 3x with 0.4s sleep before moving down the chain.

No PortAudio at module level: enumeration/probing/opening are injected
callables, so every K6 test runs against fakes and no real device is ever
touched before the K5-gated live phase.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Sequence

# ---------------------------------------------------------------- scar 21
# THE tuple. SOLE authority. Pinned verbatim by PHASE2-DESIGN.md section 2 —
# do not remove entries; additions require a design-doc change under git.

_BT_HEADSET_FORBIDDEN = (
    "bluetooth",
    "hands-free",
    "headset",
    "wh-1000xm4",
    "a2dp",
    "hfp",
    "airpods",
)

_LOOPBACK_FORBIDDEN = (
    "stereo mix",
    "loopback",
    "virtual",
    "audiorelay",
    "sound mapper",
    "primary sound capture",
)

_NEVER_MIC: tuple[str, ...] = _BT_HEADSET_FORBIDDEN + _LOOPBACK_FORBIDDEN


def forbidden_match(name: str) -> str | None:
    """The scar-21 check. Takes ONLY the device name — by construction no
    config input exists. Returns the matched forbidden token, else None."""
    lowered = name.lower()
    for token in _NEVER_MIC:
        if token in lowered:
            return token
    return None


# ---------------------------------------------------------------- scar 23 constants

RMS_LIVENESS_FLOOR = 0.0008   # scar 23: liveness evidence floor over 0.5s
OPEN_RETRIES = 3              # scar 23: transient-open retries per device
OPEN_RETRY_SLEEP_S = 0.4      # scar 23: sleep between transient retries

# WASAPI > DirectSound > WDM-KS. MME is deliberately ABSENT: a host API with
# no rank is never probed, never chained, never opened.
_HOSTAPI_RANK = {"wasapi": 0, "directsound": 1, "wdm-ks": 2}


def _hostapi_rank(hostapi: str) -> int | None:
    lowered = hostapi.lower()
    if "mme" in lowered.split():  # "MME" exact-ish; never openable
        return None
    for token, rank in _HOSTAPI_RANK.items():
        if token in lowered:
            return rank
    return None  # unknown host API: not openable — evidence over hope


# ---------------------------------------------------------------- types

@dataclass(frozen=True)
class DeviceInfo:
    """One enumerated capture endpoint (fake in tests, PortAudio row live)."""
    index: int
    name: str
    hostapi: str
    max_input_channels: int
    max_output_channels: int = 0


class SacredAudioViolation(Exception):
    """A forbidden device reached an open path, or an OUTPUT endpoint is
    held. This exception is a hard stop, never caught-and-continued."""


class TransientDeviceError(Exception):
    """Open failure worth retrying (scar 23: 'Unanticipated host error')."""


class DeviceOpenError(Exception):
    """The whole fallback chain failed to open. Loud, journaled by caller."""


@dataclass
class Selection:
    """The honest result of device resolution."""
    SELECTED = "SELECTED"
    IDLE_NO_MIC = "IDLE_NO_MIC"

    state: str
    device: DeviceInfo | None
    chain: list[DeviceInfo] = field(default_factory=list)
    refused: list[tuple[str, str]] = field(default_factory=list)  # (name, token)
    pin_honored: bool = False
    announcement: str = ""


# ---------------------------------------------------------------- helpers

def _physical_key(name: str) -> str:
    """Same-physical-mic grouping key: PortAudio truncates/wraps the same
    endpoint name differently per host API; normalize conservatively."""
    return " ".join(name.lower().split())


def _idle(refused: list[tuple[str, str]]) -> Selection:
    refused_txt = "; ".join(f"{n} [{t}]" for n, t in refused) or "none present"
    announcement = (
        "KESHEV: IDLE-NO-MIC — no allowed USB microphone is available. "
        f"Refused by device law: {refused_txt}. "
        "There is NO fallback to Bluetooth/headset/virtual devices, ever "
        "(Sacred Audio, scar 21). | "
        "קשב: אין מיקרופון מורשה — נשארים ב-IDLE, בלי שום fallback לאוזניות "
        "או התקן וירטואלי. חברו מיקרופון USB (BRIO/Scarlett)."
    )
    return Selection(state=Selection.IDLE_NO_MIC, device=None,
                     refused=refused, announcement=announcement)


# ---------------------------------------------------------------- selection

def select_device(all_devices: Iterable[DeviceInfo],
                  *,
                  pinned: str | None = None,
                  extra_avoid: Sequence[str] = (),
                  rms_probe: Callable[[DeviceInfo], float] | None = None,
                  ) -> Selection:
    """Resolve the capture device. Order of law:

      1. input-capable endpoints only (capture-only module, scar 22);
      2. `_NEVER_MIC` unconditional refusal — before pin, before probe,
         before extra_avoid, with no config input (scar 21);
      3. host-API rank filter — MME/unknown never openable (scar 23);
      4. pinned mic, if present among ALLOWED devices, wins un-probed;
      5. auto-pick: extra_avoid soft demotion, then RMS-probe liveness as
         ranking evidence (never a veto), then host-API rank;
      6. nothing allowed -> IDLE_NO_MIC, honestly announced, no fallback.
    """
    refused: list[tuple[str, str]] = []
    allowed: list[DeviceInfo] = []

    for d in all_devices:
        if d.max_input_channels <= 0:
            continue
        token = forbidden_match(d.name)   # scar 21: FIRST, unconditional
        if token is not None:
            refused.append((d.name, token))
            continue
        if _hostapi_rank(d.hostapi) is None:
            continue                      # MME/unknown: never opened (scar 23)
        allowed.append(d)

    if not allowed:
        return _idle(refused)

    def chain_for(physical: str) -> list[DeviceInfo]:
        group = [d for d in allowed if _physical_key(d.name) == physical]
        group.sort(key=lambda d: _hostapi_rank(d.hostapi))
        return group

    # ---- pinned mic: wins unconditionally, never probe-gated (scar 23)
    if pinned:
        pin = pinned.lower().strip()
        pin_matches = [d for d in allowed if pin in d.name.lower()]
        if pin_matches:
            chain = chain_for(_physical_key(pin_matches[0].name))
            return Selection(state=Selection.SELECTED, device=chain[0],
                             chain=chain, refused=refused, pin_honored=True)
        # pin unsatisfiable among allowed devices (absent, or it named a
        # forbidden device — the tuple already refused it above): fall
        # through to auto-pick; never IDLE while an allowed mic exists.

    # ---- auto-pick
    avoid_tokens = tuple(a.lower() for a in extra_avoid if isinstance(a, str) and a.strip())

    def avoided(d: DeviceInfo) -> bool:
        # additive-COSMETIC soft demotion only — never consulted above (scar 21)
        return any(t in d.name.lower() for t in avoid_tokens)

    live: dict[int, bool] = {}
    if rms_probe is not None:
        for d in allowed:
            live[d.index] = rms_probe(d) >= RMS_LIVENESS_FLOOR

    def sort_key(d: DeviceInfo):
        return (avoided(d),                       # non-avoided first
                not live.get(d.index, True),      # probed-live first (evidence, not veto)
                _hostapi_rank(d.hostapi),         # WASAPI > DS > WDM-KS
                d.index)

    best = min(allowed, key=sort_key)
    chain = chain_for(_physical_key(best.name))
    return Selection(state=Selection.SELECTED, device=best,
                     chain=chain, refused=refused, pin_honored=False)


# ---------------------------------------------------------------- open (scar 23)

def open_with_retry(open_fn: Callable[[DeviceInfo], Any],
                    chain: Sequence[DeviceInfo],
                    *,
                    retries: int = OPEN_RETRIES,
                    sleep_s: float = OPEN_RETRY_SLEEP_S,
                    sleep_fn: Callable[[float], None] = time.sleep,
                    ) -> tuple[Any, DeviceInfo]:
    """Open the first device in the same-physical-mic chain that succeeds.

    Transient errors (scar 23's 'Unanticipated host error' class, surfaced
    as TransientDeviceError) are retried `retries` times with `sleep_s`
    between attempts; any other failure moves down the chain immediately.
    Defense in depth: a forbidden device in the chain is a hard
    SacredAudioViolation — it never reaches open_fn.
    """
    failures: list[str] = []
    for device in chain:
        token = forbidden_match(device.name)  # unconditional, even here
        if token is not None:
            raise SacredAudioViolation(
                f"refusing to open {device.name!r}: matches _NEVER_MIC token "
                f"{token!r} (scar 21) — a forbidden device reached the open layer")
        for attempt in range(1, retries + 1):
            try:
                return open_fn(device), device
            except TransientDeviceError as e:
                failures.append(f"{device.name} [{device.hostapi}] "
                                f"attempt {attempt}/{retries}: transient {e}")
                if attempt < retries:
                    sleep_fn(sleep_s)
            except Exception as e:  # non-transient: next device in the chain
                failures.append(f"{device.name} [{device.hostapi}]: {e}")
                break
    raise DeviceOpenError(
        "every device in the fallback chain failed to open: " + "; ".join(failures))


# ---------------------------------------------------------------- audit (scar 22)

def device_open_audit(open_handles: Iterable[Any]) -> None:
    """Assert the process holds ZERO audio-OUTPUT endpoints (scar 22).

    Each handle must expose `.kind` ("capture" | "output") and `.name`.
    Called by selftest.py (criteria 14/23), the K17 soak, and mic-switch
    status. Any output endpoint is a SacredAudioViolation — no exceptions.
    """
    violations = [getattr(h, "name", "<unnamed>") for h in open_handles
                  if getattr(h, "kind", None) != "capture"]
    if violations:
        raise SacredAudioViolation(
            "audio-OUTPUT endpoint(s) held by a KESHEV process — Sacred Audio "
            f"violation (scar 22): {violations}")
