"""Reset a case to detected state for a fresh recovery run."""

from __future__ import annotations

import sqlite3


def reset_case_for_run(conn: sqlite3.Connection, case_id: str) -> None:
    row = conn.execute(
        "SELECT customer_id FROM recovery_cases WHERE case_id = ?", (case_id,)
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
    conn.execute(
        """
        UPDATE customers SET opt_out = 0, prior_contacts_7d = 0
        WHERE customer_id = ?
        """,
        (row["customer_id"],),
    )
    conn.execute("DELETE FROM audit_events WHERE case_id = ?", (case_id,))
    conn.execute("DELETE FROM recovery_action_log WHERE case_id = ?", (case_id,))
    conn.commit()
