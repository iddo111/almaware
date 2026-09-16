#!/usr/bin/env python3
"""Read-only ALMA Studio console and DGX3/DGX4 status probe."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import mimetypes
import os
from pathlib import Path
import subprocess
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
MANIFEST = ROOT / "MODEL_MANIFEST.json"
SYSTEM_PROMPT = ROOT / "STUDIO_PROMPT.md"
SSH = os.environ.get("ALMA_STUDIO_SSH", r"C:\Windows\System32\OpenSSH\ssh.exe")
SSH_KEY = os.environ.get("ALMA_STUDIO_SSH_KEY", r"C:\Users\<user>\.ssh\id_ed25519")
BRAIN_URL = os.environ.get("ALMA_STUDIO_BRAIN_URL", "http://127.0.0.1:8095/v1").rstrip("/")
BRAIN_MODEL = "nvidia/nemotron-3-super"


def load_manifest() -> dict:
    with MANIFEST.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_system_prompt() -> str:
    text = SYSTEM_PROMPT.read_text(encoding="utf-8")
    fence = "```text"
    start = text.find(fence)
    if start < 0:
        raise RuntimeError("STUDIO_PROMPT.md is missing its text fence")
    start += len(fence)
    end = text.find("```", start)
    if end < 0:
        raise RuntimeError("STUDIO_PROMPT.md has an unterminated text fence")
    prompt = text[start:end].strip()
    if not prompt:
        raise RuntimeError("Studio system prompt is empty")
    return prompt


def call_brain(prompt: str, job_context: object = None, max_tokens: int = 1200) -> dict:
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt must be a non-empty string")
    if job_context is not None and not isinstance(job_context, dict):
        raise ValueError("job_context must be an object when provided")
    user_content = prompt.strip()
    if job_context:
        user_content += "\n\nCurrent shot contract JSON:\n" + json.dumps(
            job_context, ensure_ascii=False, indent=2
        )
    payload = {
        "model": BRAIN_MODEL,
        "messages": [
            {"role": "system", "content": load_system_prompt()},
            {"role": "user", "content": user_content},
        ],
        "max_tokens": max(64, min(4096, int(max_tokens))),
        "temperature": 0.35,
        "top_p": 0.9,
        "stream": False,
    }
    request = urllib.request.Request(
        BRAIN_URL + "/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=900) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Studio brain returned HTTP {exc.code}: {detail[:2000]}") from exc
    if result.get("model") != BRAIN_MODEL:
        raise RuntimeError("Studio brain returned a missing or wrong model identity")
    choices = result.get("choices") or []
    message = choices[0].get("message", {}) if choices and isinstance(choices[0], dict) else {}
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("Studio brain returned empty visible content")
    return {
        "content": content,
        "model": result["model"],
        "usage": result.get("usage") or {},
        "brain": result.get("alma_harness") or {},
    }


def _node_probe(node: dict) -> dict:
    target = node["ssh"]
    remote = (
        "date -Is; "
        "nvidia-smi --query-gpu=name,temperature.gpu,clocks_throttle_reasons.active "
        "--format=csv,noheader 2>/dev/null || true; "
        "df -B1 --output=avail /home 2>/dev/null | tail -n1; "
        "for p in ~/logs/alma-studio/*.pid; do "
        "test -f \"$p\" || continue; pid=$(cat \"$p\"); "
        "if kill -0 \"$pid\" 2>/dev/null; then s=running; else s=stopped; fi; "
        "printf 'JOB|%s|%s|%s\\n' \"$(basename \"$p\" .pid)\" \"$pid\" \"$s\"; done; "
        "for d in ~/models/alma-studio/*; do "
        "test -d \"$d\" || continue; printf 'SIZE|%s|' \"$(basename \"$d\")\"; "
        "du -sb \"$d\" 2>/dev/null | cut -f1; done; "
        "for c in ~/alma-studio/canaries/*; do "
        "test -d \"$c\" || continue; "
        "test \"$(basename \"$c\")\" = logs && continue; "
        "exit_file=$(find \"$c\" -maxdepth 1 -type f "
        "\\( -name exit_code -o -name '*.exit' \\) 2>/dev/null | sort | head -n1); "
        "if test -n \"$exit_file\"; then exit_code=$(tr -d '[:space:]' < \"$exit_file\"); "
        "elif test -f \"$c/failure-receipt.json\"; then exit_code=blocked; else exit_code=unknown; fi; "
        "artifact=$(find \"$c\" -maxdepth 2 -type f "
        "\\( -name '*.wav' -o -name '*.flac' -o -name '*.mp4' -o -name '*.mov' -o -name '*.mkv' -o -name '*.png' -o -name '*.exr' \\) "
        "2>/dev/null | sort | head -n1); "
        "if test -n \"$artifact\"; then artifact_name=$(basename \"$artifact\"); artifact_bytes=$(stat -c %s \"$artifact\"); else artifact_name=none; artifact_bytes=0; fi; "
        "test -f \"$c/SHA256SUMS\" -o -f \"$c/SHA256SUMS.txt\" -o -f \"$c/EVIDENCE_SHA256SUMS\" && sha=yes || sha=no; "
        "test -f \"$c/ffprobe.json\" && ffprobe=yes || ffprobe=no; "
        "test -f \"$c/provenance.json\" && provenance=yes || provenance=no; "
        "printf 'CANARY|%s|%s|%s|%s|%s|%s|%s\\n' \"$(basename \"$c\")\" \"$exit_code\" \"$artifact_name\" \"$artifact_bytes\" \"$sha\" \"$ffprobe\" \"$provenance\"; "
        "done"
    )
    command = [
        SSH, "-F", "none", "-o", "BatchMode=yes", "-o", "ConnectTimeout=6",
        "-o", "StrictHostKeyChecking=accept-new", "-i", SSH_KEY, target, remote,
    ]
    result = {
        "id": node["id"],
        "role": node["role"],
        "ok": False,
        "jobs": [],
        "sizes": {},
        "canaries": [],
    }
    try:
        proc = subprocess.run(
            command, capture_output=True, text=True, timeout=12,
            encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL,
        )
        lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
        if proc.returncode != 0:
            result["error"] = proc.stderr.strip() or f"ssh exit {proc.returncode}"
            return result
        result["ok"] = True
        result["time"] = lines[0] if lines else None
        result["gpu"] = lines[1] if len(lines) > 1 else None
        try:
            result["free_bytes"] = int(lines[2])
        except (IndexError, ValueError):
            result["free_bytes"] = None
        for line in lines[3:]:
            if line.startswith("JOB|"):
                _, name, pid, state = line.split("|", 3)
                result["jobs"].append({"name": name, "pid": pid, "state": state})
            elif line.startswith("SIZE|"):
                _, name, size = line.split("|", 2)
                try:
                    result["sizes"][name] = int(size)
                except ValueError:
                    pass
            elif line.startswith("CANARY|"):
                _, name, exit_code, artifact, size, sha, ffprobe, provenance = line.split("|", 7)
                try:
                    artifact_bytes = int(size)
                except ValueError:
                    artifact_bytes = 0
                technical_pass = (
                    exit_code == "0"
                    and artifact != "none"
                    and artifact_bytes > 0
                    and sha == "yes"
                    and ffprobe == "yes"
                    and provenance == "yes"
                )
                result["canaries"].append({
                    "name": name,
                    "exit_code": exit_code,
                    "artifact": None if artifact == "none" else artifact,
                    "artifact_bytes": artifact_bytes,
                    "sha_receipt": sha == "yes",
                    "ffprobe_receipt": ffprobe == "yes",
                    "provenance_receipt": provenance == "yes",
                    "technical_pass": technical_pass,
                    "human_review": "not-recorded",
                })
    except Exception as exc:  # status must degrade to data, never crash the console
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


def probe_nodes() -> list[dict]:
    nodes = load_manifest()["nodes"]
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(nodes)) as pool:
        return list(pool.map(_node_probe, nodes))


class StudioHandler(BaseHTTPRequestHandler):
    server_version = "ALMAStudio/0.1"

    def _json(self, data: object, status: int = 200) -> None:
        payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > 1_000_000:
            raise ValueError("request body must be between 1 byte and 1 MB")
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("request body must be a JSON object")
        return payload

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/api/health":
            self._json({"ok": True, "service": "alma-studio", "mode": "read-only-console"})
            return
        if path == "/api/manifest":
            self._json(load_manifest())
            return
        if path == "/api/nodes":
            self._json({"nodes": probe_nodes()})
            return
        if path == "/":
            path = "/index.html"
        candidate = (WEB / path.lstrip("/")).resolve()
        if WEB.resolve() not in candidate.parents or not candidate.is_file():
            self.send_error(404)
            return
        payload = candidate.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(candidate.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path != "/api/brain/plan":
            self._json({"error": "not found"}, 404)
            return
        try:
            payload = self._read_json()
            result = call_brain(
                payload.get("prompt"),
                payload.get("job_context"),
                payload.get("max_tokens", 1200),
            )
            self._json(result)
        except (ValueError, json.JSONDecodeError) as exc:
            self._json({"error": str(exc)}, 400)
        except Exception as exc:
            self._json({"error": str(exc)}, 502)

    def log_message(self, fmt: str, *args: object) -> None:
        print("[alma-studio]", fmt % args)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8810)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), StudioHandler)
    print(f"ALMA Studio listening on http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
