"""Phase 2 — execution simulator unit tests."""

from __future__ import annotations

from datetime import datetime, timedelta

from podium.execution.simulator import simulate_execution
from podium.intelligence.diagnosis import diagnose
from podium.models.case import RecoveryCaseRuntime
from podium.models.enums import Lane
from podium.models.recovery_types import RecoveryAction
from podium.state.context import CaseRunContext


def _ctx(failure_reason: str) -> CaseRunContext:
    now = datetime(2026, 2, 1, 10, 0, 0)
    case = RecoveryCaseRuntime(
        case_id="case_sim_001",
        customer_id="cust_sim_001",
        lane=Lane.SUBSCRIPTION_PAYMENT.value,
        amount=2499.0,
        currency="INR",
        status="open",
        workflow_state="waiting",
        created_at=now,
        recovery_window_end=now + timedelta(days=14),
        source_ref_id="sub_sim_001",
        failure_reason=failure_reason,
        recoverability_hint="medium",
        days_overdue=None,
        attempt_count=0,
        estimated_recovery_prob=None,
    )
    return CaseRunContext(case=case)


RETRY = RecoveryAction("retry_24h", "Retry", "system", is_retry=True, retry_delay_hours=24)
CONTACT = RecoveryAction("payment_method_update", "Update", "email", is_contact=True)


def test_transient_failure_succeeds_on_retry():
    ctx = _ctx("network_timeout")
    diagnosis = diagnose(ctx.sync_case_view())
    result = simulate_execution(ctx, RETRY, diagnosis)
    assert result.event == "payment_succeeds"


def test_expired_card_fails_without_method_update():
    ctx = _ctx("expired_card")
    diagnosis = diagnose(ctx.sync_case_view())
    result = simulate_execution(ctx, RETRY, diagnosis)
    assert result.event == "payment_failed"


def test_expired_card_succeeds_after_method_update():
    ctx = _ctx("expired_card")
    diagnosis = diagnose(ctx.sync_case_view())
    simulate_execution(ctx, CONTACT, diagnosis)
    result = simulate_execution(ctx, RETRY, diagnosis)
    assert result.event == "payment_succeeds"


def test_repeated_failure_always_fails_retry():
    ctx = _ctx("repeated_failure")
    diagnosis = diagnose(ctx.sync_case_view())
    result = simulate_execution(ctx, RETRY, diagnosis)
    assert result.event == "payment_failed"
