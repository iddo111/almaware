"""Policy gate and audit log.

Every action the harness takes passes through `Policy.check` before it runs and
`audit` after. Carried over from perplexity-pc-harness: fail closed, never log
raw prompt text, redact anything shown on screen.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"
AUDIT_PATH = ROOT / "logs" / "audit.jsonl"


class PolicyError(RuntimeError):
    """Raised when an action is not permitted. Always fail closed."""


@dataclass
class Policy:
    allowed_verbs: set[str] = field(default_factory=set)
    allowed_hosts: set[str] = field(default_factory=set)
    max_prompt_chars: int = 8000

    @classmethod
    def load(cls, path: Path | None = None) -> "Policy":
        cfg = json.loads((path or CONFIG_PATH).read_text(encoding="utf-8"))
        return cls(
            allowed_verbs=set(cfg["allowed_verbs"]),
            allowed_hosts=set(cfg["allowed_hosts"]),
            max_prompt_chars=int(cfg.get("max_prompt_chars", 8000)),
        )

    def check(self, verb: str, *, host: str | None = None, text: str | None = None) -> None:
        if verb not in self.allowed_verbs:
            raise PolicyError(f"verb not allowlisted: {verb!r}")
        if host is not None and not self._host_allowed(host):
            raise PolicyError(f"host not allowlisted: {host!r}")
        if text is not None and len(text) > self.max_prompt_chars:
            raise PolicyError(
                f"text too long: {len(text)} > {self.max_prompt_chars}"
            )

    def _host_allowed(self, host: str) -> bool:
        host = host.lower().removeprefix("www.")
        # An entry allows the host itself and its subdomains, nothing else.
        return any(host == a or host.endswith("." + a) for a in self.allowed_hosts)


def prompt_digest(text: str) -> str:
    """Stable short hash. We log this instead of the prompt so audit.jsonl is
    safe to share without leaking what was asked."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def audit(event: str, **fields: Any) -> None:
    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    record = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "event": event, **fields}
    with AUDIT_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def redacted(text: str, limit: int = 80) -> str:
    flat = " ".join(text.split())
    return flat[:limit] + ("…" if len(flat) > limit else "")
