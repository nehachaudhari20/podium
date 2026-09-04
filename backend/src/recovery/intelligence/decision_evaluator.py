"""Policy-aware decision evaluation for intelligence proposals (Phase 3D)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import sqlite3

from recovery.ingestion.customer_loader import CustomerContext
from recovery.intelligence.contracts import DecisionProposal
from recovery.models.case import RecoveryCaseRuntime
from recovery.models.recovery_types import PolicyResult, RecoveryAction
from recovery.policy.gate import select_first_allowed_action


@dataclass(frozen=True, slots=True)
class EvaluatedDecision:
    """Decision proposal after policy gate evaluation."""

    proposal: DecisionProposal
    selected_action: RecoveryAction | None
    policy_result: PolicyResult | None
    policy_checks: tuple[PolicyResult, ...]
    used_fallback_rank: bool = False


def evaluate_decision_proposal(
    proposal: DecisionProposal,
    case: RecoveryCaseRuntime,
    customer: CustomerContext,
    conn: sqlite3.Connection | None = None,
    last_retry_at: datetime | None = None,
    now: datetime | None = None,
) -> EvaluatedDecision:
    """Select the first policy-allowed action from a decision proposal."""
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

    return EvaluatedDecision(
        proposal=proposal,
        selected_action=selected,
        policy_result=policy_result,
        policy_checks=tuple(checks),
        used_fallback_rank=used_fallback,
    )
