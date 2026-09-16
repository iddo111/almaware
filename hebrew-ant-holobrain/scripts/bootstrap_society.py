from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from holobrain.society import SocietyRuntime  # noqa: E402


def save_checkpoint(path: Path, model: torch.nn.Module) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), path)
    return {
        "path": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "bytes": path.stat().st_size,
    }


def main() -> int:
    society = SocietyRuntime(ROOT / "config" / "communities.json")
    state = ROOT / "state" / "bootstrap"
    records = []
    for community in society.communities.values():
        target = state / community.community_id
        records.append(
            save_checkpoint(
                target / f"{community.queen.identity}.pt", community.queen.active
            )
        )
        for ant in community.ants.values():
            records.append(
                save_checkpoint(target / f"{ant.identity}.pt", ant.active)
            )
    receipt = {
        "status": "random_initialized_only",
        "trained": False,
        "real_weight_tensors": True,
        "society": society.inventory(),
        "checkpoints": records,
    }
    receipt_path = state / "society-receipt.json"
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
