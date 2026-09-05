"""Batch replay of historical outcomes into the experience store (Phase 8)."""

from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from typing import Any, Iterable

from recovery.audit.trail import record_event
from recovery.learning.calibration import CalibrationReport, compute_calibration
from recovery.learning.effectiveness import ActionEffectiveness, compute_action_effectiveness
from recovery.learning.records import DecisionOutcome
from recovery.learning.store import ExperienceStore


@dataclass
class LearningReplayReport:
    outcomes_ingested: int
    action_stats: list[ActionEffectiveness]
    calibration: CalibrationReport
    detail: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcomes_ingested": self.outcomes_ingested,
            "action_stats": [a.to_dict() for a in self.action_stats],
            "calibration": self.calibration.to_dict(),
            "detail": self.detail,
        }


def replay_outcomes(
    conn: sqlite3.Connection,
    outcomes: Iterable[DecisionOutcome],
    *,
    clear: bool = False,
    audit_case_id: str | None = None,
    audit_customer_id: str | None = None,
    audit: bool = True,
) -> LearningReplayReport:
    """Deterministically ingest historical outcomes and recompute aggregates."""
    store = ExperienceStore(conn)
    if clear:
        store.clear()
    rows = list(outcomes)
    store.record_many(rows)
    stats = compute_action_effectiveness(rows)
    calibration = compute_calibration(rows)

    if audit:
        # Prefer an existing case for audit FK; fall back to hero subscription.
        case_id = audit_case_id
        customer_id = audit_customer_id
        if case_id is None:
            existing = conn.execute(
                "SELECT case_id, customer_id FROM recovery_cases ORDER BY case_id LIMIT 1"
            ).fetchone()
            if existing is not None:
                case_id = existing["case_id"]
                customer_id = existing["customer_id"]
            else:
                case_id = "case_hero_sub_001"
                customer_id = "cust_hero_001"
        record_event(
            conn,
            case_id=case_id,
            customer_id=customer_id or "unknown",
            event_type="LEARNING_REPLAY_COMPLETED",
            from_state=None,
            to_state=None,
            action=None,
            actor="learning",
            reason=f"Replayed {len(rows)} historical outcomes into experience store.",
            metadata={
                "outcomes_ingested": len(rows),
                "actions": sorted({r.action for r in rows}),
                "calibration": calibration.to_dict(),
            },
        )
        conn.commit()
    return LearningReplayReport(
        outcomes_ingested=len(rows),
        action_stats=stats,
        calibration=calibration,
        detail={"cleared": clear},
    )
