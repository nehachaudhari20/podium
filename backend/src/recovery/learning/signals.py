"""Deterministic learning signals from observed decision outcomes (Phase 8)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from recovery.learning.records import DecisionOutcome


@dataclass(frozen=True, slots=True)
class LearningSignal:
    """One outcome summarized for experience aggregation."""

    outcome_id: str
    action: str
    lane: str
    recovered: bool
    partially_recovered: bool
    not_recovered: bool
    amount_recovery_rate: float
    prediction_error: float | None
    expected_net_value: float | None
    actual_recovered_value: float
    contact_action: bool
    diagnosis: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def generate_learning_signal(
    outcome: DecisionOutcome,
    *,
    is_contact: bool = False,
) -> LearningSignal:
    recovered = outcome.observed_recovered
    partial = outcome.partially_recovered and not recovered
    amount_rate = 0.0
    if outcome.amount_at_risk > 0:
        amount_rate = round(min(1.0, outcome.amount_recovered / outcome.amount_at_risk), 4)

    prediction_error = None
    if outcome.estimated_recovery_probability is not None:
        observed = 1.0 if recovered else (amount_rate if partial else 0.0)
        prediction_error = round(observed - float(outcome.estimated_recovery_probability), 4)

    expected_net = None
    if outcome.estimated_recovery_probability is not None:
        erv = outcome.amount_at_risk * float(outcome.estimated_recovery_probability)
        expected_net = round(erv - outcome.intervention_cost, 4)

    return LearningSignal(
        outcome_id=outcome.outcome_id,
        action=outcome.action,
        lane=outcome.lane,
        recovered=recovered,
        partially_recovered=partial,
        not_recovered=not recovered and not partial,
        amount_recovery_rate=amount_rate,
        prediction_error=prediction_error,
        expected_net_value=expected_net,
        actual_recovered_value=outcome.amount_recovered,
        contact_action=is_contact,
        diagnosis=outcome.diagnosis,
    )


def amount_bucket(amount: float) -> str:
    if amount < 5000:
        return "lt_5k"
    if amount < 20000:
        return "5k_20k"
    if amount < 50000:
        return "20k_50k"
    return "gte_50k"


def overdue_bucket(days: int | None) -> str | None:
    if days is None:
        return None
    if days <= 7:
        return "0_7"
    if days <= 30:
        return "8_30"
    return "30_plus"
