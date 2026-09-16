"""Planning-only memory bounds; no Torch import."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


GIB = 1024**3


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--catalog",
        type=Path,
        default=Path(__file__).parents[1] / "configs" / "model-catalog.json",
    )
    parser.add_argument("--catalog-key", required=True)
    parser.add_argument("--nodes", type=int, default=2)
    parser.add_argument("--memory-gib-per-node", type=float, default=128.0)
    parser.add_argument("--reserve-gib-per-node", type=float, default=20.0)
    parser.add_argument(
        "--adafactor-state-bytes-per-param-low", type=float, default=0.05
    )
    parser.add_argument(
        "--adafactor-state-bytes-per-param-high", type=float, default=4.0
    )
    parser.add_argument(
        "--activation-gib-per-node",
        type=float,
        default=0.0,
        help="Measured/estimated activations; zero means unknown, not free.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.nodes < 1:
        raise SystemExit("--nodes must be positive")
    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    model = catalog["models"][args.catalog_key]
    params = model["total_parameters"]

    # ZeRO-3/FULL_SHARD planning: BF16 params + BF16 grads are partitioned.
    fixed_bytes_total = params * 4.0
    low_bytes_total = fixed_bytes_total + (
        params * args.adafactor_state_bytes_per_param_low
    )
    high_bytes_total = fixed_bytes_total + (
        params * args.adafactor_state_bytes_per_param_high
    )
    low_per_node = low_bytes_total / args.nodes / GIB
    high_per_node = high_bytes_total / args.nodes / GIB
    usable = args.memory_gib_per_node - args.reserve_gib_per_node

    payload = {
        "status": "PLANNING_ONLY",
        "catalog_key": args.catalog_key,
        "upstream_id": model["upstream_id"],
        "total_parameters": params,
        "nodes": args.nodes,
        "assumptions": {
            "bf16_parameter_bytes": 2,
            "bf16_gradient_bytes": 2,
            "factored_adafactor_state_bytes_per_parameter_range": [
                args.adafactor_state_bytes_per_param_low,
                args.adafactor_state_bytes_per_param_high,
            ],
            "zero3_or_full_shard_partitioning": True,
            "activation_checkpointing": True,
            "cpu_offload": False,
            "nvme_offload": False,
        },
        "model_state_gib_per_node_range": [
            round(low_per_node, 2),
            round(high_per_node, 2),
        ],
        "activation_gib_per_node": args.activation_gib_per_node,
        "usable_gib_per_node_before_activations": usable,
        "upper_bound_plus_supplied_activations_gib_per_node": round(
            high_per_node + args.activation_gib_per_node, 2
        ),
        "planning_headroom_gib_per_node": round(
            usable - high_per_node - args.activation_gib_per_node, 2
        ),
        "fit_verified": False,
        "warning": (
            "Adafactor state depends on exact tensor shapes and activations depend "
            "on sequence/batch/model implementation. Measure the exact checkpoint."
        ),
    }
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

