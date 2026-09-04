"""Audit trail persistence for recovery workflow events."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone

from podium.models.recovery_types import AuditEvent


def record_event(
    conn: sqlite3.Connection,
    *,
    case_id: str,
    customer_id: str,
    event_type: str,
    from_state: str | None,
    to_state: str | None,
    action: str | None,
    actor: str,
    reason: str,
    metadata: dict | None = None,
    timestamp: datetime | None = None,
) -> AuditEvent:
    ts = (timestamp or datetime.now(timezone.utc)).isoformat()
    event = AuditEvent(
        timestamp=ts,
        case_id=case_id,
        customer_id=customer_id,
        event_type=event_type,
        from_state=from_state,
        to_state=to_state,
        action=action,
        actor=actor,
        reason=reason,
        metadata=metadata or {},
    )
    conn.execute(
        """
        INSERT INTO audit_events (
            event_id, timestamp, case_id, customer_id, event_type,
            from_state, to_state, action, actor, reason, metadata
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"aud_{uuid.uuid4().hex[:12]}",
            event.timestamp,
            event.case_id,
            event.customer_id,
            event.event_type,
            event.from_state,
            event.to_state,
            event.action,
            event.actor,
            event.reason,
            json.dumps(event.metadata),
        ),
    )
    return event


def load_audit_trail(conn: sqlite3.Connection, case_id: str) -> list[AuditEvent]:
    rows = conn.execute(
        """
        SELECT timestamp, case_id, customer_id, event_type, from_state, to_state,
               action, actor, reason, metadata
        FROM audit_events
        WHERE case_id = ?
        ORDER BY timestamp
        """,
        (case_id,),
    ).fetchall()
    return [
        AuditEvent(
            timestamp=row["timestamp"],
            case_id=row["case_id"],
            customer_id=row["customer_id"],
            event_type=row["event_type"],
            from_state=row["from_state"],
            to_state=row["to_state"],
            action=row["action"],
            actor=row["actor"],
            reason=row["reason"],
            metadata=json.loads(row["metadata"] or "{}"),
        )
        for row in rows
    ]
