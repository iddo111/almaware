# לזכרה של עלמה ז״ל
"""QUORUM · registry — the fleet model registry + multi-model router.

One place that knows every way to reach a model:

  * "openai"  — any OpenAI-compatible /v1/chat/completions endpoint
                (the 4D fleet router's live /v1/models seats, local Ollama,
                anything Iddo adds in state\\registry.json).
  * "agent"   — clod's coder harness (POST /api/agent {"goal": ...}); QUORUM
                CALLS it, never reimplements it.
  * "worker"  — models donated by browser workers (Gemma WebGPU etc.); routed
                through the workers job queue.
  * "cli"/"ollama"/"alma"/"perplexity" — the existing ai_clients providers,
                merged in unchanged so the debate arena and the rooms share
                one model list.

Health checks are real HTTP probes with a short timeout, cached for
HEALTH_TTL seconds, and never block /api/models for more than the probe cap.

ALMAWARE standards: failure-is-a-value — chat() ALWAYS returns a dict with
ok/text/error, never raises; probes that fail mark the model "down", they do
not take the server down. stdlib only.
"""
from __future__ import annotations

import concurrent.futures
import json
import threading
import time
import urllib.error
import urllib.request

import config
import stateio

# ── built-in fleet (curl-verified 2026-08-08) ────────────────────────────────
# Every entry can be overridden / extended by state\registry.json (same shape).
BUILTIN_MODELS = [
    {
        "id": "gpt-oss-120b",
        "label": "GPT-OSS 120B · eran4 (47 tok/s)",
        "type": "openai",
        "base": "http://<tailnet-ip>:8000",
        "model": "gpt-oss-120b",
        "key_env": "",
        "max_tokens": 1024,
        "timeout": 180,
        "default": True,
        "slow": False,
    },
    # RETIRED 2026-09-15 (broken-windows W5-QUORUM): seat "glm-5.2" (GLM-5.2 358B colibri,
    # openai, http://<tailnet-ip>:8800, key COLI_API_KEY). Dead since FABLE-A1 09-11: eran4 has
    # no :8800 listener and no colibri units (measured 09-15 08:4x), the model was deleted from
    # the fleet, and QUORUM showed it DOWN (WinError 10061) in every roster. Same treatment as
    # the maverick note in ai_clients.py. RESTORE: uncomment the dict below (or copy it from
    # registry.py.bak-bw-20260915) once a colibri server answers /v1/models with "glm-5.2" again.
    # {
    #     "id": "glm-5.2",
    #     "label": "GLM-5.2 358B · colibri eran4 (איטי — ~3 שנ' לטוקן)",
    #     "type": "openai",
    #     "base": "http://<tailnet-ip>:8800",
    #     "model": "glm-5.2",
    #     "key_env": "COLI_API_KEY",
    #     "max_tokens": 256,
    #     "timeout": 1200,
    #     "default": False,
    #     "slow": True,
    # },
    # RETIRED 2026-09-11 (holy harness law): seat "coder-harness" (agent, https://<tailnet-host>:8449)
    # pointed at the eran4 GLM Coder UI, archived to F:/ALMAWARE-ARCHIVE/HARNESSES-20260911/eran4-glm-coder-8449.
    {
        "id": "ollama-local",
        "label": "Ollama (מכונה זו)",
        "type": "ollama-http",
        "base": "http://127.0.0.1:11434",
        "model": "",           # expands to one entry per installed model
        "key_env": "",
        "max_tokens": 1024,
        "timeout": 300,
        "default": False,
        "slow": False,
    },
]

HEALTH_TTL = 20.0          # seconds a probe result stays fresh
PROBE_TIMEOUT = 6.0        # per-endpoint health probe cap
_MAX_RESPONSE = 8 * 1024 * 1024

_REGISTRY_FILE = stateio.STATE_DIR + "\\registry.json"

_lock = threading.RLock()
_health_cache: dict[str, dict] = {}    # id -> {"state","detail","at"}
_ollama_cache: dict = {"at": 0.0, "models": []}

# Set by server.py at boot so worker-donated models appear in the list and
# chat() can route to them. Kept as a module attribute to avoid an import cycle.
workers_module = None


# ── registry assembly ────────────────────────────────────────────────────────

def _file_models() -> list[dict]:
    raw = stateio.load_json(_REGISTRY_FILE, {})
    out = []
    if isinstance(raw, dict):
        for item in raw.get("models", []):
            if isinstance(item, dict) and item.get("id") and item.get("type"):
                out.append(item)
    return out


_NOT_LISTED = "not in live /v1/models listing"   # _probe detail suffix; list_models hides these
_router_cache: dict = {"at": -1e9, "ids": None}
_router_lock = threading.Lock()


def _router_ids() -> list[str] | None:
    """The 4D fleet router's LIVE /v1/models ids (config.FLEET_ROUTER_URL) --
    the one source of truth for which router seats exist. Cached HEALTH_TTL.
    Unconfigured or unreachable = None: no router seats are added and QUORUM
    still starts. Never raises."""
    root = (getattr(config, "FLEET_ROUTER_URL", "") or "").rstrip("/")
    if not root:
        return None
    with _router_lock:
        if time.monotonic() - _router_cache["at"] < HEALTH_TTL:
            return _router_cache["ids"]
    ids = None
    try:
        with urllib.request.urlopen(root + "/v1/models", timeout=PROBE_TIMEOUT) as r:
            data = json.loads(r.read(_MAX_RESPONSE) or b"{}")
        ids = [str(i["id"]) for i in data.get("data", []) if isinstance(i, dict) and i.get("id")]
    except Exception:
        ids = None
    with _router_lock:
        _router_cache["at"] = time.monotonic()
        _router_cache["ids"] = ids
    return ids


def _router_label(model_id: str) -> str:
    try:
        import ai_clients as c
        hint = c._FLEET_MODELS.get(model_id, {}).get("label")
    except Exception:
        hint = None
    return hint or f"{model_id} · 4D router"


def _http_entries() -> list[dict]:
    """Live router seats + built-ins + registry.json overrides (file wins on id
    collision). Router seats come only from the router's live listing."""
    merged: dict[str, dict] = {}
    root = (getattr(config, "FLEET_ROUTER_URL", "") or "").rstrip("/")
    for mid in _router_ids() or []:
        merged[mid] = {"id": mid, "label": _router_label(mid), "type": "openai",
                       "base": root, "model": mid, "key_env": "", "max_tokens": 1024,
                       "timeout": 300, "default": False, "slow": False}
    for m in BUILTIN_MODELS:
        merged[m["id"]] = dict(m)
    for m in _file_models():
        base = merged.get(m["id"], {})
        base.update(m)
        merged[m["id"]] = base
    return list(merged.values())


def _entry_by_id(model_id: str) -> dict | None:
    for m in _http_entries():
        if m["id"] == model_id:
            return m
        if m.get("type") == "ollama-http" and model_id.startswith(m["id"] + ":"):
            e = dict(m)
            e["model"] = model_id.split(":", 1)[1]
            e["id"] = model_id
            return e
    return None


def _list_ollama_models(entry: dict) -> list[str]:
    now = time.monotonic()
    if now - _ollama_cache["at"] < HEALTH_TTL and _ollama_cache["models"]:
        return _ollama_cache["models"]
    try:
        with urllib.request.urlopen(entry["base"] + "/api/tags", timeout=PROBE_TIMEOUT) as r:
            data = json.loads(r.read(_MAX_RESPONSE) or b"{}")
        names = [m.get("name", "") for m in data.get("models", []) if m.get("name")]
        _ollama_cache["at"] = now
        _ollama_cache["models"] = names
        return names
    except Exception:
        return []


# ── health ───────────────────────────────────────────────────────────────────

def _probe(entry: dict) -> dict:
    """One live HTTP probe. Returns {"state": up|auth|down, "detail": str}."""
    base = (entry.get("base") or "").rstrip("/")
    typ = entry.get("type")
    try:
        if typ == "agent":
            req = urllib.request.Request(base + "/health", method="GET")
            with urllib.request.urlopen(req, timeout=PROBE_TIMEOUT) as r:
                data = json.loads(r.read(65536) or b"{}")
            if data.get("ready") is True:
                return {"state": "up", "detail": "ready"}
            return {"state": "down", "detail": "harness not ready"}
        if typ == "ollama-http":
            with urllib.request.urlopen(base + "/api/tags", timeout=PROBE_TIMEOUT) as r:
                data = json.loads(r.read(_MAX_RESPONSE) or b"{}")
            n = len(data.get("models", []))
            return {"state": "up", "detail": f"{n} local models"}
        # openai-compatible: an HTTP 200 alone proves the ROUTER is up, not
        # that THIS model is served. Require the entry's model id to be
        # present in the live /v1/models listing; absent = down/absent.
        headers = {}
        key = stateio.load_secret(entry["key_env"]) if entry.get("key_env") else ""
        if key:
            headers["Authorization"] = "Bearer " + key
        req = urllib.request.Request(base + "/v1/models", headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=PROBE_TIMEOUT) as r:
            raw = r.read(_MAX_RESPONSE)
        want = entry.get("model") or entry.get("id") or ""
        if not want:
            return {"state": "up", "detail": "200"}
        try:
            listed = {item.get("id") for item in (json.loads(raw or b"{}").get("data", []))
                      if isinstance(item, dict)}
        except Exception:
            return {"state": "down", "detail": "unreadable /v1/models listing"}
        if want in listed:
            return {"state": "up", "detail": "listed"}
        return {"state": "down", "detail": f"{want!r} {_NOT_LISTED}"}
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            need = entry.get("key_env") or "API key"
            return {"state": "auth",
                    "detail": f"endpoint is up but needs {need} "
                              f"(env or state\\secrets\\{(entry.get('key_env') or '').lower()}.txt)"}
        return {"state": "down", "detail": f"HTTP {exc.code}"}
    except Exception as exc:  # noqa: BLE001 — a dead probe is a value
        return {"state": "down", "detail": str(exc)[:160]}


def health(model_id: str) -> dict:
    entry = _entry_by_id(model_id)
    if entry is None:
        return {"state": "unknown", "detail": "not in registry"}
    with _lock:
        cached = _health_cache.get(entry["id"])
        if cached and time.monotonic() - cached["at"] < HEALTH_TTL:
            return {"state": cached["state"], "detail": cached["detail"]}
    result = _probe(entry)
    with _lock:
        _health_cache[entry["id"]] = {**result, "at": time.monotonic()}
    return result


def probe_all(parallel: bool = True) -> dict[str, dict]:
    """Fresh-enough health for every HTTP entry, probed concurrently so the
    slowest dead endpoint costs one PROBE_TIMEOUT, not a sum."""
    entries = _http_entries()
    out: dict[str, dict] = {}
    stale = []
    now = time.monotonic()
    with _lock:
        for e in entries:
            cached = _health_cache.get(e["id"])
            if cached and now - cached["at"] < HEALTH_TTL:
                out[e["id"]] = {"state": cached["state"], "detail": cached["detail"]}
            else:
                stale.append(e)
    if stale:
        if parallel and len(stale) > 1:
            with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, len(stale))) as ex:
                results = list(ex.map(_probe, stale))
        else:
            results = [_probe(e) for e in stale]
        with _lock:
            for e, r in zip(stale, results):
                _health_cache[e["id"]] = {**r, "at": time.monotonic()}
                out[e["id"]] = r
    return out


# ── listing ──────────────────────────────────────────────────────────────────

def list_models(include_health: bool = True, include_cli: bool = True) -> list[dict]:
    """The one model list: fleet HTTP + harness + ollama expansion + worker
    models + the ai_clients CLI/alma/perplexity providers. Never raises."""
    out: list[dict] = []
    health_map = probe_all() if include_health else {}

    for e in _http_entries():
        h = health_map.get(e["id"], {"state": "unknown", "detail": ""})
        if h.get("state") == "down" and str(h.get("detail", "")).endswith(_NOT_LISTED):
            continue   # the endpoint answered and its own listing says this model is not served (retired)
        if e.get("type") == "ollama-http":
            if h.get("state") != "up":
                continue
            for name in _list_ollama_models(e):
                out.append({
                    "id": f"{e['id']}:{name}", "label": f"{name} (local)",
                    "type": "ollama-http", "provider": "ollama-http",
                    "default": False, "slow": False,
                    "health": h,
                })
            continue
        out.append({
            "id": e["id"], "label": e.get("label", e["id"]),
            "type": e.get("type"), "provider": e.get("type"),
            "default": bool(e.get("default")), "slow": bool(e.get("slow")),
            "health": h,
        })

    # worker-donated models (browser Gemma etc.)
    wm = workers_module
    if wm is not None:
        try:
            for m in wm.donated_models():
                out.append({
                    "id": m["id"], "label": m["label"],
                    "type": "worker", "provider": "worker",
                    "default": False, "slow": False,
                    "health": {"state": "up", "detail": m["detail"]},
                })
        except Exception:
            pass

    if include_cli:
        try:
            import ai_clients as c
            seen = {m["id"] for m in out}
            # Per-entry tolerance (2026-09-15, W5-QUORUM): this whole block sits
            # in one try/except, so a single candidate missing "label" or
            # "provider" used to raise KeyError and silently drop EVERY CLI
            # seat (claude/grok/gemini/alma/...) from the roster -- shakla then
            # saw <2 live models. A malformed entry now costs only itself.
            for m in c.detect_models():
                mid = m.get("id") if isinstance(m, dict) else None
                if not mid or mid in seen:
                    continue     # malformed, or a registry entry already covers this id
                provider = m.get("provider") or mid
                out.append({
                    "id": mid, "label": m.get("label") or mid,
                    "type": provider, "provider": provider,
                    "default": bool(m.get("default")), "slow": False,
                    "health": {"state": "installed",
                               "detail": "presence is discovery; first turn is the gate"},
                })
        except Exception:
            pass
    return out


# ── routing ──────────────────────────────────────────────────────────────────

def _messages_to_prompt(messages: list[dict]) -> str:
    parts = []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if role == "system":
            parts.append(content)
        else:
            parts.append(content if role == "user" else f"[assistant]: {content}")
    return "\n\n".join(p for p in parts if p)


import re as _re

_HARMONY_TOKEN = _re.compile(r"<\|[^|>]{1,32}\|>")
_HARMONY_HEADER = _re.compile(r"<\|channel\|>[a-z_ ]{1,24}<\|message\|>")
_HARMONY_FINAL = _re.compile(
    r"<\|channel\|>final<\|message\|>(.*?)(?:<\|[^|>]{1,32}\|>|$)", _re.S)


def _clean_harmony(text: str) -> str:
    """gpt-oss via llama.cpp can return raw Harmony channel scaffolding.
    Observed live shapes (curl-verified against eran4:8000):
      '<|channel|>analysis<|message|>…<|end|>ANSWER'
      '<|channel|>analysis<|message|>…<|channel|>final<|message|>ANSWER<|return|>'
    Prefer the explicit final channel; else whatever follows the LAST <|end|>;
    else the text with control tokens stripped. Plain text passes through."""
    if "<|" not in text:
        return text
    m = _HARMONY_FINAL.search(text)
    if m and m.group(1).strip():
        return m.group(1).strip()
    if "<|end|>" in text:
        tail = _HARMONY_TOKEN.sub("", text.rsplit("<|end|>", 1)[1]).strip()
        if tail:
            return tail
    if _HARMONY_HEADER.search(text):
        # A channel header but no final channel and no <|end|> tail: the
        # generation was cut off INSIDE the analysis channel (small
        # max_tokens). Returning the remainder would leak raw chain-of-thought
        # as if it were the answer — fail empty instead (caller reports it).
        return ""
    return _HARMONY_TOKEN.sub("", _HARMONY_HEADER.sub("", text)).strip()


def _fail(model_id: str, error: str, note: str, t0: float) -> dict:
    return {"ok": False, "text": "", "model": model_id, "error": error,
            "note": note[:400], "elapsed": round(time.monotonic() - t0, 2)}


def _chat_openai(entry: dict, messages: list[dict], t0: float,
                 max_tokens: int, timeout: float, temperature: float) -> dict:
    base = entry["base"].rstrip("/")
    headers = {"Content-Type": "application/json"}
    key = stateio.load_secret(entry["key_env"]) if entry.get("key_env") else ""
    if key:
        headers["Authorization"] = "Bearer " + key
    payload = json.dumps({
        "model": entry.get("model") or entry["id"],
        "messages": messages,
        "stream": False,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(base + "/v1/chat/completions", data=payload,
                                 headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            value = json.loads(r.read(_MAX_RESPONSE) or b"{}")
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            return _fail(entry["id"], "auth",
                         f"401 — set {entry.get('key_env') or 'API key'} "
                         "(env or state\\secrets file)", t0)
        return _fail(entry["id"], "backend", f"HTTP {exc.code}", t0)
    except (TimeoutError, urllib.error.URLError) as exc:
        return _fail(entry["id"], "timeout" if isinstance(exc, TimeoutError) else "backend",
                     str(getattr(exc, "reason", exc))[:200], t0)
    except Exception as exc:  # noqa: BLE001
        return _fail(entry["id"], "backend", str(exc), t0)
    choices = value.get("choices") or []
    content = ""
    if choices and isinstance(choices[0], dict):
        msg = choices[0].get("message") or {}
        if isinstance(msg, dict):
            content = msg.get("content") or msg.get("reasoning_content") or ""
    text = _clean_harmony(content.strip()) if isinstance(content, str) else ""
    if not text:
        return _fail(entry["id"], "empty", "empty output", t0)
    return {"ok": True, "text": text, "model": entry["id"], "error": "none",
            "note": "", "elapsed": round(time.monotonic() - t0, 2)}


def _chat_agent(entry: dict, messages: list[dict], t0: float, timeout: float) -> dict:
    """Route to clod's coder harness: last user content becomes the goal."""
    goal = ""
    for m in reversed(messages):
        if m.get("role") == "user" and m.get("content"):
            goal = m["content"]
            break
    if not goal:
        return _fail(entry["id"], "backend", "no user goal in messages", t0)
    payload = json.dumps({"goal": goal}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(entry["base"].rstrip("/") + "/api/agent",
                                 data=payload,
                                 headers={"Content-Type": "application/json"},
                                 method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            value = json.loads(r.read(_MAX_RESPONSE) or b"{}")
    except Exception as exc:  # noqa: BLE001
        return _fail(entry["id"], "backend", f"harness: {exc}"[:300], t0)
    summary = str(value.get("summary") or "")
    ok = bool(value.get("ok"))
    steps = value.get("actions") or value.get("steps") or []
    detail = ""
    if isinstance(steps, list) and steps:
        detail = "\n\n[harness actions: " + ", ".join(
            str(s.get("action", s) if isinstance(s, dict) else s) for s in steps[:24]) + "]"
    text = (summary + detail).strip()
    if not ok or not text:
        return _fail(entry["id"], "backend",
                     ("harness returned ok=false: " + (summary or json.dumps(value)[:200])), t0)
    return {"ok": True, "text": text, "model": entry["id"], "error": "none",
            "note": "", "elapsed": round(time.monotonic() - t0, 2)}


def chat(model_id: str, messages: list[dict], *, timeout: float = 0.0,
         max_tokens: int = 0, temperature: float = 0.2) -> dict:
    """Route one chat turn to ANY registered model. ALWAYS returns a dict
    {ok, text, model, error, note, elapsed}; never raises."""
    t0 = time.monotonic()
    if not config.is_enabled():
        return _fail(model_id, "disabled", config.disabled_note(), t0)
    if not isinstance(messages, list) or not messages:
        return _fail(model_id, "backend", "messages must be a non-empty list", t0)

    # worker-donated model → job queue
    if model_id.startswith("worker:") and workers_module is not None:
        try:
            return workers_module.chat_via_worker(
                model_id, messages, timeout or 120.0, t0)
        except Exception as exc:  # noqa: BLE001
            return _fail(model_id, "backend", f"worker route: {exc}", t0)

    entry = _entry_by_id(model_id)
    if entry is not None:
        eff_timeout = timeout or float(entry.get("timeout") or 180)
        eff_max = max_tokens or int(entry.get("max_tokens") or 1024)
        if entry.get("type") == "agent":
            return _chat_agent(entry, messages, t0, eff_timeout)
        if entry.get("type") in ("openai", "ollama-http"):
            return _chat_openai(entry, messages, t0, eff_max, eff_timeout, temperature)
        return _fail(model_id, "backend", f"unroutable type {entry.get('type')!r}", t0)

    # fall through to the existing ai_clients providers (claude/grok/gemini
    # CLIs, alma:, perplexity:, ollama: ids) — one Reply contract.
    try:
        import ai_clients as c
        system = ""
        rest = messages
        if messages and messages[0].get("role") == "system":
            system = messages[0].get("content", "")
            rest = messages[1:]
        prompt = _messages_to_prompt(rest)
        reply = c.ask(prompt, model_id, system=system,
                      timeout=timeout or config.PER_TURN_TIMEOUT)
        return {"ok": bool(reply), "text": reply.text, "model": model_id,
                "error": reply.error.value, "note": reply.note,
                "elapsed": reply.elapsed}
    except Exception as exc:  # noqa: BLE001
        return _fail(model_id, "backend", str(exc), t0)
