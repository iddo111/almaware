from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from computer_use import (
    ComputerUseError,
    ComputerUseSession,
    UnavailableComputerBackend,
)


PROJECT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = PROJECT_DIR / "allowlist.json"
STOP_PATH = PROJECT_DIR / "STOP"
AUDIT_PATH = PROJECT_DIR / "logs" / "audit.jsonl"
AGENT_ENDPOINT = "https://api.perplexity.ai/v1/agent"
DEFAULT_MODEL = "perplexity/sonar"
MAX_AGENT_TURNS = 4
MAX_REQUEST_BYTES = 4_000_000
MAX_RESPONSE_BYTES = 4_000_000


class PolicyError(RuntimeError):
    pass


class StopRequested(RuntimeError):
    pass


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class LocalPolicyHarness:
    def __init__(
        self,
        config_path: Path = CONFIG_PATH,
        audit_path: Path = AUDIT_PATH,
        stop_path: Path = STOP_PATH,
        approval: Callable[[str, dict[str, Any]], bool] | None = None,
        computer_session: ComputerUseSession | None = None,
        observe_only: bool = False,
    ) -> None:
        self.config = json.loads(config_path.read_text(encoding="utf-8"))
        self.root = Path(self.config["workspace_root"]).resolve()
        self.audit_path = audit_path
        self.stop_path = stop_path
        self.approval = approval or self._interactive_approval
        self.computer_session = computer_session or ComputerUseSession(
            UnavailableComputerBackend(),
            stop_path,
            observe_only=observe_only,
        )
        self.observe_only = observe_only
        self.session_id = uuid.uuid4().hex
        self.tool_specs = {item["name"]: item for item in self.config["tools"]}
        self.handlers = {
            "pc_status": self._pc_status,
            "list_workspace": self._list_workspace,
            "read_workspace_text": self._read_workspace_text,
            "run_diagnostic": self._run_diagnostic,
            "list_windows": self._list_windows,
            "observe_window": self._observe_window,
            "computer_action": self._computer_action,
        }

    def tool_definitions(self) -> list[dict[str, Any]]:
        tools = list(self.config["tools"])
        if self.observe_only:
            tools = [item for item in tools if item["name"] != "computer_action"]
        return tools

    def check_stop(self) -> None:
        if self.stop_path.exists():
            raise StopRequested(f"Kill switch present: {self.stop_path}")

    def execute(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        started = time.monotonic()
        decision = "denied"
        success = False
        exit_code: int | None = None
        result: dict[str, Any] = {"ok": False}
        try:
            self.check_stop()
            self._validate_call(name, args)
            if not self.approval(name, args):
                result = {"ok": False, "denied": True, "message": "Local user denied this action."}
                return result
            decision = "allowed_once"
            result = self.handlers[name](args)
            success = bool(result.get("ok"))
            exit_code = result.get("exit_code")
            return result
        except (PolicyError, StopRequested, ComputerUseError) as exc:
            result = {"ok": False, "error": type(exc).__name__, "message": str(exc)}
            return result
        except Exception as exc:  # Fail closed; do not return traceback or environment details.
            result = {"ok": False, "error": type(exc).__name__, "message": str(exc)[:300]}
            return result
        finally:
            self._audit(
                name=name,
                args=args,
                decision=decision,
                duration_ms=round((time.monotonic() - started) * 1000),
                success=success,
                exit_code=exit_code,
                result=result,
            )

    def _audit(
        self,
        name: str,
        args: dict[str, Any],
        decision: str,
        duration_ms: int,
        success: bool,
        exit_code: int | None,
        result: dict[str, Any],
    ) -> None:
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "utc": datetime.now(timezone.utc).isoformat(),
            "session_id": self.session_id,
            "tool": name,
            "args_sha256": hashlib.sha256(canonical_json(args).encode("utf-8")).hexdigest(),
            "decision": decision,
            "duration_ms": duration_ms,
            "success": success,
            "exit_code": exit_code,
        }
        for key in ("observation_id", "screenshot_sha256", "risk_class"):
            value = result.get(key)
            if isinstance(value, str):
                record[key] = value
        window = result.get("window")
        if isinstance(window, dict) and isinstance(window.get("id"), str):
            record["target_window_id"] = window["id"]
        elif isinstance(result.get("window_id"), str):
            record["target_window_id"] = result["window_id"]
        with self.audit_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(canonical_json(record) + "\n")

    def _interactive_approval(self, name: str, args: dict[str, Any]) -> bool:
        print("\nLOCAL ACTION REQUEST / בקשת פעולה מקומית")
        if name in {"list_windows", "observe_window", "computer_action"}:
            view = self.computer_session.approval_view(name, args)
        else:
            view = {"tool": name, "risk_class": "read_only", "arguments": args}
        print(json.dumps(view, ensure_ascii=False, indent=2, sort_keys=True))
        answer = input("ALLOW ONCE? [y/N]: ").strip().lower()
        return answer in {"y", "yes"}

    def _validate_call(self, name: str, args: dict[str, Any]) -> None:
        if name not in self.tool_specs or name not in self.handlers:
            raise PolicyError(f"Tool is not allowlisted: {name}")
        if not isinstance(args, dict):
            raise PolicyError("Tool arguments must be a JSON object.")
        schema = self.tool_specs[name]["parameters"]
        properties = schema.get("properties", {})
        unknown = set(args) - set(properties)
        if unknown:
            raise PolicyError(f"Unknown argument(s): {', '.join(sorted(unknown))}")
        missing = set(schema.get("required", [])) - set(args)
        if missing:
            raise PolicyError(f"Missing argument(s): {', '.join(sorted(missing))}")
        for key, value in args.items():
            spec = properties[key]
            expected = spec.get("type")
            if expected == "string" and not isinstance(value, str):
                raise PolicyError(f"{key} must be a string.")
            if expected == "integer" and (not isinstance(value, int) or isinstance(value, bool)):
                raise PolicyError(f"{key} must be an integer.")
            if "maxLength" in spec and len(value) > spec["maxLength"]:
                raise PolicyError(f"{key} exceeds maxLength.")
            if "minimum" in spec and value < spec["minimum"]:
                raise PolicyError(f"{key} is below minimum.")
            if "maximum" in spec and value > spec["maximum"]:
                raise PolicyError(f"{key} exceeds maximum.")
            if "enum" in spec and value not in spec["enum"]:
                raise PolicyError(f"{key} is not allowlisted.")

    def _resolve_workspace_path(self, relative_path: str) -> Path:
        if not relative_path or Path(relative_path).is_absolute():
            raise PolicyError("Path must be non-empty and relative to the workspace root.")
        candidate = (self.root / relative_path).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise PolicyError("Path escape is blocked.") from exc
        blocked = {part.casefold() for part in self.config["blocked_path_parts"]}
        relative_parts = candidate.relative_to(self.root).parts
        if any(part.casefold() in blocked for part in relative_parts):
            raise PolicyError("Sensitive path is blocked by policy.")
        return candidate

    def _pc_status(self, args: dict[str, Any]) -> dict[str, Any]:
        del args
        return {
            "ok": True,
            "platform": platform.system(),
            "platform_release": platform.release(),
            "python": platform.python_version(),
            "workspace_available": self.root.is_dir(),
            "tailscale_cli_available": shutil.which("tailscale") is not None,
            "git_cli_available": shutil.which("git") is not None,
        }

    def _list_workspace(self, args: dict[str, Any]) -> dict[str, Any]:
        target = self._resolve_workspace_path(args["relative_path"])
        limit = args.get("limit", 50)
        if not target.is_dir():
            raise PolicyError("Requested path is not a directory.")
        blocked = {part.casefold() for part in self.config["blocked_path_parts"]}
        entries = []
        for item in sorted(target.iterdir(), key=lambda p: p.name.casefold()):
            if item.name.casefold() in blocked:
                continue
            entries.append({"name": item.name, "kind": "directory" if item.is_dir() else "file"})
            if len(entries) >= limit:
                break
        return {"ok": True, "relative_path": args["relative_path"], "entries": entries, "truncated": len(entries) == limit}

    def _read_workspace_text(self, args: dict[str, Any]) -> dict[str, Any]:
        target = self._resolve_workspace_path(args["relative_path"])
        if not target.is_file():
            raise PolicyError("Requested path is not a file.")
        allowed = {suffix.casefold() for suffix in self.config["allowed_text_extensions"]}
        if target.suffix.casefold() not in allowed:
            raise PolicyError("File extension is not allowlisted.")
        max_bytes = int(self.config["max_read_bytes"])
        size = target.stat().st_size
        if size > max_bytes:
            raise PolicyError(f"File exceeds {max_bytes} byte limit.")
        raw = target.read_bytes()
        if b"\x00" in raw:
            raise PolicyError("Binary content is blocked.")
        text = raw.decode("utf-8")
        return {"ok": True, "relative_path": args["relative_path"], "bytes": size, "text": text}

    def _run_diagnostic(self, args: dict[str, Any]) -> dict[str, Any]:
        diagnostic = args["diagnostic"]
        child_env = dict(os.environ)
        child_env.pop("PERPLEXITY_API_KEY", None)
        if diagnostic == "git_status":
            command = ["git", "status", "--short", "--untracked-files=no"]
            proc = subprocess.run(
                command,
                cwd=self.root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
                shell=False,
                check=False,
                env=child_env,
            )
            return {
                "ok": proc.returncode == 0,
                "diagnostic": diagnostic,
                "exit_code": proc.returncode,
                "output": proc.stdout[:32768],
                "error": proc.stderr[:2048],
            }
        if diagnostic == "tailscale_self":
            if shutil.which("tailscale") is None:
                return {"ok": False, "diagnostic": diagnostic, "message": "Tailscale CLI not found."}
            proc = subprocess.run(
                ["tailscale", "status", "--json"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
                shell=False,
                check=False,
                env=child_env,
            )
            if proc.returncode != 0:
                return {"ok": False, "diagnostic": diagnostic, "exit_code": proc.returncode, "message": proc.stderr[:300]}
            status = json.loads(proc.stdout)
            self_state = status.get("Self") or {}
            return {
                "ok": True,
                "diagnostic": diagnostic,
                "exit_code": 0,
                "backend_state": status.get("BackendState"),
                "self_online": self_state.get("Online"),
            }
        raise PolicyError("Diagnostic is not allowlisted.")

    def _list_windows(self, args: dict[str, Any]) -> dict[str, Any]:
        del args
        return self.computer_session.list_windows()

    def _observe_window(self, args: dict[str, Any]) -> dict[str, Any]:
        return self.computer_session.observe_window(args)

    def _computer_action(self, args: dict[str, Any]) -> dict[str, Any]:
        return self.computer_session.computer_action(args)


class PerplexityAgentClient:
    def __init__(self, api_key: str | None = None, timeout: int = 90) -> None:
        self.api_key = api_key or os.environ.get("PERPLEXITY_API_KEY", "")
        self.timeout = timeout
        if not self.api_key.strip():
            raise PolicyError("PERPLEXITY_API_KEY is absent. Use start.ps1; the signed-in web session is not an API credential.")

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = canonical_json(payload).encode("utf-8")
        if len(body) > MAX_REQUEST_BYTES:
            raise RuntimeError(f"Perplexity request exceeds {MAX_REQUEST_BYTES} bytes.")
        request = urllib.request.Request(
            AGENT_ENDPOINT,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "perplexity-pc-harness/1.0",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
                if len(raw) > MAX_RESPONSE_BYTES:
                    raise RuntimeError(f"Perplexity response exceeds {MAX_RESPONSE_BYTES} bytes.")
                decoded = json.loads(raw.decode("utf-8"))
                if not isinstance(decoded, dict):
                    raise RuntimeError("Perplexity response must be a JSON object.")
                if decoded.get("error"):
                    raise RuntimeError(f"Perplexity Agent API error: {canonical_json(decoded['error'])[:1000]}")
                return decoded
        except urllib.error.HTTPError as exc:
            detail = exc.read(2048).decode("utf-8", errors="replace")
            raise RuntimeError(f"Perplexity API returned HTTP {exc.code}: {detail}") from exc


def extract_output_text(response: dict[str, Any]) -> str:
    parts: list[str] = []
    for item in response.get("output", []):
        if item.get("type") == "message":
            for content in item.get("content", []):
                text = content.get("text")
                if isinstance(text, str):
                    parts.append(text)
    return "\n".join(parts).strip()


def run_agent(prompt: str, model: str, harness: LocalPolicyHarness, client: PerplexityAgentClient) -> str:
    instructions = (
        "You are connected to a least-privilege Windows read-only harness. "
        "Use local functions only when required by the user's request. Never imply broader access. "
        "A denial is final for that call; explain it without trying alternate paths."
    )
    payload: dict[str, Any] = {
        "model": model,
        "input": prompt,
        "instructions": instructions,
        "tools": harness.tool_definitions(),
    }
    response = client.create(payload)
    for _turn in range(MAX_AGENT_TURNS):
        if not isinstance(response.get("output"), list):
            raise RuntimeError("Perplexity response output must be an array.")
        if any(not isinstance(item, dict) for item in response["output"]):
            raise RuntimeError("Every Perplexity output item must be an object.")
        calls = [item for item in response.get("output", []) if item.get("type") == "function_call"]
        if not calls:
            text = extract_output_text(response)
            if not text:
                raise RuntimeError("Perplexity returned no visible text.")
            return text
        next_input = list(response.get("output", []))
        for call in calls:
            name = call.get("name")
            call_id = call.get("call_id")
            arguments = call.get("arguments")
            if not isinstance(name, str) or not name:
                raise RuntimeError("Function call name is missing.")
            if not isinstance(call_id, str) or not call_id:
                raise RuntimeError("Function call ID is missing.")
            if not isinstance(arguments, str):
                raise RuntimeError("Function call arguments must be a JSON string.")
            try:
                args = json.loads(arguments)
            except json.JSONDecodeError:
                result = {"ok": False, "error": "InvalidArguments", "message": "Function arguments were not valid JSON."}
            else:
                if not isinstance(args, dict):
                    result = {
                        "ok": False,
                        "error": "InvalidArguments",
                        "message": "Function arguments must decode to a JSON object.",
                    }
                else:
                    result = harness.execute(name, args)
            public_result = dict(result)
            input_image = public_result.pop("_input_image", None)
            next_input.append(
                {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": canonical_json(public_result),
                }
            )
            if input_image is not None:
                supported_image_prefixes = (
                    "data:image/png;base64,",
                    "data:image/jpeg;base64,",
                    "data:image/webp;base64,",
                    "data:image/gif;base64,",
                )
                if not isinstance(input_image, str) or not input_image.startswith(
                    supported_image_prefixes
                ):
                    raise RuntimeError("Computer observation returned an invalid image payload.")
                next_input.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": (
                                    "Fresh post-tool screenshot for observation "
                                    f"{public_result.get('observation_id', 'unknown')}."
                                ),
                            },
                            {"type": "input_image", "image_url": input_image},
                        ],
                    }
                )
        response = client.create({"model": model, "input": next_input, "tools": harness.tool_definitions()})
    raise RuntimeError(f"Maximum local tool turns exceeded ({MAX_AGENT_TURNS}).")


def self_test() -> int:
    harness = LocalPolicyHarness(approval=lambda _name, _args: True)
    result = harness.execute("pc_status", {})
    marker = "PPLX_LOCAL_POLICY_SELFTEST_OK"
    if not result.get("ok"):
        print(canonical_json(result), file=sys.stderr)
        return 1
    print(marker)
    print(canonical_json(result))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Least-privilege Perplexity PC harness")
    parser.add_argument("prompt", nargs="?", help="Request for the Perplexity Agent API")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="Approve and validate actions without injecting input")
    parser.add_argument("--observe-only", action="store_true", help="Expose observation tools but no action tool")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    prompt = args.prompt or input("Perplexity request: ").strip()
    if not prompt:
        print("A non-empty request is required.", file=sys.stderr)
        return 2
    try:
        computer_session = ComputerUseSession(
            UnavailableComputerBackend(),
            STOP_PATH,
            dry_run=args.dry_run,
            observe_only=args.observe_only,
        )
        harness = LocalPolicyHarness(
            computer_session=computer_session,
            observe_only=args.observe_only,
        )
        client = PerplexityAgentClient()
        print(run_agent(prompt, args.model, harness, client))
        print("SESSION SUMMARY / סיכום הפעלה")
        print(canonical_json(computer_session.summary()))
        return 0
    except KeyboardInterrupt:
        print("Stopped by user.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
