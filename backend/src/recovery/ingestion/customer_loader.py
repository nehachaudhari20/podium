"""Customer context for policy checks — runtime-safe, no ground truth."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class CustomerContext:
    customer_id: str
    opt_out: bool
    prior_contacts_7d: int
    segment: str


def load_customer_context(conn: sqlite3.Connection, customer_id: str) -> CustomerContext:
    row = conn.execute(
        """
        SELECT customer_id, opt_out, prior_contacts_7d, segment
        FROM customers
        WHERE customer_id = ?
        """,
        (customer_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"Customer not found: {customer_id}")
    return CustomerContext(
        customer_id=row["customer_id"],
        opt_out=bool(row["opt_out"]),
        prior_contacts_7d=int(row["prior_contacts_7d"]),
        segment=row["segment"],
    )


def count_recent_contacts(
    conn: sqlite3.Connection,
    customer_id: str,
    since: datetime,
) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*) AS cnt
        FROM contact_history
        WHERE customer_id = ?
          AND contacted_at >= ?
        """,
        (customer_id, since.isoformat()),
    ).fetchone()
    return int(row["cnt"])
