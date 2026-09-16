"""OpenAI-compatible HTTP backend — local models on the fleet.

Reaches llama-server, Colibri/GLM, vLLM and Ollama with one code path. Unlike
the browser backend there is no session to expire; the only auth is a bearer
token read from the environment.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

DEFAULT_TIMEOUT = 300


class HttpError(RuntimeError):
    pass


def chat(base_url: str, model: str, messages: list[dict], *,
         api_key_env: str | None = None, tools: list | None = None,
         max_tokens: int = 1024, temperature: float = 0.2,
         timeout_s: int = DEFAULT_TIMEOUT) -> dict:
    """POST /v1/chat/completions and return the raw response dict."""
    payload: dict = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    headers = {"Content-Type": "application/json"}
    if api_key_env:
        key = os.getenv(api_key_env, "")
        if key:
            headers["Authorization"] = f"Bearer {key}"

    req = urllib.request.Request(
        base_url.rstrip("/") + "/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:400]
        raise HttpError(f"HTTP {exc.code} from {base_url}: {body}") from exc
    except urllib.error.URLError as exc:
        raise HttpError(f"cannot reach {base_url}: {exc.reason}") from exc


def first_message(resp: dict) -> dict:
    try:
        return resp["choices"][0]["message"]
    except (KeyError, IndexError) as exc:
        raise HttpError(f"unexpected response shape: {json.dumps(resp)[:300]}") from exc


def finish_reason(resp: dict) -> str:
    try:
        return resp["choices"][0].get("finish_reason", "")
    except (KeyError, IndexError):
        return ""


def answer_text(msg: dict) -> str:
    """gpt-oss (harmony format) streams its thinking into `reasoning_content`
    and only fills `content` once it commits to a final answer. A too-small
    max_tokens therefore yields an EMPTY answer plus a stub of reasoning, which
    reads like the model ignored you. Surface that rather than returning ''.
    """
    content = (msg.get("content") or "").strip()
    if content:
        return content
    reasoning = (msg.get("reasoning_content") or "").strip()
    if reasoning:
        return (f"[no final answer — model was still reasoning when it hit the "
                f"token limit; raise --max-tokens]\n\nreasoning so far: {reasoning}")
    return ""
