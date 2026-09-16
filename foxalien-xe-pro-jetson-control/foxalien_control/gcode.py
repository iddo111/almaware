from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Sequence


COMMENT_PARENS = re.compile(r"\([^)]*\)")
WORD = re.compile(r"([A-Z])([+-]?(?:\d+(?:\.\d*)?|\.\d+))")
ALLOWED_G = {
    0.0,
    1.0,
    4.0,
    17.0,
    20.0,
    21.0,
    40.0,
    49.0,
    54.0,
    55.0,
    56.0,
    57.0,
    58.0,
    59.0,
    80.0,
    90.0,
    91.0,
    94.0,
}
ALLOWED_M = {2, 5, 30}
ALLOWED_LETTERS = {"G", "M", "N", "P", "X", "Y", "Z", "F"}


@dataclass
class ValidationIssue:
    line: int
    severity: str
    message: str

    def as_dict(self) -> Dict[str, object]:
        return {"line": self.line, "severity": self.severity, "message": self.message}


@dataclass
class ValidationResult:
    valid: bool
    normalized_lines: List[str] = field(default_factory=list)
    issues: List[ValidationIssue] = field(default_factory=list)
    extents: Dict[str, List[float]] = field(default_factory=dict)
    distance_mm: float = 0.0

    def as_dict(self) -> Dict[str, object]:
        return {
            "valid": self.valid,
            "normalized_lines": self.normalized_lines,
            "issues": [issue.as_dict() for issue in self.issues],
            "extents": self.extents,
            "distance_mm": round(self.distance_mm, 3),
        }


def normalize_line(raw: str) -> str:
    text = COMMENT_PARENS.sub("", raw.upper())
    text = text.split(";", 1)[0]
    return "".join(text.split())


def validate_program(
    source: str,
    envelope: Sequence[float] = (400.0, 400.0, 95.0),
    max_feed_mm_min: float = 5000.0,
    spindle_commands_enabled: bool = False,
) -> ValidationResult:
    issues: List[ValidationIssue] = []
    normalized: List[str] = []
    position = [0.0, 0.0, 0.0]
    minimum = [0.0, 0.0, 0.0]
    maximum = [0.0, 0.0, 0.0]
    absolute = True
    units_scale = 1.0
    saw_units = False
    saw_distance_mode = False
    distance = 0.0

    for line_number, raw in enumerate(source.splitlines(), start=1):
        line = normalize_line(raw)
        if not line:
            continue
        normalized.append(line)

        if line.startswith("$") or "%" in line:
            issues.append(
                ValidationIssue(line_number, "error", "System and percent commands are not accepted in job files")
            )
            continue

        tokens = WORD.findall(line)
        reconstructed = "".join(letter + number for letter, number in tokens)
        if not tokens or reconstructed != line:
            issues.append(
                ValidationIssue(line_number, "error", "Line contains an unrecognised or malformed word")
            )
            continue

        values: Dict[str, List[float]] = {}
        for letter, number in tokens:
            values.setdefault(letter, []).append(float(number))

        for letter in values:
            if letter not in ALLOWED_LETTERS:
                issues.append(
                    ValidationIssue(line_number, "error", f"Unsupported word {letter}")
                )
        for axis in ("X", "Y", "Z"):
            if len(values.get(axis, [])) > 1:
                issues.append(
                    ValidationIssue(line_number, "error", f"Duplicate {axis} word")
                )

        line_motion = False
        for g_value in values.get("G", []):
            rounded = round(g_value, 3)
            if rounded in {2.0, 3.0}:
                issues.append(
                    ValidationIssue(line_number, "error", "Arc moves G2/G3 are locked in this recovery build")
                )
            elif rounded not in ALLOWED_G:
                issues.append(
                    ValidationIssue(line_number, "error", f"Unsupported G-code G{g_value:g}")
                )
            elif rounded == 20.0:
                units_scale = 25.4
                saw_units = True
            elif rounded == 21.0:
                units_scale = 1.0
                saw_units = True
            elif rounded == 90.0:
                absolute = True
                saw_distance_mode = True
            elif rounded == 91.0:
                absolute = False
                saw_distance_mode = True
            elif rounded in {0.0, 1.0}:
                line_motion = True

        for m_value in values.get("M", []):
            m_code = int(m_value)
            if m_value != m_code or m_code not in ALLOWED_M:
                if m_code in {3, 4, 7, 8}:
                    message = "Spindle and coolant start commands are locked"
                    if spindle_commands_enabled and m_code in {3, 4}:
                        message = "Spindle start remains blocked in the recovery build"
                    issues.append(ValidationIssue(line_number, "error", message))
                else:
                    issues.append(
                        ValidationIssue(line_number, "error", f"Unsupported M-code M{m_value:g}")
                    )

        if "P" in values:
            if 4.0 not in [round(value, 3) for value in values.get("G", [])]:
                issues.append(ValidationIssue(line_number, "error", "P is accepted only with G4 dwell"))
            elif values["P"][-1] < 0 or values["P"][-1] > 2:
                issues.append(ValidationIssue(line_number, "error", "G4 dwell is limited to 2 seconds"))

        if "S" in values:
            issues.append(ValidationIssue(line_number, "error", "Spindle speed words are locked"))

        if "F" in values:
            feed = values["F"][-1] * units_scale
            if feed <= 0 or feed > max_feed_mm_min:
                issues.append(
                    ValidationIssue(
                        line_number,
                        "error",
                        f"Feed {feed:g} mm/min is outside 0-{max_feed_mm_min:g}",
                    )
                )

        axis_values = []
        for index, axis in enumerate(("X", "Y", "Z")):
            if axis not in values:
                continue
            requested = values[axis][-1] * units_scale
            target = requested if absolute else position[index] + requested
            axis_values.append((index, target))

        if axis_values:
            if not line_motion:
                issues.append(
                    ValidationIssue(line_number, "error", "Every recovery-build move must explicitly include G0 or G1")
                )
            if not saw_units:
                issues.append(
                    ValidationIssue(line_number, "error", "Set G20 or G21 before the first move")
                )
            if not saw_distance_mode:
                issues.append(
                    ValidationIssue(line_number, "error", "Set G90 or G91 before the first move")
                )
            previous = list(position)
            for index, target in axis_values:
                position[index] = target
                minimum[index] = min(minimum[index], target)
                maximum[index] = max(maximum[index], target)
            distance += sum((position[i] - previous[i]) ** 2 for i in range(3)) ** 0.5

    if not normalized:
        issues.append(ValidationIssue(0, "error", "Program is empty"))
    for index, axis in enumerate(("X", "Y", "Z")):
        span = maximum[index] - minimum[index]
        if span > float(envelope[index]) + 1e-6:
            issues.append(
                ValidationIssue(
                    0,
                    "error",
                    f"{axis} travel span {span:.3f} mm exceeds {float(envelope[index]):.3f} mm envelope",
                )
            )

    return ValidationResult(
        valid=not any(issue.severity == "error" for issue in issues),
        normalized_lines=normalized,
        issues=issues,
        extents={
            axis.lower(): [round(minimum[i], 3), round(maximum[i], 3)]
            for i, axis in enumerate(("X", "Y", "Z"))
        },
        distance_mm=distance,
    )
