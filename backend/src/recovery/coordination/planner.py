"""Customer-level coordinated recovery planning (Phase 6).

Reuses Phase 5 economics + capacity. Does not replace policy or intelligence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from recovery.coordination.config import CoordinationConfig, load_coordination_config
from recovery.coordination.rules import (
    CoordinationConflict,
    ProposedIntervention,
    detect_conflicts,
    is_contact_action,
    is_human_action,
    is_incentive_action,
)
from recovery.coordination.view import CustomerRecoveryView
from recovery.economics.allocator import (
    AllocationRequest,
    CapacityPool,
    allocate_batch,
)
from recovery.economics.config import load_economics_config
from recovery.economics.model import EconomicCandidate, evaluate_action_economics
from recovery.models.recovery_types import RecoveryAction


@dataclass(frozen=True, slots=True)
class PlannedAction:
    case_id: str
    lane: str
    action_id: str
    expected_net_value: float
    decision: str  # selected | deferred | blocked
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "lane": self.lane,
            "action": self.action_id,
            "expected_net_value": self.expected_net_value,
            "decision": self.decision,
            "reason": self.reason,
        }


@dataclass
class CustomerRecoveryPlan:
    customer_id: str
    selected_actions: list[PlannedAction] = field(default_factory=list)
    deferred_actions: list[PlannedAction] = field(default_factory=list)
    blocked_actions: list[PlannedAction] = field(default_factory=list)
    conflicts: list[CoordinationConflict] = field(default_factory=list)
    total_amount_at_risk: float = 0.0
    coordination_reasons: list[str] = field(default_factory=list)
    mode: str = "coordinated"  # coordinated | independent

    @property
    def sequence(self) -> list[PlannedAction]:
        return list(self.selected_actions)

    def to_dict(self) -> dict[str, Any]:
        return {
            "customer_id": self.customer_id,
            "mode": self.mode,
            "total_amount_at_risk": self.total_amount_at_risk,
            "sequence": [a.to_dict() for a in self.selected_actions],
            "deferred": [a.to_dict() for a in self.deferred_actions],
            "blocked": [a.to_dict() for a in self.blocked_actions],
            "conflicts": [
                {
                    "type": c.conflict_type,
                    "case_ids": list(c.case_ids),
                    "detail": c.detail,
                }
                for c in self.conflicts
            ],
            "coordination_reasons": list(self.coordination_reasons),
        }


def build_independent_plan(
    view: CustomerRecoveryView,
    proposals: list[ProposedIntervention],
) -> CustomerRecoveryPlan:
    """Baseline: each policy-allowed proposal proceeds independently."""
    plan = CustomerRecoveryPlan(
        customer_id=view.customer_id,
        total_amount_at_risk=view.total_amount_at_risk,
        mode="independent",
        coordination_reasons=["independent_baseline_no_customer_coordination"],
    )
    for proposal in proposals:
        item = PlannedAction(
            case_id=proposal.case_id,
            lane=proposal.lane,
            action_id=proposal.action.action_id,
            expected_net_value=proposal.expected_net_value,
            decision="selected" if proposal.policy_allowed else "blocked",
            reason=proposal.policy_reason or "independent_selection",
        )
        if proposal.policy_allowed:
            plan.selected_actions.append(item)
        else:
            plan.blocked_actions.append(item)
    plan.selected_actions.sort(key=lambda a: a.expected_net_value, reverse=True)
    return plan


def build_coordinated_plan(
    view: CustomerRecoveryView,
    proposals: list[ProposedIntervention],
    *,
    config: CoordinationConfig | None = None,
    capacity_pool: CapacityPool | None = None,
) -> CustomerRecoveryPlan:
    """Coordinate proposals using conflicts, economics ranking, and shared capacity."""
    cfg = config or load_coordination_config()
    plan = CustomerRecoveryPlan(
        customer_id=view.customer_id,
        total_amount_at_risk=view.total_amount_at_risk,
        mode="coordinated",
    )

    if not cfg.enabled:
        return build_independent_plan(view, proposals)

    # Policy blocks first
    remaining: list[ProposedIntervention] = []
    for proposal in proposals:
        if not proposal.policy_allowed:
            plan.blocked_actions.append(
                PlannedAction(
                    case_id=proposal.case_id,
                    lane=proposal.lane,
                    action_id=proposal.action.action_id,
                    expected_net_value=proposal.expected_net_value,
                    decision="blocked",
                    reason=proposal.policy_reason or "policy_rejected",
                )
            )
        else:
            remaining.append(proposal)

    conflicts = detect_conflicts(remaining, view, cfg)
    plan.conflicts = conflicts
    for conflict in conflicts:
        plan.coordination_reasons.append(f"{conflict.conflict_type}: {conflict.detail}")

    # Recovery fatigue: defer contacts when recent contacts exist (system actions still OK)
    if view.recent_contacts_7d > 0 and cfg.max_customer_contacts_per_window <= 1:
        kept: list[ProposedIntervention] = []
        for proposal in remaining:
            if is_contact_action(proposal.action) and not _is_system_retry(proposal.action):
                plan.deferred_actions.append(
                    PlannedAction(
                        case_id=proposal.case_id,
                        lane=proposal.lane,
                        action_id=proposal.action.action_id,
                        expected_net_value=proposal.expected_net_value,
                        decision="deferred",
                        reason="customer_contact_cooldown_or_fatigue",
                    )
                )
                plan.coordination_reasons.append(
                    f"{proposal.case_id}: deferred contact due to recent customer contact"
                )
            else:
                kept.append(proposal)
        remaining = kept

    # Prefer system actions; still allow one best contact if none deferred by fatigue
    if cfg.prefer_system_actions_before_contact:
        system = [p for p in remaining if _is_system_retry(p.action) or p.action.action_id == "stop_recovery"]
        contacts = [p for p in remaining if is_contact_action(p.action) and p not in system]
        others = [p for p in remaining if p not in system and p not in contacts]
        remaining = system + others + contacts

    # Contact collision: keep highest ENV contact(s) up to max
    contacts = [p for p in remaining if is_contact_action(p.action) and not _is_system_retry(p.action)]
    if len(contacts) > cfg.max_customer_contacts_per_window and cfg.defer_lower_value_contacts:
        contacts_sorted = sorted(contacts, key=lambda p: p.expected_net_value, reverse=True)
        keep = set(p.case_id for p in contacts_sorted[: cfg.max_customer_contacts_per_window])
        pruned: list[ProposedIntervention] = []
        for proposal in remaining:
            if (
                is_contact_action(proposal.action)
                and not _is_system_retry(proposal.action)
                and proposal.case_id not in keep
            ):
                plan.deferred_actions.append(
                    PlannedAction(
                        case_id=proposal.case_id,
                        lane=proposal.lane,
                        action_id=proposal.action.action_id,
                        expected_net_value=proposal.expected_net_value,
                        decision="deferred",
                        reason="contact_collision_lower_expected_net_value",
                    )
                )
                plan.coordination_reasons.append(
                    f"{proposal.case_id}: deferred — higher-value contact selected for another case"
                )
            else:
                pruned.append(proposal)
        remaining = pruned

    # Incentive collision
    incentives = [p for p in remaining if is_incentive_action(p.action)]
    if len(incentives) > cfg.max_active_incentives:
        incentives_sorted = sorted(incentives, key=lambda p: p.expected_net_value, reverse=True)
        keep_ids = {p.case_id for p in incentives_sorted[: cfg.max_active_incentives]}
        pruned = []
        for proposal in remaining:
            if is_incentive_action(proposal.action) and proposal.case_id not in keep_ids:
                plan.deferred_actions.append(
                    PlannedAction(
                        case_id=proposal.case_id,
                        lane=proposal.lane,
                        action_id=proposal.action.action_id,
                        expected_net_value=proposal.expected_net_value,
                        decision="deferred",
                        reason="incentive_collision",
                    )
                )
            else:
                pruned.append(proposal)
        remaining = pruned

    # Human escalation via shared Phase 5 capacity allocator
    humans = [p for p in remaining if is_human_action(p.action)]
    non_humans = [p for p in remaining if not is_human_action(p.action)]
    if humans:
        econ_cfg = load_economics_config()
        pool = capacity_pool or CapacityPool.from_config(econ_cfg)
        # Cap simultaneous humans by coordination config as well
        pool.human_escalations_remaining = min(
            pool.human_escalations_remaining, cfg.max_simultaneous_human_escalations
        )
        requests = [
            AllocationRequest(
                case_id=p.case_id,
                candidate=_as_economic_candidate(p),
            )
            for p in humans
        ]
        report = allocate_batch(requests, config=econ_cfg, pool=pool)
        selected_ids = {r.case_id for r in report.selected}
        for proposal in humans:
            if proposal.case_id in selected_ids:
                non_humans.append(proposal)
            else:
                deferred = next(
                    (r for r in report.deferred if r.case_id == proposal.case_id), None
                )
                plan.deferred_actions.append(
                    PlannedAction(
                        case_id=proposal.case_id,
                        lane=proposal.lane,
                        action_id=proposal.action.action_id,
                        expected_net_value=proposal.expected_net_value,
                        decision="deferred",
                        reason=(
                            deferred.reason
                            if deferred
                            else "human_escalation_capacity_exhausted"
                        ),
                    )
                )
                plan.coordination_reasons.append(
                    f"{proposal.case_id}: human escalation deferred by shared capacity"
                )
        remaining = non_humans

    # Final selection ordered by expected net value (system retries first already preferred)
    remaining.sort(
        key=lambda p: (
            1 if _is_system_retry(p.action) else 0,
            p.expected_net_value,
        ),
        reverse=True,
    )
    for proposal in remaining:
        plan.selected_actions.append(
            PlannedAction(
                case_id=proposal.case_id,
                lane=proposal.lane,
                action_id=proposal.action.action_id,
                expected_net_value=proposal.expected_net_value,
                decision="selected",
                reason="coordinated_selection",
            )
        )

    return plan


def _is_system_retry(action: RecoveryAction) -> bool:
    return action.is_retry or action.action_id.startswith("retry_")


def _as_economic_candidate(proposal: ProposedIntervention) -> EconomicCandidate:
    return evaluate_action_economics(
        proposal.action,
        amount_at_risk=proposal.amount,
        probability=(
            proposal.expected_recovery_value / proposal.amount if proposal.amount else 0.0
        ),
        intervention_cost=proposal.intervention_cost,
    )
