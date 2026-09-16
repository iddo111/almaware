from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from holobrain.colony import ColonyRuntime  # noqa: E402


def save_checkpoint(path: Path, model: torch.nn.Module) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"path": str(path), "sha256": digest, "bytes": path.stat().st_size}


def main() -> int:
    colony = ColonyRuntime(ROOT / "config" / "colony.json")
    state = ROOT / "state" / "bootstrap"
    records = []
    records.append(save_checkpoint(state / "queen-rivka.pt", colony.queen.active))
    for model_id, ant in colony.ants.items():
        records.append(save_checkpoint(state / f"{model_id}.pt", ant.active))
    receipt = {
        "status": "random_initialized_only",
        "trained": False,
        "inventory": colony.inventory(),
        "checkpoints": records,
    }
    receipt_path = state / "receipt.json"
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
