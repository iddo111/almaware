#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
לזכרה של עלמה ז"ל

test_fleet.py — LIVE fleet health check.
========================================
Unlike test_router.py (hermetic, no network), this script makes REAL calls to
every endpoint in fleet_config.json and prints, per model: status + latency.

It is honest about what it can't reach:
  * SKIP (no key)   — provider's API key env var isn't set (nothing to test)
  * SKIP (no host)  — a local/eran endpoint isn't listening (e.g. Eran not
                      started, or the DGX SSH tunnel isn't open)
  * FAIL            — endpoint was reachable but the call errored / returned junk
  * OK  <ms>        — got a real reply, with round-trip latency

Usage:
    python test_fleet.py                 # test every model in the config
    python test_fleet.py --only eran-local grok-web
    python test_fleet.py --json          # machine-readable results
    python test_fleet.py --prompt "..."  # custom probe prompt

Eran over the DGX tunnel:
    ssh -N -L 7801:localhost:7800 eran4     # open first, then run this
"""
from __future__ import annotations

import argparse
import json
import os
import re
import socket
import sys
import time
import urllib.parse
from typing import Optional

import router  # reuse the real dispatch + config so we test the actual fleet

# UTF-8 console (Hebrew memorial + Hebrew replies on Windows cp1252).
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass

DEFAULT_PROMPT = "Reply with the single word: OK"

# Secret hygiene: error strings (e.g. "Invalid header value b'Bearer xai-...'")
# can echo an API key. We NEVER print secrets — redact before display/JSON.
_SECRET_ENVS = ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "XAI_API_KEY", "ERAN_TOKEN")
_KEYLIKE = re.compile(r"\b(xai-|sk-ant-|sk-|AIza)[A-Za-z0-9_\-]{6,}")


def _redact(text: str) -> str:
    """Remove any real key value, then any key-shaped token, from a string."""
    if not text:
        return text
    for env in _SECRET_ENVS:
        val = os.environ.get(env)
        if val and val.strip():
            text = text.replace(val, "***").replace(val.strip(), "***")
    return _KEYLIKE.sub("***REDACTED***", text)

# Which env key each provider needs. Missing key -> SKIP (not FAIL).
_PROVIDER_KEY = {
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "xai": "XAI_API_KEY",
    # ollama + eran are keyless; reachability is checked by a TCP probe instead.
}


def _host_port(url: str) -> tuple[str, int]:
    p = urllib.parse.urlparse(url)
    host = p.hostname or "localhost"
    port = p.port or (443 if p.scheme == "https" else 80)
    return host, port


def _tcp_open(host: str, port: int, timeout: float = 2.0) -> bool:
    """Cheap pre-flight: is anything listening? Avoids a long timeout on a
    local/tunnel endpoint that simply isn't up."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _endpoint_url(cfg: dict, spec: dict) -> Optional[str]:
    env = spec.get("endpoint_env")
    if not env:
        return None
    return os.environ.get(env, spec.get("endpoint_default"))


def preflight(cfg: dict, key: str, spec: dict) -> Optional[str]:
    """Return a SKIP reason if we shouldn't even attempt the call, else None."""
    provider = spec["provider"]
    need_key = _PROVIDER_KEY.get(provider)
    if need_key and not os.environ.get(need_key):
        return f"no key ({need_key})"
    # Local/tunnel HTTP servers (ollama, eran): TCP-probe before calling.
    url = _endpoint_url(cfg, spec)
    if url:
        host, port = _host_port(url)
        if not _tcp_open(host, port):
            return f"no host ({host}:{port})"
    return None


def probe(cfg: dict, key: str, prompt: str) -> dict:
    """Test one model. Returns {model, provider, free, status, ms, detail}."""
    spec = cfg["models"][key]
    res = {"model": key, "provider": spec["provider"], "free": spec["free"],
           "status": "?", "ms": None, "detail": ""}

    skip = preflight(cfg, key, spec)
    if skip:
        res["status"], res["detail"] = "SKIP", skip
        return res

    t0 = time.perf_counter()
    try:
        out = router.dispatch(cfg, key, prompt)
        ms = int((time.perf_counter() - t0) * 1000)
        res["ms"] = ms
        text = (out or "").strip().replace("\n", " ")
        if not text:
            res["status"], res["detail"] = "FAIL", "empty reply"
        else:
            res["status"] = "OK"
            res["detail"] = text[:60] + ("…" if len(text) > 60 else "")
    except Exception as exc:  # noqa: BLE001 — a live probe failing is a result
        res["ms"] = int((time.perf_counter() - t0) * 1000)
        res["status"] = "FAIL"
        res["detail"] = _redact(f"{type(exc).__name__}: {exc}")[:80]
    return res


def run(only: Optional[list[str]], prompt: str) -> list[dict]:
    cfg = router.load_config()
    keys = only or list(cfg["models"].keys())
    results = []
    for k in keys:
        if k not in cfg["models"]:
            results.append({"model": k, "provider": "?", "free": None,
                            "status": "FAIL", "ms": None,
                            "detail": "not in fleet_config.json"})
            continue
        results.append(probe(cfg, k, prompt))
    return results


def _print_table(results: list[dict]) -> None:
    print('לזכרה של עלמה ז"ל — ALMAWARE Fleet · live health check\n')
    print(f"{'MODEL':<13}{'PROVIDER':<11}{'STATUS':<7}{'LATENCY':<10}DETAIL")
    print("-" * 78)
    for r in results:
        lat = f"{r['ms']} ms" if r["ms"] is not None else "-"
        icon = {"OK": "✓", "SKIP": "·", "FAIL": "✗"}.get(r["status"], "?")
        print(f"{r['model']:<13}{r['provider']:<11}"
              f"{icon+' '+r['status']:<7}{lat:<10}{r['detail']}")
    ok = sum(r["status"] == "OK" for r in results)
    skip = sum(r["status"] == "SKIP" for r in results)
    fail = sum(r["status"] == "FAIL" for r in results)
    print("-" * 78)
    print(f"{ok} OK · {skip} skipped · {fail} failed   (of {len(results)})")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="ALMAWARE fleet live health check")
    ap.add_argument("--only", nargs="*", help="test only these model keys")
    ap.add_argument("--prompt", default=DEFAULT_PROMPT, help="probe prompt")
    ap.add_argument("--json", action="store_true", help="emit JSON results")
    args = ap.parse_args(argv)

    results = run(args.only, args.prompt)

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        _print_table(results)

    # Exit non-zero only on a genuine FAIL (SKIP is fine — key/host just absent).
    return 1 if any(r["status"] == "FAIL" for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
