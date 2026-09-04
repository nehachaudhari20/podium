"""Persist in-memory case run state back to SQLite."""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone

from podium.models.enums import WorkflowState
from podium.models.recovery_types import ExecutionResult
from podium.state.context import CaseRunContext


def save_case_state(conn: sqlite3.Connection, ctx: CaseRunContext) -> None:
    status = "closed" if ctx.workflow_state in (
        WorkflowState.RECOVERED.value,
        WorkflowState.EXHAUSTED.value,
        WorkflowState.ESCALATED.value,
    ) else "open"
    conn.execute(
        """
        UPDATE recovery_cases
        SET workflow_state = ?, attempt_count = ?, status = ?
        WHERE case_id = ?
        """,
        (ctx.workflow_state, ctx.attempt_count, status, ctx.case.case_id),
    )


def log_recovery_action(
    conn: sqlite3.Connection,
    ctx: CaseRunContext,
    execution: ExecutionResult,
) -> None:
    conn.execute(
        """
        INSERT INTO recovery_action_log (
            action_id, case_id, action_type, channel, cost, outcome, executed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"act_{uuid.uuid4().hex[:12]}",
            ctx.case.case_id,
            execution.action,
            "system",
            0.0,
            execution.event,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
