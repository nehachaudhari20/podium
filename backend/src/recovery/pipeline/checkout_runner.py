"""Checkout abandonment recovery pipeline — reuses agentic loop (Phase 4C)."""

from __future__ import annotations

import sqlite3
from datetime import datetime

from recovery.audit.trail import record_event
from recovery.execution.sim_clock import SimulatedClock
from recovery.ingestion.customer_loader import load_customer_context
from recovery.ingestion.runtime_loader import load_case_by_id
from recovery.intelligence.decision_config import DecisionConfig
from recovery.intelligence.decisioning import HybridDecisionIntelligence
from recovery.models.enums import Lane, WorkflowState
from recovery.models.recovery_types import DiagnosisResult
from recovery.pipeline.agentic_loop import AgenticRecoveryLoop
from recovery.pipeline.subscription_runner import RunCaseResult, format_run_summary
from recovery.policy.gate import load_policy_config
from recovery.state.context import CaseRunContext
from recovery.state.machine import apply_transition
from recovery.state.persistence import save_case_state

__all__ = ["RunCaseResult", "format_run_summary", "run_checkout_case"]


def run_checkout_case(
    conn: sqlite3.Connection,
    case_id: str,
    *,
    start_time: datetime | None = None,
    intelligence_mode: str | None = None,
) -> RunCaseResult:
    case = load_case_by_id(conn, case_id)
    if case is None:
        raise ValueError(f"Case not found: {case_id}")
    if case.lane != Lane.CHECKOUT_ABANDONMENT.value:
        raise ValueError(
            f"run_checkout_case supports checkout_abandonment only, got {case.lane}"
        )

    customer = load_customer_context(conn, case.customer_id)
    ctx = CaseRunContext(case=case)
    clock = SimulatedClock(start_time)
    decision_config = (
        DecisionConfig.from_env()
        if intelligence_mode is None
        else DecisionConfig(
            mode=intelligence_mode,
            min_reasoning_confidence=DecisionConfig.from_env().min_reasoning_confidence,
            min_strategy_confidence=DecisionConfig.from_env().min_strategy_confidence,
        )
    )
    decision_engine = HybridDecisionIntelligence(config=decision_config)
    agent = AgenticRecoveryLoop(decision_engine, load_policy_config())

    if customer.opt_out:
        _apply_opt_out(conn, ctx, clock)
        save_case_state(conn, ctx)
        conn.commit()
        return _finalize(conn, ctx, _empty_diagnosis(), [], None, None, "deterministic", 0, 0)

    _apply_and_audit(conn, ctx, clock, "case_diagnosed", "diagnosis_engine", "Case diagnosed.")

    loop_result = agent.run(conn, case_id, ctx, customer, clock)

    save_case_state(conn, ctx)
    conn.commit()
    return _finalize(
        conn,
        ctx,
        loop_result.diagnosis or _empty_diagnosis(),
        loop_result.initial_actions,
        loop_result.selected_action,
        loop_result.policy_result,
        loop_result.decision_source,
        len(loop_result.steps),
        loop_result.replan_count,
    )


def _apply_opt_out(conn: sqlite3.Connection, ctx: CaseRunContext, clock: SimulatedClock) -> None:
    from_state = ctx.workflow_state
    apply_transition(ctx, "customer_opts_out")
    record_event(
        conn,
        case_id=ctx.case.case_id,
        customer_id=ctx.case.customer_id,
        event_type="STATE_TRANSITION",
        from_state=from_state,
        to_state=ctx.workflow_state,
        action=None,
        actor="system",
        reason="Customer opted out.",
        metadata={"trigger": "customer_opts_out"},
        timestamp=clock.now,
    )


def _apply_and_audit(
    conn: sqlite3.Connection,
    ctx: CaseRunContext,
    clock: SimulatedClock,
    trigger: str,
    actor: str,
    reason: str,
) -> None:
    from_state = ctx.workflow_state
    apply_transition(ctx, trigger)
    record_event(
        conn,
        case_id=ctx.case.case_id,
        customer_id=ctx.case.customer_id,
        event_type="STATE_TRANSITION",
        from_state=from_state,
        to_state=ctx.workflow_state,
        action=ctx.last_action,
        actor=actor,
        reason=reason,
        metadata={"trigger": trigger},
        timestamp=clock.now,
    )


def _empty_diagnosis() -> DiagnosisResult:
    return DiagnosisResult(likely_cause="unknown_abandonment", confidence=0.0, rationale="")


def _finalize(
    conn,
    ctx,
    diagnosis,
    candidates,
    selected,
    policy,
    decision_source,
    agent_steps,
    replan_count,
) -> RunCaseResult:
    audit_count = conn.execute(
        "SELECT COUNT(*) FROM audit_events WHERE case_id = ?", (ctx.case.case_id,)
    ).fetchone()[0]
    return RunCaseResult(
        case_id=ctx.case.case_id,
        lane=ctx.case.lane,
        amount=ctx.case.amount,
        currency=ctx.case.currency,
        diagnosis=diagnosis,
        candidate_actions=candidates,
        decision_source=decision_source,
        selected_action=selected,
        policy_result=policy,
        state_history=ctx.state_history,
        recovered=ctx.workflow_state == WorkflowState.RECOVERED.value,
        amount_recovered=ctx.amount_recovered,
        terminal_state=ctx.workflow_state,
        audit_event_count=int(audit_count),
        agent_steps=agent_steps,
        replan_count=replan_count,
    )
