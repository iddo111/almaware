"""Minimal local bootstrap for the Perplexity harness worker.

``agent/perplexity_worker.py`` had no entry point: nothing in the tree
constructed a ``PerplexityWorker``, so the integration could not be exercised
even with a valid key. This module supplies only the wiring — the same
``Executor`` the MCP and git transports use, an explicit local memory ledger,
and an API client whose key still comes solely from the environment.

    python -m agent.perplexity_cli --handshake
    python -m agent.perplexity_cli "find the current pricing for X"

Exit codes: 0 ok, 2 blocked (missing key / harness unreachable), 3 paused on a
policy confirmation.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from approval import ApprovalManager
    from audit import AuditLog
    from config import load_config
    from executor import Executor
    from perplexity_memory import PerplexityMemory
    from perplexity_worker import (
        DEFAULT_BASE_URL, PerplexityApiClient, PerplexityWorker, PerplexityWorkerError,
    )
    from policy import PolicyEngine
    from secrets_vault import SecretVault
except ImportError:  # pragma: no cover - installed package imports
    from agent.approval import ApprovalManager
    from agent.audit import AuditLog
    from agent.config import load_config
    from agent.executor import Executor
    from agent.perplexity_memory import PerplexityMemory
    from agent.perplexity_worker import (
        DEFAULT_BASE_URL, PerplexityApiClient, PerplexityWorker, PerplexityWorkerError,
    )
    from agent.policy import PolicyEngine
    from agent.secrets_vault import SecretVault


DEFAULT_MEMORY = Path.home() / ".iddo-harness" / "memory" / "perplexity.jsonl"


def build_executor(policy_path: str | None) -> Executor:
    """Identical wiring to mcp_server.build_adapter: one policy/audit road."""
    policy_cfg = load_config(policy_path)
    audit = AuditLog.from_config(policy_cfg)
    vault = SecretVault.from_config(policy_cfg, audit_sink=audit)
    return Executor(
        PolicyEngine(policy_cfg, audit_log=audit),
        ApprovalManager(policy_cfg, audit_log=audit),
        vault=vault,
        audit_log=audit,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Local Perplexity harness worker")
    parser.add_argument("prompt", nargs="?", help="task for the model; omit with --handshake")
    parser.add_argument("--config", default=None, help="path to policy.yaml")
    parser.add_argument("--project", default="iddo-harness")
    parser.add_argument("--model", default="sonar-pro")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--memory", default=str(DEFAULT_MEMORY))
    parser.add_argument("--max-iterations", type=int, default=25)
    parser.add_argument("--handshake", action="store_true", help="probe reachability and exit")
    args = parser.parse_args(argv)

    if not args.handshake and not args.prompt:
        parser.error("a prompt is required unless --handshake is given")

    try:
        client = PerplexityApiClient(model=args.model, base_url=args.base_url)
    except PerplexityWorkerError as exc:
        # Presence only — never echo the value or ask for it here.
        print(json.dumps({"status": "blocked", "reason": str(exc)}), file=sys.stderr)
        return 2

    with client:
        worker = PerplexityWorker(
            client=client,
            executor=build_executor(args.config),
            memory=PerplexityMemory(args.memory),
            project=args.project,
            max_iterations=args.max_iterations,
        )
        if args.handshake:
            print(json.dumps(worker.handshake(force=True), indent=2))
            return 0
        try:
            result = worker.run(args.prompt)
        except PerplexityWorkerError as exc:
            print(json.dumps({"status": "blocked", "reason": str(exc)}), file=sys.stderr)
            return 2

    print(json.dumps({
        "done": result.done,
        "paused": result.paused,
        "iterations": result.iterations,
        "task_ids": result.task_ids,
        "pending_confirmation": result.pending_confirmation,
        "final_message": result.final_message,
    }, indent=2, ensure_ascii=False))
    return 3 if result.paused else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
