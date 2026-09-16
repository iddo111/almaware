from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .model import DevelopmentStage, HolobrainConfig, TinyHolobrain
from .training import AutonomousAnt


@dataclass(frozen=True)
class BridgeDecision:
    delivered: bool
    reason: str


class CommunityRuntime:
    def __init__(self, payload: dict, stage: DevelopmentStage) -> None:
        self.community_id = str(payload["community_id"])
        self.storage_namespace = str(payload["storage_namespace"])
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
        for ant_cfg in payload["ants"]:
            ant = AutonomousAnt(
                TinyHolobrain(
                    HolobrainConfig(
                        model_id=ant_cfg["model_id"],
                        seed=int(ant_cfg["seed"]),
                        latent_dim=int(ant_cfg["latent_dim"]),
                        stage=stage,
                    )
                )
            )
            self.ants[ant.identity] = ant

    @property
    def identities(self) -> tuple[str, ...]:
        return (self.queen.identity, *self.ants.keys())

    def inventory(self) -> dict:
        return {
            "community_id": self.community_id,
            "storage_namespace": self.storage_namespace,
            "queen": {
                "model_id": self.queen.identity,
                "fingerprint": self.queen.active.fingerprint(),
                "checkpoint_version": self.queen.checkpoint_version,
            },
            "ants": [
                {
                    "model_id": ant.identity,
                    "fingerprint": ant.active.fingerprint(),
                    "checkpoint_version": ant.checkpoint_version,
                    "training_steps": ant.training_steps,
                }
                for ant in self.ants.values()
            ],
        }


class SocietyRuntime:
    def __init__(self, config_path: Path) -> None:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
        if payload.get("allow_spawn") is not False:
            raise ValueError("model spawning must remain disabled")
        if payload.get("allow_delete_identity") is not False:
            raise ValueError("identity deletion must remain disabled")

        stage = DevelopmentStage[payload["initial_stage"]]
        self.bridge_policy = dict(payload["cross_community_bridge"])
        self.communities: dict[str, CommunityRuntime] = {}
        for item in payload["communities"]:
            community = CommunityRuntime(item, stage)
            if community.community_id in self.communities:
                raise ValueError("duplicate community identity")
            self.communities[community.community_id] = community

        identities: list[str] = []
        fingerprints: list[str] = []
        namespaces: list[str] = []
        for community in self.communities.values():
            identities.extend(community.identities)
            namespaces.append(community.storage_namespace)
            inventory = community.inventory()
            fingerprints.append(inventory["queen"]["fingerprint"])
            fingerprints.extend(item["fingerprint"] for item in inventory["ants"])
        if len(set(identities)) != len(identities):
            raise ValueError("model identities must be globally unique")
        if len(set(fingerprints)) != len(fingerprints):
            raise ValueError("all learned initial weights must be distinct")
        if len(set(namespaces)) != len(namespaces):
            raise ValueError("community storage namespaces must be isolated")
        self.fixed_identities = tuple(sorted(identities))

    def spawn_ant(self, *_args, **_kwargs) -> None:
        raise RuntimeError("reproduction is disabled; the identity roster is permanent")

    def delete_identity(self, *_args, **_kwargs) -> None:
        raise RuntimeError("identity deletion is forbidden")

    def exchange(
        self,
        *,
        source_community: str,
        target_community: str,
        payload_kind: str,
    ) -> BridgeDecision:
        if source_community == target_community:
            return BridgeDecision(True, "local community event")
        if not self.bridge_policy.get("enabled", False):
            return BridgeDecision(False, "cross-community bridge is closed")
        if payload_kind in self.bridge_policy.get("forbidden_payloads", []):
            return BridgeDecision(False, "payload kind is permanently forbidden")
        if payload_kind not in self.bridge_policy.get("allowed_payloads", []):
            return BridgeDecision(False, "payload kind is not allowlisted")
        return BridgeDecision(True, "reviewed summary accepted by bridge policy")

    def inventory(self) -> dict:
        return {
            "allow_spawn": False,
            "allow_delete_identity": False,
            "cross_community_bridge_enabled": bool(
                self.bridge_policy.get("enabled", False)
            ),
            "fixed_identities": list(self.fixed_identities),
            "communities": [
                community.inventory() for community in self.communities.values()
            ],
        }
