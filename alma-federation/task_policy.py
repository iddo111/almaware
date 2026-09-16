"""Shared, deliberately tiny task schema for the private Alma Federation.

There is no generic command task. Adding a new capability requires adding a
named task here, a bounded implementation in worker.py, and security tests.
"""

from __future__ import annotations

import sys
from typing import Any


class PolicyError(ValueError):
    """A coordinator task is outside the worker's explicit policy."""


ALLOWED_KINDS = frozenset({"system.info", "python.version", "diagnostic.echo"})


def validate_task(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PolicyError("task must be a JSON object, never a command string")

    kind = value.get("kind")
    if kind not in ALLOWED_KINDS:
        raise PolicyError(f"task kind is not allowed: {kind!r}")

    if kind in {"system.info", "python.version"}:
        if set(value) != {"kind"}:
            raise PolicyError(f"{kind} accepts no arguments")
        return {"kind": kind}

    if set(value) != {"kind", "message"}:
        raise PolicyError("diagnostic.echo accepts only a message")
    message = value.get("message")
    if not isinstance(message, str) or len(message) > 256:
        raise PolicyError("diagnostic.echo message must be a string of at most 256 characters")
    return {"kind": kind, "message": message}


def planned_argv(task: Any) -> list[str] | None:
    """Return the exact process argv, if this named task needs a process."""
    normalized = validate_task(task)
    if normalized["kind"] == "python.version":
        return [sys.executable, "--version"]
    return None
