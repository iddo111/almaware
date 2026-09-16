# לזכרה של עלמה ז״ל
"""QUORUM · config — single source of truth for the safe-default gate + wiring.

ALMAWARE standards:
  * ENABLED defaults to False. Nothing calls an external model, binds a public
    surface, or runs a debate until this is deliberately turned on (config here
    or the QUORUM_ENABLED env var). Born inert.
  * failure-is-a-value: helpers never raise; they return plain values.

100% ours. stdlib only. No frameworks.
"""
from __future__ import annotations

import json
import os
import sys

# In a cx_Freeze build __file__ points inside lib\library.zip, where nothing
# can be read or written; anchor all on-disk paths to the exe directory there.
BASE_DIR: str = (os.path.dirname(sys.executable) if getattr(sys, "frozen", False)
                 else os.path.dirname(os.path.abspath(__file__)))


def _settings() -> dict:
    """state\\settings.json — survives restarts, unlike env vars set in one
    shell. Env always wins; the file is the fallback. Never raises."""
    try:
        path = os.path.join(BASE_DIR, "state", "settings.json")
        with open(path, "r", encoding="utf-8") as f:
            value = json.load(f)
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


_S = _settings()

# ── MASTER GATE ──────────────────────────────────────────────────────────────
# The whole system is inert until this is True. Flip here OR set env
# QUORUM_ENABLED=1. While False the server still boots (so you can see status),
# but every model-invoking endpoint returns a clear "disabled" value instead of
# reaching out to any model. Safe by construction.
ENABLED: bool = False

# ── network (safe defaults) ──────────────────────────────────────────────────
# Loopback-only by default. To reach it from a phone over Tailscale, set
# QUORUM_HOST=0.0.0.0 or put {"host": "0.0.0.0"} in state\settings.json —
# the server's _authorized() gate still restricts callers to loopback+tailnet.
HOST: str = os.environ.get("QUORUM_HOST", "") or str(_S.get("host") or "127.0.0.1")
PORT: int = int(os.environ.get("QUORUM_PORT", "") or _S.get("port") or 8099)

# Optional shared secret: if set, non-loopback / non-Tailscale callers must pass
# it via  X-Token  header or  ?token=  . Empty = no token path (loopback only).
TOKEN: str = os.environ.get("QUORUM_TOKEN", "") or str(_S.get("token") or "")

# Private-LAN admission.  OFF by default so a distributable stays loopback+tailnet
# only.  When True, _authorized() also admits RFC1918 callers (10/8, 172.16/12,
# 192.168/16) plus link-local — i.e. other devices on the operator's own home
# network.  This is NOT the public internet: reaching the port from outside still
# requires the host firewall rule AND a router port-forward.  Turn on with env
# QUORUM_ALLOW_LAN=1 or {"allow_lan": true} in state\settings.json, and only
# together with HOST=0.0.0.0 (a loopback bind never sees a LAN packet anyway).
ALLOW_LAN: bool = (
    os.environ.get("QUORUM_ALLOW_LAN", "").strip().lower() in {"1", "true", "yes"}
    or _S.get("allow_lan") is True
)

# Optional private Alma Harness root.  It has no public default because a
# distributable must not embed one user's tailnet hostname.  Current deployments
# set this explicitly, for example in the launching process environment.
ALMA_HARNESS_URL: str = os.environ.get("ALMA_HARNESS_URL", "").strip().rstrip("/")

# ── local DGX fleet (the 4D router — OpenAI-compatible, one URL for all four) ─
# Since 2026-08-17 the fleet is ONE router (alma-router v3, systemd on eran1)
# fronting one model family per DGX box; the model NAME selects the box.  The
# router self-repairs two backend traps (glm no-think injection, nemotron/
# gpt-oss minimum max_tokens), so Quorum just speaks plain chat-completions.
# Same no-default rule as ALMA_HARNESS_URL: a distributable must not embed one
# LAN's addresses.  Deployments set env QUORUM_FLEET_ROUTER_URL or
# "fleet_router_url" in state\settings.json.  Empty = no fleet on this machine.
FLEET_ROUTER_URL: str = (os.environ.get("QUORUM_FLEET_ROUTER_URL", "").strip()
                         or str(_S.get("fleet_router_url") or "")).rstrip("/")

# Optional exact-provider bridge for the current interactive Codex session.
# This is deliberately stricter than the master gate: all three environment
# values must be set before ai_clients will even inspect the bridge.  The
# configured root is expected to contain bridge_state.py; the database is
# created/joined by the separate stdio MCP bridge, never by Quorum discovery.
CODEX_INTERACTIVE_ENABLED: bool = (
    os.environ.get("QUORUM_CODEX_INTERACTIVE_ENABLED", "").strip().lower()
    in {"1", "true", "yes"}
)
CODEX_INTERACTIVE_ROOT: str = os.environ.get(
    "QUORUM_CODEX_INTERACTIVE_ROOT", ""
).strip()
CODEX_INTERACTIVE_DB: str = os.environ.get(
    "QUORUM_CODEX_INTERACTIVE_DB", ""
).strip()

# ── model registry (labels only; live detection lives in ai_clients) ─────────
# The trained models are "the rock"; we only orchestrate them.
CLI_LABELS = {
    "claude": "Claude (Opus)",
    "grok":   "Grok",
    "gemini": "Gemini",
}
# Which CLI models are pre-ticked in the UI.
CLI_DEFAULTS = ("claude", "grok", "gemini")
# Local ollama short-names surfaced as defaults (code/reasoning specialists).
OLLAMA_DEFAULT_SHORTS = ("deepseek-r1", "deepseek-coder", "qwen2.5", "gemma3")

# Who writes the closing מסקנה (synthesis), best-available first.  Among the
# 4D fleet the order is fastest-reliable first (measured 2026-08-17); the
# מסקנה is ADVISORY — the orchestrating (king) session issues the binding פסק.
SYNTH_PREFERENCE = ("claude", "alma:nemotron", "gemini", "grok",
                    "alma:gptoss120b", "qwen3-coder-next-fp8", "glm-4.7-flash",
                    "gpt-oss-120b", "nemotron-3-super",
                    "ollama:deepseek-r1:8b", "ollama:qwen2.5:7b")

# ── debate limits ────────────────────────────────────────────────────────────
MIN_ROUNDS = 1
MAX_ROUNDS = 5
DEFAULT_ROUNDS = 3
PER_TURN_TIMEOUT = 200.0     # seconds per model per turn
SYNTH_TIMEOUT = 220.0

# Where rendered transcripts are written (PDF/HTML per standing rule).
OUTPUT_DIR = os.environ.get(
    "QUORUM_OUTPUT_DIR", os.path.join(BASE_DIR, "debates"))


def is_enabled() -> bool:
    """True only if the master gate is on (config OR env OR the persistent
    state\\settings.json). Never raises."""
    if os.environ.get("QUORUM_ENABLED", "").strip() in ("1", "true", "True", "yes"):
        return True
    if _S.get("enabled") is True:
        return True
    return bool(ENABLED)


def disabled_note() -> str:
    return ("QUORUM is DISABLED (safe default). Click the green הפעל·Enable "
            "button (or set env QUORUM_ENABLED=1 / config.ENABLED=True) to "
            "allow it to reach models.")


def codex_interactive_configured() -> bool:
    """True only for an explicit, complete bridge configuration."""
    return bool(
        CODEX_INTERACTIVE_ENABLED
        and CODEX_INTERACTIVE_ROOT
        and CODEX_INTERACTIVE_DB
    )


def perplexity_api_key() -> str:
    """Perplexity API key, read live from the environment on every call.

    Never cached at import, never logged, never written to disk.  An empty
    string means the provider is unavailable — that absence is a value, not an
    error.  Only ai_clients touches the returned value, and only to build the
    Authorization header."""
    return os.environ.get("PERPLEXITY_API_KEY", "").strip()
