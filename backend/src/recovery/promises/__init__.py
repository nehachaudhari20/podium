"""Promise-to-pay model, validation, persistence, and observation (Phase 7)."""

from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from recovery.ingestion.invoice_loader import load_active_promise_by_case, load_invoice_by_case


@dataclass(frozen=True, slots=True)
class PromiseValidationResult:
    allowed: bool
    reason: str


@dataclass(frozen=True, slots=True)
class PromiseToPay:
    promise_id: str
    case_id: str
    customer_id: str
    promised_amount: float
    promise_date: datetime
    created_at: datetime
    status: str  # active | kept | missed | cancelled


@dataclass(frozen=True, slots=True)
class PromiseObservation:
    outcome: str  # kept | missed | partial
    amount_paid: float
    remaining_balance: float
    detail: str


def validate_promise(
    *,
    promised_amount: float,
    promise_date: datetime,
    remaining_balance: float,
    recovery_window_end: datetime,
    now: datetime | None = None,
) -> PromiseValidationResult:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    if promise_date.tzinfo is None:
        promise_date = promise_date.replace(tzinfo=timezone.utc)
    if recovery_window_end.tzinfo is None:
        recovery_window_end = recovery_window_end.replace(tzinfo=timezone.utc)

    if promised_amount <= 0:
        return PromiseValidationResult(False, "promised_amount_must_be_positive")
    if promised_amount > remaining_balance + 1e-6:
        return PromiseValidationResult(False, "promised_amount_exceeds_remaining_balance")
    if promise_date <= now:
        return PromiseValidationResult(False, "promised_date_must_be_in_the_future")
    if promise_date > recovery_window_end:
        return PromiseValidationResult(False, "promised_date_outside_recovery_window")
    return PromiseValidationResult(True, "promise_valid")


def create_promise(
    conn: sqlite3.Connection,
    *,
    case_id: str,
    customer_id: str,
    promised_amount: float,
    promise_date: datetime,
    due_date: datetime,
    created_at: datetime | None = None,
) -> PromiseToPay:
    created = created_at or datetime.now(timezone.utc)
    promise_id = f"ptp_{uuid.uuid4().hex[:12]}"
    # Cancel any prior active promise on this case
    conn.execute(
        """
        UPDATE promises_to_pay SET status = 'cancelled'
        WHERE case_id = ? AND status = 'active'
        """,
        (case_id,),
    )
    conn.execute(
        """
        INSERT INTO promises_to_pay (
            promise_id, case_id, customer_id, promised_amount,
            promise_date, due_date, status, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, 'active', ?)
        """,
        (
            promise_id,
            case_id,
            customer_id,
            promised_amount,
            promise_date.isoformat(),
            due_date.isoformat(),
            created.isoformat(),
        ),
    )
    return PromiseToPay(
        promise_id=promise_id,
        case_id=case_id,
        customer_id=customer_id,
        promised_amount=promised_amount,
        promise_date=promise_date,
        created_at=created,
        status="active",
    )


def update_promise_status(conn: sqlite3.Connection, promise_id: str, status: str) -> None:
    conn.execute(
        "UPDATE promises_to_pay SET status = ? WHERE promise_id = ?",
        (status, promise_id),
    )


def default_promise_date(now: datetime, *, days: int = 7) -> datetime:
    return now + timedelta(days=days)


def observe_promise_payment(
    *,
    promised_amount: float,
    remaining_balance: float,
    paid_amount: float,
) -> PromiseObservation:
    """Deterministic observation of payment against an active promise."""
    paid = max(0.0, paid_amount)
    remaining = max(0.0, round(remaining_balance - paid, 2))
    if paid + 1e-6 >= promised_amount and remaining <= 1e-6:
        return PromiseObservation(
            outcome="kept",
            amount_paid=paid,
            remaining_balance=0.0,
            detail="Full payment received against promise.",
        )
    if paid > 0 and remaining > 1e-6:
        return PromiseObservation(
            outcome="partial",
            amount_paid=paid,
            remaining_balance=remaining,
            detail=f"Partial payment of {paid:,.2f}; remaining {remaining:,.2f}.",
        )
    return PromiseObservation(
        outcome="missed",
        amount_paid=paid,
        remaining_balance=remaining_balance,
        detail="No payment received by promise date.",
    )


def remaining_balance_for_case(
    conn: sqlite3.Connection,
    case_id: str,
    *,
    amount_paid_runtime: float = 0.0,
) -> float:
    invoice = load_invoice_by_case(conn, case_id)
    if invoice is None:
        row = conn.execute(
            "SELECT amount FROM recovery_cases WHERE case_id = ?", (case_id,)
        ).fetchone()
        base = float(row["amount"]) if row else 0.0
    else:
        base = float(invoice.amount)
    return max(0.0, round(base - amount_paid_runtime, 2))


def has_active_promise(conn: sqlite3.Connection, case_id: str) -> bool:
    return load_active_promise_by_case(conn, case_id) is not None
