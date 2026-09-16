#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""almido_backup.py -- ALMIDO's VERIFIED-BACKUP DELETE door.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

Iddo, 2026-09-11: his own systems must be able to delete a source once it is safely copied.
He had just pulled 3,543 photos / 18.98 GB off the phone (F:\Phone-Photos-Pull\DCIM) because
the 15 GB Google tier was 100% full, and clearing the originals one by one is not work for a
person. But "a path was given, so we trust it" is how data dies.

So this door does not have a "delete" verb at all. It has two:

    verify(sources, backup)  -> reads BOTH copies off the disk, compares sha256 per file,
                                walks directories recursively, compares file counts.
                                DELETES NOTHING. Returns a single-use RECEIPT on ALLOW.
    delete(receipt)          -> the only destructive call. Re-reads the STOP file, re-checks
                                that every source is still byte-identical to what was proven
                                and every backup is still there, then removes ONLY those files.

Splitting them is the point: a bug or an injected instruction that reaches one half cannot
delete anything, because the receipt only exists if the bytes really matched.

    almido_backup  -->  almido_gate.verify_backup / delete_verified   <- THE gate
                        (STOP file, never-delete list, ~/.iddo-harness/audit.log)

FAIL CLOSED. If Iddo's gate cannot be loaded, this module refuses everything -- it does not
fall back to os.remove. Same rule as almido_computer.py: a gate that cannot be consulted is
a gate that says no.

The gate is loaded by PATH under its own module name, so ALMIDO's computer-use door and this
one never fight over one module object. They read the same STOP file and write the same
audit log, which is what actually has to be shared.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
_HOME = Path(os.path.expanduser("~"))
_TOTZAREI_CLAUDE = "\u05ea\u05d5\u05e6\u05e8\u05d9 \u05e7\u05dc\u05d5\u05d3"     # "תוצרי קלוד"
_HARNESS_NAME = "Perplexity-Computer-Use-Harness"

# The same search order almido_computer.py uses -- the Desktop tidy task has moved this
# folder before, so every place it has actually lived is tried.
HARNESS_CANDIDATES = [Path(p) for p in (
    os.environ.get("ALMIDO_BK_HARNESS", ""),
    os.environ.get("ALMIDO_CU_HARNESS", ""),
    _HOME / "Desktop" / _TOTZAREI_CLAUDE / _HARNESS_NAME,
    _HOME / "Desktop" / "_Organized" / _TOTZAREI_CLAUDE / _HARNESS_NAME,
    _HOME / "Desktop" / "_Organized" / "Docs" / _HARNESS_NAME,
    _HOME / "Desktop" / _HARNESS_NAME,
    Path(r"D:\CLAUDE") / _HARNESS_NAME,
) if str(p)]

_LOADED: dict = {"gate": None, "harness": None, "tried": [], "errors": []}


def _load_module(name: str, path: Path):
    """Import ONE file under a private name -- the code that runs is the code in the folder
    we chose, not whichever copy happens to win on sys.path."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _load() -> dict:
    """Find Iddo's harness and import the gate out of it. Cached, failures too."""
    if _LOADED["gate"] is not None or _LOADED["errors"]:
        return _LOADED
    for cand in HARNESS_CANDIDATES:
        _LOADED["tried"].append(str(cand))
        if not (cand / "almido_gate.py").is_file():
            continue
        try:
            gate = _load_module("almido_bk_gate", cand / "almido_gate.py")
        except Exception as exc:
            _LOADED["errors"].append("%s: gate: %s: %s" % (cand, type(exc).__name__, exc))
            continue
        missing = [v for v in ("verify_backup", "delete_verified") if not hasattr(gate, v)]
        if missing:
            # An OLD copy of the gate, from before this capability existed. Refuse it loudly
            # instead of silently offering a door that is not really gated.
            _LOADED["errors"].append(
                "%s: almido_gate.py has no %s -- it predates the verified-delete capability"
                % (cand, "/".join(missing)))
            continue
        _LOADED["gate"], _LOADED["harness"] = gate, cand
        return _LOADED
    if not _LOADED["errors"]:
        _LOADED["errors"].append("almido_gate.py found in none of: " + "; ".join(_LOADED["tried"]))
    return _LOADED


def gate_module():
    return _load()["gate"]


def _no_gate(verb: str) -> dict:
    return {"ok": False, "verdict": "BLOCK", "action": verb,
            "reason": "GATE UNAVAILABLE, so nothing is verified and nothing is deleted: "
                      + "; ".join(_LOADED["errors"])[:400]}


def verify(sources, backup, algorithm: str = "sha256") -> dict:
    """Prove the backup. Deletes nothing, ever. ALLOW carries a single-use receipt."""
    gate = _load()["gate"]
    if gate is None:
        return _no_gate("verify_backup")
    if isinstance(sources, str):
        sources = [sources]
    if not isinstance(sources, (list, tuple)):
        return {"ok": False, "verdict": "BLOCK", "reason": "sources must be a path or a list of paths"}
    if not isinstance(backup, str) or not backup.strip():
        return {"ok": False, "verdict": "BLOCK", "reason": "backup must be a path"}
    try:
        out = gate.verify_backup([str(s) for s in sources], str(backup), str(algorithm or "sha256"))
    except Exception as exc:
        return {"ok": False, "verdict": "BLOCK",
                "reason": "the gate raised %s: %s -- refusing" % (type(exc).__name__, exc)}
    out["ok"] = out.get("verdict") == "ALLOW"
    return out


def delete(receipt: str, dry_run: bool = False) -> dict:
    """THE destructive verb, and the only one. Needs a receipt verify() really issued."""
    gate = _load()["gate"]
    if gate is None:
        return _no_gate("delete_verified")
    if not isinstance(receipt, str) or not receipt.strip():
        return {"ok": False, "verdict": "BLOCK",
                "reason": "no receipt. Run backup_verify first -- there is no way to delete "
                          "without one, and that is deliberate."}
    try:
        return gate.delete_verified(str(receipt), bool(dry_run))
    except Exception as exc:
        return {"ok": False, "verdict": "BLOCK",
                "reason": "the gate raised %s: %s -- nothing was deleted"
                          % (type(exc).__name__, exc)}


def status() -> dict:
    """MEASURED: which gate answered, is STOP on, what receipts are outstanding. Reads only."""
    loaded = _load()
    gate = loaded["gate"]
    info: dict = {
        "gate_loaded": gate is not None,
        "gate_file": str(loaded["harness"] / "almido_gate.py") if loaded["harness"] else None,
        "tried": loaded["tried"],
        "errors": loaded["errors"],
    }
    if gate is None:
        info["stopped"] = "GATE UNAVAILABLE"
        return info
    try:
        info["stopped"] = bool(gate.is_stopped())
        info["stop_file"] = str(gate.STOP_FILE)
        info["audit_log"] = str(gate.AUDIT_LOG)
        info["algorithm"] = gate.DELETE_ALGO
        info["receipt_ttl_seconds"] = gate.RECEIPT_TTL
        info["max_verify_files"] = gate.MAX_VERIFY_FILES
        info["receipts"] = gate.receipts_outstanding()
        info["never_delete_rules"] = len(gate._NEVER_DELETE)
    except Exception as exc:
        info["errors"] = list(info["errors"]) + ["status: %s: %s" % (type(exc).__name__, exc)]
    return info


if __name__ == "__main__":
    import json
    print(json.dumps(status(), ensure_ascii=False, indent=1))
