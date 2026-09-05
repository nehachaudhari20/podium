"""SQLite-backed recovery experience store (Phase 8)."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any, Iterable

from recovery.learning.records import (
    DecisionOutcome,
    deserialize_metadata,
    serialize_metadata,
)
from recovery.learning.signals import amount_bucket, overdue_bucket


@dataclass(frozen=True, slots=True)
class ExperienceQuery:
    action: str | None = None
    lane: str | None = None
    diagnosis: str | None = None
    customer_segment: str | None = None
    amount_bucket: str | None = None
    overdue_bucket: str | None = None
    limit: int | None = None


class ExperienceStore:
    """Persist and query decision outcomes for bounded learning."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._ensure_table()

    def _ensure_table(self) -> None:
        # Idempotent for older DBs that predate Phase 8 schema.
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS decision_outcomes (
                outcome_id                      TEXT PRIMARY KEY,
                case_id                         TEXT NOT NULL,
                customer_id                     TEXT NOT NULL,
                lane                            TEXT NOT NULL,
                action                          TEXT NOT NULL,
                diagnosis                       TEXT,
                decision_source                 TEXT,
                amount_at_risk                  REAL NOT NULL,
                intervention_cost               REAL NOT NULL DEFAULT 0,
                estimated_recovery_probability  REAL,
                observed_recovered              INTEGER NOT NULL DEFAULT 0,
                partially_recovered             INTEGER NOT NULL DEFAULT 0,
                amount_recovered                REAL NOT NULL DEFAULT 0,
                amount_remaining                REAL NOT NULL DEFAULT 0,
                state_before                    TEXT,
                state_after                     TEXT,
                timestamp                       TEXT NOT NULL,
                metadata                        TEXT
            )
            """
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_decision_outcomes_action ON decision_outcomes(action)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_decision_outcomes_lane ON decision_outcomes(lane)"
        )

    def record(self, outcome: DecisionOutcome) -> DecisionOutcome:
        self._conn.execute(
            """
            INSERT INTO decision_outcomes (
                outcome_id, case_id, customer_id, lane, action, diagnosis, decision_source,
                amount_at_risk, intervention_cost, estimated_recovery_probability,
                observed_recovered, partially_recovered, amount_recovered, amount_remaining,
                state_before, state_after, timestamp, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                outcome.outcome_id,
                outcome.case_id,
                outcome.customer_id,
                outcome.lane,
                outcome.action,
                outcome.diagnosis,
                outcome.decision_source,
                outcome.amount_at_risk,
                outcome.intervention_cost,
                outcome.estimated_recovery_probability,
                1 if outcome.observed_recovered else 0,
                1 if outcome.partially_recovered else 0,
                outcome.amount_recovered,
                outcome.amount_remaining,
                outcome.state_before,
                outcome.state_after,
                outcome.timestamp,
                serialize_metadata(outcome.metadata),
            ),
        )
        return outcome

    def record_many(self, outcomes: Iterable[DecisionOutcome]) -> int:
        count = 0
        for outcome in outcomes:
            self.record(outcome)
            count += 1
        return count

    def get(self, outcome_id: str) -> DecisionOutcome | None:
        row = self._conn.execute(
            "SELECT * FROM decision_outcomes WHERE outcome_id = ?", (outcome_id,)
        ).fetchone()
        return _row_to_outcome(row) if row else None

    def list_outcomes(self, query: ExperienceQuery | None = None) -> list[DecisionOutcome]:
        query = query or ExperienceQuery()
        clauses: list[str] = []
        params: list[Any] = []
        if query.action:
            clauses.append("action = ?")
            params.append(query.action)
        if query.lane:
            clauses.append("lane = ?")
            params.append(query.lane)
        if query.diagnosis:
            clauses.append("diagnosis = ?")
            params.append(query.diagnosis)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"SELECT * FROM decision_outcomes {where} ORDER BY timestamp, outcome_id"
        if query.limit is not None:
            sql += " LIMIT ?"
            params.append(int(query.limit))
        rows = self._conn.execute(sql, params).fetchall()
        outcomes = [_row_to_outcome(r) for r in rows]
        # Contextual filters stored in metadata
        if query.customer_segment:
            outcomes = [
                o
                for o in outcomes
                if o.metadata.get("customer_segment") == query.customer_segment
            ]
        if query.amount_bucket:
            outcomes = [
                o
                for o in outcomes
                if o.metadata.get("amount_bucket") == query.amount_bucket
                or amount_bucket(o.amount_at_risk) == query.amount_bucket
            ]
        if query.overdue_bucket:
            outcomes = [
                o
                for o in outcomes
                if o.metadata.get("overdue_bucket") == query.overdue_bucket
                or overdue_bucket(o.metadata.get("days_overdue")) == query.overdue_bucket
            ]
        return outcomes

    def count(self, query: ExperienceQuery | None = None) -> int:
        return len(self.list_outcomes(query))

    def clear(self) -> None:
        self._conn.execute("DELETE FROM decision_outcomes")


def _row_to_outcome(row) -> DecisionOutcome:
    return DecisionOutcome(
        outcome_id=row["outcome_id"],
        case_id=row["case_id"],
        customer_id=row["customer_id"],
        lane=row["lane"],
        action=row["action"],
        diagnosis=row["diagnosis"],
        decision_source=row["decision_source"],
        amount_at_risk=float(row["amount_at_risk"]),
        intervention_cost=float(row["intervention_cost"] or 0),
        estimated_recovery_probability=(
            float(row["estimated_recovery_probability"])
            if row["estimated_recovery_probability"] is not None
            else None
        ),
        observed_recovered=bool(row["observed_recovered"]),
        partially_recovered=bool(row["partially_recovered"]),
        amount_recovered=float(row["amount_recovered"] or 0),
        amount_remaining=float(row["amount_remaining"] or 0),
        state_before=row["state_before"],
        state_after=row["state_after"],
        timestamp=row["timestamp"],
        metadata=deserialize_metadata(row["metadata"]),
    )
