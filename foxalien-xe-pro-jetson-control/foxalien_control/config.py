from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict


HARDWARE_ENABLE_PHRASE = "I_ACCEPT_PHYSICAL_RISK"


@dataclass(frozen=True)
class MachineConfig:
    mode: str = "simulation"
    serial_port: str = "/dev/ttyACM0"
    baud_rate: int = 115200
    x_mm: float = 400.0
    y_mm: float = 400.0
    z_mm: float = 95.0
    max_feed_mm_min: float = 5000.0
    jog_feed_mm_min: float = 600.0
    max_jog_step_mm: float = 10.0
    spindle_commands_enabled: bool = False
    physical_estop_tested: bool = False
    spindle_power_isolated: bool = False
    motion_controller_verified: bool = False
    bind_host: str = "127.0.0.1"
    bind_port: int = 8765

    @property
    def simulation(self) -> bool:
        return self.mode == "simulation"

    @property
    def hardware_gate_open(self) -> bool:
        return (
            self.mode == "serial"
            and os.environ.get("FOXALIEN_HARDWARE_ENABLE") == HARDWARE_ENABLE_PHRASE
            and self.physical_estop_tested
            and self.spindle_power_isolated
            and self.motion_controller_verified
        )

    def public_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "serial_port": self.serial_port,
            "baud_rate": self.baud_rate,
            "envelope_mm": {"x": self.x_mm, "y": self.y_mm, "z": self.z_mm},
            "max_feed_mm_min": self.max_feed_mm_min,
            "jog_feed_mm_min": self.jog_feed_mm_min,
            "max_jog_step_mm": self.max_jog_step_mm,
            "spindle_commands_enabled": self.spindle_commands_enabled,
            "hardware_gate_open": self.hardware_gate_open,
            "bind": f"{self.bind_host}:{self.bind_port}",
        }


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("Configuration root must be a JSON object")
    return data


def load_config(path: Path) -> MachineConfig:
    data = _read_json(path)
    transport = data.get("transport", {})
    machine = data.get("machine", {})
    safety = data.get("safety", {})
    server = data.get("server", {})

    config = MachineConfig(
        mode=str(transport.get("mode", "simulation")).lower(),
        serial_port=str(transport.get("serial_port", "/dev/ttyACM0")),
        baud_rate=int(transport.get("baud_rate", 115200)),
        x_mm=float(machine.get("x_mm", 400.0)),
        y_mm=float(machine.get("y_mm", 400.0)),
        z_mm=float(machine.get("z_mm", 95.0)),
        max_feed_mm_min=float(machine.get("max_feed_mm_min", 5000.0)),
        jog_feed_mm_min=float(machine.get("jog_feed_mm_min", 600.0)),
        max_jog_step_mm=float(machine.get("max_jog_step_mm", 10.0)),
        spindle_commands_enabled=bool(safety.get("spindle_commands_enabled", False)),
        physical_estop_tested=bool(safety.get("physical_estop_tested", False)),
        spindle_power_isolated=bool(safety.get("spindle_power_isolated", False)),
        motion_controller_verified=bool(safety.get("motion_controller_verified", False)),
        bind_host=str(server.get("host", "127.0.0.1")),
        bind_port=int(server.get("port", 8765)),
    )
    _validate(config)
    return config


def _validate(config: MachineConfig) -> None:
    if config.mode not in {"simulation", "serial"}:
        raise ValueError("transport.mode must be 'simulation' or 'serial'")
    if config.baud_rate != 115200:
        raise ValueError("GRBL v1.1 transport must use 115200 baud")
    if min(config.x_mm, config.y_mm, config.z_mm) <= 0:
        raise ValueError("Machine envelope dimensions must be positive")
    if config.max_feed_mm_min <= 0 or config.jog_feed_mm_min <= 0:
        raise ValueError("Feed limits must be positive")
    if not 0 < config.max_jog_step_mm <= 10:
        raise ValueError("max_jog_step_mm must be greater than 0 and at most 10")
    if config.bind_host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError(
            "This recovery build is localhost-only. Use an SSH tunnel for remote access."
        )
    if config.mode == "serial" and not config.hardware_gate_open:
        raise ValueError(
            "Serial mode is locked. Complete the three physical checks and set "
            "FOXALIEN_HARDWARE_ENABLE=I_ACCEPT_PHYSICAL_RISK for this process."
        )
