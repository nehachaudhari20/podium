"""Action effectiveness and contextual historical evidence (Phase 8)."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from typing import Any, Iterable

from recovery.learning.config import LearningConfig, load_learning_config
from recovery.learning.records import DecisionOutcome
from recovery.learning.store import ExperienceQuery, ExperienceStore


@dataclass(frozen=True, slots=True)
class ActionEffectiveness:
    action: str
    lane: str | None
    attempts: int
    successes: int
    partials: int
    recovery_rate: float
    average_amount_recovered: float
    average_intervention_cost: float
    average_net_value: float
    confidence: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class HistoricalEvidence:
    """Contextual historical evidence for one action (and optional lane)."""

    action: str
    lane: str | None
    diagnosis: str | None
    observations: int
    successes: int
    historical_success_rate: float
    confidence: str
    average_amount_recovered: float
    average_intervention_cost: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def confidence_for_count(observations: int, config: LearningConfig | None = None) -> str:
    cfg = config or load_learning_config()
    if observations <= cfg.low_max:
        return "low"
    if observations <= cfg.medium_max:
        return "medium"
    return "high"


def smoothed_success_rate(
    successes: int,
    attempts: int,
    config: LearningConfig | None = None,
) -> float:
    cfg = config or load_learning_config()
    if attempts <= 0:
        return 0.5  # cold-start neutral prior, not 0/1
    num = successes + cfg.smoothing_successes
    den = attempts + cfg.smoothing_successes + cfg.smoothing_failures
    return round(num / den, 4)


def compute_action_effectiveness(
    outcomes: Iterable[DecisionOutcome],
    *,
    action: str | None = None,
    lane: str | None = None,
    config: LearningConfig | None = None,
) -> list[ActionEffectiveness]:
    cfg = config or load_learning_config()
    buckets: dict[tuple[str, str | None], list[DecisionOutcome]] = defaultdict(list)
    for outcome in outcomes:
        if action and outcome.action != action:
            continue
        if lane and outcome.lane != lane:
            continue
        key = (outcome.action, outcome.lane if lane is not None or action is None else lane)
        # Group by action(+lane when filtering by lane or aggregating cross-lane separately)
        buckets[(outcome.action, outcome.lane)].append(outcome)

    results: list[ActionEffectiveness] = []
    for (act, ln), rows in sorted(buckets.items()):
        successes = sum(1 for o in rows if o.observed_recovered)
        partials = sum(1 for o in rows if o.partially_recovered and not o.observed_recovered)
        attempts = len(rows)
        avg_rec = sum(o.amount_recovered for o in rows) / attempts if attempts else 0.0
        avg_cost = sum(o.intervention_cost for o in rows) / attempts if attempts else 0.0
        avg_net = avg_rec - avg_cost
        rate = successes / attempts if attempts else 0.0
        results.append(
            ActionEffectiveness(
                action=act,
                lane=ln,
                attempts=attempts,
                successes=successes,
                partials=partials,
                recovery_rate=round(rate, 4),
                average_amount_recovered=round(avg_rec, 4),
                average_intervention_cost=round(avg_cost, 4),
                average_net_value=round(avg_net, 4),
                confidence=confidence_for_count(attempts, cfg),
            )
        )
    return results


def get_historical_evidence(
    store: ExperienceStore,
    *,
    action: str,
    lane: str | None = None,
    diagnosis: str | None = None,
    config: LearningConfig | None = None,
) -> HistoricalEvidence:
    cfg = config or load_learning_config()
    outcomes = store.list_outcomes(
        ExperienceQuery(action=action, lane=lane, diagnosis=diagnosis)
    )
    successes = sum(1 for o in outcomes if o.observed_recovered)
    attempts = len(outcomes)
    avg_rec = sum(o.amount_recovered for o in outcomes) / attempts if attempts else 0.0
    avg_cost = sum(o.intervention_cost for o in outcomes) / attempts if attempts else 0.0
    rate = smoothed_success_rate(successes, attempts, cfg) if attempts else 0.5
    raw_rate = successes / attempts if attempts else 0.5
    return HistoricalEvidence(
        action=action,
        lane=lane,
        diagnosis=diagnosis,
        observations=attempts,
        successes=successes,
        historical_success_rate=round(raw_rate if attempts else 0.5, 4),
        confidence=confidence_for_count(attempts, cfg),
        average_amount_recovered=round(avg_rec, 4),
        average_intervention_cost=round(avg_cost, 4),
    )


def cross_lane_effectiveness(
    store: ExperienceStore,
    action: str,
    config: LearningConfig | None = None,
) -> dict[str, ActionEffectiveness]:
    rows = compute_action_effectiveness(
        store.list_outcomes(ExperienceQuery(action=action)),
        action=action,
        config=config,
    )
    return {r.lane or "all": r for r in rows}
