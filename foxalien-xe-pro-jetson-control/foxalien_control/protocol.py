from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


VALID_STATES = {
    "Idle",
    "Run",
    "Hold",
    "Jog",
    "Alarm",
    "Door",
    "Check",
    "Home",
    "Sleep",
    "Unknown",
    "Disconnected",
}


@dataclass
class GrblStatus:
    state: str = "Disconnected"
    substate: Optional[str] = None
    machine_position: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    work_position: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    feed: float = 0.0
    spindle: float = 0.0
    pins: str = ""
    raw: str = ""
    fields: Dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, object]:
        return {
            "state": self.state,
            "substate": self.substate,
            "machine_position": self.machine_position,
            "work_position": self.work_position,
            "feed": self.feed,
            "spindle": self.spindle,
            "pins": self.pins,
            "raw": self.raw,
        }


def _floats(value: str, count: int) -> List[float]:
    values = [float(item) for item in value.split(",")]
    if len(values) != count:
        raise ValueError(f"Expected {count} values, got {len(values)}")
    return values


def parse_status_report(line: str) -> GrblStatus:
    text = line.strip()
    if not (text.startswith("<") and text.endswith(">")):
        raise ValueError("Not a GRBL status report")

    chunks = text[1:-1].split("|")
    state_bits = chunks[0].split(":", 1)
    state = state_bits[0]
    if state not in VALID_STATES:
        state = "Unknown"
    status = GrblStatus(
        state=state,
        substate=state_bits[1] if len(state_bits) > 1 else None,
        raw=text,
    )

    for chunk in chunks[1:]:
        if ":" not in chunk:
            continue
        key, value = chunk.split(":", 1)
        status.fields[key] = value

    if "MPos" in status.fields:
        status.machine_position = _floats(status.fields["MPos"], 3)
    if "WPos" in status.fields:
        status.work_position = _floats(status.fields["WPos"], 3)
    elif "WCO" in status.fields:
        wco = _floats(status.fields["WCO"], 3)
        status.work_position = [
            status.machine_position[index] - wco[index] for index in range(3)
        ]
    if "FS" in status.fields:
        values = _floats(status.fields["FS"], 2)
        status.feed, status.spindle = values
    elif "F" in status.fields:
        status.feed = float(status.fields["F"])
    status.pins = status.fields.get("Pn", "")
    return status
