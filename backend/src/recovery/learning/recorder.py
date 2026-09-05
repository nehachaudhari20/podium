"""Record decision outcomes from runtime execution (Phase 8)."""

from __future__ import annotations

import sqlite3
from typing import Any

from recovery.audit.trail import record_event
from recovery.execution.outcomes import OutcomeResult
from recovery.learning.config import load_learning_config
from recovery.learning.records import DecisionOutcome, build_decision_outcome
from recovery.learning.signals import amount_bucket, generate_learning_signal, overdue_bucket
from recovery.learning.store import ExperienceStore
from recovery.models.recovery_types import ExecutionResult, RecoveryAction
from recovery.state.context import CaseRunContext


def record_intervention_outcome(
    conn: sqlite3.Connection,
    ctx: CaseRunContext,
    *,
    action: RecoveryAction,
    execution: ExecutionResult,
    outcome: OutcomeResult,
    state_before: str,
    estimated_probability: float | None = None,
    intervention_cost: float = 0.0,
    diagnosis: str | None = None,
    decision_source: str | None = None,
    timestamp: str | None = None,
    store: ExperienceStore | None = None,
    audit: bool = True,
) -> DecisionOutcome | None:
    """Persist a decision→outcome learning record after an intervention."""
    from datetime import datetime

    cfg = load_learning_config()
    if not cfg.enabled:
        return None

    amount_at_risk = (
        ctx.remaining_balance
        if ctx.case.lane == "receivable" and ctx.remaining_balance is not None
        else ctx.case.amount
    )
    remaining = 0.0 if outcome.recovered else max(
        0.0,
        float(amount_at_risk) - float(outcome.amount_recovered or ctx.amount_recovered or 0.0),
    )
    if ctx.case.lane == "receivable" and ctx.remaining_balance is not None:
        remaining = float(ctx.remaining_balance)

    partial = execution.event == "partial_payment_received" or (
        outcome.amount_recovered > 0 and not outcome.recovered and remaining > 0
    )

    metadata: dict[str, Any] = {
        "execution_event": execution.event,
        "execution_success": execution.success,
        "amount_bucket": amount_bucket(float(amount_at_risk)),
        "days_overdue": ctx.case.days_overdue,
        "overdue_bucket": overdue_bucket(ctx.case.days_overdue),
    }

    record = build_decision_outcome(
        case_id=ctx.case.case_id,
        customer_id=ctx.case.customer_id,
        lane=ctx.case.lane,
        action=action.action_id,
        amount_at_risk=float(amount_at_risk),
        intervention_cost=intervention_cost,
        estimated_recovery_probability=estimated_probability,
        observed_recovered=outcome.recovered,
        partially_recovered=partial,
        amount_recovered=float(outcome.amount_recovered or ctx.amount_recovered or 0.0),
        amount_remaining=remaining,
        diagnosis=diagnosis,
        decision_source=decision_source,
        state_before=state_before,
        state_after=ctx.workflow_state,
        timestamp=timestamp,
        metadata=metadata,
    )

    experience = store or ExperienceStore(conn)
    experience.record(record)
    signal = generate_learning_signal(record, is_contact=action.is_contact)

    ts = None
    if timestamp:
        ts = datetime.fromisoformat(timestamp)

    if audit:
        record_event(
            conn,
            case_id=ctx.case.case_id,
            customer_id=ctx.case.customer_id,
            event_type="OUTCOME_RECORDED",
            from_state=state_before,
            to_state=ctx.workflow_state,
            action=action.action_id,
            actor="learning",
            reason="Recorded decision outcome for experience store.",
            metadata=record.to_dict(),
            timestamp=ts,
        )
        record_event(
            conn,
            case_id=ctx.case.case_id,
            customer_id=ctx.case.customer_id,
            event_type="LEARNING_SIGNAL_GENERATED",
            from_state=ctx.workflow_state,
            to_state=ctx.workflow_state,
            action=action.action_id,
            actor="learning",
            reason="Generated deterministic learning signal.",
            metadata=signal.to_dict(),
            timestamp=ts,
        )
        record_event(
            conn,
            case_id=ctx.case.case_id,
            customer_id=ctx.case.customer_id,
            event_type="EXPERIENCE_UPDATED",
            from_state=ctx.workflow_state,
            to_state=ctx.workflow_state,
            action=action.action_id,
            actor="learning",
            reason=f"Experience store updated for action {action.action_id}.",
            metadata={
                "outcome_id": record.outcome_id,
                "observed_recovered": record.observed_recovered,
                "lane": record.lane,
            },
            timestamp=ts,
        )

    return record
