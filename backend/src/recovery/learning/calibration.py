"""Calibration metrics for predicted vs observed recovery (Phase 8)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable

from recovery.learning.records import DecisionOutcome


@dataclass(frozen=True, slots=True)
class CalibrationBucket:
    bucket_label: str
    predicted_low: float
    predicted_high: float
    cases: int
    recovered: int
    observed_rate: float
    mean_predicted: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class CalibrationReport:
    cases: int
    brier_score: float
    mean_absolute_error: float
    buckets: tuple[CalibrationBucket, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "cases": self.cases,
            "brier_score": self.brier_score,
            "mean_absolute_error": self.mean_absolute_error,
            "buckets": [b.to_dict() for b in self.buckets],
        }


_BUCKETS = (
    (0.0, 0.2, "0.0-0.2"),
    (0.2, 0.4, "0.2-0.4"),
    (0.4, 0.6, "0.4-0.6"),
    (0.6, 0.8, "0.6-0.8"),
    (0.8, 1.01, "0.8-1.0"),
)


def compute_calibration(outcomes: Iterable[DecisionOutcome]) -> CalibrationReport:
    rows = [
        o
        for o in outcomes
        if o.estimated_recovery_probability is not None
    ]
    if not rows:
        return CalibrationReport(
            cases=0,
            brier_score=0.0,
            mean_absolute_error=0.0,
            buckets=tuple(),
        )

    brier_sum = 0.0
    mae_sum = 0.0
    for outcome in rows:
        pred = float(outcome.estimated_recovery_probability)
        obs = 1.0 if outcome.observed_recovered else 0.0
        brier_sum += (pred - obs) ** 2
        mae_sum += abs(pred - obs)

    bucket_rows: list[CalibrationBucket] = []
    for low, high, label in _BUCKETS:
        members = [
            o
            for o in rows
            if low <= float(o.estimated_recovery_probability) < high
        ]
        if not members:
            continue
        recovered = sum(1 for o in members if o.observed_recovered)
        mean_pred = sum(float(o.estimated_recovery_probability) for o in members) / len(members)
        bucket_rows.append(
            CalibrationBucket(
                bucket_label=label,
                predicted_low=low,
                predicted_high=min(high, 1.0),
                cases=len(members),
                recovered=recovered,
                observed_rate=round(recovered / len(members), 4),
                mean_predicted=round(mean_pred, 4),
            )
        )

    n = len(rows)
    return CalibrationReport(
        cases=n,
        brier_score=round(brier_sum / n, 6),
        mean_absolute_error=round(mae_sum / n, 6),
        buckets=tuple(bucket_rows),
    )
