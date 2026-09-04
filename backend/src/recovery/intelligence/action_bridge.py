"""Map LLM catalog action IDs to Phase 2 executable RecoveryAction objects."""

from __future__ import annotations

from recovery.intelligence.strategy import CAUSE_ACTIONS
from recovery.models.recovery_types import RecoveryAction

_RETRY_CATALOG = frozenset({"retry_payment", "wait_and_retry"})
_CONTACT_CATALOG = frozenset(
    {
        "send_email",
        "send_whatsapp",
        "send_sms",
        "voice_call",
        "request_payment_method_update",
    }
)


def runtime_pool_for_cause(likely_cause: str) -> list[RecoveryAction]:
    return list(CAUSE_ACTIONS.get(likely_cause, CAUSE_ACTIONS["unknown_failure"]))


def catalog_to_runtime(catalog_action_id: str, likely_cause: str) -> RecoveryAction | None:
    """Translate an actions.yaml catalog id into a simulator-ready RecoveryAction."""
    pool = runtime_pool_for_cause(likely_cause)

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
