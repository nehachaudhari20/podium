"""Customer-level recovery view — aggregates active revenue risks (Phase 6)."""

from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from typing import Any

from recovery.ingestion.customer_loader import load_customer_context


@dataclass(frozen=True, slots=True)
class ActiveCaseSummary:
    """One open revenue-risk case visible to coordination."""

    case_id: str
    lane: str
    amount: float
    currency: str
    workflow_state: str
    status: str
    failure_reason: str | None
    attempt_count: int
    days_overdue: int | None = None
    is_hero: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class CustomerRecoveryView:
    """Runtime coordination view over a customer's active recovery cases."""

    customer_id: str
    segment: str
    opt_out: bool
    active_cases: tuple[ActiveCaseSummary, ...]
    total_amount_at_risk: float
    active_lanes: tuple[str, ...]
    recent_contacts_7d: int
    highest_value_case_id: str | None
    open_case_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "customer_id": self.customer_id,
            "segment": self.segment,
            "opt_out": self.opt_out,
            "active_cases": [c.to_dict() for c in self.active_cases],
            "total_amount_at_risk": self.total_amount_at_risk,
            "active_lanes": list(self.active_lanes),
            "recent_contacts_7d": self.recent_contacts_7d,
            "highest_value_case_id": self.highest_value_case_id,
            "open_case_count": self.open_case_count,
        }

    def cases_by_lane(self, lane: str) -> tuple[ActiveCaseSummary, ...]:
        return tuple(c for c in self.active_cases if c.lane == lane)


def load_customer_recovery_view(
    conn: sqlite3.Connection,
    customer_id: str,
    *,
    include_closed: bool = False,
) -> CustomerRecoveryView:
    """Build a deterministic customer-level recovery view from SQLite."""
    customer = load_customer_context(conn, customer_id)
    if include_closed:
        rows = conn.execute(
            """
            SELECT case_id, lane, amount, currency, workflow_state, status,
                   failure_reason, attempt_count, days_overdue, is_hero
            FROM recovery_cases
            WHERE customer_id = ?
            ORDER BY amount DESC, case_id
            """,
            (customer_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT case_id, lane, amount, currency, workflow_state, status,
                   failure_reason, attempt_count, days_overdue, is_hero
            FROM recovery_cases
            WHERE customer_id = ? AND status = 'open'
            ORDER BY amount DESC, case_id
            """,
            (customer_id,),
        ).fetchall()

    cases = tuple(
        ActiveCaseSummary(
            case_id=row["case_id"],
            lane=row["lane"],
            amount=float(row["amount"]),
            currency=row["currency"],
            workflow_state=row["workflow_state"],
            status=row["status"],
            failure_reason=row["failure_reason"],
            attempt_count=int(row["attempt_count"] or 0),
            days_overdue=row["days_overdue"],
            is_hero=bool(row["is_hero"]),
        )
        for row in rows
    )
    total = round(sum(c.amount for c in cases), 2)
    lanes = tuple(sorted({c.lane for c in cases}))
    highest = cases[0].case_id if cases else None

    return CustomerRecoveryView(
        customer_id=customer_id,
        segment=customer.segment,
        opt_out=customer.opt_out,
        active_cases=cases,
        total_amount_at_risk=total,
        active_lanes=lanes,
        recent_contacts_7d=customer.prior_contacts_7d,
        highest_value_case_id=highest,
        open_case_count=len(cases),
    )
