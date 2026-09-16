"""Validate a DGX-generated gradient coverage artifact without Torch."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact", type=Path)
    parser.add_argument("--require-world-size", type=int, default=2)
    parser.add_argument("--minimum-optimizer-steps", type=int, default=2)
    args = parser.parse_args()

    payload = json.loads(args.artifact.read_text(encoding="utf-8"))
    parameters = payload.get("parameters", [])
    frozen = [row["name"] for row in parameters if not row.get("requires_grad")]
    missing = [
        row["name"] for row in parameters if not row.get("nonzero_gradient_seen")
    ]
    nonfinite = [
        row["name"] for row in parameters if row.get("nonfinite_gradient_seen")
    ]
    routers = payload.get("moe_router_coverage", [])
    uncovered_experts = [
        f"{router['module']}[{index}]"
        for router in routers
        for index, routed in enumerate(router.get("experts_routed", []))
        if not routed
    ]
    result = {
        "run_id": payload.get("run_id"),
        "world_size": payload.get("world_size"),
        "parameter_tensors": len(parameters),
        "frozen_count": len(frozen),
        "missing_nonzero_gradient_count": len(missing),
        "nonfinite_gradient_count": len(nonfinite),
        "moe_router_count": len(routers),
        "unrouted_expert_count": len(uncovered_experts),
        "frozen_sample": frozen[:20],
        "missing_sample": missing[:20],
        "nonfinite_sample": nonfinite[:20],
        "unrouted_expert_sample": uncovered_experts[:20],
        "pass": payload.get("schema_version") == 3
        and bool(parameters)
        and len(payload.get("parameter_inventory_sha256", "")) == 64
        and payload.get("world_size") == args.require_world_size
        and payload.get("optimizer_steps", 0) >= args.minimum_optimizer_steps
        and not frozen
        and not missing
        and not nonfinite
        and not uncovered_experts,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    if not result["pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
