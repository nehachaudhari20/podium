"""Deterministic cross-revenue conflict detection (Phase 6)."""

from __future__ import annotations

from dataclasses import dataclass

from recovery.coordination.config import CoordinationConfig
from recovery.coordination.view import CustomerRecoveryView
from recovery.models.recovery_types import RecoveryAction

CONTACT_ACTION_IDS = frozenset(
    {
        "payment_method_update",
        "send_email",
        "send_whatsapp",
        "send_sms",
        "voice_call",
        "checkout_reminder",
        "payment_link",
        "checkout_assistance",
        "human_escalation",
    }
)
INCENTIVE_ACTION_IDS = frozenset({"limited_incentive", "offer_discount"})
HUMAN_ACTION_IDS = frozenset({"human_escalation"})


@dataclass(frozen=True, slots=True)
class ProposedIntervention:
    """One case's proposed action before customer-level coordination."""

    case_id: str
    lane: str
    amount: float
    action: RecoveryAction
    expected_net_value: float
    expected_recovery_value: float
    intervention_cost: float
    policy_allowed: bool
    policy_reason: str = ""


@dataclass(frozen=True, slots=True)
class CoordinationConflict:
    conflict_type: str
    case_ids: tuple[str, ...]
    detail: str


def is_contact_action(action: RecoveryAction) -> bool:
    return action.is_contact or action.action_id in CONTACT_ACTION_IDS


def is_incentive_action(action: RecoveryAction) -> bool:
    return action.action_id in INCENTIVE_ACTION_IDS


def is_human_action(action: RecoveryAction) -> bool:
    return action.action_id in HUMAN_ACTION_IDS


def detect_conflicts(
    proposals: list[ProposedIntervention],
    view: CustomerRecoveryView,
    config: CoordinationConfig,
) -> list[CoordinationConflict]:
    """Identify customer-level conflicts among simultaneous proposals."""
    conflicts: list[CoordinationConflict] = []
    allowed = [p for p in proposals if p.policy_allowed]

    contacts = [p for p in allowed if is_contact_action(p.action)]
    if len(contacts) > config.max_customer_contacts_per_window:
        conflicts.append(
            CoordinationConflict(
                conflict_type="contact_collision",
                case_ids=tuple(p.case_id for p in contacts),
                detail=(
                    f"{len(contacts)} contact interventions proposed; "
                    f"max allowed per window is {config.max_customer_contacts_per_window}."
                ),
            )
        )

    if view.recent_contacts_7d > 0 and contacts:
        conflicts.append(
            CoordinationConflict(
                conflict_type="recovery_fatigue",
                case_ids=tuple(p.case_id for p in contacts),
                detail=(
                    f"Customer already has {view.recent_contacts_7d} contact(s) in 7d; "
                    "additional outreach risks fatigue."
                ),
            )
        )

    humans = [p for p in allowed if is_human_action(p.action)]
    if len(humans) > config.max_simultaneous_human_escalations:
        conflicts.append(
            CoordinationConflict(
                conflict_type="human_escalation_collision",
                case_ids=tuple(p.case_id for p in humans),
                detail=(
                    f"{len(humans)} human escalations compete for "
                    f"{config.max_simultaneous_human_escalations} slot(s)."
                ),
            )
        )

    incentives = [p for p in allowed if is_incentive_action(p.action)]
    if len(incentives) > config.max_active_incentives:
        conflicts.append(
            CoordinationConflict(
                conflict_type="incentive_collision",
                case_ids=tuple(p.case_id for p in incentives),
                detail=(
                    f"{len(incentives)} incentives proposed; "
                    f"max active incentives is {config.max_active_incentives}."
                ),
            )
        )

    return conflicts
