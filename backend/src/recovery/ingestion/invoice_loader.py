"""Invoice and promise-to-pay loading — runtime-safe, no ground-truth joins."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class InvoiceRow:
    invoice_id: str
    customer_id: str
    case_id: str | None
    amount: float
    currency: str
    due_date: datetime
    days_overdue: int
    status: str
    invoice_type: str


@dataclass(frozen=True, slots=True)
class PromiseRow:
    promise_id: str
    case_id: str
    customer_id: str
    promised_amount: float
    promise_date: datetime
    due_date: datetime
    status: str
    created_at: datetime


def load_invoice_by_case(conn: sqlite3.Connection, case_id: str) -> InvoiceRow | None:
    row = conn.execute(
        """
        SELECT invoice_id, customer_id, case_id, amount, currency,
               due_date, days_overdue, status, invoice_type
        FROM invoices
        WHERE case_id = ?
        """,
        (case_id,),
    ).fetchone()
    if row is None:
        return None
    return _row_to_invoice(row)


def load_active_promise_by_case(conn: sqlite3.Connection, case_id: str) -> PromiseRow | None:
    row = conn.execute(
        """
        SELECT promise_id, case_id, customer_id, promised_amount, promise_date,
               due_date, status, created_at
        FROM promises_to_pay
        WHERE case_id = ? AND status = 'active'
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (case_id,),
    ).fetchone()
    if row is None:
        return None
    return _row_to_promise(row)


def load_promises_for_case(conn: sqlite3.Connection, case_id: str) -> list[PromiseRow]:
    rows = conn.execute(
        """
        SELECT promise_id, case_id, customer_id, promised_amount, promise_date,
               due_date, status, created_at
        FROM promises_to_pay
        WHERE case_id = ?
        ORDER BY created_at
        """,
        (case_id,),
    ).fetchall()
    return [_row_to_promise(r) for r in rows]


def sum_payments_for_case(conn: sqlite3.Connection, case_id: str) -> float:
    """Sum captured/paid amounts linked via source invoice if present; else 0."""
    # Synthetic payments may not always link; use recovery_action_log outcomes as fallback later.
    row = conn.execute(
        """
        SELECT COALESCE(SUM(amount), 0) FROM payments
        WHERE case_id = ? AND status IN ('captured', 'success', 'paid', 'partial')
        """,
        (case_id,),
    ).fetchone()
    return float(row[0] if row else 0.0)


def _parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _row_to_invoice(row) -> InvoiceRow:
    return InvoiceRow(
        invoice_id=row["invoice_id"],
        customer_id=row["customer_id"],
        case_id=row["case_id"],
        amount=float(row["amount"]),
        currency=row["currency"],
        due_date=_parse_dt(row["due_date"]),
        days_overdue=int(row["days_overdue"] or 0),
        status=row["status"],
        invoice_type=row["invoice_type"],
    )


def _row_to_promise(row) -> PromiseRow:
    return PromiseRow(
        promise_id=row["promise_id"],
        case_id=row["case_id"],
        customer_id=row["customer_id"],
        promised_amount=float(row["promised_amount"]),
        promise_date=_parse_dt(row["promise_date"]),
        due_date=_parse_dt(row["due_date"]),
        status=row["status"],
        created_at=_parse_dt(row["created_at"]),
    )
