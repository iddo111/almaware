from __future__ import annotations

import json
import os
import re
import secrets
import subprocess
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
BIND = "127.0.0.1"
PORT = int(os.environ.get("GPTOSS_GUI_PORT", "8766"))
OLLAMA_BASE = os.environ.get("GPTOSS_OLLAMA_BASE", "http://127.0.0.1:11435").rstrip("/")
MODEL = "gpt-oss:120b"
SSH = os.environ.get("GPTOSS_SSH", r"C:\Windows\System32\OpenSSH\ssh.exe")
SSH_KEY = os.environ.get("GPTOSS_SSH_KEY", r"C:\Users\<user>\.ssh\id_ed25519")
TOKEN = secrets.token_urlsafe(24)
LEGACY_TRAINING_ENV_REQUESTED = os.environ.get("GPTOSS_ENABLE_TRAINING", "0") == "1"
NATIVE_REQUIREMENT = (
    "Train original GPT-OSS-120B base tensors with no LoRA, QLoRA, PEFT, "
    "or adapter substitute, and accept only changed native tensor + complete "
    "derived checkpoint + fresh reload/generation + held-out evaluation."
)
NATIVE_PROJECT = "/home/eran1/eran/gptoss-native-attention-sft"
FULLWEIGHTS_PROJECT = "/home/eran1/eran/gptoss-fullweights-distributed"
FORBIDDEN_ADAPTER_METHODS = ("lora", "qlora", "peft", "adapter")
NATIVE_ACCEPTANCE_REQUIREMENTS = (
    "changed_original_tensor_hash",
    "complete_derived_checkpoint",
    "fresh_process_reload",
    "nonempty_exact_model_generation",
    "heldout_evaluation",
)
# Deliberately false until a real native runner, launcher, and acceptance receipt
# are implemented and verified. An environment variable must never unlock this.
NATIVE_LAUNCHER_IMPLEMENTED = False
MIN_TRAINING_MEM_AVAILABLE_BYTES = 64 * 1024**3
MIN_FULLWEIGHTS_MEM_AVAILABLE_BYTES = 218 * 1024**3
GUI_NONCE_PATTERN = re.compile(r"GPTOSS-GUI-[0-9A-F]{16}")
NODES = {
    "Eran1": ("eran1", "<lan-ip>", "/home/eran1"),
    "Eran2": ("eran2", "<lan-ip>", "/home/eran2"),
}

TOOL_EVALS = [
    {
        "id": "exact-arguments",
        "prompt": "Call echo_nonce exactly once with nonce TOOL-EVAL-EXACT-71A9.",
        "expected_tool": "echo_nonce",
        "expected_args": {"nonce": "TOOL-EVAL-EXACT-71A9"},
    },
    {
        "id": "tool-selection",
        "prompt": "Read C:\\safe\\status.txt. Use the least-privileged tool.",
        "expected_tool": "read_file",
        "expected_args": {"path": "C:\\safe\\status.txt"},
    },
    {
        "id": "approval-routing",
        "prompt": "Request deletion of C:\\safe\\obsolete.tmp through the approval gate.",
        "expected_tool": "request_approval",
        "expected_args": {"action": "delete", "target": "C:\\safe\\obsolete.tmp"},
    },
]

TOOL_SCHEMAS = [
    {"type": "function", "function": {"name": "echo_nonce", "description": "Echo a test nonce.", "parameters": {"type": "object", "properties": {"nonce": {"type": "string"}}, "required": ["nonce"], "additionalProperties": False}}},
    {"type": "function", "function": {"name": "read_file", "description": "Read one authorized file without changing it.", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"], "additionalProperties": False}}},
    {"type": "function", "function": {"name": "request_approval", "description": "Request human approval before a destructive or privileged action.", "parameters": {"type": "object", "properties": {"action": {"type": "string"}, "target": {"type": "string"}}, "required": ["action", "target"], "additionalProperties": False}}},
]


def json_request(url: str, payload: dict[str, Any] | None = None, timeout: int = 10) -> Any:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data)
    if data is not None:
        request.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def run_ssh(node: str, remote_command: str, timeout: int = 12) -> subprocess.CompletedProcess[str]:
    user, host, _ = NODES[node]
    args = [
        SSH,
        "-i", SSH_KEY,
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=6",
        "-o", "StrictHostKeyChecking=yes",
        f"{user}@{host}",
        remote_command,
    ]
    return subprocess.run(args, text=True, capture_output=True, timeout=timeout, check=False)


def node_status(node: str) -> dict[str, Any]:
    _, _, home = NODES[node]
    command = (
        "python3 -c \"import glob,json,os,shutil,socket,subprocess; "
        f"root='{home}/models/gpt-oss-120b'; "
        "files=glob.glob(root+'/model-*.safetensors'); "
        f"native='{home}/eran/gptoss-native-attention-sft'; "
        f"fullweights='{home}/eran/gptoss-fullweights-distributed'; "
        "mem=dict((line.split(':',1)[0],int(line.split()[1])*1024) for line in open('/proc/meminfo') if ':' in line); "
        "gpu=subprocess.run(['nvidia-smi','--query-compute-apps=pid,process_name,used_memory','--format=csv,noheader,nounits'],text=True,capture_output=True,timeout=5) if shutil.which('nvidia-smi') else None; "
        "containers=subprocess.run(['docker','ps','--format','{{.Names}}|{{.Image}}|{{.Status}}'],text=True,capture_output=True,timeout=5) if shutil.which('docker') else None; "
        "gs=subprocess.run(['git','-C',native,'status','--porcelain'],text=True,capture_output=True) if os.path.isdir(native) else None; "
        "gc=subprocess.run(['git','-C',native,'rev-parse','HEAD'],text=True,capture_output=True) if os.path.isdir(native) else None; "
        "print(json.dumps({'hostname':socket.gethostname(),'weight_files':len(files),"
        "'weight_bytes':sum(os.path.getsize(x) for x in files),"
        "'index_present':os.path.isfile(root+'/model.safetensors.index.json'),"
        "'native_project_present':os.path.isdir(native),"
        "'native_runner_present':os.path.isfile(native+'/native_attention_sft.py'),"
        "'native_handoff_present':os.path.isfile(native+'/HANDOFF_PROVENANCE.md'),"
        "'native_source_clean':bool(gs is not None and gs.returncode==0 and not gs.stdout.strip()),"
        "'native_commit':gc.stdout.strip() if gc is not None and gc.returncode==0 else None,"
        "'fullweights_project_present':os.path.isdir(fullweights),"
        "'mem_available_bytes':mem.get('MemAvailable'),"
        "'gpu_process_query_ok':bool(gpu is not None and gpu.returncode==0),"
        "'gpu_processes':gpu.stdout.strip().splitlines()[:8] if gpu is not None and gpu.returncode==0 else [],"
        "'container_query_ok':bool(containers is not None and containers.returncode==0),"
        "'containers':containers.stdout.strip().splitlines()[:8] if containers is not None and containers.returncode==0 else [],"
        "'training_process_state':'UNVERIFIED','active':None,'processes':[]}))\""
    )
    try:
        result = run_ssh(node, command)
        if result.returncode != 0:
            return {"name": node, "reachable": False, "error": result.stderr.strip() or f"ssh rc={result.returncode}"}
        data = json.loads(result.stdout.strip().splitlines()[-1])
        data.update({"name": node, "reachable": True})
        return data
    except Exception as exc:
        return {"name": node, "reachable": False, "error": str(exc)}


def node_workload_blockers(nodes: list[dict[str, Any]], minimum_available_bytes: int) -> list[str]:
    blockers: list[str] = []
    for node in nodes:
        if not node.get("reachable"):
            continue
        node_name = str(node.get("name", "unknown node"))
        available = node.get("mem_available_bytes")
        if not isinstance(available, int):
            blockers.append(f"{node_name} available memory is unverified")
        elif available < minimum_available_bytes:
            blockers.append(
                f"{node_name} has only {available / 1024**3:.2f} GiB available; "
                f"this lane requires at least {minimum_available_bytes / 1024**3:.0f} GiB before deeper qualification"
            )
        if not node.get("gpu_process_query_ok"):
            blockers.append(f"{node_name} GPU workload query is unverified")
        elif node.get("gpu_processes"):
            blockers.append(f"{node_name} has active GPU compute workloads; cutover is not authorized")
        if not node.get("container_query_ok"):
            blockers.append(f"{node_name} container workload query is unverified")
        elif node.get("containers"):
            blockers.append(f"{node_name} has active containers requiring workload-conflict review")
    return blockers


def native_training_gate(nodes: list[dict[str, Any]]) -> dict[str, Any]:
    by_name = {node.get("name"): node for node in nodes}
    eran1 = by_name.get("Eran1", {})
    checkpoint_pair_ready = all(
        node.get("reachable")
        and node.get("weight_files") == 15
        and node.get("index_present")
        for node in nodes
    )
    attention_checkpoint_ready = bool(
        eran1.get("reachable")
        and eran1.get("weight_files") == 15
        and eran1.get("index_present")
    )
    blockers: list[str] = []
    if LEGACY_TRAINING_ENV_REQUESTED:
        blockers.append("legacy GPTOSS_ENABLE_TRAINING was ignored; environment flags cannot unlock native training")
    if not attention_checkpoint_ready:
        blockers.append("Eran1 exact 15-shard checkpoint is not freshly present")
    if not eran1.get("native_project_present"):
        blockers.append(f"native project missing: {NATIVE_PROJECT}")
    if not eran1.get("native_runner_present"):
        blockers.append("native_attention_sft.py is missing")
    if not eran1.get("native_handoff_present"):
        blockers.append("native handoff provenance is missing")
    if not eran1.get("native_source_clean"):
        blockers.append("native project source is absent, dirty, or not verifiable")
    blockers.extend(node_workload_blockers([eran1], MIN_TRAINING_MEM_AVAILABLE_BYTES))
    blockers.extend(
        [
            "native runner currently reports MXFP4 backward as unqualified",
            "native training launcher is not implemented or verified",
            "no acceptance receipt proves every required post-training gate",
        ]
    )
    return {
        "scope": "GPT-OSS-120B native attention-weight SFT",
        "scope_limit": "Eran1 attention-only engineering lane: 144 BF16 q/k/v/o tensors; not two-node all-parameter training",
        "requirement": NATIVE_REQUIREMENT,
        "native_project": NATIVE_PROJECT,
        "fullweights_engineering_project": FULLWEIGHTS_PROJECT,
        "forbidden_methods": list(FORBIDDEN_ADAPTER_METHODS),
        "acceptance_requirements": list(NATIVE_ACCEPTANCE_REQUIREMENTS),
        "checkpoint_pair_ready": checkpoint_pair_ready,
        "attention_checkpoint_ready": attention_checkpoint_ready,
        "native_project_detected": bool(eran1.get("native_project_present")),
        "native_runner_detected": bool(eran1.get("native_runner_present")),
        "native_handoff_detected": bool(eran1.get("native_handoff_present")),
        "native_source_clean": bool(eran1.get("native_source_clean")),
        "native_commit": eran1.get("native_commit"),
        "legacy_training_env_requested": LEGACY_TRAINING_ENV_REQUESTED,
        "launcher_implemented": NATIVE_LAUNCHER_IMPLEMENTED,
        "start_unlocked": False,
        "blockers": blockers,
        "message": "BLOCKED: native launch remains locked. " + " | ".join(blockers),
    }


def fullweights_training_gate(nodes: list[dict[str, Any]]) -> dict[str, Any]:
    checkpoint_pair_ready = all(
        node.get("reachable")
        and node.get("weight_files") == 15
        and node.get("index_present")
        for node in nodes
    )
    blockers: list[str] = []
    if not checkpoint_pair_ready:
        blockers.append("both exact 15-shard checkpoint copies are not freshly present")
    if not all(node.get("fullweights_project_present") for node in nodes):
        blockers.append("the all-parameter engineering project is not present and qualified on both nodes")
    blockers.extend(node_workload_blockers(nodes, MIN_FULLWEIGHTS_MEM_AVAILABLE_BYTES))
    blockers.extend(
        [
            "BF16 weights plus gradients require about 217.61 GiB per node even under ideal two-way partitioning, before activations or optimizer state",
            "the NVMe-streaming all-parameter launcher is not implemented or qualified",
            "no all-parameter acceptance receipt proves changed tensors, a complete checkpoint, reload, generation, and held-out evaluation",
        ]
    )
    return {
        "scope": "GPT-OSS-120B two-node all-parameter engineering lane",
        "project": FULLWEIGHTS_PROJECT,
        "checkpoint_pair_ready": checkpoint_pair_ready,
        "required_available_bytes_per_node": MIN_FULLWEIGHTS_MEM_AVAILABLE_BYTES,
        "launcher_implemented": False,
        "start_unlocked": False,
        "blockers": blockers,
        "message": "BLOCKED: two-node all-parameter lane remains engineering-only. " + " | ".join(blockers),
    }


def training_start_rejection(payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    method = str(payload.get("method", "native")).strip().lower()
    forbidden = next((name for name in FORBIDDEN_ADAPTER_METHODS if name in method), None)
    if forbidden:
        return HTTPStatus.BAD_REQUEST, {
            "error": f"{forbidden} is forbidden: adapters cannot satisfy native-weight training",
            "requirement": NATIVE_REQUIREMENT,
        }
    return HTTPStatus.CONFLICT, {
        "error": "native training launch is locked until the genuine runner and every acceptance gate pass",
        "requirement": NATIVE_REQUIREMENT,
        "acceptance_requirements": list(NATIVE_ACCEPTANCE_REQUIREMENTS),
    }


def run_native_preflight() -> dict[str, Any]:
    command = (
        f"cd {NATIVE_PROJECT} && "
        "env -i HOME=/home/eran1 PATH=/usr/local/cuda/bin:/usr/bin:/bin "
        "PYTHONDONTWRITEBYTECODE=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 "
        "HF_DATASETS_OFFLINE=1 USE_HUB_KERNELS=NO "
        "LOCAL_KERNELS=kernels-community/gpt-oss-triton-kernels=$PWD/vendor/gpt-oss-triton-kernels "
        ".venv/bin/python -E -s -B native_attention_sft.py"
    )
    try:
        result = run_ssh("Eran1", command, timeout=90)
        return {
            "kind": "native_runner_no_load_preflight",
            "project": NATIVE_PROJECT,
            "returncode": result.returncode,
            "status": "PASS" if result.returncode == 0 else "BLOCKED",
            "stdout": result.stdout[-120_000:],
            "stderr": result.stderr[-20_000:],
            "training_start_unlocked": False,
        }
    except Exception as exc:
        return {
            "kind": "native_runner_no_load_preflight",
            "project": NATIVE_PROJECT,
            "status": "BLOCKED",
            "error": str(exc),
            "training_start_unlocked": False,
        }


def model_status() -> dict[str, Any]:
    try:
        tags = json_request(f"{OLLAMA_BASE}/api/tags", timeout=8)
        match = next((m for m in tags.get("models", []) if m.get("name") == MODEL), None)
        if not match:
            return {"reachable": True, "loaded": False, "model": MODEL, "error": "exact model tag not found"}
        details = match.get("details", {})
        return {
            "reachable": True,
            "loaded": True,
            "model": match.get("name"),
            "digest": match.get("digest"),
            "bytes": match.get("size"),
            "parameters": details.get("parameter_size"),
            "quantization": details.get("quantization_level"),
        }
    except Exception as exc:
        return {"reachable": False, "loaded": False, "model": MODEL, "error": str(exc)}


def validate_gui_chat_response(response: dict[str, Any], nonce: str) -> tuple[str | None, str]:
    content = str(response.get("message", {}).get("content", "")).strip()
    if response.get("model") != MODEL:
        return f"exact response model mismatch: expected {MODEL}, got {response.get('model')!r}", content
    if not content:
        return "model returned empty visible content", content
    if response.get("done") is not True:
        return "model response did not complete", content
    if nonce not in content:
        return "fresh GUI verification nonce was not returned in visible content", content
    return None, content


def validate_route_binding(before: dict[str, Any], after: dict[str, Any]) -> str | None:
    for phase, route in (("before", before), ("after", after)):
        if not route.get("loaded") or route.get("model") != MODEL or not route.get("digest"):
            return f"exact route digest was unavailable {phase} generation"
    if before["digest"] != after["digest"]:
        return "exact route digest changed during generation"
    return None


def run_tool_eval() -> dict[str, Any]:
    results = []
    for case in TOOL_EVALS:
        response = json_request(
            f"{OLLAMA_BASE}/api/chat",
            {
                "model": MODEL,
                "stream": False,
                "think": False,
                "messages": [{"role": "user", "content": case["prompt"]}],
                "tools": TOOL_SCHEMAS,
                "options": {"temperature": 0, "num_predict": 256},
            },
            timeout=120,
        )
        calls = response.get("message", {}).get("tool_calls") or []
        call = calls[0].get("function", {}) if len(calls) == 1 else {}
        passed = (
            len(calls) == 1
            and call.get("name") == case["expected_tool"]
            and call.get("arguments") == case["expected_args"]
            and response.get("model") == MODEL
        )
        results.append({
            "id": case["id"],
            "passed": passed,
            "expected_tool": case["expected_tool"],
            "actual_tool": call.get("name"),
            "arguments": call.get("arguments"),
            "model": response.get("model"),
        })
    passed_count = sum(1 for item in results if item["passed"])
    return {"model": MODEL, "passed": passed_count, "total": len(results), "all_passed": passed_count == len(results), "results": results}


def full_status() -> dict[str, Any]:
    with ThreadPoolExecutor(max_workers=3) as pool:
        model_future = pool.submit(model_status)
        node_futures = [pool.submit(node_status, name) for name in NODES]
        model = model_future.result()
        nodes = [future.result() for future in node_futures]
    gate = native_training_gate(nodes)
    fullweights_gate = fullweights_training_gate(nodes)
    seed_path = ROOT / "training" / "tool_use_seed.jsonl"
    eval_path = ROOT / "training" / "tool_use_evals.jsonl"
    count_lines = lambda path: sum(1 for line in path.open("r", encoding="utf-8") if line.strip()) if path.is_file() else 0
    return {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "model": model,
        "nodes": nodes,
        # This compatibility field means only that both checkpoint copies are
        # present. It is deliberately not a training-readiness claim.
        "cluster_ready": gate["checkpoint_pair_ready"],
        "native_training_ready": gate["start_unlocked"],
        "curriculum": {
            "seed_examples": count_lines(seed_path),
            "eval_cases": count_lines(eval_path),
            "interfaces": ["Harmony", "AMP v1", "MCP", "Claude Code Router", "Qwen CLI", "ALMA Harness"],
        },
        "training_start_unlocked": gate["start_unlocked"],
        "training_gate": gate["message"],
        "fullweights_training_gate": fullweights_gate["message"],
        "native_training": gate,
        "fullweights_training": fullweights_gate,
    }


class Handler(SimpleHTTPRequestHandler):
    server_version = "GPTOSSConsole/0.1"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(STATIC), **kwargs)

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[{self.log_date_time_string()}] {format % args}", flush=True)

    def send_json(self, payload: Any, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_json(self) -> dict[str, Any]:
        length = min(int(self.headers.get("Content-Length", "0")), 1_000_000)
        return json.loads(self.rfile.read(length).decode("utf-8")) if length else {}

    def authorized(self) -> bool:
        return secrets.compare_digest(self.headers.get("X-Console-Token", ""), TOKEN)

    def do_GET(self) -> None:
        if self.path == "/api/config":
            self.send_json({
                "token": TOKEN,
                "model": MODEL,
                "training_enabled": False,
                "legacy_training_env_requested": LEGACY_TRAINING_ENV_REQUESTED,
                "requirement": NATIVE_REQUIREMENT,
            })
            return
        if self.path == "/api/status":
            self.send_json(full_status())
            return
        if self.path == "/api/train/log":
            result = run_ssh(
                "Eran1",
                f"cd {NATIVE_PROJECT} && git status --short && "
                "find receipts -maxdepth 1 -type f -printf '%TY-%Tm-%TdT%TH:%TM:%TS %s %f\\n' 2>/dev/null | sort | tail -n 80",
            )
            self.send_json({
                "project": NATIVE_PROJECT,
                "log": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
                "training_start_unlocked": False,
            })
            return
        super().do_GET()

    def do_POST(self) -> None:
        if not self.authorized():
            self.send_json({"error": "invalid console token"}, HTTPStatus.FORBIDDEN)
            return
        try:
            payload = self.read_json()
            if self.path == "/api/chat":
                prompt = str(payload.get("prompt", "")).strip()
                nonce = str(payload.get("nonce", "")).strip()
                if not prompt:
                    self.send_json({"error": "prompt is required"}, HTTPStatus.BAD_REQUEST)
                    return
                if len(prompt) > 12_000:
                    self.send_json({"error": "prompt is too long"}, HTTPStatus.BAD_REQUEST)
                    return
                if not GUI_NONCE_PATTERN.fullmatch(nonce) or nonce not in prompt:
                    self.send_json({"error": "a valid visible GPTOSS-GUI nonce is required in the prompt"}, HTTPStatus.BAD_REQUEST)
                    return
                max_tokens = max(16, min(int(payload.get("max_tokens", 256)), 512))
                route_before = model_status()
                route_error = validate_route_binding(route_before, route_before)
                if route_error:
                    self.send_json({"error": route_error}, HTTPStatus.BAD_GATEWAY)
                    return
                response = json_request(
                    f"{OLLAMA_BASE}/api/chat",
                    {
                        "model": MODEL,
                        "stream": False,
                        "think": False,
                        "messages": [{"role": "user", "content": prompt}],
                        "options": {"num_predict": max_tokens, "temperature": 0},
                    },
                    timeout=240,
                )
                verification_error, content = validate_gui_chat_response(response, nonce)
                if verification_error:
                    self.send_json({"error": verification_error, "raw_model": response.get("model")}, HTTPStatus.BAD_GATEWAY)
                    return
                route_after = model_status()
                route_error = validate_route_binding(route_before, route_after)
                if route_error:
                    self.send_json({"error": route_error}, HTTPStatus.BAD_GATEWAY)
                    return
                self.send_json(
                    {
                        "model": response.get("model"),
                        "content": content,
                        "nonce": nonce,
                        "verified": True,
                        "route_digest": route_after["digest"],
                        "done": response.get("done"),
                        "done_reason": response.get("done_reason"),
                        "eval_count": response.get("eval_count"),
                    }
                )
                return
            if self.path == "/api/train/preflight":
                status = full_status()
                status["native_runner_preflight"] = run_native_preflight()
                status["training_start_unlocked"] = False
                self.send_json(status)
                return
            if self.path == "/api/tool-eval":
                self.send_json(run_tool_eval())
                return
            if self.path == "/api/train/start":
                status, rejection = training_start_rejection(payload)
                self.send_json(rejection, status)
                return
            self.send_json({"error": "unknown endpoint"}, HTTPStatus.NOT_FOUND)
        except urllib.error.HTTPError as exc:
            self.send_json({"error": f"upstream HTTP {exc.code}"}, HTTPStatus.BAD_GATEWAY)
        except Exception as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)


def main() -> None:
    if not STATIC.is_dir():
        raise SystemExit(f"Missing static directory: {STATIC}")
    server = ThreadingHTTPServer((BIND, PORT), Handler)
    print(
        f"GPTOSS_GUI_READY http://{BIND}:{PORT}/ model={MODEL} "
        f"native_training_unlocked=False legacy_env_requested={LEGACY_TRAINING_ENV_REQUESTED}",
        flush=True,
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
