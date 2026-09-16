"""Executable public-benefit gate for ALMA initiatives.

This module does not decide whether a project is morally good. It enforces a
small set of minimum, auditable conditions before a pilot can start or scale.
Missing evidence fails closed.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Iterable, List


class Decision(str, Enum):
    APPROVE = "APPROVE"
    PAUSE = "PAUSE"
    REJECT = "REJECT"


@dataclass(frozen=True)
class InitiativeProposal:
    name: str
    domain: str
    beneficiaries: str
    lawful: bool
    voluntary_opt_in: bool
    withdrawal_without_penalty: bool
    human_rights_reviewed: bool
    preserves_democratic_choice: bool
    non_weaponized: bool
    no_coercive_surveillance: bool
    community_approval_recorded: bool
    community_controls_data_and_operations: bool
    transparent_governance: bool
    independent_reviewer_named: bool
    reviewer_can_stop_pilot: bool
    measurable_baseline: bool
    measurable_benefit_target: bool
    harm_indicators_and_stop_conditions: bool
    bounded_end_date: bool
    automation_has_scope_quota_logs_and_stop: bool
    replication_requires_separate_authorization: bool
    environmental_impact_plan: bool
    medical_claims: bool = False
    qualified_medical_and_legal_review: bool = False
    notes: Dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class GateResult:
    decision: Decision
    failed_gates: List[str]
    passed_gates: List[str]

    @property
    def approved(self) -> bool:
        return self.decision is Decision.APPROVE

    def to_dict(self) -> Dict[str, object]:
        return {
            "decision": self.decision.value,
            "approved": self.approved,
            "failed_gates": list(self.failed_gates),
            "passed_gates": list(self.passed_gates),
        }


def _all(proposal: InitiativeProposal, fields: Iterable[str]) -> bool:
    return all(bool(getattr(proposal, name)) for name in fields)


def assess_public_benefit(proposal: InitiativeProposal) -> GateResult:
    """Assess a proposal, failing closed when a hard gate lacks evidence."""

    gates = {
        "identity": bool(proposal.name.strip() and proposal.domain.strip()
                         and proposal.beneficiaries.strip()),
        "law_and_rights": _all(proposal, (
            "lawful", "human_rights_reviewed", "preserves_democratic_choice",
        )),
        "consent": _all(proposal, (
            "voluntary_opt_in", "withdrawal_without_penalty",
        )),
        "non_weaponization": _all(proposal, (
            "non_weaponized", "no_coercive_surveillance",
        )),
        "community_control": _all(proposal, (
            "community_approval_recorded",
            "community_controls_data_and_operations",
        )),
        "transparent_independent_governance": _all(proposal, (
            "transparent_governance", "independent_reviewer_named",
            "reviewer_can_stop_pilot",
        )),
        "measurable_bounded_pilot": _all(proposal, (
            "measurable_baseline", "measurable_benefit_target",
            "harm_indicators_and_stop_conditions", "bounded_end_date",
        )),
        "bounded_automation": _all(proposal, (
            "automation_has_scope_quota_logs_and_stop",
            "replication_requires_separate_authorization",
        )),
        "environment": proposal.environmental_impact_plan,
        "responsible_health_claims": (
            not proposal.medical_claims
            or proposal.qualified_medical_and_legal_review
        ),
    }

    passed = [name for name, ok in gates.items() if ok]
    failed = [name for name, ok in gates.items() if not ok]

    reject_gates = {
        "law_and_rights", "consent", "non_weaponization",
        "responsible_health_claims",
    }
    if not failed:
        decision = Decision.APPROVE
    elif reject_gates.intersection(failed):
        decision = Decision.REJECT
    else:
        decision = Decision.PAUSE

    return GateResult(decision=decision, failed_gates=failed,
                      passed_gates=passed)
