"""Tests for Gemini LLM integration (Phase 3C)."""

from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from recovery.intelligence.contracts import PredictiveSignals, ReasoningInsight
from recovery.intelligence.gemini.client import GeminiStructuredClient
from recovery.intelligence.gemini.config import GeminiConfig
from recovery.intelligence.gemini.reasoning import GeminiReasoningIntelligence
from recovery.intelligence.gemini.strategy import GeminiStrategyIntelligence
from recovery.intelligence.llm.prompts import build_reasoning_prompt
from recovery.intelligence.llm.sanitize import context_for_prompt
from recovery.intelligence.llm.schemas import ReasoningPayload, StrategyPayload, parse_json_response
from recovery.models.recovery_context import (
    CaseFacts,
    CustomerHistorySnapshot,
    DerivedSignals,
    RecoveryContext,
    RecoveryHistoryEvent,
)


@dataclass
class _FakeGeminiResponse:
    text: str


class _FakeGeminiModels:
    def __init__(self, payload: dict) -> None:
        self._payload = payload
        self.last_call: dict | None = None

    def generate_content(self, **kwargs):
        self.last_call = kwargs
        return _FakeGeminiResponse(text=json.dumps(self._payload))


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
        recovery_history=(
            RecoveryHistoryEvent(
                timestamp="2026-01-01T00:00:00+00:00",
                event_type="payment_failed",
                action=None,
                result="failed",
                state_before=None,
                state_after="detected",
                actor="system",
                detail="initial failure",
            ),
        ),
        derived_signals=DerivedSignals(
            first_failure=False,
            repeated_failure=False,
            prior_successful_payment=True,
            retry_exhaustion_risk=False,
            recent_contact=False,
            customer_non_response=False,
            customer_opt_out=False,
            near_recovery_window_end=False,
            transient_failure=False,
        ),
        built_at="2026-01-01T00:00:00+00:00",
    )


def test_context_for_prompt_excludes_forbidden_keys():
    ctx = _sample_context()
    payload = context_for_prompt(ctx)
    dumped = json.dumps(payload)
    assert "p_pay_anyway" not in dumped
    assert "ground_truth" not in dumped


def test_parse_json_response_strips_markdown_fence():
    raw = '```json\n{"summary": "ok", "likely_cause": "insufficient_funds", "confidence": 0.8, "key_factors": ["a"]}\n```'
    parsed = parse_json_response(raw)
    assert parsed["likely_cause"] == "insufficient_funds"


def test_reasoning_payload_validates_cause():
    with pytest.raises(ValueError, match="Invalid likely_cause"):
        ReasoningPayload.from_dict(
            {
                "summary": "test",
                "likely_cause": "not_a_real_cause",
                "confidence": 0.5,
                "key_factors": [],
            }
        )


def test_strategy_payload_validates_action_ids():
    with pytest.raises(ValueError, match="Invalid action_id"):
        StrategyPayload.from_dict(
            {"strategies": [{"action_id": "invalid_action", "rationale": "x", "priority": 1, "confidence": 0.5}]},
            {"retry_payment"},
        )


def test_build_reasoning_prompt_contains_context():
    ctx = _sample_context()
    system, user = build_reasoning_prompt(ctx)
    assert "RecoveryContext" in user
    assert "case_test_001" in user
    assert "JSON" in system


def test_gemini_reasoning_intelligence_with_mock_client():
    ctx = _sample_context()
    fake_payload = {
        "summary": "Insufficient funds with retry headroom.",
        "likely_cause": "insufficient_funds",
        "confidence": 0.82,
        "key_factors": ["insufficient_funds", "retry_count=1"],
    }
    models = _FakeGeminiModels(fake_payload)
    client = GeminiStructuredClient(
        config=GeminiConfig(api_key="test-key", model="gemini-3.6-flash", max_tokens=256, enabled=True),
        client=_FakeGeminiClient(models),
    )
    intel = GeminiReasoningIntelligence(client=client)
    insight = intel.interpret(ctx)
    assert insight.source == "gemini"
    assert insight.likely_cause == "insufficient_funds"
    assert insight.confidence == pytest.approx(0.82)
    assert models.last_call is not None
    assert models.last_call["model"] == "gemini-3.6-flash"
    assert models.last_call["config"]["response_mime_type"] == "application/json"


def test_gemini_strategy_intelligence_with_mock_client():
    ctx = _sample_context()
    reasoning = ReasoningInsight(
        summary="Insufficient funds",
        likely_cause="insufficient_funds",
        confidence=0.8,
        key_factors=("insufficient_funds",),
        source="gemini",
    )
    predictive = PredictiveSignals(
        estimated_recovery_probability=0.7,
        retry_success_likelihood=0.75,
        responsiveness_score=0.6,
    )
    fake_payload = {
        "strategies": [
            {
                "action_id": "wait_and_retry",
                "rationale": "Allow time for balance top-up",
                "priority": 1,
                "confidence": 0.75,
            },
            {
                "action_id": "send_email",
                "rationale": "Notify customer",
                "priority": 2,
                "confidence": 0.6,
            },
        ]
    }
    models = _FakeGeminiModels(fake_payload)
    client = GeminiStructuredClient(
        config=GeminiConfig(api_key="test-key", model="gemini-3.6-flash", max_tokens=256, enabled=True),
        client=_FakeGeminiClient(models),
    )
    intel = GeminiStrategyIntelligence(client=client)
    proposals = intel.propose_strategies(ctx, reasoning, predictive)
    assert len(proposals) == 2
    assert proposals[0].source == "gemini"
    assert proposals[0].action.action_id == "wait_and_retry"
    assert proposals[0].action.is_retry is True
    assert "balance" in proposals[0].rationale.lower()


def test_gemini_client_unavailable_without_api_key():
    client = GeminiStructuredClient(
        config=GeminiConfig(api_key=None, model="gemini-3.6-flash", max_tokens=256, enabled=True),
    )
    with pytest.raises(RuntimeError, match="not available"):
        client.complete_json(system="s", user="u")
