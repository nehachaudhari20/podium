"""Reset a case to detected state for a fresh recovery run."""

from __future__ import annotations

import sqlite3


def reset_case_for_run(conn: sqlite3.Connection, case_id: str) -> None:
    """Reset case-level simulation state only.

    Does NOT mutate customer-level attributes (opt_out, prior_contacts_7d).
    Use test fixtures when a clean customer context is required.
    """
    row = conn.execute(
        "SELECT case_id FROM recovery_cases WHERE case_id = ?", (case_id,)
    ).fetchone()
    if row is None:
        raise ValueError(f"Case not found: {case_id}")

    conn.execute(
        """
        UPDATE recovery_cases
        SET workflow_state = 'detected', attempt_count = 0, status = 'open'
        WHERE case_id = ?
        """,
        (case_id,),
    )
    conn.execute("DELETE FROM audit_events WHERE case_id = ?", (case_id,))
    conn.execute("DELETE FROM recovery_action_log WHERE case_id = ?", (case_id,))
    conn.commit()
