"""Canonical decision→outcome learning records (Phase 8).

Runtime-safe only — never stores evaluator-only fields such as p_pay_anyway.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

FORBIDDEN_LEARNING_FIELDS = frozenset({"p_pay_anyway", "case_ground_truth"})


@dataclass(frozen=True, slots=True)
class DecisionOutcome:
    """Links one executed intervention to its observed recovery outcome."""

    outcome_id: str
    case_id: str
    customer_id: str
    lane: str
    action: str
    diagnosis: str | None
    decision_source: str | None
    amount_at_risk: float
    intervention_cost: float
    estimated_recovery_probability: float | None
    observed_recovered: bool
    amount_recovered: float
    amount_remaining: float
    state_before: str | None
    state_after: str | None
    timestamp: str
    partially_recovered: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for key in FORBIDDEN_LEARNING_FIELDS:
            data.pop(key, None)
            if isinstance(data.get("metadata"), dict):
                data["metadata"].pop(key, None)
        return data


def new_outcome_id() -> str:
    return f"out_{uuid.uuid4().hex[:16]}"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_decision_outcome(
    *,
    case_id: str,
    customer_id: str,
    lane: str,
    action: str,
    amount_at_risk: float,
    intervention_cost: float = 0.0,
    estimated_recovery_probability: float | None = None,
    observed_recovered: bool = False,
    partially_recovered: bool = False,
    amount_recovered: float = 0.0,
    amount_remaining: float = 0.0,
    diagnosis: str | None = None,
    decision_source: str | None = None,
    state_before: str | None = None,
    state_after: str | None = None,
    timestamp: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> DecisionOutcome:
    meta = dict(metadata or {})
    for key in FORBIDDEN_LEARNING_FIELDS:
        meta.pop(key, None)
    remaining = amount_remaining
    if observed_recovered and remaining <= 0:
        remaining = 0.0
    elif not observed_recovered and not partially_recovered and remaining <= 0:
        remaining = max(0.0, amount_at_risk - amount_recovered)
    return DecisionOutcome(
        outcome_id=new_outcome_id(),
        case_id=case_id,
        customer_id=customer_id,
        lane=lane,
        action=action,
        diagnosis=diagnosis,
        decision_source=decision_source,
        amount_at_risk=float(amount_at_risk),
        intervention_cost=float(intervention_cost),
        estimated_recovery_probability=estimated_recovery_probability,
        observed_recovered=bool(observed_recovered),
        partially_recovered=bool(partially_recovered),
        amount_recovered=float(amount_recovered),
        amount_remaining=float(remaining),
        state_before=state_before,
        state_after=state_after,
        timestamp=timestamp or utc_now_iso(),
        metadata=meta,
    )


def serialize_metadata(metadata: dict[str, Any]) -> str:
    cleaned = {k: v for k, v in metadata.items() if k not in FORBIDDEN_LEARNING_FIELDS}
    return json.dumps(cleaned)


def deserialize_metadata(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    data = json.loads(raw)
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items() if k not in FORBIDDEN_LEARNING_FIELDS}
