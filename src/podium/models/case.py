"""Recovery case models — runtime view excludes evaluator-only fields."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class RecoveryCaseRuntime:
    """Case fields visible to diagnosis, strategy, coordination, and allocation."""

    case_id: str
    customer_id: str
    lane: str
    amount: float
    currency: str
    status: str
    workflow_state: str
    created_at: datetime
    recovery_window_end: datetime
    source_ref_id: str
    failure_reason: str | None
    recoverability_hint: str | None
    days_overdue: int | None
    attempt_count: int
    estimated_recovery_prob: float | None
    is_hero: bool = False


RUNTIME_CASE_COLUMNS: tuple[str, ...] = (
    "case_id",
    "customer_id",
    "lane",
    "amount",
    "currency",
    "status",
    "workflow_state",
    "created_at",
    "recovery_window_end",
    "source_ref_id",
    "failure_reason",
    "recoverability_hint",
    "days_overdue",
    "attempt_count",
    "estimated_recovery_prob",
    "is_hero",
)
