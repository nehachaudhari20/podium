"""Phase 2 — diagnosis and strategy unit tests."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from recovery.intelligence.diagnosis import diagnose
from recovery.intelligence.strategy import generate_actions
from recovery.models.case import RecoveryCaseRuntime
from recovery.models.enums import Lane


def _subscription_case(failure_reason: str, **overrides) -> RecoveryCaseRuntime:
    now = datetime(2026, 2, 1, 10, 0, 0)
    defaults = dict(
        case_id="case_test_001",
        customer_id="cust_test_001",
        lane=Lane.SUBSCRIPTION_PAYMENT.value,
        amount=2499.0,
        currency="INR",
        status="open",
        workflow_state="detected",
        created_at=now,
        recovery_window_end=now + timedelta(days=14),
        source_ref_id="sub_test_001",
        failure_reason=failure_reason,
        recoverability_hint="medium",
        days_overdue=None,
        attempt_count=0,
        estimated_recovery_prob=None,
        is_hero=False,
    )
    defaults.update(overrides)
    return RecoveryCaseRuntime(**defaults)


def test_diagnose_insufficient_funds():
    result = diagnose(_subscription_case("insufficient_funds"))
    assert result.likely_cause == "insufficient_funds"
    assert result.confidence >= 0.8
    assert "insufficient" in result.rationale.lower()


def test_diagnose_expired_card_maps_to_payment_method():
    result = diagnose(_subscription_case("expired_card"))
    assert result.likely_cause == "expired_payment_method"
    assert result.confidence >= 0.9


def test_diagnose_transient_failures():
    for reason in ("transient_technical", "network_timeout", "issuer_timeout"):
        result = diagnose(_subscription_case(reason))
        assert result.likely_cause == "transient_failure"


def test_diagnose_rejects_non_subscription_lane():
    case = _subscription_case("insufficient_funds", lane=Lane.CHECKOUT_ABANDONMENT.value)
    with pytest.raises(ValueError, match="subscription_payment"):
        diagnose(case)


def test_generate_actions_insufficient_funds():
    case = _subscription_case("insufficient_funds")
    diagnosis = diagnose(case)
    actions = generate_actions(case, diagnosis)
    action_ids = [a.action_id for a in actions]
    assert action_ids == ["retry_24h", "retry_72h", "payment_method_update"]
    assert actions[0].is_retry and actions[0].retry_delay_hours == 24
    assert actions[2].is_contact


def test_generate_actions_expired_card():
    case = _subscription_case("expired_card")
    diagnosis = diagnose(case)
    actions = generate_actions(case, diagnosis)
    assert [a.action_id for a in actions] == ["payment_method_update", "retry_after_update"]


def test_generate_actions_transient_failure():
    case = _subscription_case("network_timeout")
    diagnosis = diagnose(case)
    actions = generate_actions(case, diagnosis)
    assert [a.action_id for a in actions] == ["retry_6h", "retry_24h"]


def test_generate_actions_repeated_failure_includes_escalation():
    case = _subscription_case("repeated_failure")
    diagnosis = diagnose(case)
    actions = generate_actions(case, diagnosis)
    assert any(a.action_id == "human_escalation" for a in actions)
