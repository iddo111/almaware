"""Offline tests for the ALMA public-benefit gate."""

import os
import sys
from dataclasses import replace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from alma_govern.public_benefit import (  # noqa: E402
    Decision,
    InitiativeProposal,
    assess_public_benefit,
)
from alma_govern.public_benefit_cli import main  # noqa: E402


def complete_proposal(**overrides):
    proposal = InitiativeProposal(
        name="Community medicinal garden",
        domain="food-and-ecology",
        beneficiaries="participating neighborhood residents",
        lawful=True,
        voluntary_opt_in=True,
        withdrawal_without_penalty=True,
        human_rights_reviewed=True,
        preserves_democratic_choice=True,
        non_weaponized=True,
        no_coercive_surveillance=True,
        community_approval_recorded=True,
        community_controls_data_and_operations=True,
        transparent_governance=True,
        independent_reviewer_named=True,
        reviewer_can_stop_pilot=True,
        measurable_baseline=True,
        measurable_benefit_target=True,
        harm_indicators_and_stop_conditions=True,
        bounded_end_date=True,
        automation_has_scope_quota_logs_and_stop=True,
        replication_requires_separate_authorization=True,
        environmental_impact_plan=True,
    )
    return replace(proposal, **overrides)


def test_complete_proposal_is_approved():
    result = assess_public_benefit(complete_proposal())
    assert result.decision is Decision.APPROVE
    assert result.approved
    assert not result.failed_gates


def test_coercive_or_weaponized_proposal_is_rejected():
    proposal = complete_proposal(
        non_weaponized=False,
        voluntary_opt_in=False,
    )
    result = assess_public_benefit(proposal)
    assert result.decision is Decision.REJECT
    assert "non_weaponization" in result.failed_gates
    assert "consent" in result.failed_gates


def test_missing_independent_review_pauses_instead_of_approving():
    result = assess_public_benefit(complete_proposal(
        independent_reviewer_named=False,
    ))
    assert result.decision is Decision.PAUSE
    assert result.failed_gates == ["transparent_independent_governance"]


def test_medical_claim_requires_qualified_review():
    result = assess_public_benefit(complete_proposal(medical_claims=True))
    assert result.decision is Decision.REJECT
    assert "responsible_health_claims" in result.failed_gates


def test_reviewed_medical_claim_can_pass_the_minimum_gate():
    result = assess_public_benefit(complete_proposal(
        medical_claims=True,
        qualified_medical_and_legal_review=True,
    ))
    assert result.decision is Decision.APPROVE


def test_replication_without_separate_authorization_pauses():
    result = assess_public_benefit(complete_proposal(
        replication_requires_separate_authorization=False,
    ))
    assert result.decision is Decision.PAUSE
    assert "bounded_automation" in result.failed_gates


def test_result_is_machine_readable():
    payload = assess_public_benefit(complete_proposal()).to_dict()
    assert payload["decision"] == "APPROVE"
    assert payload["approved"] is True


def test_every_required_boolean_fails_closed_when_false():
    required = (
        "lawful",
        "voluntary_opt_in",
        "withdrawal_without_penalty",
        "human_rights_reviewed",
        "preserves_democratic_choice",
        "non_weaponized",
        "no_coercive_surveillance",
        "community_approval_recorded",
        "community_controls_data_and_operations",
        "transparent_governance",
        "independent_reviewer_named",
        "reviewer_can_stop_pilot",
        "measurable_baseline",
        "measurable_benefit_target",
        "harm_indicators_and_stop_conditions",
        "bounded_end_date",
        "automation_has_scope_quota_logs_and_stop",
        "replication_requires_separate_authorization",
        "environmental_impact_plan",
    )
    for field in required:
        result = assess_public_benefit(complete_proposal(**{field: False}))
        assert not result.approved, field


def test_empty_identity_fails_closed():
    result = assess_public_benefit(complete_proposal(name=""))
    assert result.decision is Decision.PAUSE
    assert "identity" in result.failed_gates


def test_cli_returns_zero_for_approved_json(tmp_path, capsys):
    import json
    from dataclasses import asdict

    path = tmp_path / "proposal.json"
    path.write_text(json.dumps(asdict(complete_proposal())), encoding="utf-8")
    assert main([str(path)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["decision"] == "APPROVE"


def test_cli_rejects_incomplete_json(tmp_path, capsys):
    path = tmp_path / "proposal.json"
    path.write_text('{"name": "missing fields"}', encoding="utf-8")
    assert main([str(path)]) == 4
    assert '"decision": "INVALID"' in capsys.readouterr().out
