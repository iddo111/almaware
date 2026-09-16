# לזכרה של עלמה ז״ל
"""QUORUM · stateio — tiny shared persistence helpers for the server-side modules.

Everything under D:\\CLAUDE\\quorum\\state\\ . Atomic writes (tmp + os.replace)
so a crash mid-write never corrupts a room or the registry. failure-is-a-value:
loaders return the fallback, savers return bool. 100% stdlib.
"""
from __future__ import annotations

import json
import os
import tempfile

import config

STATE_DIR = os.path.join(config.BASE_DIR, "state")
SECRETS_DIRS = (
    os.path.join(STATE_DIR, "secrets"),
    r"D:\CLAUDE\secrets",
)


def ensure_dir(path: str) -> str:
    try:
        os.makedirs(path, exist_ok=True)
    except Exception:
        pass
    return path


def load_json(path: str, fallback):
    """Read JSON from path; on any failure return fallback (never raises)."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return fallback


def save_json(path: str, value) -> bool:
    """Atomic JSON write. Returns False instead of raising."""
    try:
        ensure_dir(os.path.dirname(path))
        fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=os.path.dirname(path))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(value, f, ensure_ascii=False, indent=1)
            os.replace(tmp, path)
            return True
        finally:
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except Exception:
                pass
    except Exception:
        return False


def load_secret(name: str) -> str:
    """Secret lookup that survives restarts (house rule: env-only keys are a
    link killer). Order: environment variable NAME, then
    state\\secrets\\<name-lower>.txt, then D:\\CLAUDE\\secrets\\<name-lower>.txt.
    Returns "" when absent — absence is a value, not an error."""
    val = os.environ.get(name, "").strip()
    if val:
        return val
    fname = name.lower() + ".txt"
    for d in SECRETS_DIRS:
        try:
            p = os.path.join(d, fname)
            if os.path.isfile(p):
                with open(p, "r", encoding="utf-8") as f:
                    v = f.read().strip()
                if v:
                    return v
        except Exception:
            pass
    return ""
