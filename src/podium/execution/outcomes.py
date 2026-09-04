"""Translate execution events into recovery outcomes and state triggers."""

from __future__ import annotations

from dataclasses import dataclass

from podium.models.enums import WorkflowState
from podium.models.recovery_types import ExecutionResult
from podium.state.context import CaseRunContext


@dataclass(frozen=True, slots=True)
class OutcomeResult:
    trigger: str | None
    recovered: bool
    amount_recovered: float
    summary: str


def process_outcome(ctx: CaseRunContext, execution: ExecutionResult) -> OutcomeResult:
    event = execution.event

    if event == "payment_succeeds":
        ctx.amount_recovered = ctx.case.amount
        return OutcomeResult(
            trigger="payment_succeeds",
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

    if event == "payment_failed":
        if ctx.attempt_count >= 3:
            return OutcomeResult(
                trigger="max_retries_exceeded",
                recovered=False,
                amount_recovered=0.0,
                summary="Maximum retries reached without recovery.",
            )
        return OutcomeResult(
            trigger=None,
            recovered=False,
            amount_recovered=0.0,
            summary="Payment retry failed; workflow continues.",
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
    }
