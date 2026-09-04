"""Phase 2 — state machine unit tests."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from recovery.models.case import RecoveryCaseRuntime
from recovery.models.enums import Lane, WorkflowState
from recovery.state.context import CaseRunContext
from recovery.state.machine import InvalidTransitionError, apply_transition, can_transition


def _ctx(state: str = "detected") -> CaseRunContext:
    now = datetime(2026, 2, 1, 10, 0, 0)
    case = RecoveryCaseRuntime(
        case_id="case_fsm_001",
        customer_id="cust_fsm_001",
        lane=Lane.SUBSCRIPTION_PAYMENT.value,
        amount=2499.0,
        currency="INR",
        status="open",
        workflow_state=state,
        created_at=now,
        recovery_window_end=now + timedelta(days=14),
        source_ref_id="sub_fsm_001",
        failure_reason="insufficient_funds",
        recoverability_hint="medium",
        days_overdue=None,
        attempt_count=0,
        estimated_recovery_prob=None,
    )
    return CaseRunContext(case=case)


def test_detected_to_diagnosed():
    ctx = _ctx("detected")
    apply_transition(ctx, "case_diagnosed")
    assert ctx.workflow_state == WorkflowState.DIAGNOSED.value


def test_diagnosed_to_retry_scheduled_to_waiting():
    ctx = _ctx("detected")
    apply_transition(ctx, "case_diagnosed")
    apply_transition(ctx, "retry_scheduled")
    apply_transition(ctx, "waiting_for_retry")
    assert ctx.state_history == ["detected", "diagnosed", "retry_scheduled", "waiting"]


def test_waiting_to_recovered():
    ctx = _ctx("waiting")
    apply_transition(ctx, "payment_succeeds")
    assert ctx.workflow_state == WorkflowState.RECOVERED.value
    assert ctx.terminal is True


def test_max_retries_to_exhausted():
    ctx = _ctx("waiting")
    apply_transition(ctx, "max_retries_exceeded")
    assert ctx.workflow_state == WorkflowState.EXHAUSTED.value
    assert ctx.terminal is True


def test_invalid_transition_raises():
    ctx = _ctx("detected")
    with pytest.raises(InvalidTransitionError):
        apply_transition(ctx, "payment_succeeds")


def test_can_transition_helper():
    ctx = _ctx("diagnosed")
    assert can_transition(ctx, "retry_scheduled") is True
    assert can_transition(ctx, "payment_succeeds") is False
