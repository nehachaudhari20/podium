"""Checkout session loading — runtime-safe, no ground-truth joins."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class CheckoutSessionRow:
    session_id: str
    customer_id: str
    case_id: str | None
    cart_value: float
    currency: str
    stage: str
    intent_score: float | None
    abandoned_at: datetime
    items_count: int


def load_checkout_session_by_case(
    conn: sqlite3.Connection,
    case_id: str,
) -> CheckoutSessionRow | None:
    row = conn.execute(
        """
        SELECT session_id, customer_id, case_id, cart_value, currency,
               stage, intent_score, abandoned_at, items_count
        FROM checkout_sessions
        WHERE case_id = ?
        """,
        (case_id,),
    ).fetchone()
    if row is None:
        return None
    return _row_to_session(row)


def load_checkout_session_by_id(
    conn: sqlite3.Connection,
    session_id: str,
) -> CheckoutSessionRow | None:
    row = conn.execute(
        """
        SELECT session_id, customer_id, case_id, cart_value, currency,
               stage, intent_score, abandoned_at, items_count
        FROM checkout_sessions
        WHERE session_id = ?
        """,
        (session_id,),
    ).fetchone()
    if row is None:
        return None
    return _row_to_session(row)


def count_prior_checkout_abandonments(
    conn: sqlite3.Connection,
    customer_id: str,
    *,
    exclude_case_id: str | None = None,
) -> int:
    """Count other checkout abandonment cases for this customer."""
    if exclude_case_id:
        row = conn.execute(
            """
            SELECT COUNT(*) FROM recovery_cases
            WHERE customer_id = ?
              AND lane = 'checkout_abandonment'
              AND case_id != ?
            """,
            (customer_id, exclude_case_id),
        ).fetchone()
    else:
        row = conn.execute(
            """
            SELECT COUNT(*) FROM recovery_cases
            WHERE customer_id = ?
              AND lane = 'checkout_abandonment'
            """,
            (customer_id,),
        ).fetchone()
    return int(row[0])


def _row_to_session(row: sqlite3.Row) -> CheckoutSessionRow:
    abandoned = datetime.fromisoformat(row["abandoned_at"])
    return CheckoutSessionRow(
        session_id=row["session_id"],
        customer_id=row["customer_id"],
        case_id=row["case_id"],
        cart_value=float(row["cart_value"]),
        currency=row["currency"],
        stage=row["stage"],
        intent_score=float(row["intent_score"]) if row["intent_score"] is not None else None,
        abandoned_at=abandoned,
        items_count=int(row["items_count"]),
    )
