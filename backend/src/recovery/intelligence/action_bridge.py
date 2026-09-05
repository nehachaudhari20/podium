"""Map LLM catalog action IDs to executable RecoveryAction objects."""

from __future__ import annotations

from recovery.intelligence.checkout_strategy import CHECKOUT_CAUSE_ACTIONS
from recovery.intelligence.receivable_strategy import RECEIVABLE_CAUSE_ACTIONS
from recovery.intelligence.strategy import CAUSE_ACTIONS, runtime_pool_for_cause
from recovery.models.recovery_types import RecoveryAction

_RETRY_CATALOG = frozenset({"retry_payment", "wait_and_retry"})
_CONTACT_CATALOG = frozenset(
    {
        "send_email",
        "send_whatsapp",
        "send_sms",
        "voice_call",
        "request_payment_method_update",
        "checkout_reminder",
        "payment_link",
        "checkout_assistance",
        "invoice_reminder",
        "promise_to_pay_request",
        "statement_resend",
        "payment_assistance",
    }
)
_CHECKOUT_DIRECT = frozenset(
    {
        "checkout_reminder",
        "payment_link",
        "checkout_assistance",
        "limited_incentive",
        "stop_recovery",
        "human_escalation",
        "offer_discount",
    }
)
_RECEIVABLE_DIRECT = frozenset(
    {
        "invoice_reminder",
        "payment_link",
        "statement_resend",
        "payment_assistance",
        "promise_to_pay_request",
        "promise_confirmation",
        "track_promise_to_pay",
        "human_escalation",
        "escalate_collections",
        "stop_recovery",
    }
)


def catalog_to_runtime(catalog_action_id: str, likely_cause: str) -> RecoveryAction | None:
    """Translate an actions.yaml catalog id into a simulator-ready RecoveryAction."""
    if catalog_action_id in _RECEIVABLE_DIRECT or likely_cause in RECEIVABLE_CAUSE_ACTIONS:
        pool = runtime_pool_for_cause(likely_cause, lane="receivable")
        for action in pool:
            if action.action_id == catalog_action_id:
                return action
        receivable_defs = {
            "invoice_reminder": RecoveryAction(
                "invoice_reminder", "Send invoice reminder", "email", is_contact=True
            ),
            "payment_link": RecoveryAction(
                "payment_link", "Send payment link", "email", is_contact=True
            ),
            "promise_to_pay_request": RecoveryAction(
                "promise_to_pay_request", "Request promise-to-pay", "email", is_contact=True
            ),
            "track_promise_to_pay": RecoveryAction(
                "track_promise_to_pay", "Track active promise-to-pay", "system"
            ),
            "human_escalation": RecoveryAction(
                "human_escalation", "Human follow-up", "human", is_contact=True
            ),
            "escalate_collections": RecoveryAction(
                "escalate_collections", "Escalate to collections", "human", is_contact=True
            ),
            "stop_recovery": RecoveryAction("stop_recovery", "Stop recovery", "system"),
        }
        if catalog_action_id in receivable_defs and likely_cause in RECEIVABLE_CAUSE_ACTIONS:
            return receivable_defs[catalog_action_id]

    # Direct checkout catalog ids map 1:1 when present in checkout pools.
    if catalog_action_id in _CHECKOUT_DIRECT or likely_cause in CHECKOUT_CAUSE_ACTIONS:
        pool = runtime_pool_for_cause(likely_cause)
        if catalog_action_id == "offer_discount":
            catalog_action_id = "limited_incentive"
        for action in pool:
            if action.action_id == catalog_action_id:
                return action
        # Fallback: construct from known checkout action definitions.
        checkout_defs = {
            "checkout_reminder": RecoveryAction(
                "checkout_reminder", "Send checkout reminder", "email", is_contact=True
            ),
            "payment_link": RecoveryAction(
                "payment_link", "Send payment completion link", "email", is_contact=True
            ),
            "checkout_assistance": RecoveryAction(
                "checkout_assistance", "Offer checkout assistance", "email", is_contact=True
            ),
            "limited_incentive": RecoveryAction(
                "limited_incentive", "Offer limited checkout incentive", "system"
            ),
            "stop_recovery": RecoveryAction("stop_recovery", "Stop checkout recovery", "system"),
            "human_escalation": RecoveryAction(
                "human_escalation", "Escalate to human agent", "human", is_contact=True
            ),
        }
        if catalog_action_id in checkout_defs and likely_cause in CHECKOUT_CAUSE_ACTIONS:
            return checkout_defs[catalog_action_id]

    pool = list(CAUSE_ACTIONS.get(likely_cause, CAUSE_ACTIONS["unknown_failure"]))

    if catalog_action_id in _RETRY_CATALOG:
        retries = [action for action in pool if action.is_retry]
        if not retries:
            return None
        index = 0 if catalog_action_id == "retry_payment" else min(1, len(retries) - 1)
        return retries[index]

    if catalog_action_id in _CONTACT_CATALOG:
        for action in pool:
            if action.action_id == "payment_method_update":
                return action
        contacts = [action for action in pool if action.is_contact]
        return contacts[0] if contacts else None

    if catalog_action_id == "human_escalation":
        for action in pool:
            if action.action_id == "human_escalation":
                return action
        return None

    return None


def map_strategy_proposals_to_runtime(
    catalog_action_ids: list[str],
    likely_cause: str,
) -> list[RecoveryAction]:
    """Map catalog ids to runtime actions, preserving order and skipping unknowns."""
    mapped: list[RecoveryAction] = []
    seen: set[str] = set()
    for catalog_id in catalog_action_ids:
        runtime = catalog_to_runtime(catalog_id, likely_cause)
        if runtime is None or runtime.action_id in seen:
            continue
        seen.add(runtime.action_id)
        mapped.append(runtime)
    return mapped
