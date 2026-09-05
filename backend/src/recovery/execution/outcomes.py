"""Translate execution events into recovery outcomes and state triggers."""

from __future__ import annotations

from dataclasses import dataclass

from recovery.models.enums import WorkflowState
from recovery.models.recovery_types import ExecutionResult
from recovery.state.context import CaseRunContext


@dataclass(frozen=True, slots=True)
class OutcomeResult:
    trigger: str | None
    recovered: bool
    amount_recovered: float
    summary: str


def process_outcome(ctx: CaseRunContext, execution: ExecutionResult) -> OutcomeResult:
    event = execution.event

    if event in {"payment_succeeds", "checkout_completed"}:
        ctx.amount_recovered = ctx.case.amount
        trigger = "checkout_completed" if event == "checkout_completed" else "payment_succeeds"
        return OutcomeResult(
            trigger=trigger,
            recovered=True,
            amount_recovered=ctx.case.amount,
            summary=f"Recovered {ctx.case.currency} {ctx.case.amount:,.2f}",
        )

    if event == "payment_method_updated":
        return OutcomeResult(
            trigger="payment_method_updated",
            recovered=False,
            amount_recovered=0.0,
            summary="Payment method update requested; awaiting customer action.",
        )

    if event == "escalated":
        return OutcomeResult(
            trigger="escalated",
            recovered=False,
            amount_recovered=0.0,
            summary="Case escalated for human follow-up.",
        )

    if event == "recovery_stopped":
        return OutcomeResult(
            trigger="recovery_stopped",
            recovered=False,
            amount_recovered=0.0,
            summary="Recovery stopped; no further checkout intervention.",
        )

    if event == "deferred":
        return OutcomeResult(
            trigger="deferred",
            recovered=False,
            amount_recovered=0.0,
            summary="Recovery deferred.",
        )

    if event in {"payment_failed", "customer_ignored"}:
        if ctx.attempt_count >= 3:
            return OutcomeResult(
                trigger="max_retries_exceeded",
                recovered=False,
                amount_recovered=0.0,
                summary="Maximum recovery attempts reached without recovery.",
            )
        label = "Checkout intervention ignored" if event == "customer_ignored" else "Payment retry failed"
        return OutcomeResult(
            trigger=None,
            recovered=False,
            amount_recovered=0.0,
            summary=f"{label}; workflow continues.",
        )

    return OutcomeResult(
        trigger=None,
        recovered=False,
        amount_recovered=0.0,
        summary=execution.detail or "No outcome change.",
    )


def is_terminal_state(state: str) -> bool:
    return state in {
        WorkflowState.RECOVERED.value,
        WorkflowState.EXHAUSTED.value,
        WorkflowState.ESCALATED.value,
        WorkflowState.DEFERRED.value,
    }
