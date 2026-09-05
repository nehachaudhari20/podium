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

    if event in {"payment_succeeds", "checkout_completed", "payment_received", "promise_kept"}:
        if event == "checkout_completed":
            trigger = "checkout_completed"
            ctx.amount_recovered = ctx.case.amount
        elif event == "promise_kept":
            trigger = "promise_kept"
            if ctx.amount_recovered <= 0:
                recovered = (
                    ctx.remaining_balance
                    if ctx.remaining_balance is not None and ctx.remaining_balance > 0
                    else ctx.case.amount
                )
                ctx.amount_recovered = recovered
            ctx.remaining_balance = 0.0
        elif event == "payment_received":
            trigger = "payment_succeeds"
            recovered = (
                ctx.remaining_balance
                if ctx.remaining_balance is not None
                else ctx.case.amount
            )
            ctx.amount_paid = round(ctx.amount_paid + recovered, 2)
            ctx.amount_recovered = round(ctx.amount_recovered + recovered, 2)
            ctx.remaining_balance = 0.0
        else:
            trigger = "payment_succeeds"
            ctx.amount_recovered = ctx.case.amount
        return OutcomeResult(
            trigger=trigger,
            recovered=True,
            amount_recovered=ctx.amount_recovered,
            summary=f"Recovered {ctx.case.currency} {ctx.amount_recovered:,.2f}",
        )

    if event == "partial_payment_received":
        return OutcomeResult(
            trigger="partial_payment",
            recovered=False,
            amount_recovered=ctx.amount_recovered,
            summary=execution.detail or "Partial payment received; remaining exposure continues.",
        )

    if event == "promise_created":
        return OutcomeResult(
            trigger="promise_made",
            recovered=False,
            amount_recovered=0.0,
            summary="Promise-to-pay created; awaiting promise date.",
        )

    if event == "promise_confirmed":
        return OutcomeResult(
            trigger=None,
            recovered=False,
            amount_recovered=0.0,
            summary="Promise-to-pay confirmed.",
        )

    if event == "promise_broken":
        return OutcomeResult(
            trigger="promise_broken",
            recovered=False,
            amount_recovered=0.0,
            summary="Promise-to-pay broken; re-planning recovery.",
        )

    if event == "promise_due_check":
        return OutcomeResult(
            trigger=None,
            recovered=False,
            amount_recovered=0.0,
            summary="Promise due check scheduled.",
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
            summary="Recovery stopped; no further intervention.",
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
        label = (
            "Receivable outreach ignored"
            if ctx.case.lane == "receivable"
            else "Checkout intervention ignored"
            if event == "customer_ignored"
            else "Payment retry failed"
        )
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
