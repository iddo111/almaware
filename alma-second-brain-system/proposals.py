#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""proposals.py -- a model may PROPOSE a door. It may never install one.

THIS MODULE HAS NO INSTALLER, BY CONSTRUCTION.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

AUTHORSHIP (separation of powers -- the judge is never the builder)
  WRITTEN BY  qwen3-coder-next-eran4 (79.7B Q4_K_M, ollama on eran4), one prompt,
              2749 tokens at 15.21 tok/s, 2026-09-05.
  JUDGED BY   claude-cli-BRAIN3, which corrected four defects before accepting.
              Each is marked JUDGE: below.

WHY FAIL-CLOSED IS A SHAPE AND NOT A POLICY
  Iddo's 11th commission of inquiry, 2026-09-05: this workspace holds roughly a
  hundred WRITTEN laws against two EXECUTABLE gates -- and the advisory gate "was
  never once exercised in six months", while the mechanical one blocked its own
  author on day one. A rule a program cannot break is worth a hundred a program is
  asked to respect. So there is no code path here that installs anything:

    * no subprocess, no os.system, no exec, no eval, no importlib, no __import__
    * no socket, no urllib -- this module cannot reach the network at all
    * it never opens a file whose name contains mcp.json or settings.json
    * install() exists ONLY to raise, so the refusal is explicit and testable
    * tests/test_proposals.py SCANS THIS SOURCE for those capabilities and fails
      if any of them ever appears. The guarantee is enforced by a test, not a
      paragraph -- including against a future edit of this very file.

  A proposal is a JSON file in pending/. A human moves it with `brain.py decide`,
  and even approval only writes down the steps a person must perform BY HAND.

  Executable-looking keys inside a proposed spec (command, argv, shell, exec, ...)
  are REDACTED at write time, so a proposal cannot smuggle a command line into the
  store and wait for something less careful to read it back out.

  Layout:  ROOT/pending/<id>.json  ->  ROOT/approved/<id>.json | ROOT/rejected/<id>.json
"""
from __future__ import annotations

import json
import os
import re
import secrets
from datetime import datetime
from pathlib import Path

FORBIDDEN_IN_SPEC = ("command", "cmd", "argv", "shell", "exec", "eval",
                     "install", "script", "run", "entrypoint")
REDACTED = "<redacted: executable field, this system never runs proposals>"

# There is no installer. These two lines are the contract, and the tests enforce it.
INSTALLER = None

DEFAULT_ROOT = r"D:\CLAUDE\alma-second-brain-system\proposals"
_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_.\-]{0,63}$")
_PID_RE = re.compile(r"^p-[0-9a-f]{10}$")
_REQUIRED = ("id", "ts", "proposer", "name", "why", "spec", "status")
_STATUSES = ("pending", "approved", "rejected")


def install(*args, **kwargs) -> None:
    """The refusal, made explicit so it can be tested rather than merely believed."""
    raise RuntimeError("there is no installer: a door is installed by a human, by hand, never by code")


# ------------------------------------------------------------------ plumbing
def _now() -> str:
    """JUDGE: the coder stamped UTC with a colon-less offset, and left a dead
    _format_offset helper behind. store.py stamps LOCAL time; two clocks in one
    record is how a timeline stops being comparable."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _valid_pid(pid: str) -> bool:
    """JUDGE: tightened from 'has no path separators' to the documented id shape.
    A pid is minted here, so anything else is a caller error and should say so."""
    return isinstance(pid, str) and bool(_PID_RE.match(pid))


def _valid_name(name: str) -> bool:
    if not isinstance(name, str) or not name:
        return False
    if os.sep in name or "/" in name or ".." in name or "\x00" in name:
        return False
    return bool(_NAME_RE.match(name))


def _root(root: str | Path | None = None) -> Path:
    return Path(root if root is not None else os.environ.get("ALMA_BRAIN_PROPOSALS", DEFAULT_ROOT)).resolve()


def _dirs(root: Path) -> tuple:
    out = (root / "pending", root / "approved", root / "rejected")
    for d in out:
        d.mkdir(parents=True, exist_ok=True)
    return out


def _redact(spec: dict) -> tuple:
    """Replace every executable-looking VALUE, at any depth, and record its key path."""
    paths: list = []

    def walk(obj, cur: str):
        if isinstance(obj, dict):
            out = {}
            for key, value in obj.items():
                nxt = ("%s.%s" % (cur, key)) if cur else str(key)
                if str(key).lower() in FORBIDDEN_IN_SPEC:
                    paths.append(nxt)
                    out[key] = REDACTED
                else:
                    out[key] = walk(value, nxt)
            return out
        if isinstance(obj, list):
            return [walk(item, "%s[%d]" % (cur, i)) for i, item in enumerate(obj)]
        return obj

    return walk(spec, ""), sorted(paths)


def _load(path: Path) -> dict | None:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None
    if not isinstance(data, dict) or not all(k in data for k in _REQUIRED):
        return None
    return data


# ------------------------------------------------------------------ the API
def propose(proposer: str, name: str, why: str, spec: dict,
            root: str | Path | None = None) -> dict:
    """Record a wanted door. Returns pending. Installs nothing, because nothing here can."""
    if not isinstance(proposer, str) or not proposer.strip():
        raise ValueError("proposer must be a non-empty string")
    if not _valid_name(name):
        raise ValueError("name must match ^[a-z0-9][a-z0-9_.-]{0,63}$ and contain no path separators")
    if not isinstance(why, str) or not why.strip():
        raise ValueError("why must be a non-empty string")
    if not isinstance(spec, dict):
        raise ValueError("spec must be a dict")
    pending_dir, _, _ = _dirs(_root(root))
    redacted_spec, redacted_paths = _redact(spec)
    pid = "p-" + secrets.token_hex(5)
    proposal = {"id": pid, "ts": _now(), "proposer": proposer.strip(), "name": name,
                "why": why.strip(), "spec": redacted_spec, "status": "pending",
                "decided_by": "", "decided_ts": "", "note": "", "redacted": redacted_paths}
    with open(pending_dir / (pid + ".json"), "w", encoding="utf-8") as fh:
        json.dump(proposal, fh, indent=1, ensure_ascii=False)
    out = dict(proposal)
    out["installed"] = False
    out["note_to_caller"] = "pending - a human must approve this; nothing was installed"
    return out


def list_proposals(status: str | None = None, root: str | Path | None = None) -> list:
    if status is not None and status not in _STATUSES:
        raise ValueError("status must be one of %s or None" % (_STATUSES,))
    pending_dir, approved_dir, rejected_dir = _dirs(_root(root))
    wanted = {"pending": [pending_dir], "approved": [approved_dir], "rejected": [rejected_dir],
              None: [pending_dir, approved_dir, rejected_dir]}[status]
    out = []
    for d in wanted:
        for f in sorted(d.glob("*.json")):
            data = _load(f)
            if data is not None:
                out.append(data)
    out.sort(key=lambda p: str(p.get("ts", "")), reverse=True)
    return out


def get(pid: str, root: str | Path | None = None) -> dict | None:
    if not _valid_pid(pid):
        raise ValueError("invalid proposal id %r (expected p- followed by 10 hex chars)" % (pid,))
    for d in _dirs(_root(root)):
        data = _load(d / (pid + ".json"))
        if data is not None:
            return data
    return None


def _manual_steps(proposal: dict) -> list:
    """What a HUMAN must do. Derived from the spec, never executed from it."""
    steps: list = []
    seen: set = set()

    def add(step: str) -> None:
        if step not in seen:
            seen.add(step)
            steps.append(step)

    def walk(obj) -> None:
        if isinstance(obj, dict):
            for key, value in obj.items():
                low = str(key).lower()
                if "command" in low or "cmd" in low or "argv" in low:
                    add("Read the proposal's %r field yourself and type any command by hand." % key)
                elif "script" in low or "entrypoint" in low:
                    add("Write and review the code described under %r yourself before running it." % key)
                elif "install" in low:
                    add("Install anything described under %r yourself, after reading what it is." % key)
                elif "url" in low or "host" in low or "endpoint" in low:
                    add("Verify the endpoint under %r resolves to something you trust." % key)
                else:
                    walk(value)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    if isinstance(proposal.get("spec"), dict):
        walk(proposal["spec"])
    add("Read the whole proposal %r and decide it is safe -- you, not a model." % proposal.get("name"))
    add("Wire the door by hand (e.g. edit .mcp.json yourself). Nothing in this system will do it.")
    return steps


def decide(pid: str, decision: str, decided_by: str, note: str = "",
           root: str | Path | None = None) -> dict:
    """A HUMAN approves or rejects. Approval still installs NOTHING -- it writes down the steps."""
    if not _valid_pid(pid):
        raise ValueError("invalid proposal id %r (expected p- followed by 10 hex chars)" % (pid,))
    if decision not in ("approved", "rejected"):
        raise ValueError("decision must be 'approved' or 'rejected'")
    if not isinstance(decided_by, str) or not decided_by.strip():
        raise ValueError("decided_by must be a non-empty string -- a decision needs a name on it")
    pending_dir, approved_dir, rejected_dir = _dirs(_root(root))
    src = pending_dir / (pid + ".json")
    if not src.exists():
        raise ValueError("proposal %s is not in the pending queue" % pid)
    # JUDGE: the coder wrapped this read in `except Exception -> raise ValueError`,
    # which swallowed and re-wrapped its own status ValueError into a misleading
    # "Failed to read proposal". A gate that lies about why it refused is worse
    # than no gate.
    data = _load(src)
    if data is None:
        raise ValueError("proposal %s is corrupt and will not be decided" % pid)
    if data.get("status") != "pending":
        raise ValueError("proposal %s is already %s" % (pid, data.get("status")))
    data["status"] = decision
    data["decided_by"] = decided_by.strip()
    data["decided_ts"] = _now()
    data["note"] = str(note or "")
    dst = (approved_dir if decision == "approved" else rejected_dir) / (pid + ".json")
    with open(dst, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1, ensure_ascii=False)
    os.remove(src)
    out = dict(data)
    out["installed"] = False
    out["manual_steps"] = _manual_steps(data)
    return out


def stats(root: str | Path | None = None) -> dict:
    pending_dir, approved_dir, rejected_dir = _dirs(_root(root))
    return {"pending": len(list(pending_dir.glob("*.json"))),
            "approved": len(list(approved_dir.glob("*.json"))),
            "rejected": len(list(rejected_dir.glob("*.json")))}
