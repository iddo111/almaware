"""DGX-only atomic shadow checkpoint storage and resume validation."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

if os.name == "nt":
    raise RuntimeError(
        "AntVoice neural checkpointing is blocked on Windows; run it on a DGX"
    )

import torch

from .io_utils import atomic_write_json, file_sha256
from .labels import SHADOW_TRAINING_CHECKPOINT_ONLY


SHADOW_ARTIFACT_TYPE = "REAL_AUDIO_SHADOW_TRAINING_CHECKPOINT"
RANDOM_INITIALIZATION_ORIGIN = "random_explicit_seed"


def model_state_sha256(model: torch.nn.Module) -> str:
    digest = hashlib.sha256()
    for name, tensor in sorted(model.state_dict().items()):
        contiguous = tensor.detach().cpu().contiguous()
        digest.update(name.encode("utf-8"))
        digest.update(str(contiguous.dtype).encode("ascii"))
        digest.update(json.dumps(list(contiguous.shape)).encode("ascii"))
        digest.update(contiguous.numpy().tobytes())
    return digest.hexdigest()


def capture_rng_state() -> dict[str, Any]:
    import random

    return {
        "python": random.getstate(),
        "torch_cpu": torch.get_rng_state(),
        "torch_cuda": torch.cuda.get_rng_state_all(),
    }


def restore_rng_state(state: dict[str, Any]) -> None:
    import random

    required = {"python", "torch_cpu", "torch_cuda"}
    if set(state) != required:
        raise ValueError("checkpoint RNG state is incomplete")
    random.setstate(state["python"])
    torch.set_rng_state(state["torch_cpu"])
    torch.cuda.set_rng_state_all(state["torch_cuda"])


class ShadowCheckpointStore:
    """Trainer-writable shadow area; never writes to the active tree."""

    def __init__(self, run_root: str | Path) -> None:
        self.run_root = Path(run_root).resolve()
        self.shadow_root = self.run_root / "shadow"
        self.checkpoints = self.shadow_root / "checkpoints"
        self.reports = self.shadow_root / "reports"
        self.latest_pointer = self.shadow_root / "LATEST.json"
        self.active_root = self.run_root / "active"
        self.checkpoints.mkdir(parents=True, exist_ok=True)
        self.reports.mkdir(parents=True, exist_ok=True)

    def _assert_shadow_path(self, path: Path) -> Path:
        resolved = path.resolve()
        try:
            resolved.relative_to(self.shadow_root.resolve())
        except ValueError as exc:
            raise ValueError("trainer checkpoint path must remain inside shadow") from exc
        try:
            resolved.relative_to(self.active_root.resolve())
        except ValueError:
            pass
        else:
            raise ValueError("trainer must never write inside active")
        return resolved

    def _assert_checkpoint_path(self, path: Path) -> Path:
        resolved = self._assert_shadow_path(path)
        try:
            resolved.relative_to(self.checkpoints.resolve())
        except ValueError as exc:
            raise ValueError(
                "checkpoint path must remain inside shadow/checkpoints"
            ) from exc
        if resolved.suffix != ".pt":
            raise ValueError("checkpoint path must end in .pt")
        return resolved

    def save(self, payload: dict[str, Any], *, global_step: int) -> tuple[Path, str]:
        if payload.get("artifact_type") != SHADOW_ARTIFACT_TYPE:
            raise ValueError("shadow checkpoint artifact_type is invalid")
        if payload.get("acceptance") != SHADOW_TRAINING_CHECKPOINT_ONLY:
            raise ValueError("shadow checkpoint acceptance label is invalid")
        destination = self._assert_checkpoint_path(
            self.checkpoints / f"step-{global_step:012d}.pt"
        )
        if destination.exists():
            raise FileExistsError(
                f"immutable shadow checkpoint already exists: {destination}"
            )
        temporary_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=self.checkpoints,
                prefix=f".{destination.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary_name = handle.name
            torch.save(payload, temporary_name)
            with open(temporary_name, "rb") as handle:
                os.fsync(handle.fileno())
            os.replace(temporary_name, destination)
            temporary_name = None
            directory_fd = os.open(self.checkpoints, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            if temporary_name is not None:
                Path(temporary_name).unlink(missing_ok=True)
        digest = file_sha256(destination)
        atomic_write_json(
            destination.with_suffix(".sha256.json"),
            {
                "schema_version": 1,
                "checkpoint": destination.name,
                "sha256": digest,
                "global_step": global_step,
                "lineage": payload.get("lineage"),
            },
        )
        atomic_write_json(
            self.latest_pointer,
            {
                "schema_version": 1,
                "checkpoint": str(destination.relative_to(self.shadow_root)),
                "sha256": digest,
                "global_step": global_step,
            },
        )
        return destination, digest

    def latest(self) -> tuple[Path, str] | None:
        if not self.latest_pointer.is_file():
            return None
        payload = json.loads(self.latest_pointer.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("schema_version") != 1:
            raise ValueError("shadow latest pointer schema is invalid")
        checkpoint_value = payload.get("checkpoint")
        expected_hash = payload.get("sha256")
        if not isinstance(checkpoint_value, str) or not isinstance(
            expected_hash, str
        ):
            raise ValueError("shadow latest pointer fields are invalid")
        checkpoint = self._assert_checkpoint_path(
            self.shadow_root / checkpoint_value
        )
        if not checkpoint.is_file():
            raise ValueError("shadow latest checkpoint is missing")
        if file_sha256(checkpoint) != expected_hash:
            raise ValueError("shadow latest checkpoint hash mismatch")
        return checkpoint, expected_hash

    def verify_resume_lineage(
        self,
        payload: dict[str, Any],
        *,
        checkpoint_sha256: str,
    ) -> None:
        """Walk and hash every declared parent back to the random-init root."""

        lineage = payload.get("lineage")
        if not isinstance(lineage, dict):
            raise ValueError("resume checkpoint lineage is missing")
        chain_depth = lineage.get("chain_depth")
        if not isinstance(chain_depth, int) or chain_depth < 0:
            raise ValueError("resume checkpoint lineage depth is invalid")
        if chain_depth == 0:
            return

        sidecars: dict[str, tuple[Path, dict[str, Any]]] = {}
        for sidecar_path in sorted(self.checkpoints.glob("*.sha256.json")):
            try:
                sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ValueError(
                    f"checkpoint sidecar is unreadable: {sidecar_path}"
                ) from exc
            if not isinstance(sidecar, dict) or sidecar.get("schema_version") != 1:
                raise ValueError(f"checkpoint sidecar schema is invalid: {sidecar_path}")
            digest = sidecar.get("sha256")
            checkpoint_name = sidecar.get("checkpoint")
            if not isinstance(digest, str) or not isinstance(checkpoint_name, str):
                raise ValueError(f"checkpoint sidecar fields are invalid: {sidecar_path}")
            if digest in sidecars:
                raise ValueError(f"duplicate checkpoint digest sidecars: {digest}")
            parent_path = self._assert_checkpoint_path(
                self.checkpoints / checkpoint_name
            )
            sidecars[digest] = (parent_path, sidecar)

        current_indexed = sidecars.get(checkpoint_sha256)
        if current_indexed is None:
            raise ValueError("resume checkpoint sidecar is missing")
        current_path, current_sidecar = current_indexed
        if file_sha256(current_path) != checkpoint_sha256:
            raise ValueError("resume checkpoint sidecar hash mismatch")
        if current_sidecar.get("lineage") != lineage:
            raise ValueError("resume checkpoint sidecar lineage mismatch")
        if chain_depth > len(sidecars) - 1:
            raise ValueError("resume lineage depth exceeds available parent artifacts")
        root_seed = lineage.get("root_initialization_seed")
        root_state_hash = lineage.get("root_model_state_sha256")
        current_parent_hash = lineage.get("parent_checkpoint_sha256")
        child_step = int(payload["training_state"]["global_step"])
        expected_depth = chain_depth - 1
        visited = {checkpoint_sha256}

        while current_parent_hash is not None:
            if current_parent_hash in visited:
                raise ValueError("resume checkpoint lineage contains a cycle")
            visited.add(current_parent_hash)
            indexed = sidecars.get(current_parent_hash)
            if indexed is None:
                raise ValueError(
                    f"resume parent checkpoint is missing: {current_parent_hash}"
                )
            parent_path, sidecar = indexed
            if not parent_path.is_file():
                raise ValueError(f"resume parent artifact is missing: {parent_path}")
            if file_sha256(parent_path) != current_parent_hash:
                raise ValueError(
                    f"resume parent artifact hash mismatch: {parent_path}"
                )
            parent_payload = torch.load(
                parent_path,
                map_location="cpu",
                weights_only=False,
            )
            if not isinstance(parent_payload, dict):
                raise ValueError("resume parent checkpoint root is invalid")
            parent_lineage = parent_payload.get("lineage")
            if sidecar.get("lineage") != parent_lineage:
                raise ValueError("resume parent sidecar lineage mismatch")
            expected_parent_fields = {
                "artifact_type": SHADOW_ARTIFACT_TYPE,
                "acceptance": SHADOW_TRAINING_CHECKPOINT_ONLY,
                "initialization_origin": RANDOM_INITIALIZATION_ORIGIN,
                "run_id": payload.get("run_id"),
                "manifest_sha256": payload.get("manifest_sha256"),
                "model_config_sha256": payload.get("model_config_sha256"),
                "run_config_sha256": payload.get("run_config_sha256"),
            }
            for key, value in expected_parent_fields.items():
                if parent_payload.get(key) != value:
                    raise ValueError(
                        f"resume parent lineage mismatch for {key}"
                    )
            if not isinstance(parent_lineage, dict):
                raise ValueError("resume parent lineage is missing")
            expected_lineage_fields = {
                "initialization_origin": RANDOM_INITIALIZATION_ORIGIN,
                "root_initialization_seed": root_seed,
                "root_model_state_sha256": root_state_hash,
                "chain_depth": expected_depth,
            }
            for key, value in expected_lineage_fields.items():
                if parent_lineage.get(key) != value:
                    raise ValueError(
                        f"resume parent lineage mismatch for {key}"
                    )
            parent_step = int(parent_payload["training_state"]["global_step"])
            if parent_step >= child_step:
                raise ValueError("resume parent step is not earlier than child step")
            if sidecar.get("global_step") != parent_step:
                raise ValueError("resume parent sidecar step mismatch")
            if expected_depth == 0:
                if parent_lineage.get("parent_checkpoint_sha256") is not None:
                    raise ValueError("resume lineage root unexpectedly has a parent")
                if (
                    parent_payload.get("model_state_sha256")
                    != root_state_hash
                ):
                    raise ValueError("resume lineage root model-state hash mismatch")
            current_parent_hash = parent_lineage.get(
                "parent_checkpoint_sha256"
            )
            child_step = parent_step
            expected_depth -= 1
            del parent_payload
        if expected_depth != -1:
            raise ValueError("resume lineage ended before declared root depth")


def load_resume_checkpoint(
    path: str | Path,
    *,
    expected_sha256: str,
    expected_manifest_sha256: str,
    expected_model_config_sha256: str,
    expected_run_config_sha256: str,
    expected_initialization_seed: int,
) -> dict[str, Any]:
    checkpoint_path = Path(path)
    if file_sha256(checkpoint_path) != expected_sha256:
        raise ValueError("resume checkpoint file hash mismatch")
    payload = torch.load(
        checkpoint_path,
        map_location="cpu",
        weights_only=False,
    )
    if not isinstance(payload, dict):
        raise ValueError("resume checkpoint root must be a mapping")
    expected_fields = {
        "artifact_type": SHADOW_ARTIFACT_TYPE,
        "acceptance": SHADOW_TRAINING_CHECKPOINT_ONLY,
        "initialization_origin": RANDOM_INITIALIZATION_ORIGIN,
        "manifest_sha256": expected_manifest_sha256,
        "model_config_sha256": expected_model_config_sha256,
        "run_config_sha256": expected_run_config_sha256,
    }
    for key, value in expected_fields.items():
        if payload.get(key) != value:
            raise ValueError(
                f"resume checkpoint mismatch for {key}: "
                f"{payload.get(key)!r} != {value!r}"
            )
    required_state = {
        "model",
        "optimizer",
        "scaler",
        "rng",
        "sampler",
        "training_state",
    }
    missing = required_state - payload.keys()
    if missing:
        raise ValueError(f"resume checkpoint missing state: {sorted(missing)!r}")
    lineage = payload.get("lineage")
    if not isinstance(lineage, dict):
        raise ValueError("resume checkpoint lineage is missing")
    if lineage.get("initialization_origin") != RANDOM_INITIALIZATION_ORIGIN:
        raise ValueError(
            "resume checkpoint does not descend from random explicit seed"
        )
    if lineage.get("root_initialization_seed") != expected_initialization_seed:
        raise ValueError("resume checkpoint root initialization seed mismatch")
    root_state_hash = lineage.get("root_model_state_sha256")
    if not isinstance(root_state_hash, str) or len(root_state_hash) != 64:
        raise ValueError("resume checkpoint root model-state hash is invalid")
    chain_depth = lineage.get("chain_depth")
    parent_hash = lineage.get("parent_checkpoint_sha256")
    if not isinstance(chain_depth, int) or chain_depth < 0:
        raise ValueError("resume checkpoint lineage depth is invalid")
    if chain_depth == 0:
        if parent_hash is not None:
            raise ValueError("root checkpoint must not name a parent")
        if payload.get("model_state_sha256") != root_state_hash:
            raise ValueError("root checkpoint model-state lineage mismatch")
    elif not isinstance(parent_hash, str) or len(parent_hash) != 64:
        raise ValueError("resume checkpoint parent hash is invalid")
    return payload
