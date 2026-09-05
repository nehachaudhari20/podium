"""Receivable-lane strategy — Phase 7."""

from __future__ import annotations

from recovery.models.case import RecoveryCaseRuntime
from recovery.models.recovery_context import RecoveryContext
from recovery.models.recovery_types import DiagnosisResult, RecoveryAction

RECEIVABLE_CAUSE_ACTIONS: dict[str, list[RecoveryAction]] = {
    "customer_oversight": [
        RecoveryAction("invoice_reminder", "Send invoice reminder", "email", is_contact=True),
        RecoveryAction("payment_link", "Send payment link", "email", is_contact=True),
        RecoveryAction(
            "promise_to_pay_request",
            "Request promise-to-pay",
            "email",
            is_contact=True,
        ),
    ],
    "payment_processing_delay": [
        RecoveryAction("payment_link", "Send payment link", "email", is_contact=True),
        RecoveryAction("invoice_reminder", "Send invoice reminder", "email", is_contact=True),
        RecoveryAction(
            "promise_to_pay_request",
            "Request promise-to-pay",
            "email",
            is_contact=True,
        ),
    ],
    "temporary_cash_constraint": [
        RecoveryAction(
            "promise_to_pay_request",
            "Request promise-to-pay",
            "email",
            is_contact=True,
        ),
        RecoveryAction("payment_link", "Send payment link", "email", is_contact=True),
        RecoveryAction("invoice_reminder", "Send invoice reminder", "email", is_contact=True),
        RecoveryAction("human_escalation", "Human follow-up", "human", is_contact=True),
    ],
    "approval_delay": [
        RecoveryAction("invoice_reminder", "Send invoice reminder", "email", is_contact=True),
        RecoveryAction(
            "promise_to_pay_request",
            "Request promise-to-pay",
            "email",
            is_contact=True,
        ),
        RecoveryAction("human_escalation", "Human follow-up", "human", is_contact=True),
    ],
    "invoice_dispute": [
        RecoveryAction("human_escalation", "Human follow-up", "human", is_contact=True),
        RecoveryAction("stop_recovery", "Stop recovery", "system"),
    ],
    "low_responsiveness": [
        RecoveryAction("payment_link", "Send payment link", "email", is_contact=True),
        RecoveryAction("human_escalation", "Human follow-up", "human", is_contact=True),
        RecoveryAction(
            "escalate_collections",
            "Escalate to collections",
            "human",
            is_contact=True,
        ),
    ],
    "high_value_account": [
        RecoveryAction(
            "promise_to_pay_request",
            "Request promise-to-pay",
            "email",
            is_contact=True,
        ),
        RecoveryAction("human_escalation", "Human follow-up", "human", is_contact=True),
        RecoveryAction("payment_link", "Send payment link", "email", is_contact=True),
    ],
    "unknown_receivable_risk": [
        RecoveryAction("invoice_reminder", "Send invoice reminder", "email", is_contact=True),
        RecoveryAction("payment_link", "Send payment link", "email", is_contact=True),
        RecoveryAction(
            "promise_to_pay_request",
            "Request promise-to-pay",
            "email",
            is_contact=True,
        ),
    ],
}


def generate_receivable_actions(
    case: RecoveryCaseRuntime,
    diagnosis: DiagnosisResult,
    context: RecoveryContext | None = None,
) -> list[RecoveryAction]:
    actions = list(
        RECEIVABLE_CAUSE_ACTIONS.get(
            diagnosis.likely_cause, RECEIVABLE_CAUSE_ACTIONS["unknown_receivable_risk"]
        )
    )
    if context is None:
        return actions

    signals = context.derived_signals
    last = context.case.last_action
    days = case.days_overdue or 0

    if signals.active_promise:
        # While a promise is active, avoid stacking outreach.
        return [
            RecoveryAction(
                "track_promise_to_pay",
                "Track active promise-to-pay",
                "system",
            )
        ]

    if signals.customer_opt_out:
        actions = [a for a in actions if not a.is_contact]
        if not actions:
            actions = [RecoveryAction("stop_recovery", "Stop recovery", "system")]

    # Prefer low-friction first for mild overdue.
    if days <= 10 and diagnosis.likely_cause in {"customer_oversight", "payment_processing_delay"}:
        preferred = {"invoice_reminder", "payment_link", "promise_to_pay_request"}
        actions = [a for a in actions if a.action_id in preferred] or actions

    # After reminder, diversify.
    if last == "invoice_reminder":
        without = [a for a in actions if a.action_id != "invoice_reminder"]
        actions = without or actions
    if last == "payment_link":
        without = [a for a in actions if a.action_id != "payment_link"]
        ptp = [a for a in without if a.action_id == "promise_to_pay_request"]
        rest = [a for a in without if a.action_id != "promise_to_pay_request"]
        actions = ptp + rest if ptp else without or actions

    # Broken promise → prefer stronger follow-up.
    if signals.promise_broken_before:
        strong = [a for a in actions if a.action_id in {"human_escalation", "escalate_collections", "payment_link"}]
        actions = strong or actions

    # Avoid defaulting to human escalation on first touch for mild cases.
    if case.attempt_count == 0 and days < 30:
        non_human = [a for a in actions if a.action_id not in {"human_escalation", "escalate_collections"}]
        if non_human:
            actions = non_human

    return actions
