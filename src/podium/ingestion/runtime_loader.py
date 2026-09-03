"""Runtime-safe case loading — never joins evaluator ground truth."""

from __future__ import annotations

import sqlite3
from datetime import datetime

from podium.models.case import RUNTIME_CASE_COLUMNS, RecoveryCaseRuntime


def _parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def load_open_cases(conn: sqlite3.Connection) -> list[RecoveryCaseRuntime]:
    columns = ", ".join(RUNTIME_CASE_COLUMNS)
    rows = conn.execute(
        f"""
        SELECT {columns}
        FROM recovery_cases
        WHERE status = 'open'
        ORDER BY created_at
        """
    ).fetchall()
    return [_row_to_runtime(row) for row in rows]


def load_case_by_id(conn: sqlite3.Connection, case_id: str) -> RecoveryCaseRuntime | None:
    columns = ", ".join(RUNTIME_CASE_COLUMNS)
    row = conn.execute(
        f"SELECT {columns} FROM recovery_cases WHERE case_id = ?",
        (case_id,),
    ).fetchone()
    if row is None:
        return None
    return _row_to_runtime(row)


def _row_to_runtime(row: sqlite3.Row) -> RecoveryCaseRuntime:
    return RecoveryCaseRuntime(
        case_id=row["case_id"],
        customer_id=row["customer_id"],
        lane=row["lane"],
        amount=float(row["amount"]),
        currency=row["currency"],
        status=row["status"],
        workflow_state=row["workflow_state"],
        created_at=_parse_dt(row["created_at"]),
        recovery_window_end=_parse_dt(row["recovery_window_end"]),
        source_ref_id=row["source_ref_id"],
        failure_reason=row["failure_reason"],
        recoverability_hint=row["recoverability_hint"],
        days_overdue=row["days_overdue"],
        attempt_count=int(row["attempt_count"]),
        estimated_recovery_prob=row["estimated_recovery_prob"],
        is_hero=bool(row["is_hero"]),
    )
