# -*- coding: utf-8 -*-
"""MIKO TEACHER - shared plumbing. stdlib only.

Every script in this directory imports this. It owns four things and nothing else:
the free-fleet call (never a paid API), BELOW_NORMAL priority (Iddo's mic is sacred),
jsonl read/write, and the append-only run log.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
RUNS = HERE / "runs"
DATA.mkdir(exist_ok=True)
RUNS.mkdir(exist_ok=True)

#: Iddo's own free models. Order = try order. No paid API is reachable from here.
#: Measured 2026-09-12: router gpt-oss-120b 1.6 s, maverick 2.7 s, kimi-k3 HTTP 429,
#: dgx4 ollama alive (model id must be the ':latest' form or it answers 404).
FLEET = [
    ("router-gptoss120b", "http://<tailnet-ip>:8010/v1/chat/completions", "gpt-oss-120b"),
    ("router-maverick",   "http://<tailnet-ip>:8010/v1/chat/completions", "maverick"),
    ("router-kimi-k3",    "http://<tailnet-ip>:8010/v1/chat/completions", "moonshotai/kimi-k3"),
    ("dgx4-coder", "https://<tailnet-host>:8450/v1/chat/completions",
     "qwen-coder-dgx4:latest"),
]


def utf8() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def lower_priority() -> None:
    """BELOW_NORMAL on Windows. The mic and the live brains come first, always."""
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.kernel32.SetPriorityClass(
                ctypes.windll.kernel32.GetCurrentProcess(), 0x00004000)
        except Exception:
            pass


def call_fleet(messages, max_tokens=400, temperature=0.2, timeout=120.0, prefer=None):
    """First free fleet model that answers. Returns (name, model, content).

    `prefer` pins one endpoint name; everything else is still tried after it, because
    a pinned model that is rate-limited must not silently stop the night's work.
    """
    import ssl
    ctx = ssl._create_unverified_context()
    order = list(FLEET)
    if prefer:
        order.sort(key=lambda e: 0 if e[0] == prefer else 1)
    errs = []
    for name, url, model in order:
        payload = {"model": model, "messages": messages,
                   "max_tokens": max_tokens, "temperature": temperature}
        try:
            req = urllib.request.Request(
                url, data=json.dumps(payload).encode("utf-8"), method="POST",
                headers={"Content-Type": "application/json",
                         "User-Agent": "miko-teacher/0.1"})
            kw = {"timeout": timeout}
            if url.startswith("https://"):
                kw["context"] = ctx
            with urllib.request.urlopen(req, **kw) as r:
                resp = json.loads(r.read().decode("utf-8", "replace"))
            return name, model, resp["choices"][0]["message"]["content"]
        except Exception as e:
            errs.append("%s: %s" % (name, str(e)[:80]))
    raise RuntimeError("no free fleet model answered -- " + " | ".join(errs))


def read_jsonl(path):
    p = Path(path)
    if not p.exists():
        return []
    out = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def write_jsonl(path, rows):
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return len(rows)


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def log_run(record: dict, path=None) -> Path:
    """Append-only. One JSON line per run, wins and losses alike."""
    p = Path(path or (RUNS / "runlog.jsonl"))
    record = dict(record)
    record.setdefault("at", now())
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return p
