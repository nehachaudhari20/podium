"""Subscription recovery pipeline — delegates to agentic loop (Phase 3E)."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime

from recovery.audit.trail import record_event
from recovery.execution.sim_clock import SimulatedClock
from recovery.ingestion.customer_loader import load_customer_context
from recovery.ingestion.runtime_loader import load_case_by_id
from recovery.intelligence.decision_config import DecisionConfig
from recovery.intelligence.decisioning import HybridDecisionIntelligence
from recovery.models.enums import Lane, WorkflowState
from recovery.models.recovery_types import DiagnosisResult, PolicyResult, RecoveryAction
from recovery.pipeline.agentic_loop import AgenticRecoveryLoop
from recovery.policy.gate import load_policy_config
from recovery.state.context import CaseRunContext
from recovery.state.machine import apply_transition
from recovery.state.persistence import save_case_state


@dataclass
class RunCaseResult:
    case_id: str
    lane: str
    amount: float
    currency: str
    diagnosis: DiagnosisResult
    candidate_actions: list[RecoveryAction]
    decision_source: str = "deterministic"
    selected_action: RecoveryAction | None = None
    policy_result: PolicyResult | None = None
    state_history: list[str] = field(default_factory=list)
    recovered: bool = False
    amount_recovered: float = 0.0
    terminal_state: str = ""
    audit_event_count: int = 0
    agent_steps: int = 0
    replan_count: int = 0
    economic_candidates: list = field(default_factory=list)
    expected_recovery_value: float | None = None
    expected_net_value: float | None = None
    intervention_cost: float | None = None
    capacity_decision: str | None = None
    economic_reason: str | None = None


def run_subscription_case(
    conn: sqlite3.Connection,
    case_id: str,
    *,
    start_time: datetime | None = None,
    intelligence_mode: str | None = None,
) -> RunCaseResult:
    case = load_case_by_id(conn, case_id)
    if case is None:
        raise ValueError(f"Case not found: {case_id}")
    if case.lane != Lane.SUBSCRIPTION_PAYMENT.value:
        raise ValueError(f"run_subscription_case supports subscription_payment only, got {case.lane}")

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
        return _finalize(conn, ctx, _empty_diagnosis(), [], None, None, "deterministic", 0, 0, None, None)

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
        loop_result.economic_decision,
        loop_result.capacity_decision,
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
    return DiagnosisResult(likely_cause="unknown_failure", confidence=0.0, rationale="")


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
    economic_decision=None,
    capacity_decision=None,
) -> RunCaseResult:
    audit_count = conn.execute(
        "SELECT COUNT(*) FROM audit_events WHERE case_id = ?", (ctx.case.case_id,)
    ).fetchone()[0]
    eco_candidates = []
    expected_recovery = None
    expected_net = None
    intervention_cost = None
    economic_reason = None
    if economic_decision is not None:
        eco_candidates = list(economic_decision.candidates)
        economic_reason = economic_decision.economic_reason
        if economic_decision.selected is not None:
            expected_recovery = economic_decision.selected.expected_recovery_value
            expected_net = economic_decision.selected.expected_net_value
            intervention_cost = economic_decision.selected.intervention_cost
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
        economic_candidates=eco_candidates,
        expected_recovery_value=expected_recovery,
        expected_net_value=expected_net,
        intervention_cost=intervention_cost,
        capacity_decision=capacity_decision,
        economic_reason=economic_reason,
    )


def format_run_summary(result: RunCaseResult) -> str:
    lines = [
        f"Case: {result.case_id}",
        f"Lane: {result.lane}",
        f"Amount at risk: {result.currency} {result.amount:,.2f}",
        "",
        "Diagnosis:",
        f"  {result.diagnosis.likely_cause} (confidence {result.diagnosis.confidence:.0%})",
        f"  source: {result.decision_source}",
        "",
        "Candidate actions:",
    ]
    lines.extend(f"  {a.action_id}" for a in result.candidate_actions)

    if result.economic_candidates:
        lines.extend(["", "Economics:"])
        for candidate in result.economic_candidates:
            lines.append(
                f"  {candidate.action_id}: p={candidate.estimated_recovery_probability:.2f} "
                f"ERV={candidate.expected_recovery_value:,.2f} "
                f"cost={candidate.intervention_cost:,.2f} "
                f"ENV={candidate.expected_net_value:,.2f} "
                f"({'ok' if candidate.eligible else 'ineligible'}: {candidate.reason})"
            )

    lines.append("")
    if result.selected_action:
        lines.append(f"Selected action: {result.selected_action.action_id}")
    if result.economic_reason:
        lines.append(f"Economic reason: {result.economic_reason}")
    if result.expected_net_value is not None:
        lines.append(
            f"Expected net value: {result.currency} {result.expected_net_value:,.2f} "
            f"(ERV={result.expected_recovery_value:,.2f}, cost={result.intervention_cost:,.2f})"
        )
    if result.capacity_decision:
        lines.append(f"Capacity: {result.capacity_decision}")
    if result.policy_result:
        status = "ALLOWED" if result.policy_result.allowed else "BLOCKED"
        lines.append(f"Policy: {status} - {result.policy_result.reason}")
    lines.extend(
        [
            "",
            f"Agent cycles: {result.agent_steps}  Re-plans: {result.replan_count}",
            "",
            "State progression:",
            "  " + " -> ".join(result.state_history),
            "",
        ]
    )
    if result.recovered:
        lines.append(f"Outcome: Recovered {result.currency} {result.amount_recovered:,.2f}")
    else:
        lines.append(f"Outcome: Terminal state '{result.terminal_state}'")
    lines.append(f"Audit events: {result.audit_event_count}")
    return "\n".join(lines)
