"""Rule-based recovery strategy — Phase 2 deterministic implementation.

Phase 3 will replace ``generate_actions`` with Gemini-backed candidate generation
using the same ``RecoveryAction`` interface.
"""

from __future__ import annotations

from recovery.models.case import RecoveryCaseRuntime
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
) -> list[RecoveryAction]:
    """Return ordered candidate recovery actions for a diagnosed case."""
    actions = CAUSE_ACTIONS.get(diagnosis.likely_cause, CAUSE_ACTIONS["unknown_failure"])
    return list(actions)
