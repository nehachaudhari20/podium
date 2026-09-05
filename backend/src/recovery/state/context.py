"""Mutable runtime context for a single case recovery run."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from recovery.models.case import RecoveryCaseRuntime
from recovery.models.enums import WorkflowState


@dataclass
class CaseRunContext:
    """In-memory state for one recovery execution (all lanes)."""

    case: RecoveryCaseRuntime
    workflow_state: str = WorkflowState.DETECTED.value
    attempt_count: int = 0
    amount_recovered: float = 0.0
    last_retry_at: datetime | None = None
    last_action: str | None = None
    payment_method_updated: bool = False
    terminal: bool = False
    state_history: list[str] = field(default_factory=list)
    # Receivable / PTP runtime (Phase 7)
    amount_paid: float = 0.0
    remaining_balance: float | None = None
    active_promise_id: str | None = None
    promise_broken_before: bool = False
    simulated_payment_amount: float | None = None

    def __post_init__(self) -> None:
        self.workflow_state = self.case.workflow_state
        self.attempt_count = self.case.attempt_count
        self.state_history.append(self.workflow_state)
        if self.remaining_balance is None:
            self.remaining_balance = float(self.case.amount)

    def record_state(self, new_state: str) -> None:
        if new_state != self.workflow_state:
            self.workflow_state = new_state
            self.state_history.append(new_state)

    def sync_case_view(self) -> RecoveryCaseRuntime:
        """Return an updated runtime case snapshot for policy/strategy modules."""
        amount = (
            self.remaining_balance
            if self.case.lane == "receivable" and self.remaining_balance is not None
            else self.case.amount
        )
        return RecoveryCaseRuntime(
            case_id=self.case.case_id,
            customer_id=self.case.customer_id,
            lane=self.case.lane,
            amount=amount,
            currency=self.case.currency,
            status="closed"
            if self.terminal and self.workflow_state == WorkflowState.RECOVERED.value
            else self.case.status,
            workflow_state=self.workflow_state,
            created_at=self.case.created_at,
            recovery_window_end=self.case.recovery_window_end,
            source_ref_id=self.case.source_ref_id,
            failure_reason=self.case.failure_reason,
            recoverability_hint=self.case.recoverability_hint,
            days_overdue=self.case.days_overdue,
            attempt_count=self.attempt_count,
            estimated_recovery_prob=self.case.estimated_recovery_prob,
            is_hero=self.case.is_hero,
        )
