"""Shared recovery workflow types for diagnosis, strategy, policy, and execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class DiagnosisResult:
    likely_cause: str
    confidence: float
    rationale: str


@dataclass(frozen=True, slots=True)
class RecoveryAction:
    action_id: str
    label: str
    channel: str
    is_retry: bool = False
    is_contact: bool = False
    retry_delay_hours: int | None = None


@dataclass(frozen=True, slots=True)
class PolicyResult:
    allowed: bool
    action: str
    reason: str


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    action: str
    success: bool
    event: str
    detail: str = ""


@dataclass(frozen=True, slots=True)
class AuditEvent:
    timestamp: str
    case_id: str
    customer_id: str
    event_type: str
    from_state: str | None
    to_state: str | None
    action: str | None
    actor: str
    reason: str
    metadata: dict[str, Any] = field(default_factory=dict)
