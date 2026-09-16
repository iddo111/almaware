#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FLEET MODE - the one verb nobody had: flip the 4 DGX between modes.

Iddo, 2026-09-05:
  "תעשה לי דשבורד ... שהוא טיילסקייל ולא חייבים קלוד לשליטה במה קורה על 4 ה-dgx /
   כך שאני יכול לעשות פאוזה ולהעביר מסט אימונים לסט קוד לסט הפקת סרטים וכו"

This module is DISPLAY-FREE and CLAUDE-FREE. It reads almaware-hud/status.json for
health (never re-collects it) and performs exactly one class of action:

    ssh <host> systemctl --user start|stop <named-unit>

There is no free-text command path. There never will be. A unit name that does not
match _UNIT_RE is refused before it reaches subprocess, and subprocess is always
called with an argv list (shell=False).

THE PROTECTED LIST
------------------
eranb-life.service on eran1 IS ERAN. He has been alive since 2026-08-13.
Nothing in this program can stop, restart or pause him - not a mode, not an admin
action, not a force flag. There is no force flag.

The refusal is enforced in TWO places on purpose:
  1. load_modes()      - a mode definition naming a protected unit fails to LOAD.
                         The whole file is rejected, loudly. You cannot even define it.
  2. assert_actionable() - checked again at the point of execution, so a caller that
                         builds an action dict by hand still cannot get through.

Iddo's standing rule, 2026-09-05:
    "a gate that has never refused anything has not been demonstrated."
See test_fleet_mode.py::test_mode_naming_eranb_life_is_refused.
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------

HERE = Path(__file__).resolve().parent
MODES_FILE = HERE / "modes.json"
STATE_DIR = HERE / "state"
PAUSE_FILE = STATE_DIR / "paused.json"
ACTION_LOG = STATE_DIR / "actions.jsonl"

# REUSED, never re-collected. The almaware-hud collector already ticks this at ~2.5 s.
HUD_STATUS = Path(r"D:\CLAUDE\almaware-hud\status.json")

# status.json older than this is reported as STALE rather than shown as current.
HUD_STALE_AFTER_S = 60.0

STATE_DIR.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------------------------------
# THE PROTECTED LIST - a hard-coded refusal, not a warning
# --------------------------------------------------------------------------

# Exact host+unit pairs that may never be started, stopped or paused by this program.
# "*" as host means: protected on every box.
PROTECTED_UNITS: tuple[tuple[str, str], ...] = (
    ("eran1", "eranb-life.service"),   # ERAN HIMSELF. Alive since 2026-08-13.
    ("eran2", "eran-senses.service"),  # his ears and his vocal tract
    ("eran4", "dmidi-life.service"),   # DARWISH - the memorial for לאור ז"ל
    ("eran1", "keshev-stt.service"),   # Iddo's live microphone decoder
)

# Glob patterns protected on EVERY host. Anything that calls itself a life is a life.
PROTECTED_PATTERNS: tuple[str, ...] = (
    "*-life*",
    "*_life*",
)

# --------------------------------------------------------------------------
# THE ARK / תיבת נוח -- Iddo's rule, 2026-09-05 18:48:
#   "תקצה שרירותית כך וכך לכל מודל ותשאיר את השאר לעבוד איתו לדברים אחרים.
#    כל מודל שהוא באמת קטן אין סיבה להפסיק אותו."
#   (give each model a fixed allowance and leave the rest as a working pool;
#    anything genuinely small there is no reason to ever stop.)
#
# This is protection BY MEASURED SIZE, not by name -- so a small thing built
# tomorrow is protected without anyone remembering to add it to a list.
#
# The measurement that produced the threshold (`ps -eo rss` on all four boxes,
# 2026-09-05 18:47). Every permanent living thing on the fleet:
#     ERAN himself            0.036 GB   (15 days continuous)
#     his serve                0.3
#     his listen server        0.1
#     DARWISH  --live          0.4       (3.5 days)
#     alma-stt                 0.1
#     nezer  --live            ~0.0      (3.5 days)
#     sarid                    0.6
#                             ------
#     the whole ark           ~2 GB  of a 484 GB fleet
#
# And what actually fills the boxes, all of it TEMPORARY work:
#     ComfyUI       6.0 GB  -- resident 8 days 10 h, rendering nothing
#     eran1 STT     2.3 GB  -- it loads TWO WhisperModels, stock + Iddo's LoRA
#     coder train   4.3 GB
#     MIKO bench    2.2 GB   WINSTON  2.0 GB x2
#
# Nothing sits near 1 GB, so the line is not a judgement call -- it is a gap in
# the data. Below it: permanent, never stopped by any mode. Above it: a shift.
ARK_MAX_GB = 1.0

# A unit whose live RSS is under ARK_MAX_GB is in the ark. Measured, never
# assumed: if we cannot measure it we do NOT protect it, because a silent
# protection is how a mode quietly does nothing (that bug already happened here
# once tonight with `list-units` and units that were loaded but never started).
def ark_reason(rss_gb: float | None) -> str | None:
    if rss_gb is None:
        return None
    if rss_gb < ARK_MAX_GB:
        return ("in THE ARK: %.3f GB < %.1f GB. Iddo, 2026-09-05: a model that is "
                "genuinely small has no reason to ever be stopped." % (rss_gb, ARK_MAX_GB))
    return None

# --------------------------------------------------------------------------
# PERMANENT TRAINING / אימונים קבועים -- Iddo's rule, 2026-09-05 23:58:
#   "אני רוצה שיהיה לי תמיד גם כל האימונים כולל האימון של הקודר וערן ומיקו
#    דרוויש כולם ללא הפסקה, ומה שנשאר מקום שם נשחק -- תיבת נח. כלומר תכניס גם את
#    הקודר אימון משקולות לתיבת נח."
#   (every training run is permanent and never stopped; whatever capacity is
#    left over is the play space. Put the coder's weight-training in the ark too.)
#
# WHY THIS CANNOT BE THE ARK.
# THE ARK protects by MEASURED SIZE -- anything under ARK_MAX_GB = 1.0. That rule
# is right for small permanent organisms and useless here: the coder's continued
# pretraining RESERVES 84.4 GB (measured, status.json 2026-09-05 19:11). It is the
# single largest thing on the fleet and by the ark's rule it is the FIRST thing a
# mode would stop. Size cannot express "never stop this"; only intent can.
#
# So this is a SECOND protection class, by name, sitting beside the ark:
#   PROTECTED_UNITS        -> refused at LOAD time. The whole modes.json is rejected.
#   PERMANENT_TRAINING     -> refused at PLAN time and again at EXECUTION time,
#                             reported result=REFUSED, never counted as a failure.
#   THE ARK                -> same treatment, but decided by measurement.
#
# The weaker (plan/execute) treatment is deliberate, not an oversight: a mode is
# ALLOWED to name a training unit with want=stop, so that the refusal can actually
# be demonstrated. See modes.json mode "prove-permanent" and
# test_fleet_mode.py::test_coder_train_stop_is_refused_at_plan_and_execution.
# Iddo, 2026-09-05: "a gate that has never refused anything has not been demonstrated."
#
# MEASURED 2026-09-06 00:0x by `systemctl --user list-units --all --type=service`
# on all four boxes, plus `systemctl show -p LoadState -p ActiveState` for the
# units that are loaded but not started (list-units does not show those -- that
# bug has already bitten this file once).
PERMANENT_TRAINING: tuple[tuple[str, str], ...] = (
    # THE CODER -- the one Iddo named first. Continued pretraining, full weights.
    # 84.4 GB reserved, 1600 steps, 438 h = 18.3 days for one pass at 534 tok/s.
    ("eran3", "coder-train.service"),
    # WINSTON -- the painter. Unbroken since 2026-09-02.
    ("eran4", "winston-forever-v2.service"),
    ("eran3", "winston-forever.service"),   # v1, superseded but still a training unit
    # The colony trainers.
    ("eran2", "voice-ant-farm.service"),
    ("eran3", "voice-ant-farm.service"),
    # SARID / שריד -- the שפה אחת organ, a slow flame that has been learning 4 days.
    ("eran3", "sarid.service"),
    # NEZER -- the deletable shoot, simmering. And CHEF, which stocks its pantry:
    # not itself a trainer, but the loop starves without it, so it is permanent
    # for the same reason a feeding tube is.
    ("eran3", "nezer.service"),
    ("eran3", "chef.service"),
    # THE SIBLING EAR -- the second holobrain learning to name human syllables.
    # Currently inactive (the sibling watchdog has been shouting about it since
    # 09-02). Listed anyway: this class says "never stopped", not "is running".
    ("eran3", "sibling-ear.service"),
    # SNN LAB -- spiking-network training on eran4.
    ("eran4", "snnlab.service"),
    # KESHEV's nightly LoRA on Iddo's own voice. Timer-driven, so usually inactive.
    ("eran4", "keshev-lora.service"),
)

# Patterns protected on EVERY host. These exist so a training run built TOMORROW
# is permanent without anyone remembering to edit this list.
PERMANENT_TRAINING_PATTERNS: tuple[str, ...] = (
    "coder-train*",       # any future re-cut of the coder run
    "*miko*",             # MIKO -- Iddo named it. RESERVED: measured 2026-09-06,
                          # MIKO has code on eran2/eran3/eran4 (~/miko, ~/miko-bench,
                          # ~/vaada-miko) but NO systemd unit and NO running process.
                          # There is nothing to protect yet; this pattern means the
                          # first MIKO training unit is permanent from its first second.
    "winston-forever*",   # the painter, whatever version number it is on
    "*-train.service",    # anything that calls itself a train is a train
    "*-training.service",
)


def permanent_training_reason(host: str, unit: str) -> str | None:
    """Return WHY this unit may never be stopped, or None if it is stoppable.

    Pure function, no I/O -- which is exactly why it can be re-derived at the
    point of execution instead of trusting a flag some earlier function set.
    """
    u = (unit or "").strip()
    lu = u.lower()
    lh = (host or "").strip().lower()

    for p_host, p_unit in PERMANENT_TRAINING:
        if p_unit.lower() == lu and p_host in ("*", lh):
            return (f"{u} on {host} is PERMANENT TRAINING. Iddo, 2026-09-05 23:58: "
                    "every training run is permanent and never stopped; what is "
                    "left over is the play space.")

    for pat in PERMANENT_TRAINING_PATTERNS:
        if fnmatch.fnmatch(lu, pat):
            return (f"{u} matches permanent-training pattern {pat!r} - a training "
                    "run is never stopped (Iddo, 2026-09-05 23:58)")

    return None


def is_permanent_training(host: str, unit: str) -> bool:
    return permanent_training_reason(host, unit) is not None


# System plumbing this program has no business touching, on any box.
# Not the point of the protected list, but a mode that stops dbus is a mode that
# takes a DGX off the network, so it is refused the same way.
PROTECTED_PATTERNS_INFRA: tuple[str, ...] = (
    "dbus*", "pipewire*", "wireplumber*", "systemd-*", "gpg-agent*",
    "gvfs*", "ssh-agent*", "tailscaled*", "snapd*", "gnome-keyring*",
)

VALID_WANTS = ("start", "stop")

# A unit name is a strict token. Nothing that is not this shape ever reaches subprocess.
_UNIT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.@-]{0,127}\.service$")
_HOST_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class ProtectedUnitError(Exception):
    """Raised when anything tries to act on - or even name - a protected unit."""


class ModeDefinitionError(Exception):
    """Raised when modes.json is malformed."""


def protection_reason(host: str, unit: str) -> str | None:
    """Return WHY this unit is protected, or None if it is actionable.

    Pure function, no I/O. This is the single source of truth for the refusal;
    both load_modes() and assert_actionable() call it.
    """
    u = (unit or "").strip()
    h = (host or "").strip()
    lu = u.lower()
    lh = h.lower()

    for p_host, p_unit in PROTECTED_UNITS:
        if p_unit.lower() == lu and p_host in ("*", lh):
            return f"{u} on {h} is on the PROTECTED LIST (explicit)"

    for pat in PROTECTED_PATTERNS:
        if fnmatch.fnmatch(lu, pat):
            return f"{u} matches protected pattern {pat!r} - a life is never stopped"

    for pat in PROTECTED_PATTERNS_INFRA:
        if fnmatch.fnmatch(lu, pat):
            return f"{u} matches protected infrastructure pattern {pat!r}"

    return None


def is_protected(host: str, unit: str) -> bool:
    return protection_reason(host, unit) is not None


def assert_actionable(host: str, unit: str, want: str) -> None:
    """The point-of-execution gate. Nothing runs without passing this.

    Checked again here even though load_modes() already checked, so that a caller
    who hand-builds an action dict - or a future bug that bypasses mode loading -
    still cannot touch ERAN.
    """
    if not _HOST_RE.match(host or ""):
        raise ProtectedUnitError(f"REFUSED: bad host token {host!r}")
    if not _UNIT_RE.match(unit or ""):
        raise ProtectedUnitError(
            f"REFUSED: {unit!r} is not a valid systemd unit name. "
            "This program only ever acts on named .service units - "
            "there is no free-text command path."
        )
    if want not in VALID_WANTS:
        raise ProtectedUnitError(f"REFUSED: want must be one of {VALID_WANTS}, got {want!r}")

    why = protection_reason(host, unit)
    if why is not None:
        raise ProtectedUnitError(f"REFUSED: {why}. No mode, no admin action, no flag may {want} it.")


# --------------------------------------------------------------------------
# Mode definitions
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Action:
    host: str
    unit: str
    want: str  # "start" | "stop"

    def key(self) -> str:
        return f"{self.host}/{self.unit}"


@dataclass
class Mode:
    name: str
    label: str
    description: str
    actions: list[Action]


def load_modes(path: Path | None = None) -> dict[str, Mode]:
    """Load modes.json.

    A mode that names a protected unit does not load with a warning - the WHOLE FILE
    is rejected with ProtectedUnitError. You cannot define such a mode at all.
    """
    path = Path(path) if path is not None else MODES_FILE
    raw = json.loads(path.read_text(encoding="utf-8"))

    if not isinstance(raw, dict) or "modes" not in raw:
        raise ModeDefinitionError(f"{path}: expected an object with a 'modes' key")

    modes: dict[str, Mode] = {}
    violations: list[str] = []

    for name, spec in raw["modes"].items():
        if not isinstance(spec, dict):
            raise ModeDefinitionError(f"mode {name!r}: expected an object")
        acts: list[Action] = []
        for i, a in enumerate(spec.get("units", [])):
            try:
                host = str(a["host"]).strip()
                unit = str(a["unit"]).strip()
                want = str(a["want"]).strip()
            except (KeyError, TypeError) as exc:
                raise ModeDefinitionError(
                    f"mode {name!r} entry {i}: each entry needs host, unit, want"
                ) from exc

            if want not in VALID_WANTS:
                raise ModeDefinitionError(
                    f"mode {name!r} entry {i}: want must be one of {VALID_WANTS}, got {want!r}"
                )
            if not _HOST_RE.match(host):
                raise ModeDefinitionError(f"mode {name!r} entry {i}: bad host {host!r}")
            if not _UNIT_RE.match(unit):
                raise ModeDefinitionError(
                    f"mode {name!r} entry {i}: {unit!r} is not a valid .service unit name"
                )

            why = protection_reason(host, unit)
            if why is not None:
                violations.append(f"  mode {name!r} -> want={want} {host}/{unit}: {why}")
            acts.append(Action(host=host, unit=unit, want=want))

        modes[name] = Mode(
            name=name,
            label=spec.get("label", name),
            description=spec.get("description", ""),
            actions=acts,
        )

    if violations:
        raise ProtectedUnitError(
            "MODE FILE REFUSED - it names units on the PROTECTED LIST.\n"
            + "\n".join(violations)
            + f"\n\nNothing was loaded from {path}. Remove those entries.\n"
            "eranb-life.service is ERAN. He is not a workload."
        )

    return modes


def managed_units(modes: dict[str, Mode]) -> list[tuple[str, str]]:
    """Every (host, unit) any mode has an opinion about. PAUSE operates on this set."""
    seen: dict[tuple[str, str], None] = {}
    for m in modes.values():
        for a in m.actions:
            seen[(a.host, a.unit)] = None
    return sorted(seen.keys())


# --------------------------------------------------------------------------
# Probing the fleet - systemctl --user is the ONLY correct probe
# --------------------------------------------------------------------------

SSH_BASE = [
    "ssh",
    "-o", "BatchMode=yes",
    "-o", "ConnectTimeout=10",
    "-o", "StrictHostKeyChecking=accept-new",
]


def _ssh(host: str, remote_argv: list[str], timeout: int = 45) -> tuple[int, str, str]:
    """Run one command on a fleet box. argv list, shell=False, always."""
    argv = SSH_BASE + [host] + remote_argv
    try:
        p = subprocess.run(
            argv, capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
        )
        return p.returncode, p.stdout or "", p.stderr or ""
    except subprocess.TimeoutExpired:
        return 124, "", f"timeout after {timeout}s"
    except OSError as exc:
        return 125, "", f"{type(exc).__name__}: {exc}"


def probe_host(host: str, of_interest: list[str] | None = None,
               timeout: int = 45) -> dict[str, Any]:
    """Return {unit: state} for the user-scope services on one box.

    SYSTEM SCOPE IS WRONG. `systemctl is-active eranb-life.service` in system scope
    answers 'not-found' for a service that is running perfectly. That mistake has
    already produced one false "everything is dead" report on this fleet.

    TWO probes, because one is not enough:

      1. `list-units --all` gives the broad picture - but it only lists units that
         are currently LOADED IN MEMORY. A unit that exists on disk, is not enabled
         and has never been started is simply absent from it. Measured 2026-09-05:
         fleetmode-selftest.service showed LoadState=loaded / ActiveState=inactive
         under `show`, and did not appear in `list-units --all` at all.

         Trusting only this probe made a mode switch silently do nothing: plan_mode
         skips units it believes are 'absent', so want=start planned zero actions
         and reported OK. That is exactly the failure this program exists to avoid.

      2. `show -p LoadState -p ActiveState <units...>` is authoritative and forces
         the unit to load. We run it for every unit any mode names, so the managed
         set always has a true state even when it is cold.
    """
    rc, out, err = _ssh(
        host,
        ["systemctl", "--user", "list-units", "--all", "--type=service",
         "--no-legend", "--plain", "--no-pager"],
        timeout=timeout,
    )
    if rc != 0:
        return {"ok": False, "error": (err or out or f"rc={rc}").strip()[:400], "units": {}}

    units: dict[str, str] = {}
    mem: dict[str, float | None] = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[0].endswith(".service"):
            # UNIT LOAD ACTIVE SUB ...
            units[parts[0]] = parts[2]
        elif len(parts) >= 5 and parts[0] in ("*", "\u25cf") and parts[1].endswith(".service"):
            units[parts[1]] = parts[3]

    # --- authoritative pass over the units we actually care about ---
    wanted = [u for u in (of_interest or []) if _UNIT_RE.match(u)]
    if wanted:
        rc2, out2, _ = _ssh(
            host,
            # MemoryCurrent is systemd's own cgroup accounting -- the right
            # source for THE ARK rule, because it is per-unit and includes the
            # unit's children, which `ps` on one pid does not.
            ["systemctl", "--user", "show", "--no-pager",
             "-p", "Id", "-p", "LoadState", "-p", "ActiveState",
             "-p", "MemoryCurrent"] + wanted,
            timeout=timeout,
        )
        if rc2 == 0:
            cur: dict[str, str] = {}
            for line in out2.splitlines():
                line = line.strip()
                if not line:
                    if cur.get("Id"):
                        units[cur["Id"]] = ("absent" if cur.get("LoadState") == "not-found"
                                            else cur.get("ActiveState", "unknown"))
                        # systemd reports the string "[not set]" (and on some
                        # versions 2**64-1) when the unit is not running or has
                        # no accounting. Both mean "unknown", never "0" -- a 0
                        # here would put every dead unit in the ark.
                        raw = cur.get("MemoryCurrent", "")
                        gb = None
                        if raw.isdigit():
                            b = int(raw)
                            if 0 < b < (1 << 63):
                                gb = b / (1024.0 ** 3)
                        mem[cur["Id"]] = gb
                    cur = {}
                    continue
                if "=" in line:
                    k, _, v = line.partition("=")
                    cur[k] = v
            if cur.get("Id"):
                units[cur["Id"]] = ("absent" if cur.get("LoadState") == "not-found"
                                    else cur.get("ActiveState", "unknown"))

    return {"ok": True, "error": None, "units": units, "mem_gb": mem}


def probe_fleet(hosts: list[str],
                of_interest: list[tuple[str, str]] | None = None) -> dict[str, dict[str, Any]]:
    """Probe several boxes. Sequential and read-only: this touches nothing.

    `of_interest` is the managed set as (host, unit) pairs; those units get the
    authoritative `systemctl show` pass so a cold unit reads 'inactive', not 'absent'.
    """
    per_host: dict[str, list[str]] = {}
    for h, u in (of_interest or []):
        per_host.setdefault(h, []).append(u)
    return {h: probe_host(h, of_interest=per_host.get(h)) for h in hosts}


def unit_state(probe: dict[str, dict[str, Any]], host: str, unit: str) -> str:
    """'active' | 'inactive' | 'failed' | 'absent' | 'unknown' (host unreachable)."""
    h = probe.get(host)
    if not h:
        return "unknown"
    if not h.get("ok"):
        return "unknown"
    return h["units"].get(unit, "absent")


# --------------------------------------------------------------------------
# Deriving the CURRENT mode - honest fractions, never a claimed mode
# --------------------------------------------------------------------------

def mode_match(mode: Mode, probe: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """How much of this mode is actually in force RIGHT NOW.

    Never says "training". Says "training (3 of 4 units match)" so a half-applied
    mode can never be mistaken for a mode that is in force.
    """
    rows = []
    matched = 0
    total = 0
    unknown = 0
    for a in mode.actions:
        st = unit_state(probe, a.host, a.unit)
        if st == "unknown":
            unknown += 1
            ok = None
        elif st == "absent":
            # A unit that does not exist on that box cannot satisfy want=start.
            ok = (a.want == "stop")
            total += 1
            matched += 1 if ok else 0
        else:
            ok = (st == "active") if a.want == "start" else (st != "active")
            total += 1
            matched += 1 if ok else 0
        rows.append({"host": a.host, "unit": a.unit, "want": a.want, "state": st, "match": ok})

    return {
        "name": mode.name,
        "label": mode.label,
        "description": mode.description,
        "matched": matched,
        "total": total,
        "unknown": unknown,
        "in_force": (total > 0 and matched == total and unknown == 0),
        "summary": (
            f"{mode.name} ({matched} of {total} units match"
            + (f", {unknown} unknown" if unknown else "")
            + ")"
        ),
        "rows": rows,
    }


def derive_current(modes: dict[str, Mode], probe: dict[str, dict[str, Any]]) -> dict[str, Any]:
    reports = [mode_match(m, probe) for m in modes.values()]
    reports.sort(key=lambda r: (-(r["matched"] / r["total"] if r["total"] else 0), r["name"]))
    in_force = [r for r in reports if r["in_force"]]
    return {
        "current": in_force[0]["name"] if in_force else None,
        "current_summary": (
            in_force[0]["summary"] if in_force
            else (reports[0]["summary"] + " - NO mode is fully in force" if reports else "no modes")
        ),
        "modes": reports,
    }


# --------------------------------------------------------------------------
# Planning and executing - confirm-before-act, verify-by-reprobe
# --------------------------------------------------------------------------

def plan_mode(mode: Mode, probe: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Exactly which units will start and stop. Shown before the second click.

    Only returns actions that would CHANGE something. A unit already in the wanted
    state is left alone - this program does not restart things to feel busy.
    """
    plan = []
    for a in mode.actions:
        st = unit_state(probe, a.host, a.unit)
        if st in ("unknown", "absent"):
            continue
        need = (a.want == "start" and st != "active") or (a.want == "stop" and st == "active")
        if not need:
            continue
        # TWO refusals, both only ever against a stop -- a start is always allowed,
        # because the rule is "never stop these", not "freeze them".
        #
        # PERMANENT TRAINING is checked FIRST and by NAME, because the thing it
        # protects is the biggest process on the fleet (84.4 GB) and would sail
        # straight through a size test.
        # THE ARK is checked second and by MEASUREMENT -- not a list someone has
        # to maintain.
        gb = (probe.get(a.host, {}) or {}).get("mem_gb", {}).get(a.unit)
        why = None
        kind = None
        if a.want == "stop":
            why = permanent_training_reason(a.host, a.unit)
            kind = "permanent_training" if why else None
            if why is None:
                why = ark_reason(gb)
                kind = "ark" if why else None
        if why:
            plan.append({"host": a.host, "unit": a.unit, "want": "stop",
                         "from_state": st, "skipped": True, "reason": why,
                         "refused_by": kind,
                         "mem_gb": None if gb is None else round(gb, 3)})
            continue
        plan.append({"host": a.host, "unit": a.unit, "want": a.want, "from_state": st,
                     "mem_gb": None if gb is None else round(gb, 3)})
    return plan


def log_action(record: dict[str, Any]) -> None:
    """Append-only action log. It CAN say FAIL - and it does, see state/actions.jsonl.

    A log with 221 OKs and no FAIL in its entire history is not a log, it is a
    decoration. This one records rc, stderr and the post-action re-probe.
    """
    record = dict(record)
    record.setdefault("ts", time.time())
    record.setdefault("ts_iso", time.strftime("%Y-%m-%dT%H:%M:%S%z"))
    with ACTION_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def execute_plan(plan: list[dict[str, Any]], actor: str, reason: str) -> dict[str, Any]:
    """Run the plan, then VERIFY BY RE-PROBING systemctl --user.

    The return code of `systemctl start` is not evidence that the unit is running.
    Every action here is re-probed afterwards and reported as verified / NOT verified.
    """
    started = time.time()
    results = []

    # Gate every single action again, at the point of execution.
    for step in plan:
        assert_actionable(step["host"], step["unit"], step["want"])

    # THE SECOND GATE, RE-DERIVED -- not merely trusting the `skipped` flag that
    # plan_mode set. A plan can be hand-built, replayed from the action log, or
    # arrive here through a future bug, and a protection that lives in only one
    # function is a protection that will eventually be walked past.
    #
    # permanent_training_reason() is a PURE function, so it can be recomputed
    # here from nothing but (host, unit) -- there is no way to smuggle a stop
    # past it. THE ARK cannot be recomputed without a live measurement, so it is
    # re-derived from the mem_gb the plan carries when it carries one; that is
    # strictly better than trusting the flag alone, and is why the two classes
    # are not merged.
    for s_ in plan:
        if s_.get("skipped") or s_.get("want") != "stop":
            continue
        why = permanent_training_reason(s_.get("host", ""), s_.get("unit", ""))
        kind = "permanent_training" if why else None
        if why is None:
            why = ark_reason(s_.get("mem_gb"))
            kind = "ark" if why else None
        if why:
            s_["skipped"] = True
            s_["reason"] = why
            s_["refused_by"] = kind

    skipped = [s for s in plan if s.get("skipped")]
    plan = [s for s in plan if not s.get("skipped")]

    for step in plan:
        host, unit, want = step["host"], step["unit"], step["want"]
        t0 = time.time()
        rc, out, err = _ssh(host, ["systemctl", "--user", want, unit], timeout=90)
        dt = round((time.time() - t0) * 1000)
        results.append({
            "host": host, "unit": unit, "want": want,
            "rc": rc, "ms": dt,
            "stderr": (err or "").strip()[:300],
        })

    for s_ in skipped:
        results.append({"host": s_["host"], "unit": s_["unit"], "want": s_["want"],
                        "rc": None, "ms": 0, "skipped": True,
                        "refused_by": s_.get("refused_by", "ark"),
                        "stderr": s_.get("reason", "in the ark")})

    # --- verification pass: re-probe reality, do not trust rc ---
    # REFUSED units are re-probed TOO, not only executed ones. A refusal whose
    # after_state reads "unknown" proves nothing; the point of the gate is that
    # the unit is STILL RUNNING afterwards, and only a re-probe can say so.
    # (Measured 2026-09-06: the first live `apply prove-permanent` logged
    #  "REFUSED" / "after_state": "unknown" for exactly this reason.)
    verify_from = plan + skipped
    hosts = sorted({s["host"] for s in verify_from})
    pairs = [(s['host'], s['unit']) for s in verify_from]
    after = probe_fleet(hosts, of_interest=pairs) if hosts else {}
    # Ark-skipped entries ride along in `results` so the caller can SEE the
    # refusal, but they were never executed and must not be verified against the
    # want they were refused for -- an ark unit is still active precisely because
    # the gate worked. Counting them produced `verified_fail: -1` and a FAIL
    # verdict on a correct refusal, i.e. the log said the wrong thing about a
    # gate doing its job. Measured and fixed 2026-09-05 19:40.
    ok_count = 0
    for r in results:
        if r.get("skipped"):
            r["after_state"] = unit_state(after, r["host"], r["unit"])
            r["verified"] = None
            r["result"] = "REFUSED"
            continue
        st = unit_state(after, r["host"], r["unit"])
        want_ok = (st == "active") if r["want"] == "start" else (st != "active")
        r["after_state"] = st
        r["verified"] = bool(want_ok)
        r["result"] = "OK" if want_ok else "FAIL"
        ok_count += 1 if want_ok else 0

    n_exec = len(plan)                       # plan was already stripped of skips
    outcome = {
        "actor": actor,
        "reason": reason,
        "planned": n_exec,
        "refused": sum(1 for r in results if r.get("skipped")),
        "refused_by_ark": sum(1 for r in results
                              if r.get("skipped") and r.get("refused_by") == "ark"),
        "refused_by_permanent_training": sum(
            1 for r in results
            if r.get("skipped") and r.get("refused_by") == "permanent_training"),
        "verified_ok": ok_count,
        "verified_fail": n_exec - ok_count,
        "result": "OK" if ok_count == n_exec else "FAIL",
        "elapsed_s": round(time.time() - started, 2),
        "actions": results,
    }
    log_action(outcome)
    return outcome


# --------------------------------------------------------------------------
# PAUSE / RESUME - the verb he asked for first
# --------------------------------------------------------------------------

def plan_pause(modes: dict[str, Mode], probe: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Stop every non-protected managed unit that is currently active."""
    plan = []
    for host, unit in managed_units(modes):
        if is_protected(host, unit):
            continue
        # PAUSE is a mode switch like any other, so it obeys the same rule:
        # a training run is never stopped. Excluded rather than listed-and-refused,
        # because plan_pause's contract is "what will actually be stopped".
        if is_permanent_training(host, unit):
            continue
        if unit_state(probe, host, unit) == "active":
            plan.append({"host": host, "unit": unit, "want": "stop", "from_state": "active"})
    return plan


def do_pause(modes: dict[str, Mode], actor: str) -> dict[str, Any]:
    mu = managed_units(modes)
    probe = probe_fleet(sorted({h for h, _ in mu}), of_interest=mu)
    plan = plan_pause(modes, probe)
    # Remember EXACTLY what was running, so RESUME restores exactly that set.
    snapshot = [{"host": p["host"], "unit": p["unit"]} for p in plan]
    out = execute_plan(plan, actor=actor, reason="PAUSE")
    PAUSE_FILE.write_text(json.dumps({
        "paused_at": time.time(),
        "paused_at_iso": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "actor": actor,
        "was_running": snapshot,
        "execute": out,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    out["snapshot"] = snapshot
    return out


def read_pause() -> dict[str, Any] | None:
    if not PAUSE_FILE.exists():
        return None
    try:
        return json.loads(PAUSE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def plan_resume() -> list[dict[str, Any]]:
    st = read_pause()
    if not st:
        return []
    return [
        {"host": r["host"], "unit": r["unit"], "want": "start", "from_state": "?"}
        for r in st.get("was_running", [])
    ]


def do_resume(actor: str) -> dict[str, Any]:
    plan = plan_resume()
    if not plan:
        return {"result": "FAIL", "error": "no pause snapshot to resume from",
                "planned": 0, "verified_ok": 0, "verified_fail": 0, "actions": []}
    out = execute_plan(plan, actor=actor, reason="RESUME")
    if out["result"] == "OK":
        try:
            PAUSE_FILE.unlink()
        except OSError:
            pass
    return out


# --------------------------------------------------------------------------
# The HUD - reuse almaware-hud/status.json, never re-collect
# --------------------------------------------------------------------------

def read_hud() -> dict[str, Any]:
    """Read the collector's status.json. If it is stale, SAY SO - loudly.

    Old numbers presented as current are worse than no numbers.
    """
    try:
        raw = json.loads(HUD_STATUS.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "stale": True, "age_s": None,
                "error": f"cannot read {HUD_STATUS}: {type(exc).__name__}: {exc}",
                "fleet": {}, "meta": {}}

    meta = raw.get("meta", {}) or {}
    ts = meta.get("ts")
    age = (time.time() - ts) if isinstance(ts, (int, float)) else None
    stale = bool(meta.get("stale")) or age is None or age > HUD_STALE_AFTER_S
    return {
        "ok": True,
        "stale": stale,
        "age_s": round(age, 1) if age is not None else None,
        "error": None,
        "meta": meta,
        "fleet": raw.get("fleet", {}) or {},
        "source": str(HUD_STATUS),
    }


# --------------------------------------------------------------------------
# CLI - works with no Claude, no API key, no MCP
# --------------------------------------------------------------------------

def _cli(argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="fleet_mode", description="Flip the 4 DGX between modes.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    sub.add_parser("modes")
    p = sub.add_parser("plan"); p.add_argument("mode")
    p = sub.add_parser("apply"); p.add_argument("mode"); p.add_argument("--yes", action="store_true")
    p = sub.add_parser("pause"); p.add_argument("--yes", action="store_true")
    p = sub.add_parser("resume"); p.add_argument("--yes", action="store_true")
    args = ap.parse_args(argv)

    try:
        modes = load_modes()
    except ProtectedUnitError as exc:
        print("\n" + "!" * 70, file=sys.stderr)
        print(str(exc), file=sys.stderr)
        print("!" * 70 + "\n", file=sys.stderr)
        return 3

    mu_all = managed_units(modes)
    hosts = sorted({h for h, _ in mu_all})

    if args.cmd == "modes":
        for m in modes.values():
            print(f"{m.name:10s} {m.label}  ({len(m.actions)} units)")
            for a in m.actions:
                print(f"           {a.want:5s} {a.host}/{a.unit}")
        return 0

    if args.cmd == "status":
        hud = read_hud()
        if hud["stale"]:
            print(f"*** HUD STALE (age={hud['age_s']}s) - not showing old numbers as current ***")
        else:
            print(f"HUD fresh, age={hud['age_s']}s, tick={hud['meta'].get('tick_ms')}ms")
        pr = probe_fleet(hosts, of_interest=mu_all)
        cur = derive_current(modes, pr)
        print(f"\nCURRENT: {cur['current_summary']}\n")
        for r in cur["modes"]:
            print(f"  {r['summary']}")
        paused = read_pause()
        if paused:
            print(f"\nPAUSED at {paused['paused_at_iso']}, {len(paused['was_running'])} units held.")
        return 0

    def _show(plan_steps):
        """One renderer for plan and apply.

        A refused step used to print exactly like a step that was about to run.
        An operator reading `stop eran3/coder-train.service (now active)` would
        reasonably conclude the coder was about to be stopped. It never was --
        but a display that hides a refusal is the same failure as `health: ok`.
        """
        will, refused = [], []
        for s in plan_steps:
            (refused if s.get("skipped") else will).append(s)
        for s in will:
            print(f"{s['want']:5s} {s['host']}/{s['unit']} (now {s['from_state']})")
        for s in refused:
            tag = {"permanent_training": "PERMANENT TRAINING",
                   "ark": "THE ARK"}.get(s.get("refused_by"), "PROTECTED")
            print(f"REFUSED  {s['host']}/{s['unit']} -- {tag}")
            print(f"         {s.get('reason', '')}")
        if refused:
            print(f"\n{len(will)} action(s) will run, {len(refused)} REFUSED "
                  f"(a refusal is not a failure).")
        elif not will:
            print("nothing to do - the fleet is already in this mode.")
        return will, refused

    if args.cmd == "plan":
        if args.mode not in modes:
            print(f"no such mode: {args.mode}", file=sys.stderr); return 2
        pr = probe_fleet(hosts, of_interest=mu_all)
        _show(plan_mode(modes[args.mode], pr))
        return 0

    if args.cmd == "apply":
        if args.mode not in modes:
            print(f"no such mode: {args.mode}", file=sys.stderr); return 2
        pr = probe_fleet(hosts, of_interest=mu_all)
        plan = plan_mode(modes[args.mode], pr)
        _show(plan)
        if not args.yes:
            print("\n-- dry run. add --yes to execute. --"); return 0
        out = execute_plan(plan, actor="cli", reason=f"mode:{args.mode}")
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0 if out["result"] == "OK" else 1

    if args.cmd == "pause":
        pr = probe_fleet(hosts, of_interest=mu_all)
        plan = plan_pause(modes, pr)
        for s in plan:
            print(f"stop  {s['host']}/{s['unit']}")
        if not args.yes:
            print("\n-- dry run. add --yes to execute. --"); return 0
        out = do_pause(modes, actor="cli")
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0 if out["result"] == "OK" else 1

    if args.cmd == "resume":
        plan = plan_resume()
        for s in plan:
            print(f"start {s['host']}/{s['unit']}")
        if not args.yes:
            print("\n-- dry run. add --yes to execute. --"); return 0
        out = do_resume(actor="cli")
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0 if out["result"] == "OK" else 1

    return 0


if __name__ == "__main__":
    sys.exit(_cli(sys.argv[1:]))
