"""Propose per-case interventions and coordinate at customer level (Phase 6)."""

from __future__ import annotations

import sqlite3
from datetime import datetime

from recovery.audit.trail import record_event
from recovery.coordination.config import CoordinationConfig, load_coordination_config
from recovery.coordination.planner import (
    CustomerRecoveryPlan,
    build_coordinated_plan,
    build_independent_plan,
)
from recovery.coordination.rules import ProposedIntervention
from recovery.coordination.view import CustomerRecoveryView, load_customer_recovery_view
from recovery.economics.allocator import CapacityPool
from recovery.economics.config import load_economics_config
from recovery.economics.engine import select_best_economic_action
from recovery.ingestion.customer_loader import load_customer_context
from recovery.ingestion.runtime_loader import load_case_by_id
from recovery.intelligence.context_builder import build_recovery_context
from recovery.intelligence.decision_config import DecisionConfig
from recovery.intelligence.decisioning import HybridDecisionIntelligence
from recovery.models.enums import Lane
from recovery.models.recovery_types import RecoveryAction
from recovery.policy.gate import check_policy


def propose_intervention_for_case(
    conn: sqlite3.Connection,
    case_id: str,
    *,
    intelligence_mode: str = "deterministic",
    now: datetime | None = None,
) -> ProposedIntervention | None:
    """Intelligence + economics + policy for one case — no execution."""
    case = load_case_by_id(conn, case_id)
    if case is None:
        return None

    # Receivable: coordination-visible stub (full receivables recovery is Phase 7).
    if case.lane == Lane.RECEIVABLE.value:
        action = RecoveryAction(
            "human_escalation",
            "Human follow-up on overdue invoice",
            "human",
            is_contact=True,
        )
        customer = load_customer_context(conn, case.customer_id)
        policy = check_policy(case, action, customer, conn, now=now)
        # Simple ENV estimate without full predictive stack
        probability = 0.55 if (case.days_overdue or 0) < 45 else 0.35
        cost = 500.0
        erv = case.amount * probability
        return ProposedIntervention(
            case_id=case.case_id,
            lane=case.lane,
            amount=case.amount,
            action=action,
            expected_net_value=round(erv - cost, 4),
            expected_recovery_value=round(erv, 4),
            intervention_cost=cost,
            policy_allowed=policy.allowed,
            policy_reason=policy.reason,
        )

    decision_config = DecisionConfig(
        mode=intelligence_mode,
        min_reasoning_confidence=DecisionConfig.from_env().min_reasoning_confidence,
        min_strategy_confidence=DecisionConfig.from_env().min_strategy_confidence,
    )
    engine = HybridDecisionIntelligence(config=decision_config)
    context = build_recovery_context(conn, case_id, now=now)
    proposal = engine.propose_decision(context)
    econ = select_best_economic_action(
        list(proposal.candidate_actions),
        amount_at_risk=case.amount,
        predictive=proposal.predictive,
        config=load_economics_config(),
    )
    customer = load_customer_context(conn, case.customer_id)

    # Prefer economically ranked action if present; else recommended
    ordered = []
    if econ.selected is not None:
        ordered.append(econ.selected.action)
    for candidate in econ.candidates:
        if candidate.action_id not in {a.action_id for a in ordered}:
            ordered.append(candidate.action)
    if proposal.recommended_action.action_id not in {a.action_id for a in ordered}:
        ordered.append(proposal.recommended_action)

    selected_action = None
    policy_reason = "no_feasible_action"
    policy_allowed = False
    env = 0.0
    erv = 0.0
    cost = 0.0
    for action in ordered:
        result = check_policy(case, action, customer, conn, now=now)
        match = next((c for c in econ.candidates if c.action_id == action.action_id), None)
        if result.allowed:
            selected_action = action
            policy_allowed = True
            policy_reason = result.reason
            if match is not None:
                env = match.expected_net_value
                erv = match.expected_recovery_value
                cost = match.intervention_cost
            break
        policy_reason = result.reason

    if selected_action is None:
        selected_action = proposal.recommended_action
        match = next(
            (c for c in econ.candidates if c.action_id == selected_action.action_id), None
        )
        if match is not None:
            env = match.expected_net_value
            erv = match.expected_recovery_value
            cost = match.intervention_cost

    return ProposedIntervention(
        case_id=case.case_id,
        lane=case.lane,
        amount=case.amount,
        action=selected_action,
        expected_net_value=env,
        expected_recovery_value=erv,
        intervention_cost=cost,
        policy_allowed=policy_allowed,
        policy_reason=policy_reason,
    )


def plan_customer_recovery(
    conn: sqlite3.Connection,
    customer_id: str,
    *,
    intelligence_mode: str = "deterministic",
    coordinated: bool = True,
    capacity_pool: CapacityPool | None = None,
    config: CoordinationConfig | None = None,
    audit: bool = True,
) -> tuple[CustomerRecoveryView, list[ProposedIntervention], CustomerRecoveryPlan]:
    """Build customer view, propose per-case actions, return coordinated (or independent) plan."""
    cfg = config or load_coordination_config()
    view = load_customer_recovery_view(conn, customer_id)
    if audit:
        record_event(
            conn,
            case_id=view.active_cases[0].case_id if view.active_cases else customer_id,
            customer_id=customer_id,
            event_type="CUSTOMER_RECOVERY_VIEW_BUILT",
            from_state=None,
            to_state=None,
            action=None,
            actor="coordination",
            reason="Built customer-level recovery view.",
            metadata=view.to_dict(),
        )

    proposals: list[ProposedIntervention] = []
    for case in view.active_cases:
        proposed = propose_intervention_for_case(
            conn, case.case_id, intelligence_mode=intelligence_mode
        )
        if proposed is not None:
            proposals.append(proposed)

    if coordinated:
        plan = build_coordinated_plan(
            view, proposals, config=cfg, capacity_pool=capacity_pool
        )
    else:
        plan = build_independent_plan(view, proposals)

    if audit:
        for conflict in plan.conflicts:
            record_event(
                conn,
                case_id=view.active_cases[0].case_id if view.active_cases else customer_id,
                customer_id=customer_id,
                event_type="CROSS_REVENUE_CONFLICT_DETECTED",
                from_state=None,
                to_state=None,
                action=None,
                actor="coordination",
                reason=conflict.detail,
                metadata={
                    "conflict_type": conflict.conflict_type,
                    "case_ids": list(conflict.case_ids),
                },
            )
        for deferred in plan.deferred_actions:
            record_event(
                conn,
                case_id=deferred.case_id,
                customer_id=customer_id,
                event_type="ACTION_DEFERRED_BY_COORDINATION",
                from_state=None,
                to_state=None,
                action=deferred.action_id,
                actor="coordination",
                reason=deferred.reason,
                metadata=deferred.to_dict(),
            )
        record_event(
            conn,
            case_id=view.active_cases[0].case_id if view.active_cases else customer_id,
            customer_id=customer_id,
            event_type="CUSTOMER_RECOVERY_PLAN_CREATED",
            from_state=None,
            to_state=None,
            action=None,
            actor="coordination",
            reason=f"Created {plan.mode} customer recovery plan.",
            metadata=plan.to_dict(),
        )
        conn.commit()

    return view, proposals, plan
