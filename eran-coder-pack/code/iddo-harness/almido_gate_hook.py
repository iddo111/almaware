#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""ALMIDO's PreToolUse gate — Iddo's policy, in front of the body's hands.

    qwen-code (the body)  --PreToolUse-->  this script  -->  PolicyEngine.decide()
                          <--allow/ask/deny--                AuditLog.record()

Until 2026-09-06 nothing gated ALMIDO. The policy harness had not run since
2026-08-25, `agent/mcp_server.py` was registered in no MCP client, and the
body's hands (`run_shell_command`, `write_file`, desktop-commander) were
governed only by qwen-code's own LLM classifier. The mission line "every action
gated and audited" was false. This script is the smallest honest thing that
makes it true, and it is ADDITIVE: it adds a refusal, it changes nothing that
already worked.

CONTRACT (qwen-code 0.21.4, verified in lib/chunks/chunk-E2SYUEIA.js and
chunk-A5YZ3FA2.js):
  in  : one JSON object on stdin -- session_id, cwd, hook_event_name,
        tool_name, tool_input, tool_use_id, permission_mode, timestamp
  out : one JSON object on stdout --
        {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                "permissionDecision": "allow"|"ask"|"deny",
                                "permissionDecisionReason": "<the rule>"}}
  exit: 0 always. The framework already fails closed when a hook errors; this
        script additionally denies on its own exceptions rather than letting a
        crash read as silence.

WHAT IT READS: exactly one policy file, `policy.yaml` next to this script, and
it says so in the reason of every decision. `load_config()` with no argument
would prefer `~/.iddo-harness/policy.yaml` (the 2026-07-23 v1 policy, which has
no ERAN fence) -- the whole point of the canonical home is that there is one.

WHAT IT WRITES: `state/almido-audit.jsonl` in this repo, HMAC-chained with its
own key (`state/almido-audit.key`). Deliberately NOT `~/.iddo-harness/audit.jsonl`:
almido's unsigned rows already broke that chain at line 33 on 2026-09-03, and
the fix for that is a separate chain until Iddo approves the merge, not another
foreign write into a security log.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
POLICY_PATH = Path(os.environ.get("ALMIDO_GATE_POLICY") or (HERE / "policy.yaml"))
AUDIT_PATH = Path(os.environ.get("ALMIDO_GATE_AUDIT") or (HERE / "state" / "almido-audit.jsonl"))
AUDIT_KEY_PATH = AUDIT_PATH.parent / "almido-audit.key"

sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "agent"))

# Tools whose whole job is to read. They still go through the engine (a read of
# ~/.iddo-harness/audit.key is a real event), but as a read verb.
_READ_TOOLS = {
    "read_file": "read",
    "read_many_files": "read",
    "list_directory": "ls",
    "glob": "glob",
    "search_file_content": "grep",
    "grep": "grep",
}

# Tools that put bytes on the disk.
_WRITE_TOOLS = {
    "write_file": "write",
    "replace": "patch",
    "edit": "patch",
    "smart_edit": "patch",
}

_SHELL_TOOLS = {"run_shell_command", "shell", "bash", "execute_command"}

# desktop-commander speaks its own dialect. Its MCP names arrive prefixed.
_DC_SHELL = ("execute_command", "start_process", "interact_with_process")
_DC_WRITE = ("write_file", "edit_block", "move_file", "create_directory")
_DC_READ = ("read_file", "read_multiple_files", "list_directory", "search_files", "search_code", "get_file_info")

# THE EMERGENCY STOP, extended to the tool qwen-code drives the screen with itself.
# ~/.iddo-harness/STOP is the harness's computer-use kill switch: almido_gate.gate()
# refuses every action while that file exists, so ALMIDO's own mcp__almido__computer_*
# door is covered in-process. qwen-code 0.21.4 ALSO ships its own computer use
# (tools.computerUse, the cua-driver, tool names computer_use__*), and that path never
# touches almido_gate at all -- this hook is the only thing in front of it. Without the
# check below, creating the STOP file would stop one pair of hands and not the other.
# 2026-09-11.
_COMPUTER_USE_PREFIXES = ("computer_use__", "computer_")
# Overridable for the same reason POLICY_PATH and AUDIT_PATH are: so a test can prove
# this branch without creating the REAL emergency stop on a living machine.
STOP_FILE = Path(os.environ.get("ALMIDO_GATE_STOP")
                 or (Path(os.path.expanduser("~")) / ".iddo-harness" / "STOP"))


def _is_computer_use(name: str) -> bool:
    short = name.split("__")[-1] if name.startswith("mcp__") else name
    return any(name.startswith(p) or short.startswith(p) for p in _COMPUTER_USE_PREFIXES)


def _first(d: dict, *names, default=""):
    for name in names:
        value = d.get(name)
        if isinstance(value, str) and value.strip():
            return value
    return default


def _synthesise(tool_name: str, tool_input: dict) -> tuple[str, list[str]]:
    """Turn one tool call into the (command, target_paths) the engine judges.

    The v2 executors already do exactly this for their own kinds -- a `grep`
    becomes `grep <path>` -- so the path globs in policy.yaml apply to a tool
    call the same way they apply to a task packet. Nothing new is invented here.
    """
    name = tool_name.split("__")[-1] if tool_name.startswith("mcp__") else tool_name
    lowered = name.lower()

    if lowered in _SHELL_TOOLS or lowered in _DC_SHELL:
        command = _first(tool_input, "command", "cmd", "script", "input")
        directory = _first(tool_input, "directory", "cwd", "path")
        return command, [directory] if directory else []

    if lowered in _WRITE_TOOLS or lowered in _DC_WRITE:
        verb = _WRITE_TOOLS.get(lowered, "write")
        path = _first(tool_input, "file_path", "path", "absolute_path", "source")
        extra = _first(tool_input, "destination")
        paths = [p for p in (path, extra) if p]
        return f"{verb} {path}".strip(), paths

    if lowered in _READ_TOOLS or lowered in _DC_READ:
        verb = _READ_TOOLS.get(lowered, "read")
        path = _first(tool_input, "file_path", "path", "absolute_path", "pattern", "paths")
        return f"{verb} {path}".strip(), [path] if path else []

    # An unknown tool that carries a `command` is still a command. This is the
    # branch that matters if a future qwen-code renames `run_shell_command`:
    # the rule must bite on the command line itself, not on a JSON blob whose
    # first token is the tool name (fnmatch is start-anchored, so `ssh*eran1*`
    # would never have matched `run_shell_command {...}`).
    command = _first(tool_input, "command", "cmd", "script")
    if command:
        directory = _first(tool_input, "directory", "cwd", "path")
        return command, [directory] if directory else []

    # Anything else: judge the whole call as text so a fence glob (an eran1
    # address inside an MCP argument, say) still bites, and let the default
    # CONFIRM cover what no rule names.
    blob = json.dumps(tool_input, ensure_ascii=False, sort_keys=True)
    return f"{name} {blob}", []


def _emit(decision: str, reason: str) -> None:
    sys.stdout.write(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": decision,
                    "permissionDecisionReason": reason,
                }
            },
            ensure_ascii=False,
        )
    )
    sys.stdout.flush()


def main() -> int:
    try:
        raw = sys.stdin.read()
        event = json.loads(raw) if raw.strip() else {}
    except Exception as exc:  # unreadable input is not a reason to open the gate
        _emit("deny", f"ALMIDO gate: could not read the hook input ({exc})")
        return 0

    tool_name = str(event.get("tool_name") or "")
    tool_input = event.get("tool_input")
    if not isinstance(tool_input, dict):
        tool_input = {}

    try:
        from config import load_config
        from policy import Decision, PolicyEngine
        from audit import AuditLog

        cfg = load_config(str(POLICY_PATH))
        audit = AuditLog(path=AUDIT_PATH, key_path=AUDIT_KEY_PATH)
        engine = PolicyEngine(cfg)

        # The emergency stop wins over every rule, including an auto_allow. It is checked
        # here, before the engine, so that ONE file stops both pairs of hands.
        if _is_computer_use(tool_name) and STOP_FILE.exists():
            reason = ("ALMIDO gate: the computer-use emergency STOP is engaged (%s). "
                      "Delete that file to allow screen control again." % STOP_FILE)
            audit.record(actor=os.environ.get("ALMIDO_GATE_ACTOR", "almido-qwen"),
                         action="pretooluse:deny", resource=tool_name[:400], outcome="deny",
                         meta={"rule": "STOP file present", "tool_name": tool_name,
                               "stop_file": str(STOP_FILE), "policy": str(POLICY_PATH)})
            _emit("deny", reason)
            return 0

        command, paths = _synthesise(tool_name, tool_input)
        # Identify as the almido-qwen agent profile (policy.yaml agents.profiles)
        # instead of the default "legacy" identity, which has no profile and so
        # gets zero autonomy beyond the global lists. See that profile's own
        # comment for what this does and does not loosen.
        decision, reason = engine.decide(command, paths, agent_id="almido-qwen")
        verdict = {
            Decision.AUTO: "allow",
            Decision.CONFIRM: "ask",
            Decision.BLOCK: "deny",
        }[decision]

        audit.record(
            actor=os.environ.get("ALMIDO_GATE_ACTOR", "almido-qwen"),
            action=f"pretooluse:{verdict}",
            resource=f"{tool_name}: {command}"[:400],
            outcome="deny" if verdict == "deny" else "ok",
            meta={
                "rule": reason,
                "decision": decision.value,
                "tool_name": tool_name,
                "target_paths": paths,
                "policy": str(POLICY_PATH),
                "session_id": str(event.get("session_id", "")),
                "tool_use_id": str(event.get("tool_use_id", "")),
                "cwd": str(event.get("cwd", "")),
                "permission_mode": str(event.get("permission_mode", "")),
            },
        )
        _emit(verdict, f"{reason} [policy: {POLICY_PATH}]")
        return 0

    except Exception as exc:
        # Fail CLOSED. The Python port of this gate used to swallow a missing
        # PyYAML and answer ALLOW to everything, including `rm -rf /`
        # (Phase-1 defect #2). A gate that cannot read its policy has no
        # opinion, and no opinion means no.
        try:
            AuditLog(path=AUDIT_PATH, key_path=AUDIT_KEY_PATH).record(
                actor="almido-gate",
                action="pretooluse:deny",
                resource=f"{tool_name}",
                outcome="error",
                meta={"rule": f"gate failure: {exc!r}", "policy": str(POLICY_PATH)},
            )
        except Exception:
            pass
        _emit("deny", f"ALMIDO gate failed closed: {exc!r} [policy: {POLICY_PATH}]")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
