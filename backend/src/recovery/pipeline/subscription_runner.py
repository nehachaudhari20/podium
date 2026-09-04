"""Phase 2/3 — subscription recovery pipeline with hybrid intelligence (3D)."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone

from recovery.audit.trail import record_event
from recovery.execution.outcomes import is_terminal_state, process_outcome
from recovery.execution.sim_clock import SimulatedClock
from recovery.execution.simulator import simulate_execution
from recovery.ingestion.customer_loader import load_customer_context
from recovery.ingestion.runtime_loader import load_case_by_id
from recovery.intelligence.context_builder import build_recovery_context
from recovery.intelligence.contracts import DecisionProposal
from recovery.intelligence.decision_config import DecisionConfig
from recovery.intelligence.decision_evaluator import evaluate_decision_proposal
from recovery.intelligence.decisioning import HybridDecisionIntelligence
from recovery.models.enums import Lane, WorkflowState
from recovery.models.recovery_types import DiagnosisResult, PolicyResult, RecoveryAction
from recovery.policy.gate import load_policy_config
from recovery.state.context import CaseRunContext
from recovery.state.machine import apply_transition, can_transition
from recovery.state.persistence import log_recovery_action, save_case_state

MAX_STEPS = 30


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
        raise ValueError(f"Phase 2 run_case supports subscription_payment only, got {case.lane}")

    customer = load_customer_context(conn, case.customer_id)
    ctx = CaseRunContext(case=case)
    clock = SimulatedClock(start_time)
    policy = load_policy_config()
    selected: RecoveryAction | None = None
    policy_result: PolicyResult | None = None
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

    if customer.opt_out:
        _apply_and_audit(conn, ctx, clock, "customer_opts_out", "system", "Customer opted out.")
        save_case_state(conn, ctx)
        conn.commit()
        fallback = _empty_diagnosis()
        return _finalize(conn, ctx, fallback, [], None, None, "deterministic")

    _apply_and_audit(conn, ctx, clock, "case_diagnosed", "diagnosis_engine", "Case diagnosed.")

    initial_actions: list[RecoveryAction] = []
    diagnosis = _empty_diagnosis()
    decision_source = "deterministic"

    for step in range(MAX_STEPS):
        if is_terminal_state(ctx.workflow_state):
            break

        context = build_recovery_context(conn, case_id, run_context=ctx, now=clock.now)
        proposal = decision_engine.propose_decision(context)
        diagnosis = _diagnosis_from_proposal(proposal)
        decision_source = proposal.source

        if step == 0:
            initial_actions = list(proposal.candidate_actions)
            _audit(
                conn,
                ctx,
                clock,
                "DIAGNOSED",
                None,
                "intelligence",
                diagnosis.rationale,
                {"likely_cause": diagnosis.likely_cause, "source": proposal.reasoning.source},
            )
            _audit(
                conn,
                ctx,
                clock,
                "DECISION_PROPOSED",
                proposal.recommended_action.action_id,
                "intelligence",
                proposal.explanation,
                {
                    "source": proposal.source,
                    "actions": [a.action_id for a in proposal.candidate_actions],
                    "reasoning_source": proposal.reasoning.source,
                },
            )

        evaluated = evaluate_decision_proposal(
            proposal,
            ctx.sync_case_view(),
            customer,
            conn,
            ctx.last_retry_at,
            clock.now,
        )
        selected = evaluated.selected_action
        policy_result = evaluated.policy_result
        checks = list(evaluated.policy_checks)
        actions = list(proposal.candidate_actions)

        for check in checks:
            _audit(
                conn,
                ctx,
                clock,
                "POLICY_CHECK",
                check.action,
                "policy_gate",
                check.reason,
                {"allowed": check.allowed},
            )

        if selected is None:
            cooldown_hours = clock.hours_until_cooldown_clear(
                ctx.last_retry_at, policy.min_contact_cooldown_hours
            )
            if cooldown_hours > 0 and any(a.is_retry for a in actions):
                clock.advance_hours(cooldown_hours)
                _audit(
                    conn,
                    ctx,
                    clock,
                    "SIM_TIME_ADVANCED",
                    None,
                    "sim_clock",
                    f"Advanced {cooldown_hours}h to satisfy retry cooldown.",
                    {"simulated_now": clock.now.isoformat(), "reason": "cooldown"},
                )
                continue

            ctx.record_state(WorkflowState.EXHAUSTED.value)
            ctx.terminal = True
            _audit(conn, ctx, clock, "EXHAUSTED", None, "policy_gate", "No feasible action under policy.")
            break

        if ctx.payment_method_updated and selected.action_id == "payment_method_update":
            if not any(a.action_id != "payment_method_update" for a in actions):
                ctx.record_state(WorkflowState.EXHAUSTED.value)
                ctx.terminal = True
                _audit(conn, ctx, clock, "EXHAUSTED", None, "policy_gate", "Only method update remains; already requested.")
                break
            continue

        _prepare_for_execution(conn, ctx, clock, selected)

        if selected.is_retry and selected.retry_delay_hours:
            clock.advance_hours(selected.retry_delay_hours)
            _audit(
                conn,
                ctx,
                clock,
                "RETRY_SCHEDULED",
                selected.action_id,
                "sim_clock",
                f"Advanced {selected.retry_delay_hours}h for scheduled retry.",
                {"simulated_now": clock.now.isoformat(), "delay_hours": selected.retry_delay_hours},
            )

        execution = simulate_execution(ctx, selected, diagnosis)
        ctx.last_action = selected.action_id
        if selected.is_retry:
            ctx.last_retry_at = clock.now

        log_recovery_action(conn, ctx, execution)
        _audit(
            conn,
            ctx,
            clock,
            "ACTION_EXECUTED",
            selected.action_id,
            "execution_simulator",
            execution.detail,
            {"event": execution.event, "success": execution.success},
        )

        outcome = process_outcome(ctx, execution)
        if outcome.trigger and can_transition(ctx, outcome.trigger):
            _apply_and_audit(conn, ctx, clock, outcome.trigger, "outcome_engine", outcome.summary)
            _audit(conn, ctx, clock, _outcome_event_type(outcome), selected.action_id, "outcome_engine", outcome.summary)

        if outcome.recovered:
            break

        if execution.event == "payment_failed" and outcome.trigger != "max_retries_exceeded":
            if ctx.workflow_state != WorkflowState.WAITING.value:
                ctx.record_state(WorkflowState.WAITING.value)
                _audit(conn, ctx, clock, "STATE_TRANSITION", None, "state_machine", f"Waiting for next action (attempt {ctx.attempt_count}).")

        if execution.event == "payment_method_updated":
            if ctx.workflow_state == WorkflowState.CONTACTED.value:
                ctx.record_state(WorkflowState.WAITING.value)
                _audit(conn, ctx, clock, "STATE_TRANSITION", None, "state_machine", "Awaiting retry after method update request.")

    save_case_state(conn, ctx)
    conn.commit()
    return _finalize(conn, ctx, diagnosis, initial_actions, selected, policy_result, decision_source)


def _empty_diagnosis() -> DiagnosisResult:
    return DiagnosisResult(likely_cause="unknown_failure", confidence=0.0, rationale="")


def _diagnosis_from_proposal(proposal: DecisionProposal) -> DiagnosisResult:
    reasoning = proposal.reasoning
    return DiagnosisResult(
        likely_cause=reasoning.likely_cause,
        confidence=reasoning.confidence,
        rationale=reasoning.summary,
    )


def _prepare_for_execution(
    conn: sqlite3.Connection,
    ctx: CaseRunContext,
    clock: SimulatedClock,
    action: RecoveryAction,
) -> None:
    state = ctx.workflow_state

    if action.is_retry:
        if state in (WorkflowState.DIAGNOSED.value, WorkflowState.WAITING.value, WorkflowState.CONTACTED.value):
            if can_transition(ctx, "retry_scheduled"):
                _apply_and_audit(conn, ctx, clock, "retry_scheduled", "state_machine", f"Scheduling {action.action_id}.")
            if can_transition(ctx, "waiting_for_retry"):
                _apply_and_audit(conn, ctx, clock, "waiting_for_retry", "state_machine", "Waiting to execute retry.")
        return

    if action.is_contact and state in (WorkflowState.DIAGNOSED.value, WorkflowState.WAITING.value):
        if can_transition(ctx, "contact_sent"):
            _apply_and_audit(conn, ctx, clock, "contact_sent", "state_machine", f"Sending {action.action_id}.")
        return

    if action.action_id == "human_escalation" and can_transition(ctx, "escalated"):
        _apply_and_audit(conn, ctx, clock, "escalated", "state_machine", "Escalating to human agent.")


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


def _audit(
    conn: sqlite3.Connection,
    ctx: CaseRunContext,
    clock: SimulatedClock,
    event_type: str,
    action: str | None,
    actor: str,
    reason: str,
    metadata: dict | None = None,
) -> None:
    record_event(
        conn,
        case_id=ctx.case.case_id,
        customer_id=ctx.case.customer_id,
        event_type=event_type,
        from_state=ctx.workflow_state,
        to_state=ctx.workflow_state,
        action=action,
        actor=actor,
        reason=reason,
        metadata=metadata or {},
        timestamp=clock.now,
    )


def _outcome_event_type(outcome) -> str:
    if outcome.recovered:
        return "RECOVERED"
    if outcome.trigger == "max_retries_exceeded":
        return "EXHAUSTED"
    if outcome.trigger == "escalated":
        return "ESCALATED"
    if outcome.trigger == "payment_method_updated":
        return "PAYMENT_METHOD_UPDATE"
    return "PAYMENT_FAILED"


def _finalize(conn, ctx, diagnosis, candidates, selected, policy, decision_source) -> RunCaseResult:
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
    )


def format_run_summary(result: RunCaseResult) -> str:
    lines = [
        f"Case: {result.case_id}",
        f"Lane: {result.lane}",
        f"Amount: {result.currency} {result.amount:,.2f}",
        "",
        "Diagnosis:",
        f"  {result.diagnosis.likely_cause} (confidence {result.diagnosis.confidence:.0%})",
        f"  source: {result.decision_source}",
        "",
        "Candidate actions:",
    ]
    lines.extend(f"  {a.action_id}" for a in result.candidate_actions)
    lines.append("")
    if result.selected_action:
        lines.append(f"Selected action: {result.selected_action.action_id}")
    if result.policy_result:
        status = "ALLOWED" if result.policy_result.allowed else "BLOCKED"
        lines.append(f"Policy: {status} - {result.policy_result.reason}")
    lines.extend(["", "State progression:", "  " + " -> ".join(result.state_history), ""])
    if result.recovered:
        lines.append(f"Outcome: Recovered {result.currency} {result.amount_recovered:,.2f}")
    else:
        lines.append(f"Outcome: Terminal state '{result.terminal_state}'")
    lines.append(f"Audit events: {result.audit_event_count}")
    return "\n".join(lines)
