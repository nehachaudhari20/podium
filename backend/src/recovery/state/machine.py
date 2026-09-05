"""Explicit recovery state machine (subscription / checkout / receivable)."""

from __future__ import annotations

from recovery.models.enums import WorkflowState
from recovery.models.recovery_types import RecoveryAction
from recovery.state.context import CaseRunContext

# trigger -> (from_states, to_state)
SUBSCRIPTION_TRANSITIONS: dict[str, tuple[frozenset[str], str]] = {
    "case_diagnosed": (frozenset({WorkflowState.DETECTED.value}), WorkflowState.DIAGNOSED.value),
    "retry_scheduled": (
        frozenset({WorkflowState.DIAGNOSED.value, WorkflowState.WAITING.value}),
        WorkflowState.RETRY_SCHEDULED.value,
    ),
    "waiting_for_retry": (
        frozenset({WorkflowState.RETRY_SCHEDULED.value}),
        WorkflowState.WAITING.value,
    ),
    "contact_sent": (
        frozenset(
            {
                WorkflowState.DIAGNOSED.value,
                WorkflowState.WAITING.value,
                WorkflowState.PROMISED.value,
            }
        ),
        WorkflowState.CONTACTED.value,
    ),
    "payment_method_updated": (
        frozenset({WorkflowState.CONTACTED.value, WorkflowState.WAITING.value}),
        WorkflowState.WAITING.value,
    ),
    "promise_made": (
        frozenset(
            {
                WorkflowState.CONTACTED.value,
                WorkflowState.WAITING.value,
                WorkflowState.DIAGNOSED.value,
            }
        ),
        WorkflowState.PROMISED.value,
    ),
    "promise_kept": (
        frozenset({WorkflowState.PROMISED.value}),
        WorkflowState.RECOVERED.value,
    ),
    "promise_broken": (
        frozenset({WorkflowState.PROMISED.value}),
        WorkflowState.WAITING.value,
    ),
    "partial_payment": (
        frozenset({WorkflowState.PROMISED.value, WorkflowState.CONTACTED.value}),
        WorkflowState.WAITING.value,
    ),
    "payment_succeeds": (
        frozenset(
            {
                WorkflowState.WAITING.value,
                WorkflowState.RETRY_SCHEDULED.value,
                WorkflowState.CONTACTED.value,
                WorkflowState.PROMISED.value,
            }
        ),
        WorkflowState.RECOVERED.value,
    ),
    "checkout_completed": (
        frozenset(
            {
                WorkflowState.DIAGNOSED.value,
                WorkflowState.WAITING.value,
                WorkflowState.CONTACTED.value,
            }
        ),
        WorkflowState.RECOVERED.value,
    ),
    "max_retries_exceeded": (
        frozenset(
            {
                WorkflowState.WAITING.value,
                WorkflowState.RETRY_SCHEDULED.value,
                WorkflowState.CONTACTED.value,
                WorkflowState.DIAGNOSED.value,
                WorkflowState.PROMISED.value,
            }
        ),
        WorkflowState.EXHAUSTED.value,
    ),
    "escalated": (
        frozenset(
            {
                WorkflowState.WAITING.value,
                WorkflowState.CONTACTED.value,
                WorkflowState.DIAGNOSED.value,
                WorkflowState.PROMISED.value,
            }
        ),
        WorkflowState.ESCALATED.value,
    ),
    "recovery_stopped": (
        frozenset(
            {
                WorkflowState.DETECTED.value,
                WorkflowState.DIAGNOSED.value,
                WorkflowState.WAITING.value,
                WorkflowState.CONTACTED.value,
                WorkflowState.PROMISED.value,
            }
        ),
        WorkflowState.EXHAUSTED.value,
    ),
    "deferred": (
        frozenset(
            {
                WorkflowState.DIAGNOSED.value,
                WorkflowState.WAITING.value,
                WorkflowState.CONTACTED.value,
                WorkflowState.PROMISED.value,
            }
        ),
        WorkflowState.DEFERRED.value,
    ),
    "customer_opts_out": (
        frozenset(
            {
                WorkflowState.DETECTED.value,
                WorkflowState.DIAGNOSED.value,
                WorkflowState.WAITING.value,
                WorkflowState.CONTACTED.value,
                WorkflowState.PROMISED.value,
            }
        ),
        WorkflowState.EXHAUSTED.value,
    ),
}


class InvalidTransitionError(ValueError):
    pass


def can_transition(ctx: CaseRunContext, trigger: str) -> bool:
    if trigger not in SUBSCRIPTION_TRANSITIONS:
        return False
    allowed_from, _ = SUBSCRIPTION_TRANSITIONS[trigger]
    return ctx.workflow_state in allowed_from


def apply_transition(ctx: CaseRunContext, trigger: str) -> str:
    if trigger not in SUBSCRIPTION_TRANSITIONS:
        raise InvalidTransitionError(f"Unknown trigger: {trigger}")
    allowed_from, to_state = SUBSCRIPTION_TRANSITIONS[trigger]
    if ctx.workflow_state not in allowed_from:
        raise InvalidTransitionError(
            f"Cannot apply '{trigger}' from state '{ctx.workflow_state}'"
        )
    ctx.record_state(to_state)
    if to_state in (
        WorkflowState.RECOVERED.value,
        WorkflowState.EXHAUSTED.value,
        WorkflowState.ESCALATED.value,
        WorkflowState.DEFERRED.value,
    ):
        ctx.terminal = True
    return to_state


def action_to_initial_trigger(action: RecoveryAction) -> str:
    if action.is_retry:
        return "retry_scheduled"
    if action.action_id == "track_promise_to_pay":
        return "promise_made"
    if action.is_contact or action.action_id in {"limited_incentive", "offer_discount"}:
        return "contact_sent"
    if action.action_id == "stop_recovery":
        return "recovery_stopped"
    return "retry_scheduled"
