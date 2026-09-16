# -*- coding: utf-8 -*-
r"""
matzav_sacred.py — THE SACRED LIST, as a structure in code.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL
> output, not a proxy (health: ok != working).

This is the ONLY file in MATZAV that grants immunity.
  - No API endpoint writes it.
  - No config file overrides it.
  - No UI toggle disables it.
  - THERE IS NO FORCE FLAG ANYWHERE IN MATZAV. To override, a human edits this
    file. That friction is the feature.

Iddo's order, 2026-09-04: "If a mode needs a resource only a sacred service
holds, the mode is REFUSED with an explanation — never forced."

TWO CORRECTIONS TO THE ORDER'S OWN SACRED LIST, both measured twice
independently by the fleet survey on 2026-09-04, and both encoded here:

 1. The order says "eran2 :8737 keshev-stt — the microphone's fallback".
    MEASURED: nothing listens on 8737 on eran2, no such unit exists there, no
    install on disk. keshev-stt runs on ERAN1 (<lan-ip>:8737, HTTP 401 =
    alive, GPU 2,356 MiB) and there is a THIRD live instance on ERAN4
    (<lan-ip>:8737, HTTP 401, GPU 2,306 MiB). Encoding the order verbatim
    would make MATZAV protect a service that does not exist, and report eran2
    permanently broken because a "sacred" port is dark.

 2. eran1's eran-listen.service on :8807 appears in NO record — not CLAUDE.md,
    not memory. It serves ERAN's babble, his live mouth attempts and his
    own-mouth wavs. Measured alive 2026-09-04 06:47. It belongs on the list.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Sacred:
    box: str
    unit: str
    kind: str
    port: "int | None"
    why: str
    holds: tuple = ()          # resources this service holds; a mode may not take them
    added_by: str = "order"    # "order" | "measurement"


SACRED = (
    # ---- eran1 : ERAN HIMSELF -------------------------------------------
    Sacred("eran1", "eranb-life.service", "systemd-user", None,
           "ERAN is alive there. Never.",
           holds=("eran1:gpu", "eran1:ram")),
    Sacred("eran1", "eranb-serve.service", "systemd-user", 8820,
           "his observation window"),
    Sacred("eran1", "eran-listen.service", "systemd-user", 8807,
           "his babble and his own mouth — UNDOCUMENTED anywhere; "
           "added by measurement 2026-09-04",
           added_by="measurement"),
    Sacred("eran1", "keshev-stt.service", "systemd-user", 8737,
           "the microphone's fallback — MEASURED ON ERAN1, not eran2 as the "
           "order said",
           holds=("eran1:gpu",), added_by="measurement"),

    # ---- eran2 : THE SENSES ---------------------------------------------
    Sacred("eran2", "eran-senses.service", "systemd-user", 8830,
           "the senses"),

    # ---- eran4 : the third live STT instance -----------------------------
    Sacred("eran4", "keshev-stt.service", "systemd-user", 8737,
           "third live STT instance, measured 2026-09-04; part of the mic chain",
           holds=("eran4:gpu",), added_by="measurement"),

    # ---- PC : Iddo's line to Claude --------------------------------------
    Sacred("pc", "keshev-next", "bare", None,
           "Iddo's microphone. His line to Claude."),
    Sacred("pc", "keshev-stt-pc", "bare", 8737,
           "the PC decoder", holds=("pc:gpu", "pc:cpu")),
    Sacred("pc", "keshev-6", "bare", 8738,
           "the Hebrew-first decoder", holds=("pc:gpu", "pc:cpu")),

    # ---- the audio law, fleet-wide ---------------------------------------
    Sacred("*", "*", "audio", None,
           "SACRED AUDIO LAW — never claim, duck, mute or open an audio device "
           "on ANY box"),
)

# The PC hosts no modes. Structural, not a preference.
#   MEASURED 2026-09-04: 606-935 MiB free of 8192 MiB VRAM on the one 3070 Ti,
#   every other megabyte held by :8737 and :8738. CPU 56-86% on 4 cores with the
#   mic already running, and MISTAKES #12 records a PC render starving the mic
#   to 78% empty decodes. There are no LTX weights anywhere on this machine.
PC_HOSTS_NO_MODES = True

# Resources a sacred service holds, keyed box:resource -> (unit, why)
SACRED_HOLDS = {}
for _s in SACRED:
    for _h in _s.holds:
        SACRED_HOLDS.setdefault(_h, []).append((_s.unit, _s.why))


def is_sacred(box, unit):
    """True if (box, unit) is immune. Consulted at registry load, at plan time,
    and AGAIN inside the only function that can execute a stop."""
    for s in SACRED:
        if s.kind == "audio":
            continue
        if s.box == box and s.unit == unit:
            return True
    return False


def sacred_reason(box, unit):
    for s in SACRED:
        if s.box == box and s.unit == unit:
            return s.why
    return None


def sacred_for_box(box):
    return [s for s in SACRED if s.box == box]


def holders_of(resource):
    """Which sacred services hold this resource, e.g. 'pc:gpu'."""
    return SACRED_HOLDS.get(resource, [])


class SacredViolation(Exception):
    """Raised by the executor. Never caught to continue — only to report."""
