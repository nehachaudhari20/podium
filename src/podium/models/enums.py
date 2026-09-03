"""Domain enums and constants."""

from __future__ import annotations

from enum import StrEnum


class Lane(StrEnum):
    SUBSCRIPTION_PAYMENT = "subscription_payment"
    CHECKOUT_ABANDONMENT = "checkout_abandonment"
    RECEIVABLE = "receivable"


class WorkflowState(StrEnum):
    DETECTED = "detected"
    DIAGNOSED = "diagnosed"
    WAITING = "waiting"
    RETRY_SCHEDULED = "retry_scheduled"
    CONTACTED = "contacted"
    PROMISED = "promised"
    ESCALATED = "escalated"
    RECOVERED = "recovered"
    EXHAUSTED = "exhausted"
    DEFERRED = "deferred"


class CustomerSegment(StrEnum):
    B2C = "b2c"
    B2B_SMB = "b2b_smb"
    B2B_ENTERPRISE = "b2b_enterprise"
