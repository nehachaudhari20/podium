"""Checkout-abandonment strategy — Phase 4B.

Produces RecoveryAction candidates using the existing action abstraction.
Incentives are optional and context-gated — never the default path.
"""

from __future__ import annotations

from recovery.models.case import RecoveryCaseRuntime
from recovery.models.recovery_context import RecoveryContext
from recovery.models.recovery_types import DiagnosisResult, RecoveryAction

CHECKOUT_CAUSE_ACTIONS: dict[str, list[RecoveryAction]] = {
    "payment_friction": [
        RecoveryAction("payment_link", "Send payment completion link", "email", is_contact=True),
        RecoveryAction("checkout_assistance", "Offer checkout assistance", "email", is_contact=True),
        RecoveryAction("checkout_reminder", "Send checkout reminder", "email", is_contact=True),
    ],
    "distraction_or_delay": [
        RecoveryAction("checkout_reminder", "Send checkout reminder", "email", is_contact=True),
        RecoveryAction("payment_link", "Send payment completion link", "email", is_contact=True),
    ],
    "checkout_friction": [
        RecoveryAction("checkout_reminder", "Send checkout reminder", "email", is_contact=True),
        RecoveryAction("checkout_assistance", "Offer checkout assistance", "email", is_contact=True),
        RecoveryAction("payment_link", "Send payment completion link", "email", is_contact=True),
    ],
    "price_sensitivity": [
        RecoveryAction("checkout_reminder", "Send checkout reminder", "email", is_contact=True),
        RecoveryAction(
            "limited_incentive",
            "Offer limited checkout incentive",
            "system",
            is_contact=False,
        ),
        RecoveryAction("payment_link", "Send payment completion link", "email", is_contact=True),
    ],
    "low_intent": [
        RecoveryAction("checkout_reminder", "Send checkout reminder", "email", is_contact=True),
        RecoveryAction("stop_recovery", "Stop checkout recovery", "system", is_contact=False),
    ],
    "technical_friction": [
        RecoveryAction("checkout_assistance", "Offer checkout assistance", "email", is_contact=True),
        RecoveryAction("payment_link", "Send payment completion link", "email", is_contact=True),
        RecoveryAction("human_escalation", "Escalate to human agent", "human", is_contact=True),
    ],
    "unknown_abandonment": [
        RecoveryAction("checkout_reminder", "Send checkout reminder", "email", is_contact=True),
        RecoveryAction("payment_link", "Send payment completion link", "email", is_contact=True),
    ],
}


def generate_checkout_actions(
    case: RecoveryCaseRuntime,
    diagnosis: DiagnosisResult,
    context: RecoveryContext | None = None,
) -> list[RecoveryAction]:
    """Return ordered checkout recovery actions for a diagnosed case."""
    actions = list(
        CHECKOUT_CAUSE_ACTIONS.get(diagnosis.likely_cause, CHECKOUT_CAUSE_ACTIONS["unknown_abandonment"])
    )

    if context is None:
        return actions

    signals = context.derived_signals
    last_action = context.case.last_action

    # Never default to incentive for high-intent recent abandonments.
    if signals.high_intent and signals.recent_abandonment:
        actions = [a for a in actions if a.action_id != "limited_incentive"]

    # Low intent: keep reminder + stop only.
    if signals.high_intent is False and diagnosis.likely_cause == "low_intent":
        preferred = {"checkout_reminder", "stop_recovery"}
        actions = [a for a in actions if a.action_id in preferred] or actions

    # After a reminder with no completion, prefer a different next action.
    if last_action == "checkout_reminder":
        without_reminder = [a for a in actions if a.action_id != "checkout_reminder"]
        payment_first = [a for a in without_reminder if a.action_id == "payment_link"]
        rest = [a for a in without_reminder if a.action_id != "payment_link"]
        actions = payment_first + rest if payment_first else without_reminder or actions

    if last_action == "payment_link":
        without_link = [a for a in actions if a.action_id != "payment_link"]
        assist = [a for a in without_link if a.action_id == "checkout_assistance"]
        rest = [a for a in without_link if a.action_id != "checkout_assistance"]
        actions = assist + rest if assist else without_link or actions

    # Already attempted recovery and non-response → avoid repeating same contact blindly.
    if signals.customer_non_response and signals.recovery_attempted_before:
        if diagnosis.likely_cause == "low_intent":
            actions = [a for a in actions if a.action_id == "stop_recovery"] or [
                RecoveryAction("stop_recovery", "Stop checkout recovery", "system")
            ]
        else:
            # Prefer assistance / stop over another identical reminder.
            actions = [a for a in actions if a.action_id != last_action]

    if signals.customer_opt_out:
        actions = [a for a in actions if not a.is_contact]
        if not actions:
            actions = [RecoveryAction("stop_recovery", "Stop checkout recovery", "system")]

    # Incentive only when cause and signals justify it — and never as sole first action
    # for first-touch high-intent cases (already filtered above).
    if diagnosis.likely_cause != "price_sensitivity" and not (
        signals.high_value_cart and signals.early_stage_abandonment and signals.recovery_attempted_before
    ):
        actions = [a for a in actions if a.action_id != "limited_incentive"]

    return actions
