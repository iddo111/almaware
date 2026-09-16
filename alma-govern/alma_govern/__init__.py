"""ALMA-Govern -- shared thermal/CPU/GPU + fleet-health governance SDK.

Principle: "mic always wins", protect the hardware. Detection first; every
"protect" action is advisory and opt-in, never auto-destructive.
"""
from .fleet_health import (
    Severity,
    Thresholds,
    DEFAULT_THRESHOLDS,
    Finding,
    NodeAssessment,
    detect_network_storm,
    detect_memory_pressure,
    detect_gpu_health,
    assess_node,
)
from .public_benefit import (
    Decision,
    InitiativeProposal,
    GateResult,
    assess_public_benefit,
)

__all__ = [
    "Severity",
    "Thresholds",
    "DEFAULT_THRESHOLDS",
    "Finding",
    "NodeAssessment",
    "detect_network_storm",
    "detect_memory_pressure",
    "detect_gpu_health",
    "assess_node",
    "Decision",
    "InitiativeProposal",
    "GateResult",
    "assess_public_benefit",
]

__version__ = "0.3.0"
