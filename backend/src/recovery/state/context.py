"""Mutable runtime context for a single case recovery run."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from recovery.models.case import RecoveryCaseRuntime
from recovery.models.enums import WorkflowState


@dataclass
class CaseRunContext:
    """In-memory state for one subscription recovery execution."""

    case: RecoveryCaseRuntime
    workflow_state: str = WorkflowState.DETECTED.value
    attempt_count: int = 0
    amount_recovered: float = 0.0
    last_retry_at: datetime | None = None
    last_action: str | None = None
    payment_method_updated: bool = False
    terminal: bool = False
    state_history: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.workflow_state = self.case.workflow_state
        self.attempt_count = self.case.attempt_count
        self.state_history.append(self.workflow_state)

    def record_state(self, new_state: str) -> None:
        if new_state != self.workflow_state:
            self.workflow_state = new_state
            self.state_history.append(new_state)

    def sync_case_view(self) -> RecoveryCaseRuntime:
        """Return an updated runtime case snapshot for policy/strategy modules."""
        return RecoveryCaseRuntime(
            case_id=self.case.case_id,
            customer_id=self.case.customer_id,
            lane=self.case.lane,
            amount=self.case.amount,
            currency=self.case.currency,
            status="closed" if self.terminal and self.workflow_state == WorkflowState.RECOVERED.value else self.case.status,
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
