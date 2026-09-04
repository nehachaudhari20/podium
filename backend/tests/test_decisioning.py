"""Tests for Phase 3D hybrid decisioning and policy evaluation."""

from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from recovery.intelligence.action_bridge import catalog_to_runtime, map_strategy_proposals_to_runtime
from recovery.intelligence.contracts import ReasoningInsight, StrategyProposal
from recovery.intelligence.decision_config import DecisionConfig
from recovery.intelligence.decision_evaluator import evaluate_decision_proposal
from recovery.intelligence.decisioning import HybridDecisionIntelligence
from recovery.intelligence.deterministic.decision import propose_deterministic_decision
from recovery.intelligence.gemini.client import GeminiStructuredClient
from recovery.intelligence.gemini.config import GeminiConfig
from recovery.models.recovery_context import (
    CaseFacts,
    CustomerHistorySnapshot,
    DerivedSignals,
    RecoveryContext,
    RecoveryHistoryEvent,
)
from recovery.models.recovery_types import RecoveryAction


@dataclass
class _FakeGeminiResponse:
    text: str


class _FakeGeminiModels:
    def __init__(self, payloads: list[dict]) -> None:
        self._payloads = payloads
        self.calls = 0

    def generate_content(self, **kwargs):
        payload = self._payloads[min(self.calls, len(self._payloads) - 1)]
        self.calls += 1
        return _FakeGeminiResponse(text=json.dumps(payload))


class _FakeGeminiClient:
    def __init__(self, models: _FakeGeminiModels) -> None:
        self.models = models


def _sample_context() -> RecoveryContext:
    return RecoveryContext(
        case=CaseFacts(
            case_id="case_test_001",
            customer_id="cust_001",
            lane="subscription_payment",
            amount=999.0,
            currency="INR",
            workflow_state="detected",
            status="open",
            failure_reason="insufficient_funds",
            recoverability_hint="retryable",
            attempt_count=1,
            created_at="2026-01-01T00:00:00+00:00",
            recovery_window_end="2026-01-15T00:00:00+00:00",
            source_ref_id="sub_001",
        ),
        customer=CustomerHistorySnapshot(
            customer_id="cust_001",
            segment="standard",
            opt_out=False,
            prior_contacts_7d=0,
            total_failed_payments=1,
            total_successful_payments=2,
            prior_recovery_actions=0,
            contacts_with_no_response=0,
        ),
        recovery_history=(),
        derived_signals=DerivedSignals(
            first_failure=False,
            repeated_failure=False,
            prior_successful_payment=True,
            retry_exhaustion_risk=False,
            recent_contact=False,
            customer_non_response=False,
            customer_opt_out=False,
            near_recovery_window_end=False,
        ),
        built_at="2026-01-01T00:00:00+00:00",
    )


def test_catalog_to_runtime_maps_retry_actions():
    action = catalog_to_runtime("wait_and_retry", "insufficient_funds")
    assert action is not None
    assert action.is_retry is True
    assert action.action_id in {"retry_24h", "retry_72h"}


def test_hybrid_falls_back_to_deterministic_on_low_confidence():
    reasoning_payload = {
        "summary": "Low confidence guess",
        "likely_cause": "insufficient_funds",
        "confidence": 0.1,
        "key_factors": ["insufficient_funds"],
    }
    strategy_payload = {
        "strategies": [
            {
                "action_id": "wait_and_retry",
                "rationale": "retry",
                "priority": 1,
                "confidence": 0.9,
            }
        ]
    }
    client = GeminiStructuredClient(
        config=GeminiConfig(api_key="test", model="gemini-3.6-flash", max_tokens=256, enabled=True),
        client=_FakeGeminiClient(_FakeGeminiModels([reasoning_payload, strategy_payload])),
    )
    from recovery.intelligence.gemini.reasoning import GeminiReasoningIntelligence
    from recovery.intelligence.gemini.strategy import GeminiStrategyIntelligence

    intel = HybridDecisionIntelligence(
        config=DecisionConfig(mode="hybrid", min_reasoning_confidence=0.4, min_strategy_confidence=0.3),
        gemini_reasoning=GeminiReasoningIntelligence(client=client),
        gemini_strategy=GeminiStrategyIntelligence(client=client),
    )
    proposal = intel.propose_decision(_sample_context())
    assert proposal.source == "deterministic"


def test_hybrid_uses_gemini_when_confident():
    reasoning_payload = {
        "summary": "Insufficient funds with retry headroom.",
        "likely_cause": "insufficient_funds",
        "confidence": 0.9,
        "key_factors": ["insufficient_funds"],
    }
    strategy_payload = {
        "strategies": [
            {
                "action_id": "wait_and_retry",
                "rationale": "Allow balance top-up",
                "priority": 1,
                "confidence": 0.85,
            }
        ]
    }
    client = GeminiStructuredClient(
        config=GeminiConfig(api_key="test", model="gemini-3.6-flash", max_tokens=256, enabled=True),
        client=_FakeGeminiClient(_FakeGeminiModels([reasoning_payload, strategy_payload])),
    )
    from recovery.intelligence.gemini.reasoning import GeminiReasoningIntelligence
    from recovery.intelligence.gemini.strategy import GeminiStrategyIntelligence

    intel = HybridDecisionIntelligence(
        config=DecisionConfig(mode="hybrid", min_reasoning_confidence=0.4, min_strategy_confidence=0.3),
        gemini_reasoning=GeminiReasoningIntelligence(client=client),
        gemini_strategy=GeminiStrategyIntelligence(client=client),
    )
    proposal = intel.propose_decision(_sample_context())
    assert proposal.source == "gemini"
    assert proposal.recommended_action.is_retry is True


def test_evaluate_decision_proposal_respects_policy():
    context = _sample_context()
    proposal = propose_deterministic_decision(context)
    from recovery.intelligence.adapters import case_facts_to_runtime
    from recovery.ingestion.customer_loader import CustomerContext

    runtime_case = case_facts_to_runtime(context.case)
    customer = CustomerContext(
        customer_id="cust_001",
        segment="standard",
        opt_out=False,
        prior_contacts_7d=0,
    )
    evaluated = evaluate_decision_proposal(proposal, runtime_case, customer)
    assert evaluated.selected_action is not None
    assert evaluated.policy_result is not None
    assert evaluated.policy_result.allowed is True
