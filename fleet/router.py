#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
לזכרה של עלמה ז"ל

ALMAWARE Fleet Router
=====================
Smart router that assigns each task to the right model in the fleet, to
maximize free AI compute: cheap/fast jobs go to Ollama (gemma2:2b, free),
complex jobs to Claude/Gemini, real-time to Grok.

Routing is data-driven: it reads fleet_config.json. To re-route a task type
or add a model, edit that JSON — no code change here.

Usage:
    python router.py --task code "Write a Python function to reverse a list"
    python router.py --task hebrew "תרגם: hello world"
    echo "summarize this" | python router.py --task document
    python router.py --auto "what's the latest news on AI chips?"   # auto-classify
    python router.py --list                                         # show the fleet

Keys are read from environment variables (see setup_secrets.sh). On GCP they
come from Secret Manager, surfaced as env vars in the runtime.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional

CONFIG_PATH = Path(__file__).with_name("fleet_config.json")
# eran-live writes a training heartbeat here (train.py -> write_fleet_status).
ERAN_STATUS_PATH = Path(__file__).with_name("eran_live_status.json")

# Windows consoles default to cp1252; the fleet speaks Hebrew. Force UTF-8.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


# --------------------------------------------------------------------------- #
# Task classification (when --auto is used instead of an explicit --task)
# --------------------------------------------------------------------------- #
_KEYWORDS = {
    "realtime": ["news", "latest", "today", "current", "right now", "breaking",
                 "stock", "price now", "weather", "אחרונות", "עכשיו", "היום"],
    "code": ["code", "function", "bug", "refactor", "python", "javascript",
             "compile", "stack trace", "regex", "api ", "def ", "class "],
    # ALMAWARE-specific queries -> our own model (Eran). Checked before the
    # generic document/hebrew buckets so "ask Eran ..." routes to Eran.
    "almaware": ["almaware", "אלמאוור", "eran", 'ער"ן', "ער״ן", "ערן",
                 "ask eran", "שאל את ערן"],
    "creative": ["write a poem", "write a story", "creative", "imagine a",
                 "make up a", "שיר על", "סיפור על", "דמיין", "כתוב שיר"],
    "document": ["summarize", "analyze this document", "long context", "pdf",
                 "transcript", "summary of", "תקציר", "סכם", "מסמך"],
    "hebrew": ["עברית", "translate to hebrew", "תרגם", "ניקוד", "לעברית"],
    "whatsapp": ["whatsapp", "reply to", "quick reply", "וואטסאפ", "תענה"],
}


def classify(prompt: str) -> str:
    """Best-effort task-type guess from prompt text. Falls back to 'default'."""
    low = prompt.lower()
    # Hebrew detection: any Hebrew chars -> lean Hebrew unless clearly code/realtime
    has_hebrew = any("֐" <= ch <= "׿" for ch in prompt)
    for task, kws in _KEYWORDS.items():
        if any(kw in low for kw in kws):
            return task
    if has_hebrew:
        return "hebrew"
    if len(prompt) > 4000:
        return "long_context"
    return "default"


def pick_model(cfg: dict, task: str) -> str:
    routing = cfg["task_routing"]
    return routing.get(task, routing["default"])


# --------------------------------------------------------------------------- #
# Provider clients — minimal, dependency-free (urllib only)
# --------------------------------------------------------------------------- #
def _http_post(url: str, payload: dict, headers: dict, timeout: int) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _secret(name: str) -> Optional[str]:
    # Strip whitespace/newlines: a trailing "\n" in a key (common when a key is
    # exported from a file) makes an HTTP header value invalid (ValueError).
    v = os.environ.get(name)
    return v.strip() if v else v


def call_anthropic(model_id: str, prompt: str, timeout: int) -> str:
    key = _secret("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    body = {
        "model": model_id,
        "max_tokens": 2048,
        "messages": [{"role": "user", "content": prompt}],
    }
    headers = {
        "x-api-key": key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    out = _http_post("https://api.anthropic.com/v1/messages", body, headers, timeout)
    return "".join(b.get("text", "") for b in out.get("content", []))


def call_gemini(model_id: str, prompt: str, timeout: int) -> str:
    key = _secret("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY not set")
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{model_id}:generateContent?key={key}")
    body = {"contents": [{"parts": [{"text": prompt}]}]}
    out = _http_post(url, body, {"content-type": "application/json"}, timeout)
    cands = out.get("candidates", [])
    if not cands:
        return ""
    parts = cands[0].get("content", {}).get("parts", [])
    return "".join(p.get("text", "") for p in parts)


def call_xai(model_id: str, prompt: str, timeout: int,
             extra: Optional[dict] = None) -> str:
    key = _secret("XAI_API_KEY")
    if not key:
        raise RuntimeError("XAI_API_KEY not set")
    body = {
        "model": model_id,
        "messages": [{"role": "user", "content": prompt}],
    }
    # `extra` lets a model spec enable features (e.g. Live Search) purely from
    # JSON — see "grok-web" in fleet_config.json (search_parameters). Data-driven:
    # adding a Grok variant needs no code change here.
    if extra:
        body.update(extra)
    headers = {"Authorization": f"Bearer {key}", "content-type": "application/json"}
    out = _http_post("https://api.x.ai/v1/chat/completions", body, headers, timeout)
    return out["choices"][0]["message"]["content"]


def call_ollama(model_id: str, endpoint: str, prompt: str, timeout: int) -> str:
    url = f"{endpoint.rstrip('/')}/api/generate"
    body = {"model": model_id, "prompt": prompt, "stream": False}
    out = _http_post(url, body, {"content-type": "application/json"}, timeout)
    return out.get("response", "")


def call_eran(endpoint: str, token: str, prompt: str, timeout: int) -> str:
    """ER:N — ALMAWARE's own from-scratch byte-LM (eran/chat_server.py).

    POST {endpoint}/chat with the server's native schema and return its reply.
    Loopback (local run OR an SSH tunnel to the DGX) is trusted without a token;
    `token` is only needed for remote/Cloudflare-fronted access.

    NOTE (honesty): Eran v1 is a tiny 4-layer byte-LM trained ONLY on Iddo's
    voice. It is a prototype, not a general Hebrew/NLP engine. The router keeps a
    real model in each Eran route's fallback so a low/empty answer can escalate.
    """
    url = f"{endpoint.rstrip('/')}/chat"
    body = {"prompt": prompt, "max": 200, "temperature": 0.85, "top_k": 40}
    headers = {"content-type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    out = _http_post(url, body, headers, timeout)
    if isinstance(out, dict) and out.get("error"):
        raise RuntimeError(f"eran: {out['error']}")
    reply = (out.get("reply", "") if isinstance(out, dict) else "") or ""
    if not reply.strip():
        # Empty generation -> treat as failure so route() falls back to a real model.
        raise RuntimeError("eran: empty reply")
    return reply


# --------------------------------------------------------------------------- #
# Dispatch
# --------------------------------------------------------------------------- #
def dispatch(cfg: dict, model_key: str, prompt: str) -> str:
    spec = cfg["models"][model_key]
    provider = spec["provider"]
    timeout = cfg["defaults"]["timeout_seconds"]

    if provider == "anthropic":
        return call_anthropic(spec["model_id"], prompt, timeout)
    if provider == "gemini":
        return call_gemini(spec["model_id"], prompt, timeout)
    if provider == "xai":
        return call_xai(spec["model_id"], prompt, timeout, spec.get("extra_body"))
    if provider == "ollama":
        endpoint = os.environ.get(spec["endpoint_env"], spec["endpoint_default"])
        return call_ollama(spec["model_id"], endpoint, prompt, timeout)
    if provider == "eran":
        endpoint = os.environ.get(spec["endpoint_env"], spec["endpoint_default"])
        token = os.environ.get(spec.get("token_env", "ERAN_TOKEN"), "")
        return call_eran(endpoint, token, prompt, timeout)
    raise RuntimeError(f"Unknown provider: {provider}")


def route(prompt: str, task: Optional[str] = None,
          dry_run: bool = False) -> dict:
    """Pick a model for the task, then call it (unless dry_run).

    Returns a dict: {task, model, provider, free, output|error}.
    On failure, walks defaults.fallback_chain before giving up.
    """
    cfg = load_config()
    task = task or classify(prompt)
    primary = pick_model(cfg, task)

    # Build the fallback chain: primary first, then the primary's own preferred
    # fallbacks (model spec "fallback_to" — e.g. eran-local -> eran-dgx4 -> sonnet
    # so a Hebrew/creative route degrades to a REAL model, not generic gemma2),
    # then the global fallback_chain. De-duped, order preserved.
    chain: list[str] = [primary]
    for fb in cfg["models"].get(primary, {}).get("fallback_to", []):
        if fb not in chain:
            chain.append(fb)
    for m in cfg["defaults"]["fallback_chain"]:
        if m not in chain:
            chain.append(m)

    result = {"task": task, "model": primary,
              "provider": cfg["models"][primary]["provider"],
              "free": cfg["models"][primary]["free"]}

    if dry_run:
        result["output"] = "(dry run — no call made)"
        return result

    last_err = None
    for model_key in chain:
        spec = cfg["models"].get(model_key)
        if not spec:
            continue
        try:
            out = dispatch(cfg, model_key, prompt)
            result.update(model=model_key, provider=spec["provider"],
                          free=spec["free"], output=out)
            if model_key != primary:
                result["fell_back_from"] = primary
            return result
        except Exception as exc:  # noqa: BLE001 — fall through to next model
            last_err = f"{model_key}: {exc}"
            continue

    result["error"] = f"all models failed; last: {last_err}"
    return result


# --------------------------------------------------------------------------- #
# Eran live-training health (read the heartbeat eran-live writes)
# --------------------------------------------------------------------------- #
def read_eran_status() -> Optional[dict]:
    """Return eran-live's latest training heartbeat, or None if it hasn't run."""
    try:
        with open(ERAN_STATUS_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _print_eran_status() -> int:
    st = read_eran_status()
    if not st:
        print(f"eran-live: no heartbeat yet ({ERAN_STATUS_PATH.name} missing). "
              f"Is the trainer running?", file=sys.stderr)
        return 1
    print("לזכרה של עלמה ז\"ל — ERAN live training\n")
    print(f"  host        {st.get('host', '?')}  ({st.get('device', '?')})")
    print(f"  gpus        {st.get('world_size', 1)}")
    print(f"  step        {st.get('step', '?'):,}" if isinstance(st.get('step'), int)
          else f"  step        {st.get('step', '?')}")
    print(f"  loss / ema  {st.get('loss', '?')} / {st.get('ema_loss', '?')}")
    print(f"  speed       {st.get('steps_per_s', '?')} steps/s  "
          f"({st.get('tokens_per_s', '?')} tok/s)")
    print(f"  vram        {st.get('vram_mb', '?')} MB")
    print(f"  updated     {st.get('updated', '?')}")
    return 0


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _print_fleet(cfg: dict) -> None:
    print("לזכרה של עלמה ז\"ל — ALMAWARE Fleet\n")
    print(f"{'MODEL':<14}{'PROVIDER':<11}{'TIER':<8}{'FREE':<6}BEST FOR")
    print("-" * 70)
    for key, m in cfg["models"].items():
        print(f"{key:<14}{m['provider']:<11}{m['cost_tier']:<8}"
              f"{'yes' if m['free'] else 'no':<6}{', '.join(m['best_for'])}")
    print("\nTask routing:")
    for t, model in cfg["task_routing"].items():
        print(f"  {t:<16} -> {model}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="ALMAWARE multi-AI fleet router")
    ap.add_argument("prompt", nargs="?", help="prompt text (or pipe via stdin)")
    ap.add_argument("--task", help="explicit task type (see fleet_config.json)")
    ap.add_argument("--auto", action="store_true",
                    help="auto-classify task from the prompt")
    ap.add_argument("--list", action="store_true", help="show the fleet and exit")
    ap.add_argument("--eran-status", action="store_true",
                    help="show eran-live's training heartbeat and exit")
    ap.add_argument("--dry-run", action="store_true",
                    help="show which model would be picked, don't call it")
    ap.add_argument("--json", action="store_true", help="emit full JSON result")
    args = ap.parse_args(argv)

    if args.eran_status:
        if args.json:
            st = read_eran_status()
            print(json.dumps(st, ensure_ascii=False, indent=2) if st else "null")
            return 0 if st else 1
        return _print_eran_status()

    cfg = load_config()
    if args.list:
        _print_fleet(cfg)
        return 0

    prompt = args.prompt
    if not prompt and not sys.stdin.isatty():
        prompt = sys.stdin.read().strip()
    if not prompt:
        ap.error("no prompt given (pass as arg or pipe via stdin)")

    task = None if args.auto else args.task
    res = route(prompt, task=task, dry_run=args.dry_run)

    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        tag = f"[{res['model']} · {res['provider']} · " \
              f"{'free' if res['free'] else 'paid'}]"
        print(tag, file=sys.stderr)
        print(res.get("output", res.get("error", "")))
    return 0 if "error" not in res else 1


if __name__ == "__main__":
    raise SystemExit(main())
