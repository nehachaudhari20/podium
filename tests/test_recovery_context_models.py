"""Tests for Phase 3A recovery context domain models."""

from __future__ import annotations

import pytest

from podium.models.recovery_context import (
    FORBIDDEN_CONTEXT_FIELDS,
    CaseFacts,
    CustomerHistorySnapshot,
    DerivedSignals,
    RecoveryContext,
    RecoveryHistoryEvent,
    assert_no_forbidden_fields,
    utc_now_iso,
)


def _minimal_context(**overrides) -> RecoveryContext:
    case = CaseFacts(
        case_id="case_ctx_001",
        customer_id="cust_ctx_001",
        lane="subscription_payment",
        amount=2499.0,
        currency="INR",
        workflow_state="diagnosed",
        status="open",
        failure_reason="insufficient_funds",
        recoverability_hint="medium",
        attempt_count=1,
        created_at="2026-02-01T09:00:00+00:00",
        recovery_window_end="2026-02-15T09:00:00+00:00",
        source_ref_id="sub_ctx_001",
    )
    customer = CustomerHistorySnapshot(
        customer_id="cust_ctx_001",
        segment="b2c",
        opt_out=False,
        prior_contacts_7d=0,
        total_failed_payments=1,
        total_successful_payments=3,
        prior_recovery_actions=0,
        contacts_with_no_response=0,
    )
    history = (
        RecoveryHistoryEvent(
            timestamp="2026-02-01T09:05:00+00:00",
            event_type="DIAGNOSED",
            action=None,
            result=None,
            state_before="detected",
            state_after="diagnosed",
            actor="diagnosis_engine",
            detail="Case diagnosed.",
        ),
    )
    signals = DerivedSignals(
        first_failure=True,
        repeated_failure=False,
        prior_successful_payment=True,
        retry_exhaustion_risk=False,
        recent_contact=False,
        customer_non_response=False,
        customer_opt_out=False,
        near_recovery_window_end=False,
    )
    defaults = dict(
        case=case,
        customer=customer,
        recovery_history=history,
        derived_signals=signals,
        built_at=utc_now_iso(),
    )
    defaults.update(overrides)
    return RecoveryContext(**defaults)


def test_recovery_context_serializable():
    ctx = _minimal_context()
    data = ctx.to_dict()
    assert data["case"]["case_id"] == "case_ctx_001"
    assert data["schema_version"] == "3a.1"
    assert len(data["recovery_history"]) == 1


def test_forbidden_fields_guard():
    with pytest.raises(ValueError, match="p_pay_anyway"):
        assert_no_forbidden_fields({"case": {"p_pay_anyway": 0.5}})
    with pytest.raises(ValueError, match="case_ground_truth"):
        assert_no_forbidden_fields({"meta": {"case_ground_truth": {}}})


def test_forbidden_fields_not_in_model_fields():
    ctx = _minimal_context()
    assert "p_pay_anyway" not in ctx.to_dict()
    assert FORBIDDEN_CONTEXT_FIELDS.isdisjoint(ctx.to_dict().keys())
