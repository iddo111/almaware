from __future__ import annotations

import json
from pathlib import Path

from .model import DevelopmentStage, HolobrainConfig, TinyHolobrain
from .training import AutonomousAnt


class ColonyRuntime:
    def __init__(self, config_path: Path) -> None:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
        stage = DevelopmentStage[payload["initial_stage"]]
        queen_cfg = payload["queen"]
        self.queen = AutonomousAnt(
            TinyHolobrain(
                HolobrainConfig(
                    model_id=queen_cfg["model_id"],
                    seed=int(queen_cfg["seed"]),
                    latent_dim=int(queen_cfg["latent_dim"]),
                    reasoning_steps=int(queen_cfg["reasoning_steps"]),
                    stage=stage,
                    queen=True,
                )
            )
        )
        self.ants: dict[str, AutonomousAnt] = {}
        for item in payload["ants"]:
            model = TinyHolobrain(
                HolobrainConfig(
                    model_id=item["model_id"],
                    seed=int(item["seed"]),
                    latent_dim=int(item["latent_dim"]),
                    stage=stage,
                )
            )
            self.ants[item["model_id"]] = AutonomousAnt(model)

        fingerprints = [self.queen.active.fingerprint()]
        fingerprints.extend(ant.active.fingerprint() for ant in self.ants.values())
        if len(set(fingerprints)) != len(fingerprints):
            raise ValueError("Queen and ants must have distinct initial weights")

    def inventory(self) -> dict:
        return {
            "queen": {
                "model_id": self.queen.active.config.model_id,
                "fingerprint": self.queen.active.fingerprint(),
                "parameters": self.queen.active.parameter_count,
            },
            "ants": [
                {
                    "model_id": ant.active.config.model_id,
                    "fingerprint": ant.active.fingerprint(),
                    "parameters": ant.active.parameter_count,
                    "training_steps": ant.training_steps,
                }
                for ant in self.ants.values()
            ],
            "pretrained_weights": False,
        }
