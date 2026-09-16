# לזכרה של עלמה ז״ל
"""QUORUM · ai_clients — the ONE lego for talking to any model.

Every provider (claude / grok / gemini CLIs, Alma Harness routes, Perplexity
HTTP, ollama locals) is reached through a single contract. There is exactly one
Reply shape and one error taxonomy.

ALMAWARE standards:
  * failure-is-a-value — ask() ALWAYS returns a Reply; it never raises. A timeout,
    a missing CLI, a crash — all become Reply(ok=False, error=<kind>, note=...).
  * ENABLED gate — while config.is_enabled() is False, ask()/astream() short-circuit
    to Reply(ok=False, error=DISABLED) and touch no external process. Born inert.

100% ours. stdlib only. No embedded API keys, no SDKs, no frameworks.
"""
from __future__ import annotations

import asyncio
import dataclasses
import enum
import hashlib
import hmac
import importlib.util
import ipaddress
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import AsyncIterator, Optional

import config


class ErrorKind(enum.Enum):
    NONE = "none"
    DISABLED = "disabled"          # master gate off
    NOT_INSTALLED = "not_installed"  # CLI / ollama not on PATH
    TIMEOUT = "timeout"
    EMPTY = "empty"                # ran but produced nothing
    BACKEND = "backend"            # non-zero exit / crash
    CANCELLED = "cancelled"


@dataclasses.dataclass
class Reply:
    """The frozen return contract. Truthy iff a live, non-empty answer came back."""
    ok: bool
    text: str = ""
    provider: str = ""
    model: str = ""
    error: ErrorKind = ErrorKind.NONE
    note: str = ""
    elapsed: float = 0.0
    correlation_id: str = ""
    turn_id: str = ""
    request_nonce: str = ""

    def __bool__(self) -> bool:  # `if reply:` == got a real answer
        return self.ok and bool(self.text)


@dataclasses.dataclass
class Chunk:
    """One streamed piece. kind in {"text","status"}."""
    kind: str
    text: str = ""
    provider: str = ""
    correlation_id: str = ""
    turn_id: str = ""
    request_nonce: str = ""


# ── how each CLI provider is invoked ─────────────────────────────────────────
# 100% ours orchestration — argv is always passed with shell=False.  The three
# CLIs do not share a prompt contract: Claude accepts stdin, while current Grok
# and Gemini require the value immediately after -p/--prompt.  Keeping that
# distinction here prevents an executable-presence check from becoming a false
# claim that a provider is callable.
_CLI_BASE = {
    "claude": ["claude", "-p", "--output-format", "text"],
    "grok": [
        "grok", "--output-format", "plain", "--no-subagents",
        "--disable-web-search", "--no-memory", "--permission-mode", "plan",
        "--verbatim",
    ],
    "gemini": [
        "gemini", "--output-format", "text", "--approval-mode", "plan",
    ],
}

_ALMA_MODELS = {
    "alma:nemotron": {
        "model": "nvidia/nemotron-3-super",
        "label": "Nemotron 3 Super 120B (Alma Harness)",
        "route": "nemotron",
    },
    "alma:gptoss120b": {
        "model": "openai/gpt-oss-120b",
        "label": "GPT-OSS 120B (Alma Harness)",
        "route": "gptoss120b",
    },
}
_MAX_ALMA_RESPONSE = 4 * 1024 * 1024

# ── local DGX fleet (the 4D council, via the ONE alma-router on eran1) ───────
# Since 2026-08-17: one model family per DGX box, all fronted by a single
# OpenAI-compatible router (alma-router v3, :8010 on eran1).  The model NAME
# selects the box.  Same admission law as every provider: the /v1/models
# listing is discovery only; the first real non-empty turn is the gate, and
# each chat reply must echo the exact model asked for.  The URL lives in
# config (env or state\settings.json), never here — a distributable must not
# embed one LAN's addresses.
# NOTE (2026-09-15): this map is LABEL/SPEC hints only — it is NOT the
# fleet roster. The roster is the router's LIVE /v1/models response, fetched
# by _detect_fleet_models at runtime; an id here appears as a participant
# only while the live listing contains it. Legacy ids below are kept so old
# transcripts/callers still resolve, but they surface only if live-listed.
# "maverick" (Llama-4 Maverick 400B) was RETIRED — removed from the fleet, so
# its entry is deleted here and it must never appear as up/available.
_FLEET_MODELS = {
    # Legacy candidate ids (kept for back-compat; live listing gates them).
    "qwen3-coder-480b": {
        "model": "qwen3-coder-480b",
        "label": "Qwen3-Coder 480B (eran1+2+3 pipeline · 4D router)",
        "url_attr": "FLEET_ROUTER_URL",
    },
    "qwen3-coder-next-fp8": {
        "model": "qwen3-coder-next-fp8",
        "label": "Qwen3-Coder-Next FP8 (eran1 · 4D router)",
        "url_attr": "FLEET_ROUTER_URL",
    },
    "glm-4.7-flash": {
        "model": "glm-4.7-flash",
        "label": "GLM-4.7 Flash (eran2 · 4D router)",
        "url_attr": "FLEET_ROUTER_URL",
    },
    "nemotron-3-super": {
        "model": "nemotron-3-super",
        "label": "Nemotron-3 Super (eran3 · 4D router)",
        "url_attr": "FLEET_ROUTER_URL",
    },
    "gpt-oss-120b": {
        "model": "gpt-oss-120b",
        "label": "GPT-OSS 120B (eran2 · 4D router)",
        "url_attr": "FLEET_ROUTER_URL",
    },
    # LIVE fleet ids (router /v1/models, verified 2026-09-15).
    "moonshotai/kimi-k3": {
        "model": "moonshotai/kimi-k3",
        "label": "Kimi K3 (moonshotai · 4D router)",
        "url_attr": "FLEET_ROUTER_URL",
    },
    "nvidia/nemotron-3-super-120b-a12b": {
        "model": "nvidia/nemotron-3-super-120b-a12b",
        "label": "Nemotron 3 Super 120B (nvidia · 4D router)",
        "url_attr": "FLEET_ROUTER_URL",
    },
    "z-ai/glm-5.3-flash": {
        "model": "z-ai/glm-5.3-flash",
        "label": "GLM-5.3 Flash (z-ai · 4D router)",
        "url_attr": "FLEET_ROUTER_URL",
    },
}
# gpt-oss spends Harmony "analysis" tokens before its answer; budget for both.
_FLEET_MAX_TOKENS = 2048

# ── Perplexity chat-completions (HTTP, key-gated) ────────────────────────────
# Key presence (PERPLEXITY_API_KEY) is discovery only, exactly like a CLI being
# on PATH: the first real non-empty turn remains the admission gate.  The key
# VALUE must never appear in logs, notes, or transcripts — every error note
# passes through _redact_perplexity_key before it can travel.
_PERPLEXITY_URL = "https://api.perplexity.ai/chat/completions"
_PERPLEXITY_DEFAULT = "perplexity:sonar"
_PERPLEXITY_MODELS = {
    "perplexity:sonar": {
        "model": "sonar",
        "label": "Perplexity Sonar",
        "default": True,
    },
    "perplexity:sonar-pro": {
        "model": "sonar-pro",
        "label": "Perplexity Sonar Pro",
        "default": False,
    },
}

CODEX_INTERACTIVE_ID = "codex-interactive"
_CODEX_INTERACTIVE_LABEL = "Codex (interactive MCP bridge)"
_INTERACTIVE_MODULE_CACHE: dict[str, object] = {}


def _cli_invocation(provider: str, prompt: str) -> tuple[list[str], Optional[str]]:
    """Return (argv, stdin).  No shell is involved and prompts stay data."""
    base = _CLI_BASE.get(provider)
    if not base:
        raise ValueError(f"unknown provider {provider!r}")
    if provider == "claude":
        return list(base), prompt
    if provider == "grok":
        return [*base, "-p", prompt], None
    return [*base, "-p", prompt], None


def _which(name: str) -> Optional[str]:
    try:
        return shutil.which(name)
    except Exception:
        return None


def _materialize_command(cmd: list[str]) -> list[str]:
    """Resolve a logical CLI command to an executable argv without a shell.

    npm exposes Gemini as a Windows ``.cmd`` shim, which CreateProcess cannot
    execute directly.  Invoke its installed JavaScript entry point with Node
    instead of using ``cmd.exe /c``.
    """
    executable = _which(cmd[0])
    if not executable:
        raise FileNotFoundError(f"{cmd[0]} not on PATH")
    if executable.lower().endswith((".cmd", ".bat")):
        if cmd[0] != "gemini":
            raise FileNotFoundError(f"unsupported command shim for {cmd[0]}")
        node = _which("node")
        entry = os.path.join(
            os.path.dirname(executable), "node_modules", "@google", "gemini-cli",
            "bundle", "gemini.js",
        )
        if not node or not os.path.isfile(entry):
            raise FileNotFoundError("Gemini Node entry point is not installed")
        return [node, entry, *cmd[1:]]
    return [executable, *cmd[1:]]


def _validated_private_root(raw: str, label: str) -> str:
    """Shared guard for every private HTTP provider root (Alma Harness, DGX
    fleet): absolute http(s), no credentials/query/fragment/path, and the host
    must be loopback, RFC-1918 private, or Tailscale (CGNAT / .ts.net)."""
    if not raw:
        raise ValueError(f"{label} is not configured")
    parsed = urllib.parse.urlsplit(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"{label} must be an absolute http(s) URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
        raise ValueError(f"{label} cannot contain credentials, query, fragment, or path")
    host = parsed.hostname.lower()
    private = host == "localhost" or host.endswith(".ts.net")
    if not private:
        try:
            address = ipaddress.ip_address(host)
            tailscale_cgnat = address.version == 4 and address in ipaddress.ip_network("<tailnet-ip>/10")
            private = address.is_private or address.is_loopback or tailscale_cgnat
        except ValueError:
            private = False
    if not private:
        raise ValueError(f"{label} must be loopback, private-address, or Tailscale-only")
    if parsed.scheme == "http" and not (host == "localhost" or private and not host.endswith(".ts.net")):
        raise ValueError("Tailscale DNS routes must use HTTPS")
    return raw.rstrip("/")


def _validated_alma_root() -> str:
    return _validated_private_root(config.ALMA_HARNESS_URL, "ALMA_HARNESS_URL")


def _validated_fleet_root(provider: str) -> str:
    spec = _FLEET_MODELS[provider]
    return _validated_private_root(getattr(config, spec["url_attr"], ""), spec["url_attr"])


def _validated_interactive_paths() -> tuple[Path, Path]:
    """Return the exact bridge module/database paths or fail closed.

    The bridge is executable Python, so Quorum never searches for it and never
    imports a relative/default path.  Its SQLite database must already exist:
    joining the stdio MCP provider creates it; model discovery is read-only with
    respect to bridge creation.
    """
    if not config.codex_interactive_configured():
        raise ValueError("interactive Codex bridge is not explicitly configured")

    root_raw = Path(config.CODEX_INTERACTIVE_ROOT)
    if not root_raw.is_absolute():
        raise ValueError("QUORUM_CODEX_INTERACTIVE_ROOT must be absolute")
    root = root_raw.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("interactive Codex bridge root is not a directory")

    bridge = (root / "bridge_state.py").resolve(strict=True)
    if bridge.parent != root or not bridge.is_file():
        raise ValueError("bridge_state.py must be a regular file directly under the configured root")

    database_raw = Path(config.CODEX_INTERACTIVE_DB)
    if not database_raw.is_absolute():
        raise ValueError("QUORUM_CODEX_INTERACTIVE_DB must be absolute")
    database = database_raw.resolve(strict=True)
    if not database.is_file():
        raise ValueError("interactive Codex bridge database does not exist")
    return bridge, database


def _load_interactive_bridge():
    """Load only the validated configured bridge_state.py module."""
    bridge_path, _database_path = _validated_interactive_paths()
    cache_key = str(bridge_path)
    cached = _INTERACTIVE_MODULE_CACHE.get(cache_key)
    if cached is not None:
        return cached

    module_name = (
        "_quorum_codex_interactive_bridge_"
        + hashlib.sha256(cache_key.encode("utf-8")).hexdigest()[:16]
    )
    spec = importlib.util.spec_from_file_location(module_name, bridge_path)
    if spec is None or spec.loader is None:
        raise ValueError("cannot load configured bridge_state.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    if getattr(module, "CODEX_INTERACTIVE_ID", None) != CODEX_INTERACTIVE_ID:
        sys.modules.pop(module_name, None)
        raise ValueError("configured bridge provider identity does not match codex-interactive")
    if not callable(getattr(module, "BridgeStore", None)):
        sys.modules.pop(module_name, None)
        raise ValueError("configured bridge has no callable BridgeStore")
    _INTERACTIVE_MODULE_CACHE[cache_key] = module
    return module


def _interactive_store():
    module = _load_interactive_bridge()
    _bridge_path, database_path = _validated_interactive_paths()
    return module.BridgeStore(str(database_path))


def _store_has_exact_active_participant(store) -> bool:
    status = store.status()
    if not isinstance(status, dict):
        return False
    if status.get("canonical_provider_id") != CODEX_INTERACTIVE_ID:
        return False
    participants = status.get("participants")
    if not isinstance(participants, list):
        return False
    return any(
        isinstance(item, dict)
        and item.get("participant_id") == CODEX_INTERACTIVE_ID
        and item.get("active") is True
        for item in participants
    )


def _interactive_provider_active() -> bool:
    """Exact active-participant proof for discovery; never raises."""
    if not config.codex_interactive_configured():
        return False
    try:
        return _store_has_exact_active_participant(_interactive_store())
    except Exception:
        return False


def _read_json_response(response, label: str = "Alma Harness") -> dict:
    raw = response.read(_MAX_ALMA_RESPONSE + 1)
    if len(raw) > _MAX_ALMA_RESPONSE:
        raise ValueError(f"{label} response exceeded 4 MiB")
    value = json.loads(raw or b"{}")
    if not isinstance(value, dict):
        raise ValueError(f"{label} response must be a JSON object")
    return value


def _detect_alma_models() -> list[dict]:
    root = _validated_alma_root()
    request = urllib.request.Request(root + "/v1/models", method="GET")
    with urllib.request.urlopen(request, timeout=8) as response:
        value = _read_json_response(response)
    available = {
        item.get("id"): item for item in value.get("data", [])
        if isinstance(item, dict) and item.get("ready") is True
    }
    result = []
    for provider, spec in _ALMA_MODELS.items():
        item = available.get(spec["model"])
        if item and item.get("owned_by") == "alma-local":
            result.append({
                "id": provider,
                "provider": "alma",
                "model": spec["model"],
                "label": spec["label"],
                "default": True,
            })
    return result


def _strip_harmony_channels(text: str) -> str:
    """gpt-oss served by llama.cpp can leave raw Harmony scaffolding in content
    ('<|channel|>analysis<|message|>…<|end|>answer').  Keep only the final
    channel (or the segment after the last <|end|>); the analysis channel is
    reasoning, not the answer.  Plain text passes through untouched."""
    if "<|" not in text:
        return text
    final = "<|channel|>final<|message|>"
    if final in text:
        text = text.rsplit(final, 1)[1]
    elif "<|end|>" in text:
        text = text.rsplit("<|end|>", 1)[1]
    elif "<|message|>" in text:
        text = text.rsplit("<|message|>", 1)[1]
    for token in ("<|return|>", "<|end|>", "<|start|>", "<|call|>"):
        if token in text:
            text = text.split(token, 1)[0]
    return re.sub(r"<\|[^|>]{1,32}\|>", "", text).strip()


def _detect_fleet_models() -> list[dict]:
    """Fleet discovery: a provider appears only when its server's /v1/models
    lists the exact expected model id.  Presence is discovery only — the first
    real non-empty turn remains the admission gate.  Never raises."""
    out: list[dict] = []
    listings: dict[str, set] = {}  # root -> listed ids (all 4D providers share one router)
    for provider, spec in _FLEET_MODELS.items():
        try:
            root = _validated_fleet_root(provider)
        except Exception:
            continue  # unconfigured = provider simply absent
        if root not in listings:
            try:
                request = urllib.request.Request(root + "/v1/models", method="GET")
                with urllib.request.urlopen(request, timeout=8) as response:
                    value = _read_json_response(response, provider)
                listings[root] = {item.get("id") for item in value.get("data", [])
                                  if isinstance(item, dict)}
            except Exception:
                listings[root] = set()  # unreachable server = its providers absent
        if spec["model"] in listings[root]:
            out.append({"id": provider, "provider": "fleet",
                        "model": spec["model"], "label": spec["label"],
                        "default": True})
    return out


def _ask_fleet(prompt: str, provider: str, system: str, timeout: float,
               started: float) -> Reply:
    """One chat-completions turn against a local llama.cpp fleet server.
    Mirrors _ask_alma: stdlib HTTP, exact-model echo required, failure-is-a-value."""
    spec = _FLEET_MODELS[provider]

    def failed(kind: ErrorKind, note: str) -> Reply:
        return Reply(False, provider=provider, model=spec["model"], error=kind,
                     note=note[:400], elapsed=round(time.monotonic() - started, 2))

    try:
        root = _validated_fleet_root(provider)
    except ValueError as exc:
        return failed(ErrorKind.NOT_INSTALLED, str(exc))

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    payload = json.dumps({
        "model": spec["model"],
        "messages": messages,
        "stream": False,
        "max_tokens": _FLEET_MAX_TOKENS,
        "temperature": 0,
        "top_p": 0.9,
        "seed": 42,
    }, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        root + "/v1/chat/completions",
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            value = _read_json_response(response, provider)
    except (TimeoutError, subprocess.TimeoutExpired):
        return failed(ErrorKind.TIMEOUT, f"timeout after {timeout}s")
    except urllib.error.HTTPError as exc:
        return failed(ErrorKind.BACKEND, f"{provider} HTTP {exc.code}")
    except urllib.error.URLError as exc:
        return failed(ErrorKind.BACKEND, f"{provider} unreachable: {exc.reason}")
    except Exception as exc:  # noqa: BLE001 — failure-is-a-value
        return failed(ErrorKind.BACKEND, str(exc))

    if value.get("model") != spec["model"]:
        return failed(ErrorKind.BACKEND,
                      f"{provider} returned a different model than asked for")
    choices = value.get("choices") or []
    content = ""
    if choices and isinstance(choices[0], dict):
        message = choices[0].get("message") or {}
        content = message.get("content", "") if isinstance(message, dict) else ""
    text = _strip_harmony_channels(content.strip()) if isinstance(content, str) else ""
    if not text:
        return failed(ErrorKind.EMPTY, "empty output")
    return Reply(True, text=text, provider=provider, model=spec["model"],
                 elapsed=round(time.monotonic() - started, 2))


def _perplexity_spec(provider: str) -> dict:
    """Model spec for a perplexity id; a bare "perplexity" means the default."""
    return _PERPLEXITY_MODELS.get(provider) or _PERPLEXITY_MODELS[_PERPLEXITY_DEFAULT]


def _redact_perplexity_key(text: str, key: str) -> str:
    """Strip the credential from any note before it can reach a transcript."""
    if key and text:
        text = text.replace(key, "<PERPLEXITY_API_KEY>")
    return text


def _ask_perplexity(prompt: str, provider: str, system: str, timeout: float,
                    started: float) -> Reply:
    """One Perplexity chat-completions turn over stdlib HTTP.

    The API key is read live from the environment at call time — never cached,
    never logged, never echoed.  A missing key is NOT_INSTALLED (unavailable),
    not a crash; every failure note is redacted defensively."""
    spec = _perplexity_spec(provider)
    model = spec["model"]
    key = config.perplexity_api_key()

    def failed(kind: ErrorKind, note: str) -> Reply:
        return Reply(False, provider=provider, model=model, error=kind,
                     note=_redact_perplexity_key(note, key)[:400],
                     elapsed=round(time.monotonic() - started, 2))

    if not key:
        return failed(ErrorKind.NOT_INSTALLED,
                      "PERPLEXITY_API_KEY is not set — provider unavailable")

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    payload = json.dumps({
        "model": model,
        "messages": messages,
        "stream": False,
        "max_tokens": 512,
        "temperature": 0,
    }, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        _PERPLEXITY_URL,
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + key,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            value = _read_json_response(response, "Perplexity")
    except (TimeoutError, subprocess.TimeoutExpired):
        return failed(ErrorKind.TIMEOUT, f"timeout after {timeout}s")
    except urllib.error.HTTPError as exc:
        return failed(ErrorKind.BACKEND, f"Perplexity HTTP {exc.code}")
    except urllib.error.URLError as exc:
        return failed(ErrorKind.BACKEND, f"Perplexity unreachable: {exc.reason}")
    except Exception as exc:  # noqa: BLE001 — redact before the note can travel
        return failed(ErrorKind.BACKEND, str(exc))

    choices = value.get("choices") or []
    content = ""
    if choices and isinstance(choices[0], dict):
        message = choices[0].get("message") or {}
        content = message.get("content", "") if isinstance(message, dict) else ""
    text = content.strip() if isinstance(content, str) else ""
    if not text:
        return failed(ErrorKind.EMPTY, "empty output")
    return Reply(True, text=text, provider=provider, model=model,
                 elapsed=round(time.monotonic() - started, 2))


def detect_models() -> list[dict]:
    """Best-effort candidate discovery. Never raises; returns [] on total failure.

    Alma candidates require a ready model-list response. CLI entries mean the
    executable is installed; the first real turn remains their callability gate.
    Perplexity entries mean PERPLEXITY_API_KEY is present — same rule: presence
    is discovery only, admission is a real non-empty first turn.
    Shape: {id, provider, model, label, default}."""
    out: list[dict] = []
    for mid, label in config.CLI_LABELS.items():
        if _which(mid):
            out.append({"id": mid, "provider": mid, "model": mid, "label": label,
                        "default": mid in config.CLI_DEFAULTS})
    if config.ALMA_HARNESS_URL:
        try:
            out.extend(_detect_alma_models())
        except Exception:
            pass  # route listing is evidence only when it validates completely
    out.extend(_detect_fleet_models())
    if config.perplexity_api_key():
        for provider, spec in _PERPLEXITY_MODELS.items():
            out.append({"id": provider, "provider": "perplexity",
                        "model": spec["model"], "label": spec["label"],
                        "default": spec["default"]})
    if _interactive_provider_active():
        out.append({
            "id": CODEX_INTERACTIVE_ID,
            "provider": CODEX_INTERACTIVE_ID,
            "model": CODEX_INTERACTIVE_ID,
            "label": _CODEX_INTERACTIVE_LABEL,
            "default": False,
        })
    # ollama locals
    if _which("ollama"):
        try:
            r = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=10,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            for line in (r.stdout or "").splitlines()[1:]:
                name = line.split()[0] if line.split() else ""
                if not name:
                    continue
                short = name.split(":")[0]
                out.append({"id": f"ollama:{name}", "provider": "ollama", "model": name,
                            "label": f"{name} (local)",
                            "default": short in config.OLLAMA_DEFAULT_SHORTS})
        except Exception:
            pass  # failure-is-a-value: locals simply won't appear
    return out


def _provider_model(model_id: str) -> tuple[str, str]:
    if model_id.startswith("ollama:"):
        return "ollama", model_id.split(":", 1)[1]
    if model_id in _ALMA_MODELS:
        return "alma", _ALMA_MODELS[model_id]["model"]
    if model_id in _FLEET_MODELS:
        return "fleet", _FLEET_MODELS[model_id]["model"]
    if model_id == "perplexity" or model_id in _PERPLEXITY_MODELS:
        return "perplexity", _perplexity_spec(model_id)["model"]
    if model_id == CODEX_INTERACTIVE_ID:
        return CODEX_INTERACTIVE_ID, CODEX_INTERACTIVE_ID
    return model_id, model_id


def _ask_alma(prompt: str, provider: str, system: str, timeout: float, started: float) -> Reply:
    spec = _ALMA_MODELS[provider]
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    payload = json.dumps({
        "model": spec["model"],
        "messages": messages,
        "stream": False,
        "max_tokens": 512,
        "temperature": 0,
        "top_p": 0.9,
        "seed": 42,
        "reasoning_effort": "low",
    }, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        _validated_alma_root() + "/v1/chat/completions",
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            value = _read_json_response(response)
    except (TimeoutError, subprocess.TimeoutExpired):
        return Reply(False, provider=provider, model=spec["model"], error=ErrorKind.TIMEOUT,
                     note=f"timeout after {timeout}s", elapsed=round(time.monotonic() - started, 2))
    except urllib.error.HTTPError as exc:
        return Reply(False, provider=provider, model=spec["model"], error=ErrorKind.BACKEND,
                     note=f"Alma Harness HTTP {exc.code}", elapsed=round(time.monotonic() - started, 2))
    except urllib.error.URLError as exc:
        return Reply(False, provider=provider, model=spec["model"], error=ErrorKind.BACKEND,
                     note=f"Alma Harness route unavailable: {exc.reason}",
                     elapsed=round(time.monotonic() - started, 2))

    routed = value.get("alma_harness") or {}
    if value.get("model") != spec["model"] or routed.get("model_key") != spec["route"]:
        return Reply(False, provider=provider, model=spec["model"], error=ErrorKind.BACKEND,
                     note="Alma Harness returned a different model or route",
                     elapsed=round(time.monotonic() - started, 2))
    choices = value.get("choices") or []
    content = ""
    if choices and isinstance(choices[0], dict):
        message = choices[0].get("message") or {}
        content = message.get("content", "") if isinstance(message, dict) else ""
    text = content.strip() if isinstance(content, str) else ""
    elapsed = round(time.monotonic() - started, 2)
    if not text:
        return Reply(False, provider=provider, model=spec["model"], error=ErrorKind.EMPTY,
                     note="empty output", elapsed=elapsed)
    return Reply(True, text=text, provider=provider, model=spec["model"], elapsed=elapsed)


def _entitlement_failure(stderr: str) -> bool:
    """Recognize hard auth/licensing failures even when a CLI exits zero."""
    lowered = (stderr or "").lower()
    return any(marker in lowered for marker in (
        "permission-denied",
        "requires a grok subscription",
        "doesn't have any credits or licenses",
        "organization has disabled claude subscription access",
    ))


def _ask_interactive(prompt: str, correlation_id: str, timeout: float,
                     started: float) -> Reply:
    """Enqueue and await one exact, correlated stdio-MCP contribution."""
    provider = CODEX_INTERACTIVE_ID
    correlation = correlation_id.strip() if isinstance(correlation_id, str) else ""
    turn_id = ""
    request_nonce = ""

    def failed(kind: ErrorKind, note: str) -> Reply:
        return Reply(
            False,
            provider=provider,
            model=provider,
            error=kind,
            note=note[:400],
            elapsed=round(time.monotonic() - started, 2),
            correlation_id=correlation,
            turn_id=turn_id,
            request_nonce=request_nonce,
        )

    if not correlation:
        return failed(ErrorKind.BACKEND, "interactive Codex requires a debate correlation_id")

    try:
        store = _interactive_store()
        if not _store_has_exact_active_participant(store):
            return failed(ErrorKind.BACKEND, "codex-interactive participant is not active")

        turn = store.enqueue_turn(
            prompt,
            debate_id=correlation,
            participant_id=CODEX_INTERACTIVE_ID,
        )
        if not isinstance(turn, dict):
            return failed(ErrorKind.BACKEND, "interactive bridge returned an invalid turn")
        turn_id = turn.get("turn_id", "")
        request_nonce = turn.get("request_nonce", "")
        if not all((
            turn.get("participant_id") == CODEX_INTERACTIVE_ID,
            turn.get("debate_id") == correlation,
            isinstance(turn_id, str) and bool(turn_id),
            isinstance(request_nonce, str) and bool(request_nonce),
        )):
            return failed(ErrorKind.BACKEND, "interactive bridge turn correlation mismatch")

        deadline = started + max(0.0, float(timeout))
        while True:
            completed = store.completed_turn(turn_id)
            if completed is not None:
                if not isinstance(completed, dict):
                    return failed(ErrorKind.BACKEND, "interactive bridge returned an invalid contribution")
                response = completed.get("response", "")
                digest = completed.get("response_sha256", "")
                exact = all((
                    completed.get("participant_id") == CODEX_INTERACTIVE_ID,
                    completed.get("debate_id") == correlation,
                    completed.get("turn_id") == turn_id,
                    completed.get("request_nonce") == request_nonce,
                    isinstance(response, str),
                    isinstance(digest, str),
                    bool(digest),
                ))
                if not exact:
                    return failed(
                        ErrorKind.BACKEND,
                        "interactive contribution correlation mismatch",
                    )
                expected_digest = hashlib.sha256(response.encode("utf-8")).hexdigest()
                if not hmac.compare_digest(digest, expected_digest):
                    return failed(ErrorKind.BACKEND, "interactive contribution digest mismatch")
                text = response.strip()
                if not text:
                    return failed(ErrorKind.EMPTY, "interactive contribution was empty")
                return Reply(
                    True,
                    text=text,
                    provider=provider,
                    model=provider,
                    elapsed=round(time.monotonic() - started, 2),
                    correlation_id=correlation,
                    turn_id=turn_id,
                    request_nonce=request_nonce,
                )

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return failed(
                    ErrorKind.TIMEOUT,
                    f"interactive contribution timeout after {timeout}s",
                )
            time.sleep(min(0.05, remaining))
    except Exception as exc:  # failure-is-a-value; bridge errors do not escape
        return failed(ErrorKind.BACKEND, str(exc))


def ask(prompt: str, provider: str, model: str = "", *,
        system: str = "", timeout: float = config.PER_TURN_TIMEOUT,
        correlation_id: str = "") -> Reply:
    """Blocking single call. ALWAYS returns a Reply — never raises."""
    t0 = time.monotonic()
    if not config.is_enabled():
        return Reply(False, provider=provider, model=model, error=ErrorKind.DISABLED,
                     note=config.disabled_note())
    prov, mdl = _provider_model(provider)
    full = (system + "\n\n" + prompt) if system else prompt
    try:
        if prov == "alma":
            return _ask_alma(prompt, provider, system, timeout, t0)
        if prov == "fleet":
            return _ask_fleet(prompt, provider, system, timeout, t0)
        if prov == "perplexity":
            return _ask_perplexity(prompt, provider, system, timeout, t0)
        if prov == CODEX_INTERACTIVE_ID:
            return _ask_interactive(full, correlation_id, timeout, t0)
        if prov == "ollama" or provider.startswith("ollama:"):
            _, mdl = _provider_model(provider)
            if not _which("ollama"):
                return Reply(False, provider="ollama", model=mdl, error=ErrorKind.NOT_INSTALLED,
                             note="ollama not on PATH")
            cmd = ["ollama", "run", mdl]
        else:
            try:
                cmd, stdin_text = _cli_invocation(prov, full)
            except ValueError:
                return Reply(False, provider=prov, model=mdl, error=ErrorKind.BACKEND,
                             note=f"unknown provider {prov!r}")
            try:
                cmd = _materialize_command(cmd)
            except FileNotFoundError as exc:
                return Reply(False, provider=prov, model=mdl, error=ErrorKind.NOT_INSTALLED,
                             note=str(exc))
        if prov == "ollama" or provider.startswith("ollama:"):
            stdin_text = full
        r = subprocess.run(cmd, input=stdin_text, shell=False, capture_output=True, text=True,
                           timeout=timeout, encoding="utf-8", errors="replace",
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        text = (r.stdout or "").strip()
        el = round(time.monotonic() - t0, 2)
        if _entitlement_failure(r.stderr or ""):
            return Reply(False, provider=prov, model=mdl, error=ErrorKind.BACKEND,
                         note="provider authentication or entitlement refused the request", elapsed=el)
        if r.returncode != 0:
            return Reply(False, provider=prov, model=mdl, error=ErrorKind.BACKEND,
                         note=(r.stderr or "non-zero exit").strip()[:400], elapsed=el)
        if not text:
            return Reply(False, provider=prov, model=mdl, error=ErrorKind.EMPTY,
                         note="empty output", elapsed=el)
        return Reply(True, text=text, provider=prov, model=mdl, elapsed=el)
    except subprocess.TimeoutExpired:
        return Reply(False, provider=prov, model=mdl, error=ErrorKind.TIMEOUT,
                     note=f"timeout after {timeout}s", elapsed=round(time.monotonic() - t0, 2))
    except Exception as e:  # noqa: BLE001 — failure-is-a-value, nothing escapes
        return Reply(False, provider=prov, model=mdl, error=ErrorKind.BACKEND,
                     note=str(e)[:400], elapsed=round(time.monotonic() - t0, 2))


async def astream(prompt: str, provider: str, model: str = "", *,
                  system: str = "", timeout: float = config.PER_TURN_TIMEOUT,
                  cancel: Optional[asyncio.Event] = None,
                  correlation_id: str = "") -> AsyncIterator[Chunk]:
    """Async streaming wrapper. SCAFFOLD: runs ask() off-thread and yields the whole
    answer as one text chunk (true token-streaming is a TODO — see README §Roadmap).
    Never raises; a failed call is emitted as a status chunk carrying the note."""
    if cancel and cancel.is_set():
        yield Chunk("status", "[cancelled]", provider=provider,
                    correlation_id=correlation_id)
        return
    reply = await asyncio.to_thread(
        ask,
        prompt,
        provider,
        model,
        system=system,
        timeout=timeout,
        correlation_id=correlation_id,
    )
    if cancel and cancel.is_set():
        yield Chunk("status", "[cancelled]", provider=provider,
                    correlation_id=correlation_id)
        return
    if reply:
        yield Chunk(
            "text",
            reply.text,
            provider=reply.provider,
            correlation_id=reply.correlation_id or correlation_id,
            turn_id=reply.turn_id,
            request_nonce=reply.request_nonce,
        )
    else:
        yield Chunk(
            "status",
            f"[{reply.error.value}: {reply.note}]",
            provider=reply.provider,
            correlation_id=reply.correlation_id or correlation_id,
            turn_id=reply.turn_id,
            request_nonce=reply.request_nonce,
        )
