"""Agentic recovery loop — Observe → Reason → Act → Re-plan (Phase 3E)."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime

from recovery.audit.trail import record_event
from recovery.economics.allocator import CapacityPool
from recovery.economics.config import EconomicsConfig, load_economics_config
from recovery.execution.outcomes import is_terminal_state, process_outcome
from recovery.execution.sim_clock import SimulatedClock
from recovery.execution.simulator import simulate_execution
from recovery.ingestion.customer_loader import CustomerContext
from recovery.ingestion.invoice_loader import load_active_promise_by_case, load_invoice_by_case
from recovery.intelligence.context_builder import build_recovery_context
from recovery.intelligence.contracts import DecisionProposal
from recovery.intelligence.decision_evaluator import EvaluatedDecision, evaluate_decision_proposal
from recovery.intelligence.decisioning import HybridDecisionIntelligence
from recovery.learning.blend import blend_from_store
from recovery.learning.config import load_learning_config
from recovery.learning.recorder import record_intervention_outcome
from recovery.learning.store import ExperienceStore
from recovery.models.enums import Lane, WorkflowState
from recovery.models.recovery_types import DiagnosisResult, ExecutionResult, PolicyResult, RecoveryAction
from recovery.policy.gate import PolicyConfig
from recovery.promises import (
    create_promise,
    default_promise_date,
    observe_promise_payment,
    update_promise_status,
    validate_promise,
)
from recovery.state.context import CaseRunContext
from recovery.state.machine import apply_transition, can_transition
from recovery.state.persistence import log_recovery_action

MAX_AGENT_STEPS = 30


@dataclass
class AgentStepRecord:
    """One Observe → Reason → Act cycle."""

    step: int
    workflow_state: str
    proposal: DecisionProposal
    evaluated: EvaluatedDecision
    execution: ExecutionResult | None = None
    outcome_summary: str = ""
    replanned: bool = False


@dataclass
class AgenticLoopResult:
    """Aggregate outcome from the agentic recovery loop."""

    steps: list[AgentStepRecord] = field(default_factory=list)
    diagnosis: DiagnosisResult | None = None
    initial_actions: list[RecoveryAction] = field(default_factory=list)
    decision_source: str = "deterministic"
    selected_action: RecoveryAction | None = None
    policy_result: PolicyResult | None = None
    replan_count: int = 0
    recovered: bool = False
    economic_decision: object | None = None
    capacity_decision: str | None = None
    outcomes_recorded: int = 0


class AgenticRecoveryLoop:
    """Runs the subscription recovery agent loop until terminal or max steps."""

    def __init__(
        self,
        decision_engine: HybridDecisionIntelligence,
        policy: PolicyConfig,
        *,
        max_steps: int = MAX_AGENT_STEPS,
        economics_config: EconomicsConfig | None = None,
        capacity_pool: CapacityPool | None = None,
        learning_enabled: bool | None = None,
    ) -> None:
        self._decision_engine = decision_engine
        self._policy = policy
        self._max_steps = max_steps
        self._economics_config = economics_config if economics_config is not None else load_economics_config()
        self._capacity_pool = capacity_pool
        self._learning_enabled = (
            load_learning_config().enabled if learning_enabled is None else learning_enabled
        )

    def run(
        self,
        conn: sqlite3.Connection,
        case_id: str,
        ctx: CaseRunContext,
        customer: CustomerContext,
        clock: SimulatedClock,
    ) -> AgenticLoopResult:
        result = AgenticLoopResult()
        previous_recommended: str | None = None
        experience_store = ExperienceStore(conn) if self._learning_enabled else None

        for step in range(self._max_steps):
            if is_terminal_state(ctx.workflow_state):
                break

            context = build_recovery_context(conn, case_id, run_context=ctx, now=clock.now)
            self._audit(
                conn,
                ctx,
                clock,
                "AGENT_OBSERVE",
                None,
                "agentic_loop",
                f"Observed state {ctx.workflow_state} before step {step + 1}.",
                {
                    "step": step + 1,
                    "workflow_state": ctx.workflow_state,
                    "attempt_count": ctx.attempt_count,
                    "history_events": len(context.recovery_history),
                },
            )

            proposal = self._decision_engine.propose_decision(context)
            result.diagnosis = _diagnosis_from_proposal(proposal)
            result.decision_source = proposal.source

            replanned = step > 0 or (
                previous_recommended is not None
                and proposal.recommended_action.action_id != previous_recommended
            )
            if replanned:
                result.replan_count += 1
                self._audit(
                    conn,
                    ctx,
                    clock,
                    "AGENT_REPLAN",
                    proposal.recommended_action.action_id,
                    "agentic_loop",
                    proposal.explanation,
                    {
                        "step": step + 1,
                        "source": proposal.source,
                        "previous": previous_recommended,
                        "recommended": proposal.recommended_action.action_id,
                    },
                )

            if step == 0:
                result.initial_actions = list(proposal.candidate_actions)
                self._audit(
                    conn,
                    ctx,
                    clock,
                    "DIAGNOSED",
                    None,
                    "intelligence",
                    result.diagnosis.rationale,
                    {"likely_cause": result.diagnosis.likely_cause, "source": proposal.reasoning.source},
                )

            self._audit(
                conn,
                ctx,
                clock,
                "DECISION_PROPOSED",
                proposal.recommended_action.action_id,
                "intelligence",
                proposal.explanation,
                {
                    "step": step + 1,
                    "source": proposal.source,
                    "actions": [a.action_id for a in proposal.candidate_actions],
                    "reasoning_source": proposal.reasoning.source,
                },
            )

            if experience_store is not None:
                for candidate in proposal.candidate_actions:
                    model_p = proposal.predictive.estimated_recovery_probability
                    blended = blend_from_store(
                        experience_store,
                        action=candidate.action_id,
                        lane=ctx.case.lane,
                        model_probability=model_p,
                        diagnosis=result.diagnosis.likely_cause if result.diagnosis else None,
                    )
                    if blended.used_history:
                        self._audit(
                            conn,
                            ctx,
                            clock,
                            "HISTORICAL_EVIDENCE_USED",
                            candidate.action_id,
                            "learning",
                            blended.reason,
                            blended.to_dict(),
                        )

            evaluated = evaluate_decision_proposal(
                proposal,
                ctx.sync_case_view(),
                customer,
                conn,
                ctx.last_retry_at,
                clock.now,
                economics_config=self._economics_config,
                capacity_pool=self._capacity_pool,
                last_action=ctx.last_action,
                experience_store=experience_store,
            )
            result.economic_decision = evaluated.economic_decision
            result.capacity_decision = evaluated.capacity_decision

            if evaluated.economic_decision is not None:
                self._audit(
                    conn,
                    ctx,
                    clock,
                    "ECONOMIC_EVALUATION",
                    None,
                    "economic_engine",
                    evaluated.economic_decision.economic_reason,
                    {
                        "step": step + 1,
                        "candidates": [
                            {
                                "action": c.action_id,
                                "probability": c.estimated_recovery_probability,
                                "cost": c.intervention_cost,
                                "expected_net_value": c.expected_net_value,
                                "eligible": c.eligible,
                                "reason": c.reason,
                            }
                            for c in evaluated.economic_decision.candidates
                        ],
                    },
                )
                if evaluated.economic_decision.selected is not None:
                    sel = evaluated.economic_decision.selected
                    self._audit(
                        conn,
                        ctx,
                        clock,
                        "ECONOMIC_ACTION_SELECTED",
                        sel.action_id,
                        "economic_engine",
                        evaluated.economic_decision.economic_reason,
                        {
                            "expected_recovery_value": sel.expected_recovery_value,
                            "intervention_cost": sel.intervention_cost,
                            "expected_net_value": sel.expected_net_value,
                        },
                    )
                for candidate in evaluated.economic_decision.candidates:
                    if not candidate.eligible:
                        self._audit(
                            conn,
                            ctx,
                            clock,
                            "ECONOMIC_ACTION_REJECTED",
                            candidate.action_id,
                            "economic_engine",
                            candidate.reason,
                            {
                                "expected_net_value": candidate.expected_net_value,
                                "intervention_cost": candidate.intervention_cost,
                            },
                        )

            if evaluated.capacity_decision:
                event = (
                    "CAPACITY_DEFERRED"
                    if evaluated.capacity_decision.startswith("deferred")
                    else "CAPACITY_ALLOCATED"
                )
                self._audit(
                    conn,
                    ctx,
                    clock,
                    event,
                    evaluated.selected_action.action_id if evaluated.selected_action else None,
                    "economic_engine",
                    evaluated.capacity_decision,
                    {"step": step + 1},
                )

            for check in evaluated.policy_checks:
                self._audit(
                    conn,
                    ctx,
                    clock,
                    "POLICY_CHECK",
                    check.action,
                    "policy_gate",
                    check.reason,
                    {"allowed": check.allowed, "step": step + 1},
                )

            selected = evaluated.selected_action
            result.selected_action = selected
            result.policy_result = evaluated.policy_result
            actions = list(proposal.candidate_actions)
            execution: ExecutionResult | None = None
            outcome_summary = ""

            if selected is None:
                if self._try_advance_cooldown(conn, ctx, clock, actions):
                    result.steps.append(
                        AgentStepRecord(
                            step=step,
                            workflow_state=ctx.workflow_state,
                            proposal=proposal,
                            evaluated=evaluated,
                            replanned=replanned,
                        )
                    )
                    continue

                ctx.record_state(WorkflowState.EXHAUSTED.value)
                ctx.terminal = True
                self._audit(conn, ctx, clock, "EXHAUSTED", None, "policy_gate", "No feasible action under policy.")
                result.steps.append(
                    AgentStepRecord(
                        step=step,
                        workflow_state=ctx.workflow_state,
                        proposal=proposal,
                        evaluated=evaluated,
                        replanned=replanned,
                    )
                )
                break

            if ctx.payment_method_updated and selected.action_id == "payment_method_update":
                if not any(a.action_id != "payment_method_update" for a in actions):
                    ctx.record_state(WorkflowState.EXHAUSTED.value)
                    ctx.terminal = True
                    self._audit(
                        conn,
                        ctx,
                        clock,
                        "EXHAUSTED",
                        None,
                        "policy_gate",
                        "Only method update remains; already requested.",
                    )
                    break
                result.steps.append(
                    AgentStepRecord(
                        step=step,
                        workflow_state=ctx.workflow_state,
                        proposal=proposal,
                        evaluated=evaluated,
                        replanned=replanned,
                    )
                )
                continue

            self._prepare_for_execution(conn, ctx, clock, selected)

            if selected.is_retry and selected.retry_delay_hours:
                clock.advance_hours(selected.retry_delay_hours)
                self._audit(
                    conn,
                    ctx,
                    clock,
                    "RETRY_SCHEDULED",
                    selected.action_id,
                    "sim_clock",
                    f"Advanced {selected.retry_delay_hours}h for scheduled retry.",
                    {"simulated_now": clock.now.isoformat(), "delay_hours": selected.retry_delay_hours},
                )

            execution = simulate_execution(ctx, selected, result.diagnosis)
            ctx.last_action = selected.action_id
            if selected.is_retry:
                ctx.last_retry_at = clock.now

            log_recovery_action(conn, ctx, execution)
            self._audit(
                conn,
                ctx,
                clock,
                "ACTION_EXECUTED",
                selected.action_id,
                "execution_simulator",
                execution.detail,
                {"event": execution.event, "success": execution.success, "step": step + 1},
            )

            # Receivable PTP: create / observe before generic outcome processing.
            if ctx.case.lane == Lane.RECEIVABLE.value and execution.event in {
                "promise_created",
                "promise_due_check",
            }:
                execution, outcome = self._handle_promise_lifecycle(
                    conn, ctx, clock, execution, result.diagnosis
                )
            else:
                outcome = process_outcome(ctx, execution)

            outcome_summary = outcome.summary
            state_before_outcome = ctx.workflow_state
            if outcome.trigger and can_transition(ctx, outcome.trigger):
                self._apply_and_audit(conn, ctx, clock, outcome.trigger, "outcome_engine", outcome.summary)
                self._audit(
                    conn,
                    ctx,
                    clock,
                    _outcome_event_type(outcome),
                    selected.action_id,
                    "outcome_engine",
                    outcome.summary,
                )

            if experience_store is not None:
                est_prob = None
                cost = 0.0
                if evaluated.economic_decision is not None:
                    for candidate in evaluated.economic_decision.candidates:
                        if candidate.action_id == selected.action_id:
                            est_prob = candidate.estimated_recovery_probability
                            cost = candidate.intervention_cost
                            break
                recorded = record_intervention_outcome(
                    conn,
                    ctx,
                    action=selected,
                    execution=execution,
                    outcome=outcome,
                    state_before=state_before_outcome,
                    estimated_probability=est_prob,
                    intervention_cost=cost,
                    diagnosis=result.diagnosis.likely_cause if result.diagnosis else None,
                    decision_source=result.decision_source,
                    timestamp=clock.now.isoformat(),
                    store=experience_store,
                )
                if recorded is not None:
                    result.outcomes_recorded += 1

            result.steps.append(
                AgentStepRecord(
                    step=step,
                    workflow_state=ctx.workflow_state,
                    proposal=proposal,
                    evaluated=evaluated,
                    execution=execution,
                    outcome_summary=outcome_summary,
                    replanned=replanned,
                )
            )
            previous_recommended = proposal.recommended_action.action_id

            if outcome.recovered:
                result.recovered = True
                break

            if (
                execution.event
                in {"payment_failed", "customer_ignored", "promise_broken", "partial_payment_received"}
                and outcome.trigger != "max_retries_exceeded"
            ):
                if ctx.workflow_state not in {
                    WorkflowState.WAITING.value,
                    WorkflowState.PROMISED.value,
                    WorkflowState.ESCALATED.value,
                }:
                    ctx.record_state(WorkflowState.WAITING.value)
                    self._audit(
                        conn,
                        ctx,
                        clock,
                        "STATE_TRANSITION",
                        None,
                        "state_machine",
                        f"Waiting for next action (attempt {ctx.attempt_count}).",
                    )

            if execution.event == "payment_method_updated":
                if ctx.workflow_state == WorkflowState.CONTACTED.value:
                    ctx.record_state(WorkflowState.WAITING.value)
                    self._audit(
                        conn,
                        ctx,
                        clock,
                        "STATE_TRANSITION",
                        None,
                        "state_machine",
                        "Awaiting retry after method update request.",
                    )

        if result.diagnosis is None:
            result.diagnosis = _empty_diagnosis()
        return result

    def _try_advance_cooldown(
        self,
        conn: sqlite3.Connection,
        ctx: CaseRunContext,
        clock: SimulatedClock,
        actions: list[RecoveryAction],
    ) -> bool:
        cooldown_hours = clock.hours_until_cooldown_clear(
            ctx.last_retry_at, self._policy.min_contact_cooldown_hours
        )
        if cooldown_hours > 0 and any(a.is_retry for a in actions):
            clock.advance_hours(cooldown_hours)
            self._audit(
                conn,
                ctx,
                clock,
                "SIM_TIME_ADVANCED",
                None,
                "sim_clock",
                f"Advanced {cooldown_hours}h to satisfy retry cooldown.",
                {"simulated_now": clock.now.isoformat(), "reason": "cooldown"},
            )
            return True
        return False

    def _prepare_for_execution(
        self,
        conn: sqlite3.Connection,
        ctx: CaseRunContext,
        clock: SimulatedClock,
        action: RecoveryAction,
    ) -> None:
        state = ctx.workflow_state

        if action.is_retry:
            if state in (WorkflowState.DIAGNOSED.value, WorkflowState.WAITING.value, WorkflowState.CONTACTED.value):
                if can_transition(ctx, "retry_scheduled"):
                    self._apply_and_audit(
                        conn, ctx, clock, "retry_scheduled", "state_machine", f"Scheduling {action.action_id}."
                    )
                if can_transition(ctx, "waiting_for_retry"):
                    self._apply_and_audit(
                        conn, ctx, clock, "waiting_for_retry", "state_machine", "Waiting to execute retry."
                    )
            return

        if action.is_contact and state in (WorkflowState.DIAGNOSED.value, WorkflowState.WAITING.value):
            if can_transition(ctx, "contact_sent"):
                self._apply_and_audit(
                    conn, ctx, clock, "contact_sent", "state_machine", f"Sending {action.action_id}."
                )
            return

        if action.action_id in {"limited_incentive", "offer_discount"} and state in (
            WorkflowState.DIAGNOSED.value,
            WorkflowState.WAITING.value,
        ):
            if can_transition(ctx, "contact_sent"):
                self._apply_and_audit(
                    conn, ctx, clock, "contact_sent", "state_machine", f"Applying {action.action_id}."
                )
            return

        if action.action_id == "human_escalation" and can_transition(ctx, "escalated"):
            self._apply_and_audit(conn, ctx, clock, "escalated", "state_machine", "Escalating to human agent.")

        if action.action_id == "escalate_collections" and can_transition(ctx, "escalated"):
            self._apply_and_audit(
                conn, ctx, clock, "escalated", "state_machine", "Escalating to collections."
            )

        if action.action_id == "track_promise_to_pay" and ctx.workflow_state != WorkflowState.PROMISED.value:
            if can_transition(ctx, "promise_made"):
                self._apply_and_audit(
                    conn, ctx, clock, "promise_made", "state_machine", "Tracking active promise."
                )

    def _handle_promise_lifecycle(
        self,
        conn: sqlite3.Connection,
        ctx: CaseRunContext,
        clock: SimulatedClock,
        execution: ExecutionResult,
        diagnosis: DiagnosisResult | None,
    ):
        """Create PTP, advance clock to due date, observe payment, feed outcome."""
        remaining = ctx.remaining_balance if ctx.remaining_balance is not None else ctx.case.amount

        if execution.event == "promise_created":
            window_end = ctx.case.recovery_window_end
            if window_end.tzinfo is None:
                from datetime import timezone as _tz

                window_end = window_end.replace(tzinfo=_tz.utc)
            days_left = max(1, (window_end - clock.now).days)
            promise_days = min(7, max(1, days_left - 1))
            promise_date = default_promise_date(clock.now, days=promise_days)
            validation = validate_promise(
                promised_amount=remaining,
                promise_date=promise_date,
                remaining_balance=remaining,
                recovery_window_end=ctx.case.recovery_window_end,
                now=clock.now,
            )
            if not validation.allowed:
                self._audit(
                    conn,
                    ctx,
                    clock,
                    "PROMISE_REJECTED",
                    "promise_to_pay_request",
                    "promise_validator",
                    validation.reason,
                    {
                        "promised_amount": remaining,
                        "promise_date": promise_date.isoformat(),
                        "remaining_balance": remaining,
                    },
                )
                return (
                    ExecutionResult(
                        action=execution.action,
                        success=False,
                        event="customer_ignored",
                        detail=f"Promise rejected: {validation.reason}",
                    ),
                    process_outcome(
                        ctx,
                        ExecutionResult(
                            action=execution.action,
                            success=False,
                            event="customer_ignored",
                            detail=f"Promise rejected: {validation.reason}",
                        ),
                    ),
                )

            invoice = load_invoice_by_case(conn, ctx.case.case_id)
            due_date = invoice.due_date if invoice is not None else ctx.case.created_at
            promise = create_promise(
                conn,
                case_id=ctx.case.case_id,
                customer_id=ctx.case.customer_id,
                promised_amount=remaining,
                promise_date=promise_date,
                due_date=due_date,
                created_at=clock.now,
            )
            ctx.active_promise_id = promise.promise_id
            self._audit(
                conn,
                ctx,
                clock,
                "PROMISE_CREATED",
                "promise_to_pay_request",
                "promise_engine",
                "Promise-to-pay recorded.",
                {
                    "promise_id": promise.promise_id,
                    "promised_amount": promise.promised_amount,
                    "promise_date": promise.promise_date.isoformat(),
                    "remaining_balance": remaining,
                },
            )
            # Move to promised before waiting for due date.
            if can_transition(ctx, "promise_made"):
                self._apply_and_audit(
                    conn, ctx, clock, "promise_made", "outcome_engine", "Customer promised payment."
                )

            return self._observe_active_promise(conn, ctx, clock, diagnosis)

        # track_promise_to_pay / promise_due_check
        return self._observe_active_promise(conn, ctx, clock, diagnosis)

    def _observe_active_promise(
        self,
        conn: sqlite3.Connection,
        ctx: CaseRunContext,
        clock: SimulatedClock,
        diagnosis: DiagnosisResult | None,
    ):
        active = load_active_promise_by_case(conn, ctx.case.case_id)
        if active is None and ctx.active_promise_id:
            # Just created in same transaction path — reload
            active = load_active_promise_by_case(conn, ctx.case.case_id)
        if active is None:
            return (
                ExecutionResult(
                    action="track_promise_to_pay",
                    success=False,
                    event="customer_ignored",
                    detail="No active promise to observe.",
                ),
                process_outcome(
                    ctx,
                    ExecutionResult(
                        action="track_promise_to_pay",
                        success=False,
                        event="customer_ignored",
                        detail="No active promise to observe.",
                    ),
                ),
            )

        promise_date = active.promise_date
        if promise_date.tzinfo is None:
            from datetime import timezone

            promise_date = promise_date.replace(tzinfo=timezone.utc)
        if clock.now < promise_date:
            hours = max(1, int((promise_date - clock.now).total_seconds() / 3600) + 1)
            clock.advance_hours(hours)
            self._audit(
                conn,
                ctx,
                clock,
                "SIM_TIME_ADVANCED",
                None,
                "sim_clock",
                f"Advanced to promise date ({promise_date.isoformat()}).",
                {"simulated_now": clock.now.isoformat(), "reason": "promise_due"},
            )

        self._audit(
            conn,
            ctx,
            clock,
            "PROMISE_DUE",
            "track_promise_to_pay",
            "promise_engine",
            "Promise date reached; observing payment.",
            {
                "promise_id": active.promise_id,
                "promised_amount": active.promised_amount,
                "remaining_balance": ctx.remaining_balance,
            },
        )

        remaining = ctx.remaining_balance if ctx.remaining_balance is not None else ctx.case.amount
        paid = _simulated_promise_payment(ctx, diagnosis, remaining, active.promised_amount)
        observation = observe_promise_payment(
            promised_amount=float(active.promised_amount),
            remaining_balance=remaining,
            paid_amount=paid,
        )

        if observation.outcome == "kept":
            update_promise_status(conn, active.promise_id, "kept")
            ctx.active_promise_id = None
            ctx.amount_paid = round(ctx.amount_paid + observation.amount_paid, 2)
            ctx.amount_recovered = round(ctx.amount_recovered + observation.amount_paid, 2)
            ctx.remaining_balance = 0.0
            execution = ExecutionResult(
                action="observe_payment",
                success=True,
                event="promise_kept",
                detail=observation.detail,
            )
            self._audit(
                conn,
                ctx,
                clock,
                "PROMISE_KEPT",
                "observe_payment",
                "promise_engine",
                observation.detail,
                {
                    "promise_id": active.promise_id,
                    "amount_paid": observation.amount_paid,
                    "remaining_balance": 0.0,
                },
            )
            return execution, process_outcome(ctx, execution)

        if observation.outcome == "partial":
            update_promise_status(conn, active.promise_id, "missed")
            ctx.active_promise_id = None
            ctx.promise_broken_before = True
            ctx.amount_paid = round(ctx.amount_paid + observation.amount_paid, 2)
            ctx.remaining_balance = observation.remaining_balance
            ctx.amount_recovered = round(ctx.amount_recovered + observation.amount_paid, 2)
            execution = ExecutionResult(
                action="observe_payment",
                success=False,
                event="partial_payment_received",
                detail=observation.detail,
            )
            self._audit(
                conn,
                ctx,
                clock,
                "PARTIAL_PAYMENT_RECEIVED",
                "observe_payment",
                "promise_engine",
                observation.detail,
                {
                    "promise_id": active.promise_id,
                    "amount_paid": observation.amount_paid,
                    "remaining_balance": observation.remaining_balance,
                },
            )
            self._audit(
                conn,
                ctx,
                clock,
                "PROMISE_BROKEN",
                "observe_payment",
                "promise_engine",
                "Promise only partially fulfilled; re-planning for remaining balance.",
                {"promise_id": active.promise_id, "remaining_balance": observation.remaining_balance},
            )
            return execution, process_outcome(ctx, execution)

        update_promise_status(conn, active.promise_id, "missed")
        ctx.active_promise_id = None
        ctx.promise_broken_before = True
        execution = ExecutionResult(
            action="observe_payment",
            success=False,
            event="promise_broken",
            detail=observation.detail,
        )
        self._audit(
            conn,
            ctx,
            clock,
            "PROMISE_BROKEN",
            "observe_payment",
            "promise_engine",
            observation.detail,
            {
                "promise_id": active.promise_id,
                "amount_paid": observation.amount_paid,
                "remaining_balance": observation.remaining_balance,
            },
        )
        return execution, process_outcome(ctx, execution)

    def _apply_and_audit(
        self,
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
        self,
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


def _empty_diagnosis() -> DiagnosisResult:
    return DiagnosisResult(likely_cause="unknown_failure", confidence=0.0, rationale="")


def _simulated_promise_payment(
    ctx: CaseRunContext,
    diagnosis: DiagnosisResult | None,
    remaining: float,
    promised_amount: float,
) -> float:
    """Deterministic payment amount at promise due — never uses evaluator ground truth."""
    if ctx.simulated_payment_amount is not None:
        return max(0.0, float(ctx.simulated_payment_amount))
    cause = diagnosis.likely_cause if diagnosis is not None else ""
    if cause in {"low_responsiveness", "invoice_dispute"} or ctx.promise_broken_before:
        # First broken-promise observation pays nothing; subsequent replans use other actions.
        if ctx.last_action in {"promise_to_pay_request", "track_promise_to_pay", "payment_assistance"}:
            return 0.0
    if cause == "temporary_cash_constraint" and ctx.attempt_count <= 1:
        # Allow demos to force partial via simulated_payment_amount; default full.
        pass
    return min(remaining, promised_amount)


def _diagnosis_from_proposal(proposal: DecisionProposal) -> DiagnosisResult:
    reasoning = proposal.reasoning
    return DiagnosisResult(
        likely_cause=reasoning.likely_cause,
        confidence=reasoning.confidence,
        rationale=reasoning.summary,
    )


def _outcome_event_type(outcome) -> str:
    if outcome.recovered:
        return "RECOVERED"
    if outcome.trigger in {"max_retries_exceeded", "recovery_stopped"}:
        return "EXHAUSTED"
    if outcome.trigger == "escalated":
        return "ESCALATED"
    if outcome.trigger == "deferred":
        return "DEFERRED"
    if outcome.trigger == "payment_method_updated":
        return "PAYMENT_METHOD_UPDATE"
    if outcome.trigger == "promise_broken":
        return "PROMISE_BROKEN"
    if outcome.trigger == "partial_payment":
        return "PARTIAL_PAYMENT_RECEIVED"
    if outcome.trigger == "promise_made":
        return "PROMISE_CREATED"
    if outcome.trigger is None and (
        "Checkout" in (outcome.summary or "") or "Receivable" in (outcome.summary or "")
    ):
        return "CUSTOMER_IGNORED"
    return "PAYMENT_FAILED"
