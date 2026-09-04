"""Adapters between RecoveryContext and Phase 2 runtime models."""

from __future__ import annotations

from datetime import datetime

from podium.models.case import RecoveryCaseRuntime
from podium.models.recovery_context import CaseFacts, RecoveryContext


def case_facts_to_runtime(facts: CaseFacts) -> RecoveryCaseRuntime:
    """Convert context case facts to RecoveryCaseRuntime for Phase 2 modules."""
    created = datetime.fromisoformat(facts.created_at)
    window_end = datetime.fromisoformat(facts.recovery_window_end)
    return RecoveryCaseRuntime(
        case_id=facts.case_id,
        customer_id=facts.customer_id,
        lane=facts.lane,
        amount=facts.amount,
        currency=facts.currency,
        status=facts.status,
        workflow_state=facts.workflow_state,
        created_at=created,
        recovery_window_end=window_end,
        source_ref_id=facts.source_ref_id,
        failure_reason=facts.failure_reason,
        recoverability_hint=facts.recoverability_hint,
        days_overdue=facts.days_overdue,
        attempt_count=facts.attempt_count,
        estimated_recovery_prob=None,
        is_hero=facts.is_hero,
    )


def context_key_factors(context: RecoveryContext) -> tuple[str, ...]:
    """Collect active derived signal names for reasoning output."""
    signals = context.derived_signals
    factors: list[str] = []
    mapping = {
        "first_failure": signals.first_failure,
        "repeated_failure": signals.repeated_failure,
        "prior_successful_payment": signals.prior_successful_payment,
        "retry_exhaustion_risk": signals.retry_exhaustion_risk,
        "recent_contact": signals.recent_contact,
        "customer_non_response": signals.customer_non_response,
        "customer_opt_out": signals.customer_opt_out,
        "near_recovery_window_end": signals.near_recovery_window_end,
        "transient_failure": signals.transient_failure,
        "expired_payment_method": signals.expired_payment_method,
    }
    for name, active in mapping.items():
        if active:
            factors.append(name)
    return tuple(factors)
