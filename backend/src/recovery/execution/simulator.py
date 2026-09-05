"""Simulated execution boundary — no access to evaluator ground truth."""

from __future__ import annotations

from recovery.models.enums import Lane
from recovery.models.recovery_types import DiagnosisResult, ExecutionResult, RecoveryAction
from recovery.state.context import CaseRunContext

RETRY_ACTIONS = frozenset(
    {"retry_6h", "retry_24h", "retry_72h", "retry_after_update", "retry_payment"}
)
CHECKOUT_ACTIONS = frozenset(
    {
        "checkout_reminder",
        "payment_link",
        "checkout_assistance",
        "limited_incentive",
        "stop_recovery",
    }
)
RECEIVABLE_ACTIONS = frozenset(
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


def simulate_execution(
    ctx: CaseRunContext,
    action: RecoveryAction,
    diagnosis: DiagnosisResult,
) -> ExecutionResult:
    """Simulate a recovery action using observable case context only."""
    if action.action_id == "payment_method_update":
        ctx.payment_method_updated = True
        return ExecutionResult(
            action=action.action_id,
            success=True,
            event="payment_method_updated",
            detail="Customer notified to update payment method.",
        )

    if action.action_id in {"human_escalation", "escalate_collections"}:
        return ExecutionResult(
            action=action.action_id,
            success=True,
            event="escalated",
            detail="Case escalated to human recovery / collections.",
        )

    if action.action_id in RETRY_ACTIONS:
        return _simulate_retry(ctx, action, diagnosis)

    if ctx.case.lane == Lane.RECEIVABLE.value or action.action_id in RECEIVABLE_ACTIONS:
        return _simulate_receivable(ctx, action, diagnosis)

    if action.action_id in CHECKOUT_ACTIONS or ctx.case.lane == Lane.CHECKOUT_ABANDONMENT.value:
        return _simulate_checkout(ctx, action, diagnosis)

    return ExecutionResult(
        action=action.action_id,
        success=False,
        event="unsupported_action",
        detail=f"No simulator handler for action '{action.action_id}'.",
    )


def _simulate_receivable(
    ctx: CaseRunContext,
    action: RecoveryAction,
    diagnosis: DiagnosisResult,
) -> ExecutionResult:
    """Deterministic receivable intervention outcomes."""
    cause = diagnosis.likely_cause

    if action.action_id == "stop_recovery":
        return ExecutionResult(
            action=action.action_id,
            success=True,
            event="recovery_stopped",
            detail="Receivable recovery stopped.",
        )

    if action.action_id == "track_promise_to_pay":
        return ExecutionResult(
            action=action.action_id,
            success=True,
            event="promise_due_check",
            detail="Tracking active promise-to-pay until due date.",
        )

    ctx.attempt_count += 1

    if action.action_id == "promise_to_pay_request":
        return ExecutionResult(
            action=action.action_id,
            success=True,
            event="promise_created",
            detail="Customer agreed to a promise-to-pay.",
        )

    if action.action_id == "promise_confirmation":
        return ExecutionResult(
            action=action.action_id,
            success=True,
            event="promise_confirmed",
            detail="Promise-to-pay confirmed with customer.",
        )

    if action.action_id in {"invoice_reminder", "statement_resend"}:
        # Low-friction outreach alone rarely clears aged receivables immediately.
        if cause == "customer_oversight" and (ctx.case.days_overdue or 0) <= 7 and ctx.attempt_count >= 2:
            return ExecutionResult(
                action=action.action_id,
                success=True,
                event="payment_received",
                detail="Customer paid after invoice reminder.",
            )
        return ExecutionResult(
            action=action.action_id,
            success=False,
            event="customer_ignored",
            detail="Invoice reminder delivered; no payment yet.",
        )

    if action.action_id == "payment_link":
        if cause in {"customer_oversight", "payment_processing_delay"} and ctx.attempt_count >= 2:
            return ExecutionResult(
                action=action.action_id,
                success=True,
                event="payment_received",
                detail="Customer paid via payment link.",
            )
        if cause == "low_responsiveness":
            return ExecutionResult(
                action=action.action_id,
                success=False,
                event="customer_ignored",
                detail="Payment link sent; customer did not respond.",
            )
        return ExecutionResult(
            action=action.action_id,
            success=False,
            event="customer_ignored",
            detail="Payment link sent; awaiting payment.",
        )

    if action.action_id == "payment_assistance":
        if cause in {"approval_delay", "temporary_cash_constraint"} or ctx.attempt_count >= 2:
            return ExecutionResult(
                action=action.action_id,
                success=True,
                event="promise_created",
                detail="Assistance led to a payment promise.",
            )
        return ExecutionResult(
            action=action.action_id,
            success=False,
            event="customer_ignored",
            detail="Payment assistance offered; no commitment yet.",
        )

    return ExecutionResult(
        action=action.action_id,
        success=False,
        event="customer_ignored",
        detail=f"Receivable action '{action.action_id}' did not clear exposure.",
    )


def _simulate_checkout(
    ctx: CaseRunContext,
    action: RecoveryAction,
    diagnosis: DiagnosisResult,
) -> ExecutionResult:
    """Deterministic checkout intervention outcomes."""
    cause = diagnosis.likely_cause

    if action.action_id == "stop_recovery":
        return ExecutionResult(
            action=action.action_id,
            success=True,
            event="recovery_stopped",
            detail="Checkout recovery stopped under bounded intervention policy.",
        )

    ctx.attempt_count += 1

    if action.action_id == "checkout_reminder":
        # Reminder alone does not complete checkout — enables observe → re-plan.
        return ExecutionResult(
            action=action.action_id,
            success=False,
            event="customer_ignored",
            detail="Checkout reminder delivered; customer did not complete checkout.",
        )

    if action.action_id == "payment_link":
        # Price-sensitive abandonments need more than a bare payment link.
        if cause == "price_sensitivity":
            return ExecutionResult(
                action=action.action_id,
                success=False,
                event="customer_ignored",
                detail="Payment link sent; price-sensitive customer did not complete.",
            )
        if cause in {"payment_friction", "distraction_or_delay"} or ctx.attempt_count >= 2:
            return ExecutionResult(
                action=action.action_id,
                success=True,
                event="checkout_completed",
                detail="Customer completed checkout via payment link.",
            )
        return ExecutionResult(
            action=action.action_id,
            success=False,
            event="customer_ignored",
            detail="Payment link sent; customer did not complete checkout.",
        )

    if action.action_id == "checkout_assistance":
        if cause in {"checkout_friction", "technical_friction", "payment_friction"} or ctx.attempt_count >= 2:
            return ExecutionResult(
                action=action.action_id,
                success=True,
                event="checkout_completed",
                detail="Customer completed checkout after assistance.",
            )
        return ExecutionResult(
            action=action.action_id,
            success=False,
            event="customer_ignored",
            detail="Assistance offered; customer did not complete checkout.",
        )

    if action.action_id == "limited_incentive":
        if cause == "price_sensitivity" or (
            cause in {"checkout_friction", "unknown_abandonment"} and ctx.attempt_count >= 2
        ):
            return ExecutionResult(
                action=action.action_id,
                success=True,
                event="checkout_completed",
                detail="Customer completed checkout after limited incentive.",
            )
        return ExecutionResult(
            action=action.action_id,
            success=False,
            event="customer_ignored",
            detail="Incentive offered; customer did not complete checkout.",
        )

    return ExecutionResult(
        action=action.action_id,
        success=False,
        event="customer_ignored",
        detail=f"Checkout action '{action.action_id}' did not convert.",
    )


def _simulate_retry(
    ctx: CaseRunContext,
    action: RecoveryAction,
    diagnosis: DiagnosisResult,
) -> ExecutionResult:
    """Deterministic retry outcome from diagnosis and attempt context."""
    ctx.attempt_count += 1
    cause = diagnosis.likely_cause

    if cause == "transient_failure" and ctx.attempt_count >= 1:
        return ExecutionResult(
            action=action.action_id,
            success=True,
            event="payment_succeeds",
            detail="Transient failure cleared on retry.",
        )

    if cause == "expired_payment_method":
        if ctx.payment_method_updated:
            return ExecutionResult(
                action=action.action_id,
                success=True,
                event="payment_succeeds",
                detail="Payment succeeded after method update.",
            )
        return ExecutionResult(
            action=action.action_id,
            success=False,
            event="payment_failed",
            detail="Retry failed; payment method still invalid.",
        )

    if cause == "insufficient_funds" and ctx.attempt_count >= 2:
        return ExecutionResult(
            action=action.action_id,
            success=True,
            event="payment_succeeds",
            detail="Funds available on subsequent retry.",
        )

    if cause == "bank_decline" and ctx.payment_method_updated and ctx.attempt_count >= 2:
        return ExecutionResult(
            action=action.action_id,
            success=True,
            event="payment_succeeds",
            detail="Payment accepted after method update and retry.",
        )

    if cause == "mandate_failure" and ctx.payment_method_updated:
        return ExecutionResult(
            action=action.action_id,
            success=True,
            event="payment_succeeds",
            detail="New mandate established; payment succeeded.",
        )

    if cause == "repeated_failure":
        return ExecutionResult(
            action=action.action_id,
            success=False,
            event="payment_failed",
            detail="Repeated failure pattern; retry unsuccessful.",
        )

    return ExecutionResult(
        action=action.action_id,
        success=False,
        event="payment_failed",
        detail="Payment retry failed.",
    )
