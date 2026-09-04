"""Structured recovery context for adaptive intelligence (Phase 3A).

RecoveryContext is the runtime-safe snapshot passed to future reasoning,
predictive, and deterministic intelligence layers. It must never include
evaluator-only fields such as p_pay_anyway.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

FORBIDDEN_CONTEXT_FIELDS = frozenset({"p_pay_anyway", "case_ground_truth"})


@dataclass(frozen=True, slots=True)
class CaseFacts:
    """Current case facts visible to intelligence components."""

    case_id: str
    customer_id: str
    lane: str
    amount: float
    currency: str
    workflow_state: str
    status: str
    failure_reason: str | None
    recoverability_hint: str | None
    attempt_count: int
    created_at: str
    recovery_window_end: str
    source_ref_id: str
    days_overdue: int | None = None
    is_hero: bool = False
    last_action: str | None = None
    payment_method_updated: bool = False


@dataclass(frozen=True, slots=True)
class CustomerHistorySnapshot:
    """Customer-level history aggregated from available runtime data."""

    customer_id: str
    segment: str
    opt_out: bool
    prior_contacts_7d: int
    total_failed_payments: int
    total_successful_payments: int
    prior_recovery_actions: int
    contacts_with_no_response: int
    open_case_count: int = 0


@dataclass(frozen=True, slots=True)
class RecoveryHistoryEvent:
    """One structured recovery event derived from audit/action history."""

    timestamp: str
    event_type: str
    action: str | None
    result: str | None
    state_before: str | None
    state_after: str | None
    actor: str
    detail: str


@dataclass(frozen=True, slots=True)
class DerivedSignals:
    """Deterministic signals computed from case facts and history."""

    first_failure: bool
    repeated_failure: bool
    prior_successful_payment: bool
    retry_exhaustion_risk: bool
    recent_contact: bool
    customer_non_response: bool
    customer_opt_out: bool
    near_recovery_window_end: bool
    transient_failure: bool = False
    expired_payment_method: bool = False


@dataclass(frozen=True, slots=True)
class RecoveryContext:
    """Complete structured context for one recovery decision point."""

    case: CaseFacts
    customer: CustomerHistorySnapshot
    recovery_history: tuple[RecoveryHistoryEvent, ...]
    derived_signals: DerivedSignals
    built_at: str
    schema_version: str = "3a.1"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_loggable_dict(self) -> dict[str, Any]:
        """JSON-serializable representation for debugging and audit."""
        return self.to_dict()


def assert_no_forbidden_fields(payload: dict[str, Any], *, path: str = "root") -> None:
    """Raise if evaluator-only fields appear in a context payload."""
    for key, value in payload.items():
        if key in FORBIDDEN_CONTEXT_FIELDS:
            raise ValueError(f"Forbidden evaluator field '{key}' at {path}")
        if isinstance(value, dict):
            assert_no_forbidden_fields(value, path=f"{path}.{key}")
        elif isinstance(value, list):
            for idx, item in enumerate(value):
                if isinstance(item, dict):
                    assert_no_forbidden_fields(item, path=f"{path}[{idx}]")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
