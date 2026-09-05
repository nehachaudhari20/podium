"""Rule-based recovery strategy — subscription, checkout, receivable."""

from __future__ import annotations

from recovery.intelligence.checkout_strategy import CHECKOUT_CAUSE_ACTIONS, generate_checkout_actions
from recovery.intelligence.receivable_strategy import (
    RECEIVABLE_CAUSE_ACTIONS,
    generate_receivable_actions,
)
from recovery.models.case import RecoveryCaseRuntime
from recovery.models.enums import Lane
from recovery.models.recovery_context import RecoveryContext
from recovery.models.recovery_types import DiagnosisResult, RecoveryAction

CAUSE_ACTIONS: dict[str, list[RecoveryAction]] = {
    "insufficient_funds": [
        RecoveryAction("retry_24h", "Retry in 24 hours", "system", is_retry=True, retry_delay_hours=24),
        RecoveryAction("retry_72h", "Retry in 72 hours", "system", is_retry=True, retry_delay_hours=72),
        RecoveryAction(
            "payment_method_update",
            "Request payment method update",
            "email",
            is_contact=True,
        ),
    ],
    "expired_payment_method": [
        RecoveryAction(
            "payment_method_update",
            "Request payment method update",
            "email",
            is_contact=True,
        ),
        RecoveryAction(
            "retry_after_update",
            "Retry after payment method update",
            "system",
            is_retry=True,
            retry_delay_hours=1,
        ),
    ],
    "transient_failure": [
        RecoveryAction("retry_6h", "Retry in 6 hours", "system", is_retry=True, retry_delay_hours=6),
        RecoveryAction("retry_24h", "Retry in 24 hours", "system", is_retry=True, retry_delay_hours=24),
    ],
    "bank_decline": [
        RecoveryAction(
            "payment_method_update",
            "Request payment method update",
            "email",
            is_contact=True,
        ),
        RecoveryAction("retry_72h", "Retry in 72 hours", "system", is_retry=True, retry_delay_hours=72),
    ],
    "mandate_failure": [
        RecoveryAction(
            "payment_method_update",
            "Request payment method update",
            "email",
            is_contact=True,
        ),
        RecoveryAction("retry_24h", "Retry in 24 hours", "system", is_retry=True, retry_delay_hours=24),
    ],
    "repeated_failure": [
        RecoveryAction("retry_72h", "Retry in 72 hours", "system", is_retry=True, retry_delay_hours=72),
        RecoveryAction(
            "payment_method_update",
            "Request payment method update",
            "email",
            is_contact=True,
        ),
        RecoveryAction("human_escalation", "Escalate to human agent", "human", is_contact=True),
    ],
    "unknown_failure": [
        RecoveryAction("retry_24h", "Retry in 24 hours", "system", is_retry=True, retry_delay_hours=24),
        RecoveryAction(
            "payment_method_update",
            "Request payment method update",
            "email",
            is_contact=True,
        ),
    ],
}


def generate_actions(
    case: RecoveryCaseRuntime,
    diagnosis: DiagnosisResult,
    context: RecoveryContext | None = None,
) -> list[RecoveryAction]:
    """Return ordered candidate recovery actions for a diagnosed case."""
    if case.lane == Lane.CHECKOUT_ABANDONMENT.value:
        return generate_checkout_actions(case, diagnosis, context)
    if case.lane == Lane.RECEIVABLE.value:
        return generate_receivable_actions(case, diagnosis, context)

    actions = CAUSE_ACTIONS.get(diagnosis.likely_cause, CAUSE_ACTIONS["unknown_failure"])
    return list(actions)


def runtime_pool_for_cause(likely_cause: str, *, lane: str | None = None) -> list[RecoveryAction]:
    """Union lookup for action bridging across lanes."""
    if lane == Lane.RECEIVABLE.value or likely_cause in RECEIVABLE_CAUSE_ACTIONS:
        return list(
            RECEIVABLE_CAUSE_ACTIONS.get(
                likely_cause, RECEIVABLE_CAUSE_ACTIONS["unknown_receivable_risk"]
            )
        )
    if lane == Lane.CHECKOUT_ABANDONMENT.value or likely_cause in CHECKOUT_CAUSE_ACTIONS:
        return list(
            CHECKOUT_CAUSE_ACTIONS.get(likely_cause, CHECKOUT_CAUSE_ACTIONS["unknown_abandonment"])
        )
    return list(CAUSE_ACTIONS.get(likely_cause, CAUSE_ACTIONS["unknown_failure"]))
