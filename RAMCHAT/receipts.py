#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
receipts.py — enforcement for RAMCHAT RULES.md section 7,
"כל שינוי מצב חי משאיר שובר" / every live-state change leaves a receipt.

Born from the scar of 2026-09-03 22:55: an agent wrote
D:\\CLAUDE\\keshev-next\\state\\PAUSED containing nothing but an ISO timestamp
and walked away. Iddo's microphone was dead until 06:34 the next morning and the
window looked alive the whole time. 28 bytes, no author, no reason, no expiry.

Two verbs:

    python receipts.py write <path> --who <agent> --why "<reason>" \
           --restore "<command>" [--expires-in 4h] [--disables]
    python receipts.py check [--root D:\\CLAUDE] [--quiet]

`check` exits 0 when clean, 1 when any receipt is broken, expired, or missing.
That exit code is the whole point: it can be wired to a scheduled task, a
pre-flight in RUN-*.cmd, or a nightly nag. A rule nobody can check is a wish.

Pure stdlib. PYTHONIOENCODING=utf-8 — these files are full of Hebrew.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import sys

# --------------------------------------------------------------------------
# What counts as a live-state marker.
# --------------------------------------------------------------------------

# Bare names that mean "something is switched off / held".
# NOTE: plain "LOCK" is deliberately absent — that name belongs to LevelDB and
# Chromium profiles, which litter every browser-harness directory with 0-byte
# LOCK files. Claiming those as agent receipts made this check cry wolf 40 times
# and a check nobody believes is worse than no check.
MARKER_NAMES = {
    "PAUSED", "PAUSE", "STOP", "STOPPED", "HALT", "HOLD", "DISABLED",
    "FROZEN", "FREEZE", "MAINTENANCE", "DRAIN", "MUTED", "SILENCE", "OFF",
}
# Extensions that mean the same thing.
MARKER_EXTS = {".pid", ".lock", ".paused", ".claim", ".claimed", ".inprogress", ".halt"}

# Directories that are never ours to police (vendor trees, caches, browser
# profiles, build output). A Chromium profile LOCK is not an agent's receipt.
SKIP_DIR_NAMES = {
    "node_modules", ".git", "venv", ".venv", "env", "envs", "site-packages",
    "__pycache__", "dist", "build", ".next", ".cache", "target", ".pytest_cache",
    ".mypy_cache", "_genizah", ".tox", "vendor", "third_party", ".svn", "Lib",
    "pkgs", "wheels", "checkpoints", ".ipynb_checkpoints", ".pio", "libdeps",
    ".platformio", "Arduino15", "packages", "worktrees", "profiles", "archive",
    ".godot", ".wrangler", ".kotlin", "provenance", "_security-audit-upstream",
}

# Dependency manifests that happen to end in ".lock". They pin package versions;
# they never hold a resource and nobody is waiting on them.
DEPENDENCY_LOCKFILES = {
    "requirements.lock", "poetry.lock", "cargo.lock", "uv.lock", "yarn.lock",
    "package-lock.json", "pnpm-lock.yaml", "flake.lock", "gemfile.lock",
    "composer.lock", "pdm.lock", "bun.lock", "conda-lock.yml", "npm-shrinkwrap.json",
}

REQUIRED_FIELDS = ("who", "why", "at", "restore")

# The hard ceiling on how long a disabling marker may live unattended.
MAX_DISABLE_HOURS = 12


def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc).astimezone()


def _parse_ts(s: str):
    if not isinstance(s, str):
        return None
    try:
        t = _dt.datetime.fromisoformat(s.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=_now().tzinfo)
    return t


def _parse_duration(s: str) -> _dt.timedelta:
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([smhd])\s*", s or "", re.I)
    if not m:
        raise argparse.ArgumentTypeError(
            "duration must look like 30m, 4h, 2d (max %dh)" % MAX_DISABLE_HOURS
        )
    n, unit = float(m.group(1)), m.group(2).lower()
    return _dt.timedelta(**{{"s": "seconds", "m": "minutes", "h": "hours", "d": "days"}[unit]: n})


def _pid_alive(pid: int) -> bool:
    if os.name == "nt":
        import ctypes
        # PROCESS_QUERY_LIMITED_INFORMATION
        h = ctypes.windll.kernel32.OpenProcess(0x1000, False, int(pid))
        if not h:
            return False
        code = ctypes.c_ulong()
        ok = ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code))
        ctypes.windll.kernel32.CloseHandle(h)
        return bool(ok) and code.value == 259  # STILL_ACTIVE
    try:
        os.kill(int(pid), 0)
    except (ProcessLookupError, ValueError):
        return False
    except PermissionError:
        return True
    return True


# --------------------------------------------------------------------------
# write
# --------------------------------------------------------------------------

def cmd_write(a) -> int:
    now = _now()
    receipt = {
        "who": a.who,
        "why": a.why,
        "at": now.isoformat(timespec="seconds"),
        "restore": a.restore,
        "disables": bool(a.disables),
    }
    if a.expires_in:
        delta = _parse_duration(a.expires_in)
        if a.disables and delta > _dt.timedelta(hours=MAX_DISABLE_HOURS):
            print(
                "REFUSED: a marker that disables something may not live longer than "
                f"{MAX_DISABLE_HOURS}h (RULES.md §7b).",
                file=sys.stderr,
            )
            return 2
        receipt["expires"] = (now + delta).isoformat(timespec="seconds")
    elif a.disables:
        print(
            "REFUSED: --disables requires --expires-in (RULES.md §7b). "
            "State that switches off something Iddo uses may never be open-ended.",
            file=sys.stderr,
        )
        return 2
    if a.pid is not None:
        receipt["pid"] = int(a.pid)

    path = os.path.abspath(a.path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(receipt, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print(f"wrote receipt: {path}")
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0


# --------------------------------------------------------------------------
# check
# --------------------------------------------------------------------------

def _is_marker(name: str) -> bool:
    if name.lower() in DEPENDENCY_LOCKFILES:
        return False
    stem, ext = os.path.splitext(name)
    # A bare switch-off name counts only when it carries no extension at all
    # ("PAUSED", "STOP"). Otherwise "lock.cpp.d" and "stop_recorder.cmd" would
    # masquerade as markers.
    if not ext and stem.upper() in MARKER_NAMES:
        return True
    return ext.lower() in MARKER_EXTS


def _walk(root: str):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIR_NAMES and not d.startswith(".venv")]
        for f in filenames:
            if _is_marker(f):
                yield os.path.join(dirpath, f)


def cmd_check(a) -> int:
    now = _now()
    violations, ok_count = [], 0

    for path in _walk(a.root):
        try:
            raw = open(path, encoding="utf-8-sig").read().strip()
        except (OSError, UnicodeDecodeError):
            continue
        rel = path
        mtime = _dt.datetime.fromtimestamp(os.path.getmtime(path)).astimezone()
        age_h = (now - mtime).total_seconds() / 3600.0

        try:
            data = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            data = None

        # A running process is its own receipt: you can see it, name it and kill
        # it. So a .pid/.lock naming a LIVE process passes, whether it holds a
        # bare number or JSON. Only when the process is gone does the file have
        # to explain itself — because then nothing else can.
        if os.path.splitext(path)[1].lower() in (".pid", ".lock"):
            claimed = raw if raw.isdigit() else (
                str(data.get("pid")) if isinstance(data, dict) and data.get("pid") is not None else None
            )
            if claimed and claimed.isdigit():
                if _pid_alive(int(claimed)):
                    ok_count += 1
                else:
                    violations.append((rel, f"stale {os.path.splitext(path)[1]} — process {claimed} "
                                            f"is DEAD (written {mtime:%Y-%m-%d %H:%M}, "
                                            f"{age_h:.0f}h ago)"))
                continue

        if not isinstance(data, dict):
            violations.append((rel, f"UNATTRIBUTED — not a receipt, just {len(raw)} bytes of "
                                    f"'{raw[:40]}' (written {mtime:%Y-%m-%d %H:%M}). "
                                    f"This is the 2026-09-03 KESHEV shape."))
            continue

        missing = [f for f in REQUIRED_FIELDS if not data.get(f)]
        if missing:
            violations.append((rel, f"receipt missing required field(s): {', '.join(missing)}"))
            continue

        if data.get("pid") is not None and not _pid_alive(int(data["pid"])):
            violations.append((rel, f"receipt's process {data['pid']} is DEAD but the marker "
                                    f"is still here — who='{data['who']}'"))
            continue

        exp = _parse_ts(data.get("expires", ""))
        if data.get("disables"):
            if not exp:
                violations.append((rel, f"disables=true with no valid expiry — who='{data['who']}' "
                                        f"(RULES.md §7b forbids open-ended disabling state)"))
                continue
            if exp < now:
                violations.append((rel, f"EXPIRED {(now - exp).total_seconds()/3600:.1f}h ago and "
                                        f"still in force — who='{data['who']}', why='{data['why']}'. "
                                        f"RESTORE: {data['restore']}"))
                continue
        elif exp and exp < now:
            violations.append((rel, f"expired {(now - exp).total_seconds()/3600:.1f}h ago — "
                                    f"who='{data['who']}'. RESTORE: {data['restore']}"))
            continue

        ok_count += 1

    if violations:
        print("=" * 78)
        print(f"RECEIPT CHECK FAILED — {len(violations)} violation(s), {ok_count} clean")
        print("RAMCHAT RULES.md §7 — every live-state change leaves a receipt.")
        print("=" * 78)
        for p, msg in sorted(violations):
            print(f"\n  {p}\n      {msg}")
        print()
        return 1

    if not a.quiet:
        print(f"receipt check clean — {ok_count} marker(s) accounted for under {a.root}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    w = sub.add_parser("write", help="write a compliant marker/receipt")
    w.add_argument("path")
    w.add_argument("--who", required=True, help="agent name, same one you use for ramlink post")
    w.add_argument("--why", required=True, help="one human line: why this state exists")
    w.add_argument("--restore", required=True, help="the exact command that undoes this")
    w.add_argument("--expires-in", help="30m / 4h / 2d — REQUIRED with --disables")
    w.add_argument("--disables", action="store_true",
                   help="this marker switches off something Iddo uses")
    w.add_argument("--pid", type=int, help="the process this marker belongs to")
    w.set_defaults(func=cmd_write)

    c = sub.add_parser("check", help="audit every marker under a root; exit 1 on violations")
    c.add_argument("--root", default=r"D:\CLAUDE")
    c.add_argument("--quiet", action="store_true")
    c.set_defaults(func=cmd_check)

    a = ap.parse_args()
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
