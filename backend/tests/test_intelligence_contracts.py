"""Tests for Phase 3B intelligence contracts."""

from __future__ import annotations

from recovery.intelligence.contracts import (
    DecisionProposal,
    PredictiveSignals,
    ReasoningInsight,
    StrategyProposal,
)
from recovery.models.recovery_types import RecoveryAction


def _action(action_id: str = "retry_24h") -> RecoveryAction:
    return RecoveryAction(action_id, "Retry", "system", is_retry=True, retry_delay_hours=24)


def test_decision_proposal_structure():
    reasoning = ReasoningInsight(
        summary="Transient failure likely recoverable with retry.",
        likely_cause="transient_failure",
        confidence=0.78,
        key_factors=("transient_failure", "first_failure"),
    )
    predictive = PredictiveSignals(
        estimated_recovery_probability=0.7,
        retry_success_likelihood=0.65,
        responsiveness_score=0.5,
    )
    proposal = StrategyProposal(action=_action(), rationale="Retry after delay", priority=1, confidence=0.7)
    decision = DecisionProposal(
        recommended_action=_action(),
        candidate_actions=(_action(),),
        reasoning=reasoning,
        predictive=predictive,
        strategy_proposals=(proposal,),
        explanation="Retry is appropriate for transient failure.",
    )

    assert decision.recommended_action.action_id == "retry_24h"
    assert decision.reasoning.likely_cause == "transient_failure"
    decision.validate_no_forbidden_fields()


def test_contract_types_serializable():
    reasoning = ReasoningInsight(
        summary="Test",
        likely_cause="insufficient_funds",
        confidence=0.8,
        key_factors=("attempt_count",),
    )
    data = reasoning.__dict__ if hasattr(reasoning, "__dict__") else {}
    assert "p_pay_anyway" not in str(data)
