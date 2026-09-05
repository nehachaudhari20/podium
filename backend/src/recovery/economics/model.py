"""Economic evaluation types and pure calculations (Phase 5)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from recovery.models.recovery_types import RecoveryAction


@dataclass(frozen=True, slots=True)
class EconomicCandidate:
    """Explainable economic view of one candidate recovery action."""

    action: RecoveryAction
    amount_at_risk: float
    estimated_recovery_probability: float
    intervention_cost: float
    expected_recovery_value: float
    expected_net_value: float
    eligible: bool
    reason: str

    @property
    def action_id(self) -> str:
        return self.action.action_id

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["action"] = self.action.action_id
        return payload


@dataclass(frozen=True, slots=True)
class EconomicDecision:
    """Per-case economic selection result (action choice, not capacity)."""

    candidates: tuple[EconomicCandidate, ...]
    selected: EconomicCandidate | None
    economic_reason: str
    capacity_decision: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidates": [c.to_dict() for c in self.candidates],
            "selected_action": self.selected.action_id if self.selected else None,
            "expected_recovery_value": (
                self.selected.expected_recovery_value if self.selected else None
            ),
            "intervention_cost": self.selected.intervention_cost if self.selected else None,
            "expected_net_value": self.selected.expected_net_value if self.selected else None,
            "economic_reason": self.economic_reason,
            "capacity_decision": self.capacity_decision,
        }


def expected_recovery_value(amount_at_risk: float, probability: float) -> float:
    return round(amount_at_risk * probability, 4)


def expected_net_value(recovery_value: float, intervention_cost: float) -> float:
    return round(recovery_value - intervention_cost, 4)


def evaluate_action_economics(
    action: RecoveryAction,
    *,
    amount_at_risk: float,
    probability: float,
    intervention_cost: float,
    minimum_expected_net_value: float = 0.0,
    minimum_recovery_probability: float = 0.0,
    maximum_intervention_cost: float | None = None,
) -> EconomicCandidate:
    """Compute EV / net value and eligibility for one action."""
    erv = expected_recovery_value(amount_at_risk, probability)
    env = expected_net_value(erv, intervention_cost)

    if action.action_id in {"stop_recovery", "defer"}:
        return EconomicCandidate(
            action=action,
            amount_at_risk=amount_at_risk,
            estimated_recovery_probability=0.0,
            intervention_cost=0.0,
            expected_recovery_value=0.0,
            expected_net_value=0.0,
            eligible=True,
            reason="stop_or_defer_fallback",
        )

    if probability < minimum_recovery_probability:
        return EconomicCandidate(
            action=action,
            amount_at_risk=amount_at_risk,
            estimated_recovery_probability=probability,
            intervention_cost=intervention_cost,
            expected_recovery_value=erv,
            expected_net_value=env,
            eligible=False,
            reason="below_minimum_recovery_probability",
        )

    if maximum_intervention_cost is not None and intervention_cost > maximum_intervention_cost:
        return EconomicCandidate(
            action=action,
            amount_at_risk=amount_at_risk,
            estimated_recovery_probability=probability,
            intervention_cost=intervention_cost,
            expected_recovery_value=erv,
            expected_net_value=env,
            eligible=False,
            reason="exceeds_maximum_intervention_cost",
        )

    if env < minimum_expected_net_value:
        return EconomicCandidate(
            action=action,
            amount_at_risk=amount_at_risk,
            estimated_recovery_probability=probability,
            intervention_cost=intervention_cost,
            expected_recovery_value=erv,
            expected_net_value=env,
            eligible=False,
            reason="negative_or_below_minimum_expected_net_value",
        )

    return EconomicCandidate(
        action=action,
        amount_at_risk=amount_at_risk,
        estimated_recovery_probability=probability,
        intervention_cost=intervention_cost,
        expected_recovery_value=erv,
        expected_net_value=env,
        eligible=True,
        reason="positive_expected_net_value",
    )
