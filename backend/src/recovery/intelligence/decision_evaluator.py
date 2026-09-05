"""Policy-aware decision evaluation with optional economic ranking (Phase 3D/5)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import sqlite3

from recovery.economics.allocator import CapacityPool, try_reserve_capacity
from recovery.economics.config import EconomicsConfig, load_economics_config
from recovery.economics.engine import economically_ordered_actions, select_best_economic_action
from recovery.economics.model import EconomicDecision
from recovery.ingestion.customer_loader import CustomerContext
from recovery.intelligence.contracts import DecisionProposal
from recovery.models.case import RecoveryCaseRuntime
from recovery.models.recovery_types import PolicyResult, RecoveryAction
from recovery.policy.gate import check_policy, select_first_allowed_action


@dataclass(frozen=True, slots=True)
class EvaluatedDecision:
    """Decision proposal after economic ranking and policy gate evaluation."""

    proposal: DecisionProposal
    selected_action: RecoveryAction | None
    policy_result: PolicyResult | None
    policy_checks: tuple[PolicyResult, ...]
    used_fallback_rank: bool = False
    economic_decision: EconomicDecision | None = None
    capacity_decision: str | None = None


def evaluate_decision_proposal(
    proposal: DecisionProposal,
    case: RecoveryCaseRuntime,
    customer: CustomerContext,
    conn: sqlite3.Connection | None = None,
    last_retry_at: datetime | None = None,
    now: datetime | None = None,
    *,
    economics_config: EconomicsConfig | None = None,
    capacity_pool: CapacityPool | None = None,
    last_action: str | None = None,
) -> EvaluatedDecision:
    """Rank by economics (when enabled), then select first policy-allowed action.

    Invariant: no economically attractive action may bypass policy.
    """
    cfg = economics_config if economics_config is not None else load_economics_config()
    economic_decision: EconomicDecision | None = None
    capacity_decision: str | None = None

    if cfg.enabled:
        economic_decision = select_best_economic_action(
            list(proposal.candidate_actions),
            amount_at_risk=case.amount,
            predictive=proposal.predictive,
            config=cfg,
            last_action=last_action,
        )
        actions = economically_ordered_actions(economic_decision)
        # Ensure recommended remains available as fallback candidate.
        if proposal.recommended_action.action_id not in {a.action_id for a in actions}:
            actions = [*actions, proposal.recommended_action]
    else:
        actions = list(proposal.candidate_actions)

    selected, policy_result, checks = select_first_allowed_action(
        case, actions, customer, conn, last_retry_at, now
    )
    used_fallback = False
    if selected is None and proposal.recommended_action not in actions:
        actions = [proposal.recommended_action, *actions]
        selected, policy_result, checks = select_first_allowed_action(
            case, actions, customer, conn, last_retry_at, now
        )
        used_fallback = selected is not None

    # Capacity gate for scarce actions (batch/demo). Policy already passed.
    if selected is not None and cfg.enabled:
        # Prefer matching economic candidate for cost metadata
        cost = 0.0
        if economic_decision is not None:
            for candidate in economic_decision.candidates:
                if candidate.action_id == selected.action_id:
                    cost = candidate.intervention_cost
                    break
        ok, reason = try_reserve_capacity(capacity_pool, selected.action_id, cost, cfg)
        if not ok:
            capacity_decision = f"deferred:{reason}"
            # Try next policy-allowed non-scarce (or available) action
            selected, policy_result, more_checks, capacity_decision = _select_with_capacity(
                case,
                customer,
                conn,
                last_retry_at,
                now,
                actions,
                selected.action_id,
                capacity_pool,
                cfg,
                economic_decision,
            )
            checks = list(checks) + list(more_checks)
        else:
            capacity_decision = reason

    return EvaluatedDecision(
        proposal=proposal,
        selected_action=selected,
        policy_result=policy_result,
        policy_checks=tuple(checks),
        used_fallback_rank=used_fallback,
        economic_decision=economic_decision,
        capacity_decision=capacity_decision,
    )


def _select_with_capacity(
    case,
    customer,
    conn,
    last_retry_at,
    now,
    actions: list[RecoveryAction],
    blocked_action_id: str,
    capacity_pool: CapacityPool | None,
    cfg: EconomicsConfig,
    economic_decision: EconomicDecision | None,
) -> tuple[RecoveryAction | None, PolicyResult | None, list[PolicyResult], str]:
    checks: list[PolicyResult] = []
    for action in actions:
        if action.action_id == blocked_action_id:
            continue
        result = check_policy(case, action, customer, conn, last_retry_at, now)
        checks.append(result)
        if not result.allowed:
            continue
        cost = 0.0
        if economic_decision is not None:
            for candidate in economic_decision.candidates:
                if candidate.action_id == action.action_id:
                    cost = candidate.intervention_cost
                    break
        ok, reason = try_reserve_capacity(capacity_pool, action.action_id, cost, cfg)
        if ok:
            return action, result, checks, reason
    return (
        None,
        checks[-1] if checks else None,
        checks,
        "deferred:no_feasible_action_under_remaining_capacity",
    )
