"""Disk, thermal, and heartbeat guards without a neural dependency."""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from .io_utils import atomic_write_json
from .labels import HEARTBEAT_NOT_ACCEPTANCE_EVIDENCE


class SafetyBlock(RuntimeError):
    """Raised when a fail-closed operational guard blocks training."""


@dataclass(frozen=True)
class GuardSnapshot:
    free_gib: float
    free_percent: float
    gpu_temperatures_c: tuple[float, ...]

    def to_dict(self) -> dict[str, float | list[float]]:
        return {
            "free_gib": self.free_gib,
            "free_percent": self.free_percent,
            "gpu_temperatures_c": list(self.gpu_temperatures_c),
        }


def _gpu_temperatures(timeout_seconds: float = 5.0) -> tuple[float, ...]:
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=temperature.gpu",
                "--format=csv,noheader,nounits",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise SafetyBlock(f"thermal guard could not query nvidia-smi: {exc}") from exc
    temperatures: list[float] = []
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if stripped:
            try:
                temperatures.append(float(stripped))
            except ValueError as exc:
                raise SafetyBlock(
                    f"thermal guard received invalid temperature {stripped!r}"
                ) from exc
    if not temperatures:
        raise SafetyBlock("thermal guard found no GPU temperatures")
    return tuple(temperatures)


def assert_operational_guards(
    storage_path: str | Path,
    *,
    min_free_gib: float,
    min_free_percent: float,
    max_gpu_temp_c: float,
) -> GuardSnapshot:
    target = Path(storage_path)
    target.mkdir(parents=True, exist_ok=True)
    usage = shutil.disk_usage(target)
    free_gib = usage.free / (1024.0**3)
    free_percent = 100.0 * usage.free / max(usage.total, 1)
    if free_gib < min_free_gib:
        raise SafetyBlock(
            f"disk guard blocked: {free_gib:.2f} GiB free, "
            f"minimum {min_free_gib:.2f} GiB"
        )
    if free_percent < min_free_percent:
        raise SafetyBlock(
            f"disk guard blocked: {free_percent:.2f}% free, "
            f"minimum {min_free_percent:.2f}%"
        )
    temperatures = _gpu_temperatures()
    hottest = max(temperatures)
    if hottest > max_gpu_temp_c:
        raise SafetyBlock(
            f"thermal guard blocked: hottest GPU is {hottest:.1f} C, "
            f"maximum {max_gpu_temp_c:.1f} C"
        )
    return GuardSnapshot(
        free_gib=free_gib,
        free_percent=free_percent,
        gpu_temperatures_c=temperatures,
    )


class HeartbeatWriter:
    def __init__(self, path: str | Path, *, run_id: str) -> None:
        self.path = Path(path)
        self.run_id = run_id

    def write(
        self,
        *,
        global_step: int,
        state: str,
        latest_shadow_checkpoint: str | None,
        guard_snapshot: GuardSnapshot | None,
    ) -> None:
        atomic_write_json(
            self.path,
            {
                "schema_version": 1,
                "artifact_type": "ANTVOICE_TRAINING_HEARTBEAT",
                "acceptance": HEARTBEAT_NOT_ACCEPTANCE_EVIDENCE,
                "run_id": self.run_id,
                "hostname": socket.gethostname(),
                "pid": os.getpid(),
                "updated_unix": time.time(),
                "global_step": global_step,
                "state": state,
                "latest_shadow_checkpoint": latest_shadow_checkpoint,
                "guards": (
                    guard_snapshot.to_dict()
                    if guard_snapshot is not None
                    else None
                ),
            },
        )


def assert_fresh_heartbeat(
    path: str | Path,
    *,
    max_age_seconds: float,
    require_live_pid: bool = True,
) -> dict[str, object]:
    heartbeat_path = Path(path)
    if not heartbeat_path.is_file():
        raise SafetyBlock(f"heartbeat is missing: {heartbeat_path}")
    try:
        payload = json.loads(heartbeat_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SafetyBlock(f"heartbeat is unreadable: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise SafetyBlock("heartbeat schema is invalid")
    if payload.get("acceptance") != HEARTBEAT_NOT_ACCEPTANCE_EVIDENCE:
        raise SafetyBlock("heartbeat acceptance label is invalid")
    try:
        age = time.time() - float(payload["updated_unix"])
    except (KeyError, TypeError, ValueError) as exc:
        raise SafetyBlock("heartbeat timestamp is invalid") from exc
    if age < -5.0 or age > max_age_seconds:
        raise SafetyBlock(
            f"heartbeat is stale or future-dated: age={age:.1f} seconds"
        )
    state = payload.get("state")
    if not isinstance(state, str) or not state:
        raise SafetyBlock("heartbeat state is invalid")
    if "BLOCKED" in state:
        raise SafetyBlock(f"heartbeat reports blocked state: {state}")
    if require_live_pid and state.startswith("ACTIVE_"):
        try:
            pid = int(payload["pid"])
            os.kill(pid, 0)
        except (KeyError, TypeError, ValueError, OSError) as exc:
            raise SafetyBlock("heartbeat process is not alive") from exc
    return payload
