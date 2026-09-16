"""Bridge fleet models into the RAMCHAT council.

Usage:
    python council_bridge.py <provider> "<text>"          # ask + post answer to RAMCHAT
    python council_bridge.py <provider> "<text>" --no-post  # ask, print only

Providers are OpenAI-compatible llama-server / Colibri endpoints on the DGX
fleet. Answers are posted to the council via ramlink.py under the provider's
own name, so every member's words appear attributed in the GUI.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
GLM_KEY_FILE = Path(r"D:\CLAUDE\quorum\state\secrets\coli_api_key.txt")

PROVIDERS: dict[str, dict[str, object]] = {
    "gptoss": {
        "base": "http://<tailnet-ip>:8000",
        "model": "gpt-oss-120b",
        "post_as": "GPT-OSS 120B",
        "timeout": 180,
    },
    "qwen480b": {
        "base": "http://<tailnet-ip>:8080",
        "model": "qwen3-coder-480b",
        "post_as": "Qwen3-480B",
        "timeout": 180,
    },
    "glm52": {
        "base": "http://<tailnet-ip>:8800",
        "model": "glm-5.2",
        "post_as": "GLM-5.2",
        "timeout": 600,  # ~3 s/token out-of-core MoE; slow by design
        "key_file": GLM_KEY_FILE,
        "max_tokens": 200,
    },
}


def _clean_harmony(text: str) -> str:
    """Drop raw harmony analysis channels that llama.cpp can leak into content."""
    if "<|channel|>" in text and "<|message|>" in text:
        final = re.search(r"<\|channel\|>final<\|message\|>(.*?)(?:<\|end\|>|<\|return\|>|$)",
                          text, re.DOTALL)
        text = final.group(1) if final else text.rsplit("<|message|>", 1)[-1]
    return re.sub(r"<\|[a-z_]+\|>", "", text).strip()


def ask(provider: str, text: str) -> str:
    spec = PROVIDERS[provider]
    payload = {
        "model": spec["model"],
        "messages": [{"role": "user", "content": text}],
        "max_tokens": int(spec.get("max_tokens", 1024)),
        "temperature": 0.7,
        "stream": False,
    }
    headers = {"Content-Type": "application/json; charset=utf-8"}
    key_file = spec.get("key_file")
    if isinstance(key_file, Path) and key_file.exists():
        headers["Authorization"] = "Bearer " + key_file.read_text(encoding="utf-8").strip()
    request = urllib.request.Request(
        str(spec["base"]) + "/v1/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers=headers,
    )
    with urllib.request.urlopen(request, timeout=int(spec["timeout"])) as response:
        result = json.loads(response.read().decode("utf-8"))
    message = (result.get("choices") or [{}])[0].get("message", {})
    answer = _clean_harmony((message.get("content") or "").strip())
    if not answer:
        raise RuntimeError(f"{provider} returned empty content")
    return answer


def post(who: str, text: str) -> None:
    subprocess.run(
        [sys.executable, str(ROOT / "ramlink.py"), "post", who, text],
        cwd=ROOT, check=True,
        env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"},
    )


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    provider, text = sys.argv[1], sys.argv[2]
    if provider not in PROVIDERS:
        print(f"unknown provider {provider!r}; known: {', '.join(PROVIDERS)}")
        return 2
    answer = ask(provider, text)
    print(answer)
    if "--no-post" not in sys.argv[3:]:
        post(str(PROVIDERS[provider]["post_as"]), answer)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
